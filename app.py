# app.py
# -*- coding: utf-8 -*-

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
# Normalización fuerte
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
    t = str(s).strip().replace("_", " ").replace("-", " ")
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
    parts = base.split("_")
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[1].replace("_", " ").strip()
    return "Desconocida", base


# -----------------------------
# CSV robusto + ALINEACIÓN filas
# -----------------------------
def parse_csv_robusto(file_bytes: bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"', skipinitialspace=False)

    rows = []
    for row in reader:
        if not row:
            continue
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
        if len(r) > ncols:
            r = r[:ncols]
        elif len(r) < ncols:
            r = r + ([""] * (ncols - len(r)))
        fixed.append(r)

    return header, fixed


# -----------------------------
# Detectar columna Distrito (sin confundir preguntas)
# -----------------------------
def clean_header_token(h: str) -> str:
    x = norm(h)
    x = re.sub(r"^\s*\d+\s*[\.\)\-:]+\s*", "", x).strip()
    x = x.rstrip(":").strip()
    return x


def find_district_col(header: list[str], data: list[list[str]]):
    candidates = []
    for i, h in enumerate(header):
        ch = clean_header_token(h)
        if ch in ("distrito", "district"):
            candidates.append(i)

    if not candidates:
        return None

    def score(col):
        vals = [data[r][col] for r in range(min(len(data), 200))]
        good = 0
        for v in vals:
            vv = str(v).strip()
            if norm(vv) == "":
                continue
            if "?" in vv or ":" in vv:
                continue
            if len(vv) > 35:
                continue
            if re.match(r"^\d+\s*[\.\)]", vv):
                continue
            good += 1
        return good

    best = max(candidates, key=score)
    return best


def get_unique_values(data, col_idx: int) -> list[str]:
    vals = set()
    for r in data:
        v = r[col_idx]
        if norm(v) != "":
            vals.add(str(v).strip())
    return sorted(list(vals), key=lambda x: strip_accents(x.lower()))


# -----------------------------
# Ubicar SI/NO: ranking de columnas
# -----------------------------
def rank_yesno_columns(header: list[str], data: list[list[str]], top_k: int = 8) -> pd.DataFrame:
    rows = []
    for j in range(len(header)):
        si = 0
        no = 0
        filled = 0
        for r in data:
            v = r[j]
            if norm(v) == "":
                continue
            filled += 1
            if is_yes(v):
                si += 1
            elif is_no(v):
                no += 1
        hits = si + no
        ratio = (hits / filled) if filled > 0 else 0.0
        rows.append({
            "idx": j,
            "columna": header[j],
            "SI": si,
            "NO": no,
            "SI+NO": hits,
            "no_vacias": filled,
            "ratio_SI_NO": ratio
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(["SI+NO", "ratio_SI_NO"], ascending=[False, False]).head(top_k).reset_index(drop=True)
    return df


def choose_default_yesno_col(header: list[str], data: list[list[str]]) -> int:
    prefer = ["acepta", "consent", "consentimiento"]
    best_pref = None
    best_hits = -1

    for j, h in enumerate(header):
        hn = norm(h)
        if any(p in hn for p in prefer):
            si = sum(1 for r in data if is_yes(r[j]))
            no = sum(1 for r in data if is_no(r[j]))
            if (si + no) > best_hits:
                best_hits = si + no
                best_pref = j

    if best_pref is not None and best_hits > 0:
        return best_pref

    ranked = rank_yesno_columns(header, data, top_k=1)
    if len(ranked) == 0:
        return 0
    return int(ranked.loc[0, "idx"])


# -----------------------------
# Construir tablas base (SI/NO ya calculados)
# -----------------------------
def build_base_comunidad(header, data, col_yesno):
    dist_col = find_district_col(header, data)

    if dist_col is None:
        si = sum(1 for r in data if is_yes(r[col_yesno]))
        no = sum(1 for r in data if is_no(r[col_yesno]))
        return pd.DataFrame([{"Tipo": "Comunidad", "Distrito": "TOTAL (Delegación)", "SI": si, "NO": no}])

    distritos_raw = get_unique_values(data, dist_col)

    si_map = {pretty_title(d): 0 for d in distritos_raw}
    no_map = {pretty_title(d): 0 for d in distritos_raw}

    for r in data:
        d = pretty_title(r[dist_col])
        if norm(d) == "":
            continue
        if d not in si_map:
            si_map[d] = 0
            no_map[d] = 0

        if is_yes(r[col_yesno]):
            si_map[d] += 1
        elif is_no(r[col_yesno]):
            no_map[d] += 1

    df = pd.DataFrame({
        "Tipo": "Comunidad",
        "Distrito": list(si_map.keys()),
        "SI": list(si_map.values()),
        "NO": [no_map[k] for k in si_map.keys()]
    }).sort_values("Distrito").reset_index(drop=True)

    # filtro extra por seguridad
    df = df[~df["Distrito"].str.contains(r"\?", regex=True)]
    df = df[~df["Distrito"].str.contains(r"^\d+\.", regex=True)]

    return df


def build_base_simple(tipo, lugar, header, data, col_yesno):
    si = sum(1 for r in data if is_yes(r[col_yesno]))
    no = sum(1 for r in data if is_no(r[col_yesno]))
    return pd.DataFrame([{"Tipo": tipo, "Distrito": pretty_title(lugar), "SI": si, "NO": no}])


def apply_meta_calc(df_base: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    df = df_base.copy()
    df["Contabilidad"] = df["SI"]  # Contabilidad = SI

    metas = []
    for i, row in df.iterrows():
        meta = st.number_input(
            f"Meta {row['Tipo']} - {row['Distrito']}",
            min_value=0,
            value=0,
            step=1,
            key=f"{key_prefix}_meta_{i}"
        )
        metas.append(int(meta))
    df["Meta"] = metas

    df["% Avance"] = df.apply(lambda r: (r["Contabilidad"] / r["Meta"]) if r["Meta"] > 0 else 0.0, axis=1)
    df["Pendiente"] = df.apply(lambda r: max(int(r["Meta"]) - int(r["Contabilidad"]), 0), axis=1)
    df["% Avance"] = df["% Avance"].apply(lambda x: f"{int(round(float(x) * 100))}%")

    return df[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO"]]


# -----------------------------
# PDF
# -----------------------------
def build_pdf_bytes(delegacion_label: str, hora_reporte: str, fecha_str: str, logo_path: str | None,
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

    story.append(Paragraph(f"<b>{delegacion_label}</b>", styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Hora del reporte:</b> {hora_reporte or '-'}", styles["Normal"]))
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
st.caption("Primero ubicamos SI/NO. Luego ingresás Meta (manual) para calcular Avance y Pendiente.")

files = st.file_uploader("Cargá los CSV (pueden ser varios)", type=["csv"], accept_multiple_files=True)
if not files:
    st.stop()

logo_path = "001.png" if Path("001.png").exists() else None

parsed = []
lugares = set()
for f in files:
    header, data = parse_csv_robusto(f.getvalue())
    tipo, lugar = infer_tipo_lugar(f.name)
    parsed.append((f.name, tipo, lugar, header, data))
    lugares.add(lugar)

lugares = sorted(list(lugares), key=lambda x: strip_accents(x.lower()))
delegacion_sel = st.selectbox("Delegación (Lugar):", lugares)

# ✅ Cambios solicitados en etiquetas
hora_reporte = st.text_input("Hora del reporte:", value="")

fecha_str = fecha_es(datetime.now())
delegacion_label = f"Delegación: {pretty_title(delegacion_sel)}"

def pick(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if lugar == delegacion_sel and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None

fname_com, h_com, d_com = pick("Comunidad")
fname_con, h_con, d_con = pick("Comercio")
fname_pol, h_pol, d_pol = pick("Policial")

st.divider()
st.subheader("1) ✅ Ubicar los SI/NO (antes de metas)")

def ui_pick_yesno(tipo_label: str, header, data):
    if not header:
        st.info(f"No hay CSV de {tipo_label} para esta delegación.")
        return None

    ranked = rank_yesno_columns(header, data, top_k=8)
    default_idx = choose_default_yesno_col(header, data)

    st.markdown(f"**{tipo_label}:** columnas candidatas (top 8)")
    st.dataframe(ranked[["idx","columna","SI","NO","SI+NO","ratio_SI_NO"]], use_container_width=True)

    labels = [f"[{i+1}] {header[i]}" for i in range(len(header))]
    choice = st.selectbox(
        f"Columna SI/NO a usar ({tipo_label}):",
        labels,
        index=default_idx,
        key=f"yesno_{tipo_label}_{delegacion_sel}"
    )
    col = labels.index(choice)

    si_total = sum(1 for r in data if is_yes(r[col]))
    no_total = sum(1 for r in data if is_no(r[col]))

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{tipo_label} - SI", si_total)
    c2.metric(f"{tipo_label} - NO", no_total)
    c3.metric(f"{tipo_label} - SI+NO", si_total + no_total)

    return col

col_com = ui_pick_yesno("Comunidad", h_com, d_com) if h_com else None
st.divider()
col_con = ui_pick_yesno("Comercio", h_con, d_con) if h_con else None
st.divider()
col_pol = ui_pick_yesno("Policial", h_pol, d_pol) if h_pol else None

st.divider()
st.subheader("2) Metas (manual) → % Avance y Pendiente")

# Comunidad
st.markdown("### Comunidad")
if h_com and d_com and col_com is not None:
    base_com = build_base_comunidad(h_com, d_com, col_com)
    df_comunidad = apply_meta_calc(base_com, key_prefix=f"com_{delegacion_sel}")
    st.dataframe(df_comunidad[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_comunidad = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV o columna SI/NO en Comunidad.")

# Comercio
st.markdown("### Comercio")
if h_con and d_con and col_con is not None:
    base_con = build_base_simple("Comercio", delegacion_sel, h_con, d_con, col_con)
    df_comercio = apply_meta_calc(base_con, key_prefix=f"con_{delegacion_sel}")
    st.dataframe(df_comercio[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_comercio = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV o columna SI/NO en Comercio.")

# Policial
st.markdown("### Policial")
if h_pol and d_pol and col_pol is not None:
    base_pol = build_base_simple("Policial", delegacion_sel, h_pol, d_pol, col_pol)
    df_policial = apply_meta_calc(base_pol, key_prefix=f"pol_{delegacion_sel}")
    st.dataframe(df_policial[["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"]], use_container_width=True)
else:
    df_policial = pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])
    st.warning("Falta CSV o columna SI/NO en Policial.")

st.divider()
st.subheader("3) PDF")

if st.button("📄 Generar PDF"):
    pdf = build_pdf_bytes(
        delegacion_label=delegacion_label,
        hora_reporte=hora_reporte,
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

st.caption("Listo: Contabilidad = SI. Meta es lo único manual.")
