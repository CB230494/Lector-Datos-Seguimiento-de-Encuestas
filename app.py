# app.py
# -*- coding: utf-8 -*-
"""
✅ REPORTE POR DELEGACIÓN (Sembremos Seguridad)

LO QUE CORRIGE ESTA VERSIÓN:
✅ 1) Comunidad: detecta BIEN la columna de DISTRITO (ya NO se “confunde” con preguntas que incluyen la palabra “distrito”).
✅ 2) Comunidad: SOLO lista distritos reales y contabiliza SI por distrito (contabilidad = conteo de "SI").
✅ 3) Distritos “bien escritos”: convierte snake_case / MAYÚSCULAS a “Title Case” (Ej: espiritu_santo -> Espiritu Santo).
✅ 4) PDF: arregla márgenes/anchos y hace WRAP del texto (no se desborda).
✅ 5) Fecha automática del sistema + Hora manual por delegación.
✅ 6) Metas manuales (por distrito o por delegación) y calcula % Avance + Pendiente.

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

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


# -----------------------------
# Streamlit config
# -----------------------------
st.set_page_config(page_title="Sembremos Seguridad - Reporte", layout="wide")


# -----------------------------
# Texto / normalización
# -----------------------------
def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(val) -> str:
    if val is None:
        return ""
    v = str(val).strip().strip("\ufeff")
    v = v.replace("\n", " ").replace("\r", " ").strip()
    v = _strip_accents(v.lower())
    v = re.sub(r"\s+", " ", v).strip()
    # normalizar "sí" / "si." / "no."
    v = v.replace("sí", "si").replace("si.", "si").replace("no.", "no")
    return v


def pretty_distrito(val: str) -> str:
    """Convierte 'espiritu_santo' / 'SAN_RAFAEL' -> 'Espiritu Santo' / 'San Rafael'."""
    if val is None:
        return ""
    s = str(val).strip()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # title case sin inventar acentos
    return s.lower().title()


SPANISH_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
SPANISH_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es(dt: datetime) -> str:
    wd = SPANISH_WEEKDAYS[dt.weekday()]
    month = SPANISH_MONTHS[dt.month - 1]
    return f"{wd}, {dt.day} de {month} de {dt.year}"


def infer_tipo_lugar(filename: str, header_row_cells: list[str]) -> tuple[str, str]:
    base = Path(filename).stem
    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        return m.group(1).capitalize(), m.group(2).replace("_", " ").strip()

    if header_row_cells:
        joined = " | ".join(header_row_cells[:12])
        m2 = re.search(r"(?i)encuesta\s+(policial|comunidad|comercio)\s*[–-]\s*([^|,]+)", joined)
        if m2:
            return m2.group(1).capitalize(), m2.group(2).strip()

    return "Desconocida", base


# -----------------------------
# CSV robusto
# -----------------------------
def parse_csv(file_bytes: bytes):
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
    return rows[0], rows[1:]


def best_si_column(header, data, prefer_terms=None) -> int:
    """
    1) Si encuentra encabezado con términos preferidos ("acepta participar"/"consentimiento"), la usa.
    2) Si no, elige la columna con MÁS ocurrencias exactas de SI/NO.
    """
    if not header or not data:
        return 0

    prefer_terms = prefer_terms or []
    header_norm = [norm(h) for h in header]

    for i, h in enumerate(header_norm):
        if any(t in h for t in prefer_terms):
            return i

    best_idx = 0
    best_hits = -1
    for j in range(len(header)):
        hits = 0
        for r in data:
            if j >= len(r):
                continue
            v = norm(r[j])
            if v in ("si", "no"):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_idx = j

    return best_idx


def count_si_in_col(data, col_idx: int) -> int:
    si = 0
    for r in data:
        if col_idx < len(r) and norm(r[col_idx]) == "si":
            si += 1
    return si


# -----------------------------
# ✅ DETECCIÓN CORRECTA DE COLUMNA DISTRITO
# -----------------------------
def _value_quality_for_district(values: list[str]) -> float:
    """
    Puntúa si los valores 'parecen' distritos:
    - Cortos (<= 30)
    - No son oraciones con ? . :
    - No tienen muchos dígitos
    """
    vals = [v for v in values if norm(v) != ""]
    if len(vals) < 3:
        return 0.0

    good = 0
    for v in vals[:200]:
        vv = str(v).strip()
        vnorm = norm(vv)

        # penalizar oraciones/preguntas
        if "?" in vv or "." in vv or ":" in vv:
            continue
        # penalizar muy largos
        if len(vv) > 30:
            continue
        # penalizar muchos números
        digits = sum(ch.isdigit() for ch in vv)
        if digits >= 2:
            continue
        # distritos suelen ser texto simple
        good += 1

    return good / max(1, min(len(vals), 200))


def find_district_col(header: list[str], data: list[list[str]]) -> int | None:
    """
    Busca la mejor columna para 'Distrito' evitando falsas coincidencias como:
    '38. ¿Considera ... en su distrito?'
    """
    if not header or not data:
        return None

    ncols = len(header)
    best = None
    best_score = -1.0

    for j in range(ncols):
        h = norm(header[j])

        # candidato si el encabezado sugiere distrito
        header_hint = 0.0
        if "distrito" in h or "district" in h:
            header_hint = 1.0

        # muestrear valores
        vals = []
        for r in data[:300]:
            if j < len(r):
                vals.append(r[j])

        q = _value_quality_for_district(vals)

        # score combinado (favor fuerte a encabezado correcto + calidad)
        score = (2.0 * header_hint) + (3.0 * q)

        # además: valores deben tener variedad razonable (no todo distinto infinito, ni todo igual vacío)
        uniq = len({norm(v) for v in vals if norm(v) != ""})
        if uniq < 2:
            score *= 0.2

        if score > best_score:
            best_score = score
            best = j

    # umbral mínimo para aceptar
    if best_score < 1.5:
        return None
    return best


def get_unique_values(data, col_idx: int) -> list[str]:
    vals = set()
    for r in data:
        if col_idx < len(r):
            v = str(r[col_idx]).strip()
            if norm(v) != "":
                vals.add(v)
    return sorted(vals, key=lambda x: _strip_accents(x.lower()))


# -----------------------------
# Cálculos tabla
# -----------------------------
def build_rows(tipo: str, lugar: str, distritos: list[str] | None, conteos: dict, metas: dict) -> list[dict]:
    rows = []
    if distritos:
        for d in distritos:
            meta = int(metas.get(d, 0) or 0)
            cont = int(conteos.get(d, 0) or 0)
            avance = (cont / meta) if meta > 0 else 0.0
            pend = max(meta - cont, 0)
            rows.append({
                "Tipo": tipo,
                "Distrito": pretty_distrito(d),
                "Meta": meta,
                "Contabilidad": cont,
                "% Avance": avance,   # 0..1
                "Pendiente": pend
            })
    else:
        meta = int(metas.get(lugar, 0) or 0)
        cont = int(conteos.get(lugar, 0) or 0)
        avance = (cont / meta) if meta > 0 else 0.0
        pend = max(meta - cont, 0)
        rows.append({
            "Tipo": tipo,
            "Distrito": pretty_distrito(lugar),
            "Meta": meta,
            "Contabilidad": cont,
            "% Avance": avance,
            "Pendiente": pend
        })
    return rows


def format_for_screen(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["% Avance"] = out["% Avance"].apply(lambda x: f"{int(round(float(x) * 100))}%")
    return out


# -----------------------------
# PDF (márgenes + wrap)
# -----------------------------
def build_pdf_bytes(delegacion: str, hora: str, fecha_str: str, logo_path: str | None,
                    comunidad_df: pd.DataFrame, comercio_df: pd.DataFrame, policial_df: pd.DataFrame) -> bytes:
    buff = io.BytesIO()

    # márgenes más cómodos para que no se coma el contenido
    doc = SimpleDocTemplate(
        buff,
        pagesize=letter,
        leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28
    )
    styles = getSampleStyleSheet()
    story = []

    # estilos de celda con wrap
    cell_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        spaceAfter=0,
        spaceBefore=0,
    )
    head_style = ParagraphStyle(
        "head",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
    )

    # logo
    if logo_path and Path(logo_path).exists():
        try:
            img = RLImage(logo_path, width=2.8 * inch, height=2.8 * inch)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 8))
        except Exception:
            pass

    # título
    story.append(Paragraph(f"<b>{delegacion}</b>", styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Hora (manual):</b> {hora or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fecha:</b> {fecha_str}", styles["Normal"]))
    story.append(Spacer(1, 10))

    def _section(title: str, df: pd.DataFrame):
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        story.append(Spacer(1, 4))

        data = [
            [
                Paragraph("Tipo", head_style),
                Paragraph("Distrito", head_style),
                Paragraph("Meta", head_style),
                Paragraph("Contabilidad", head_style),
                Paragraph("% Avance", head_style),
                Paragraph("Pendiente", head_style),
            ]
        ]

        for _, r in df.iterrows():
            data.append([
                Paragraph(str(r["Tipo"]), cell_style),
                Paragraph(str(r["Distrito"]), cell_style),
                Paragraph(str(int(r["Meta"])), cell_style),
                Paragraph(str(int(r["Contabilidad"])), cell_style),
                Paragraph(f"{int(round(float(r['% Avance']) * 100))}%", cell_style),
                Paragraph(str(int(r["Pendiente"])), cell_style),
            ])

        # anchos (Distrito más ancho, resto compacto)
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

    _section("Comunidad", comunidad_df)
    _section("Comercio", comercio_df)
    _section("Policial", policial_df)

    doc.build(story)
    buff.seek(0)
    return buff.getvalue()


# -----------------------------
# UI
# -----------------------------
st.title("📄 Reporte por Delegación (Comunidad / Comercio / Policial)")
st.caption("Contabilidad = conteo de “SI” (auto-detectado). Metas y hora se ingresan manualmente.")

files = st.file_uploader("Cargá los CSV (pueden ser varios)", type=["csv"], accept_multiple_files=True)
if not files:
    st.info("Subí los CSV para armar el reporte.")
    st.stop()

logo_path = "001.png" if Path("001.png").exists() else None

# Parsear
parsed = []
lugares_set = set()
for f in files:
    header, data = parse_csv(f.getvalue())
    tipo, lugar = infer_tipo_lugar(f.name, header or [])
    parsed.append((f.name, tipo, lugar, header, data))
    lugares_set.add(lugar)

lugares = sorted(list(lugares_set), key=lambda x: _strip_accents(x.lower()))
delegacion_sel = st.selectbox("Delegación (Lugar) para armar el reporte:", lugares)

hora_manual = st.text_input("Hora (manual) para el informe (ej: 14:35):", value="")
hoy = datetime.now()
fecha_str = fecha_es(hoy)

st.divider()

# obtener CSV por tipo para esa delegación
def pick_file(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if lugar == delegacion_sel and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None

fname_com, head_com, data_com = pick_file("Comunidad")
fname_con, head_con, data_con = pick_file("Comercio")
fname_pol, head_pol, data_pol = pick_file("Policial")

PREFER = ["acepta participar", "acepta_participar", "consent", "consentimiento"]

st.subheader("1) Columna usada para Contabilidad (conteo de SI)")
st.caption("Por defecto usa 'Acepta participar/Consentimiento'. Si no, usa la columna con más SI/NO. Podés cambiarla manualmente.")

def col_selector(tipo_label: str, header: list[str] | None, data: list[list[str]] | None):
    if not header:
        st.info(f"No hay CSV de {tipo_label} para esta delegación.")
        return None

    labels = [f"[{i+1}] {header[i]}" for i in range(len(header))]
    default_idx = best_si_column(header, data or [], prefer_terms=PREFER)
    default_idx = max(0, min(default_idx, len(labels) - 1))

    choice = st.selectbox(
        f"Columna para contar SI ({tipo_label}):",
        labels,
        index=default_idx,
        key=f"col_{tipo_label}_{delegacion_sel}"
    )
    return labels.index(choice)

col_si_com = col_selector("Comunidad", head_com, data_com)
col_si_con = col_selector("Comercio", head_con, data_con)
col_si_pol = col_selector("Policial", head_pol, data_pol)

st.divider()
st.subheader("2) Tablas (Metas manuales + cálculo automático)")

# -----------------------------
# COMUNIDAD (por distrito si existe)
# -----------------------------
st.markdown("### Comunidad")
comunidad_rows = []
df_comunidad = pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"])

if head_com and data_com and col_si_com is not None:
    # ✅ detectar columna distrito BIEN
    dist_idx = find_district_col(head_com, data_com)

    if dist_idx is not None:
        distritos_raw = get_unique_values(data_com, dist_idx)

        # conteo SI por distrito
        conteos = {}
        for d in distritos_raw:
            si = 0
            for r in data_com:
                if dist_idx < len(r) and col_si_com < len(r):
                    if str(r[dist_idx]).strip() == d and norm(r[col_si_com]) == "si":
                        si += 1
            conteos[d] = si

        # metas manuales por distrito (guardadas por delegación)
        key_meta = f"meta_com_{delegacion_sel}"
        base_meta = pd.DataFrame({"Distrito": [pretty_distrito(x) for x in distritos_raw], "Meta": [0]*len(distritos_raw)})

        # recuperar metas previas si existen
        if key_meta in st.session_state:
            prev = st.session_state[key_meta]
            # merge por Distrito ya “bonito”
            base_meta = base_meta.merge(prev[["Distrito", "Meta"]], on="Distrito", how="left", suffixes=("", "_prev"))
            base_meta["Meta"] = base_meta["Meta_prev"].fillna(base_meta["Meta"]).astype(int)
            base_meta = base_meta[["Distrito", "Meta"]]

        edited = st.data_editor(base_meta, use_container_width=True, num_rows="fixed", key=f"edit_{key_meta}")
        st.session_state[key_meta] = edited

        metas = {str(row["Distrito"]): int(row["Meta"] or 0) for _, row in edited.iterrows()}

        # construir filas usando distritos “bonitos”
        rows = []
        for d_raw in distritos_raw:
            d_pretty = pretty_distrito(d_raw)
            meta = int(metas.get(d_pretty, 0))
            cont = int(conteos.get(d_raw, 0))
            avance = (cont / meta) if meta > 0 else 0.0
            pend = max(meta - cont, 0)
            rows.append({
                "Tipo": "Comunidad",
                "Distrito": d_pretty,
                "Meta": meta,
                "Contabilidad": cont,
                "% Avance": avance,
                "Pendiente": pend
            })

        df_comunidad = pd.DataFrame(rows)

    else:
        # sin distrito -> una fila por delegación
        meta_single = st.number_input("Meta Comunidad (manual):", min_value=0, value=0, step=1, key=f"meta_com_single_{delegacion_sel}")
        cont = count_si_in_col(data_com, col_si_com)
        avance = (cont / meta_single) if meta_single > 0 else 0.0
        pend = max(int(meta_single) - cont, 0)
        df_comunidad = pd.DataFrame([{
            "Tipo": "Comunidad",
            "Distrito": pretty_distrito(delegacion_sel),
            "Meta": int(meta_single),
            "Contabilidad": int(cont),
            "% Avance": float(avance),
            "Pendiente": int(pend)
        }])
else:
    st.warning("No se cargó CSV de Comunidad para esta delegación o falta seleccionar columna SI.")

st.dataframe(format_for_screen(df_comunidad), use_container_width=True)

# -----------------------------
# COMERCIO (1 fila por delegación)
# -----------------------------
st.markdown("### Comercio")
df_comercio = pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"])

if head_con and data_con and col_si_con is not None:
    meta_con = st.number_input("Meta Comercio (manual):", min_value=0, value=0, step=1, key=f"meta_con_{delegacion_sel}")
    cont = count_si_in_col(data_con, col_si_con)
    avance = (cont / meta_con) if meta_con > 0 else 0.0
    pend = max(int(meta_con) - cont, 0)
    df_comercio = pd.DataFrame([{
        "Tipo": "Comercio",
        "Distrito": pretty_distrito(delegacion_sel),
        "Meta": int(meta_con),
        "Contabilidad": int(cont),
        "% Avance": float(avance),
        "Pendiente": int(pend)
    }])
else:
    st.warning("No se cargó CSV de Comercio para esta delegación o falta seleccionar columna SI.")

st.dataframe(format_for_screen(df_comercio), use_container_width=True)

# -----------------------------
# POLICIAL (1 fila por delegación)
# -----------------------------
st.markdown("### Policial")
df_policial = pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"])

if head_pol and data_pol and col_si_pol is not None:
    meta_pol = st.number_input("Meta Policial (manual):", min_value=0, value=0, step=1, key=f"meta_pol_{delegacion_sel}")
    cont = count_si_in_col(data_pol, col_si_pol)
    avance = (cont / meta_pol) if meta_pol > 0 else 0.0
    pend = max(int(meta_pol) - cont, 0)
    df_policial = pd.DataFrame([{
        "Tipo": "Policial",
        "Distrito": pretty_distrito(delegacion_sel),
        "Meta": int(meta_pol),
        "Contabilidad": int(cont),
        "% Avance": float(avance),
        "Pendiente": int(pend)
    }])
else:
    st.warning("No se cargó CSV de Policial para esta delegación o falta seleccionar columna SI.")

st.dataframe(format_for_screen(df_policial), use_container_width=True)

# -----------------------------
# PDF
# -----------------------------
st.divider()
st.subheader("3) Descargar PDF")

if st.button("📄 Generar PDF del reporte"):
    pdf_bytes = build_pdf_bytes(
        delegacion=delegacion_sel,
        hora=hora_manual,
        fecha_str=fecha_str,
        logo_path=logo_path,
        comunidad_df=df_comunidad,
        comercio_df=df_comercio,
        policial_df=df_policial,
    )
    st.success("PDF generado. Descargalo aquí 👇")
    st.download_button(
        "⬇️ Descargar PDF",
        data=pdf_bytes,
        file_name=f"Reporte_{delegacion_sel.replace(' ', '_')}_{hoy.strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
    )

st.caption("Nota: Contabilidad = conteo de SI en la columna seleccionada. Metas y hora son manuales.")ta: Contabilidad sale del conteo de SI en la columna seleccionada (auto-detectada por defecto).")

