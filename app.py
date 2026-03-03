# app.py
# -*- coding: utf-8 -*-
"""
REPORTE POR DELEGACIÓN - Sembremos Seguridad
- Contabilidad = conteo de "SI" (robusto: Sí/si/SI/ " si ")
- Comunidad: desglose por distrito si existe (detecta "2. Distrito:" y similares)
- Meta: manual (por distrito o por delegación)
- % Avance y Pendiente: calculados
- PDF: logo 001.png + fecha del sistema + hora manual

requirements.txt:
streamlit
pandas
openpyxl
reportlab
"""

import io
import re
import csv
import unicodedata
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

st.set_page_config(page_title="Sembremos Seguridad - Reporte", layout="wide")


# -----------------------------
# Normalización
# -----------------------------
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().strip("\ufeff")
    s = s.replace("\n", " ").replace("\r", " ")
    s = strip_accents(s).lower().strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("sí", "si").replace("si.", "si").replace("no.", "no")
    return s


def is_yes(v) -> bool:
    return norm(v) == "si"


def is_no(v) -> bool:
    return norm(v) == "no"


def pretty_title(s: str) -> str:
    if s is None:
        return ""
    t = str(s).strip()
    t = t.replace("_", " ").replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower().title()


# -----------------------------
# Fecha en español
# -----------------------------
SPANISH_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
SPANISH_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es(dt: datetime) -> str:
    wd = SPANISH_WEEKDAYS[dt.weekday()]
    month = SPANISH_MONTHS[dt.month - 1]
    return f"{wd}, {dt.day} de {month} de {dt.year}"


# -----------------------------
# Inferir tipo/lugar por filename
# -----------------------------
def infer_tipo_lugar(filename: str):
    base = Path(filename).stem
    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        return m.group(1).capitalize(), m.group(2).replace("_", " ").strip()
    # fallback
    parts = base.split("_")
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[1].replace("_", " ").strip()
    return "Desconocida", base


# -----------------------------
# CSV robusto + ALINEACIÓN de filas
# (esto arregla el conteo SI que se te fue a 0)
# -----------------------------
def parse_csv_robusto(file_bytes: bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"', skipinitialspace=False)

    rows = []
    for row in reader:
        if not row:
            continue
        # descartar filas completamente vacías
        if all(norm(c) == "" for c in row):
            continue
        rows.append(row)

    if not rows:
        return [], []

    header = rows[0]
    data = rows[1:]
    ncols = len(header)

    fixed = []
    for r in data:
        # si viene más larga, truncar; si viene más corta, rellenar
        if len(r) > ncols:
            r = r[:ncols]
        elif len(r) < ncols:
            r = r + ([""] * (ncols - len(r)))
        fixed.append(r)

    return header, fixed


# -----------------------------
# Detectar columna "Distrito"
# - Acepta: "Distrito", "2. Distrito:", "Distrito:" etc.
# - Y evita confundir preguntas largas que incluyen la palabra "distrito"
# -----------------------------
def clean_header_token(h: str) -> str:
    x = norm(h)
    # quitar leading "2." "7)" etc
    x = re.sub(r"^\s*\d+\s*[\.\)\-:]+\s*", "", x).strip()
    # quitar ":" final
    x = x.rstrip(":").strip()
    return x


def find_district_col(header: list[str], data: list[list[str]]):
    candidates = []
    for i, h in enumerate(header):
        ch = clean_header_token(h)
        # SOLO si el encabezado (limpio) es distrito/district
        if ch in ("distrito", "district"):
            candidates.append(i)

    if not candidates:
        return None

    # Si hay varios, elegir el que tenga valores "cortos" y sin signos de pregunta
    def score(col):
        vals = [data[r][col] for r in range(min(len(data), 200))]
        good = 0
        for v in vals:
            vv = str(v).strip()
            if norm(vv) == "":
                continue
            if "?" in vv or ":" in vv or "." in vv:
                continue
            if len(vv) > 35:
                continue
            good += 1
        return good

    best = max(candidates, key=score)
    return best


# -----------------------------
# Elegir columna para SI/NO (Contabilidad)
# - Preferir "Acepta participar..." si existe
# - Si no, elegir la que tenga MÁS SI+NO
# -----------------------------
def best_yesno_col(header: list[str], data: list[list[str]]):
    header_norm = [norm(h) for h in header]
    prefer = ["acepta participar", "acepta_participar", "consent", "consentimiento"]

    for i, h in enumerate(header_norm):
        if any(p in h for p in prefer):
            return i

    best_i = 0
    best_hits = -1
    for j in range(len(header)):
        hits = 0
        for r in data:
            v = r[j]
            if is_yes(v) or is_no(v):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_i = j

    return best_i


# -----------------------------
# Construcción de tablas
# -----------------------------
def tabla_comunidad(header, data, col_yesno):
    dist_col = find_district_col(header, data)
    if dist_col is None:
        # sin distrito -> 1 fila
        si = sum(1 for r in data if is_yes(r[col_yesno]))
        no = sum(1 for r in data if is_no(r[col_yesno]))
        df = pd.DataFrame([{
            "Tipo": "Comunidad",
            "Distrito": "TOTAL (Delegación)",
            "SI": si,
            "NO": no
        }])
        return df, False

    # con distrito
    conteos = {}
    conteos_no = {}

    for r in data:
        d = pretty_title(r[dist_col])
        if norm(d) == "":
            continue
        conteos.setdefault(d, 0)
        conteos_no.setdefault(d, 0)
        if is_yes(r[col_yesno]):
            conteos[d] += 1
        elif is_no(r[col_yesno]):
            conteos_no[d] += 1

    df = pd.DataFrame({
        "Tipo": "Comunidad",
        "Distrito": list(conteos.keys()),
        "SI": list(conteos.values()),
        "NO": [conteos_no[k] for k in conteos.keys()]
    })
    return df.sort_values("Distrito").reset_index(drop=True), True


def tabla_simple(tipo, lugar, header, data, col_yesno):
    si = sum(1 for r in data if is_yes(r[col_yesno]))
    no = sum(1 for r in data if is_no(r[col_yesno]))
    return pd.DataFrame([{
        "Tipo": tipo,
        "Distrito": pretty_title(lugar),
        "SI": si,
        "NO": no
    }])


def aplicar_meta_y_calculos(df: pd.DataFrame, key_prefix: str):
    # Meta manual (por fila)
    # Contabilidad = SI (como pediste)
    df = df.copy()
    df["Contabilidad"] = df["SI"]

    # input de metas
    metas = []
    for i, row in df.iterrows():
        label = f"Meta {row['Tipo']} - {row['Distrito']}"
        meta = st.number_input(label, min_value=0, value=0, step=1, key=f"{key_prefix}_meta_{i}")
        metas.append(int(meta))
    df["Meta"] = metas

    df["% Avance"] = df.apply(lambda r: (r["Contabilidad"] / r["Meta"]) if r["Meta"] > 0 else 0.0, axis=1)
    df["Pendiente"] = df.apply(lambda r: max(int(r["Meta"]) - int(r["Contabilidad"]), 0), axis=1)
    df["% Avance"] = df["% Avance"].apply(lambda x: f"{int(round(float(x) * 100))}%")

    # Orden de columnas final
    return df[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO"]]


# -----------------------------
# PDF
# -----------------------------
def build_pdf_bytes(delegacion: str, hora: str, fecha_str: str, logo_path: str | None,
                    df_com: pd.DataFrame, df_con: pd.DataFrame, df_pol: pd.DataFrame) -> bytes:
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=letter, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()

    cell = ParagraphStyle("cell", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11)
    head = ParagraphStyle("head", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11)

    story = []

    if logo_path and Path(logo_path).exists():
        img = RLImage(logo_path, width=2.8 * inch, height=2.8 * inch)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>{delegacion}</b>", styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Hora (manual):</b> {hora or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fecha:</b> {fecha_str}", styles["Normal"]))
    story.append(Spacer(1, 10))

    def section(title: str, df: pd.DataFrame):
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        story.append(Spacer(1, 4))

        cols = ["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]
        data = [[Paragraph(c, head) for c in cols]]

        for _, r in df.iterrows():
            data.append([
                Paragraph(str(r["Tipo"]), cell),
                Paragraph(str(r["Distrito"]), cell),
                Paragraph(str(int(r["Meta"])), cell),
                Paragraph(str(int(r["Contabilidad"])), cell),
                Paragraph(str(r["% Avance"]), cell),
                Paragraph(str(int(r["Pendiente"])), cell),
            ])

        tbl = Table(data, colWidths=[62, 210, 55, 78, 58, 62])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        story.append(tbl)
        story.append(Spacer(1, 12))

    section("Comunidad", df_com)
    section("Comercio", df_con)
    section("Policial", df_pol)

    doc.build(story)
    buff.seek(0)
    return buff.getvalue()


# -----------------------------
# UI
# -----------------------------
st.title("📄 Reporte por Delegación (Comunidad / Comercio / Policial)")
st.caption("Contabilidad = conteo de SI. La Meta se ingresa manual para calcular Avance y Pendiente.")

files = st.file_uploader("Cargá los CSV (pueden ser varios)", type=["csv"], accept_multiple_files=True)
if not files:
    st.stop()

logo_path = "001.png" if Path("001.png").exists() else None

# Parsear y agrupar por lugar
parsed = []
lugares = set()
for f in files:
    header, data = parse_csv_robusto(f.getvalue())
    tipo, lugar = infer_tipo_lugar(f.name)
    parsed.append((f.name, tipo, lugar, header, data))
    lugares.add(lugar)

lugares = sorted(list(lugares), key=lambda x: strip_accents(x.lower()))
delegacion_sel = st.selectbox("Delegación (Lugar):", lugares)

hora_manual = st.text_input("Hora (manual) para el informe (ej: 14:35):", value="")
fecha_str = fecha_es(datetime.now())

def pick(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if lugar == delegacion_sel and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None

# Tomar archivos por tipo
_, h_com, d_com = pick("Comunidad")
_, h_con, d_con = pick("Comercio")
_, h_pol, d_pol = pick("Policial")

st.divider()
st.subheader("1) Columna SI/NO usada para Contabilidad")

def selector_si(tipo_label: str, header, data):
    if not header:
        st.info(f"No hay CSV de {tipo_label} para esta delegación.")
        return None

    default_idx = best_yesno_col(header, data)
    labels = [f"[{i+1}] {header[i]}" for i in range(len(header))]
    choice = st.selectbox(f"Columna SI/NO ({tipo_label}):", labels, index=default_idx, key=f"sel_{tipo_label}_{delegacion_sel}")
    return labels.index(choice)

col_com = selector_si("Comunidad", h_com, d_com) if h_com else None
col_con = selector_si("Comercio", h_con, d_con) if h_con else None
col_pol = selector_si("Policial", h_pol, d_pol) if h_pol else None

st.divider()
st.subheader("2) Tablas (Meta manual → Avance y Pendiente)")

# Comunidad
st.markdown("### Comunidad")
if h_com and d_com and col_com is not None:
    base_com, _has_dist = tabla_comunidad(h_com, d_com, col_com)
    df_comunidad = aplicar_meta_y_calculos(base_com, key_prefix=f"com_{delegacion_sel}")
    st.dataframe(df_comunidad[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_comunidad = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV de Comunidad o columna SI/NO.")

# Comercio
st.markdown("### Comercio")
if h_con and d_con and col_con is not None:
    base_con = tabla_simple("Comercio", delegacion_sel, h_con, d_con, col_con)
    df_comercio = aplicar_meta_y_calculos(base_con, key_prefix=f"con_{delegacion_sel}")
    st.dataframe(df_comercio[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_comercio = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV de Comercio o columna SI/NO.")

# Policial
st.markdown("### Policial")
if h_pol and d_pol and col_pol is not None:
    base_pol = tabla_simple("Policial", delegacion_sel, h_pol, d_pol, col_pol)
    df_policial = aplicar_meta_y_calculos(base_pol, key_prefix=f"pol_{delegacion_sel}")
    st.dataframe(df_policial[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_policial = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV de Policial o columna SI/NO.")

st.divider()
st.subheader("3) PDF")

if st.button("📄 Generar PDF"):
    pdf = build_pdf_bytes(
        delegacion=pretty_title(delegacion_sel),
        hora=hora_manual,
        fecha_str=fecha_str,
        logo_path=logo_path,
        df_com=df_comunidad,
        df_con=df_comercio,
        df_pol=df_policial
    )
    st.download_button(
        "⬇️ Descargar PDF",
        data=pdf,
        file_name=f"Reporte_{delegacion_sel.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Listo: Contabilidad siempre es SI. La Meta es lo único manual.")
