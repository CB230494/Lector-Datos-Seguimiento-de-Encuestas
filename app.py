# app.py
# -*- coding: utf-8 -*-
"""
Dashboard por Delegación (Sembremos Seguridad)
- Lee CSVs (Comunidad / Comercio / Policial)
- Contabiliza "SI" (por defecto en la pregunta: "¿Acepta participar en esta encuesta?")
- Comunidad: desglosa por Distrito (si existe columna de distrito)
- Metas: las ingresás manualmente (por distrito o por delegación)
- Calcula % Avance y Pendiente como en tu tabla
- Fecha del sistema (automática) + Hora por delegación (manual)
- Exporta PDF con el logo 001.png (del repo) y la tabla
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

st.set_page_config(page_title="Sembremos Seguridad - Reporte", layout="wide")


# -----------------------------
# Helpers de texto / fecha
# -----------------------------
def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(val) -> str:
    if val is None:
        return ""
    v = str(val).strip().strip("\ufeff")
    v = v.replace("\n", " ").replace("\r", " ").strip()
    return _strip_accents(v.lower())


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


def find_col_idx(header: list[str], candidates: list[str]) -> int | None:
    """
    candidates: lista de fragmentos (normalizados) que deben aparecer en el encabezado
    """
    header_norm = [norm(h) for h in header]
    for i, h in enumerate(header_norm):
        for c in candidates:
            if c in h:
                return i
    return None


def count_si_in_col(header, data, col_idx: int) -> int:
    si = 0
    for r in data:
        if col_idx >= len(r):
            continue
        if norm(r[col_idx]) == "si":
            si += 1
    return si


def get_unique_values(header, data, col_idx: int) -> list[str]:
    vals = set()
    for r in data:
        if col_idx >= len(r):
            continue
        v = str(r[col_idx]).strip()
        if norm(v) == "":
            continue
        vals.add(v)
    return sorted(vals, key=lambda x: _strip_accents(x.lower()))


# -----------------------------
# Cálculos para tabla
# -----------------------------
def build_rows(tipo: str, lugar: str, distritos: list[str] | None, conteos: dict, metas: dict) -> list[dict]:
    """
    Devuelve filas con: Tipo, Distrito, Meta, Contabilidad, % Avance, Pendiente
    - conteos: {"<distrito o lugar>": si_count}
    - metas: {"<distrito o lugar>": meta_int}
    """
    rows = []
    if distritos:
        for d in distritos:
            meta = int(metas.get(d, 0) or 0)
            cont = int(conteos.get(d, 0) or 0)
            avance = (cont / meta) if meta > 0 else 0.0
            pend = max(meta - cont, 0)
            rows.append({
                "Tipo": tipo,
                "Distrito": d,
                "Meta": meta,
                "Contabilidad": cont,
                "% Avance": avance,  # 0..1
                "Pendiente": pend
            })
    else:
        key = lugar
        meta = int(metas.get(key, 0) or 0)
        cont = int(conteos.get(key, 0) or 0)
        avance = (cont / meta) if meta > 0 else 0.0
        pend = max(meta - cont, 0)
        rows.append({
            "Tipo": tipo,
            "Distrito": lugar,
            "Meta": meta,
            "Contabilidad": cont,
            "% Avance": avance,
            "Pendiente": pend
        })
    return rows


def format_for_screen(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["% Avance"] = out["% Avance"].apply(lambda x: f"{(float(x)*100):.0f}%")
    return out


# -----------------------------
# PDF
# -----------------------------
def build_pdf_bytes(delegacion: str, hora: str, fecha_str: str, logo_path: str | None,
                    comunidad_df: pd.DataFrame, comercio_df: pd.DataFrame, policial_df: pd.DataFrame) -> bytes:
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    # Logo
    if logo_path and Path(logo_path).exists():
        try:
            img = RLImage(logo_path, width=3.2*inch, height=3.2*inch)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 12))
        except Exception:
            pass

    # Título
    story.append(Paragraph(f"<b>{delegacion}</b>", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>Hora (manual):</b> {hora or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fecha:</b> {fecha_str}", styles["Normal"]))
    story.append(Spacer(1, 12))

    def _section(title: str, df: pd.DataFrame):
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        data = [["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]]

        for _, r in df.iterrows():
            data.append([
                str(r["Tipo"]),
                str(r["Distrito"]),
                str(int(r["Meta"])),
                str(int(r["Contabilidad"])),
                f"{int(round(float(r['% Avance']) * 100))}%",
                str(int(r["Pendiente"]))
            ])

        tbl = Table(data, colWidths=[70, 170, 70, 90, 70, 70])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
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
st.caption("Contabilidad = conteo de “SI” (por defecto: “¿Acepta participar en esta encuesta?”). Metas y hora las ingresás manualmente.")

# Cargar CSVs
files = st.file_uploader("Cargá los CSV (pueden ser varios)", type=["csv"], accept_multiple_files=True)
if not files:
    st.info("Subí los CSV para armar el reporte.")
    st.stop()

# Logo (tu repo)
logo_default = "001.png"
logo_path = logo_default if Path(logo_default).exists() else None

# Elegir delegación
# Se arma catálogo de (tipo, lugar) desde los archivos
catalog = []
parsed = []
for f in files:
    header, data = parse_csv(f.getvalue())
    tipo, lugar = infer_tipo_lugar(f.name, header or [])
    catalog.append((tipo, lugar, f.name))
    parsed.append((f.name, tipo, lugar, header, data))

# Delegaciones únicas por "Lugar"
lugares = sorted(list({l for _, l, _ in catalog}), key=lambda x: _strip_accents(x.lower()))
delegacion_sel = st.selectbox("Delegación (Lugar) para armar el reporte:", lugares)

# Hora manual por delegación
hora_manual = st.text_input("Hora (manual) para el informe (ej: 14:35):", value="")

# Fecha sistema (automática)
hoy = datetime.now()
fecha_str = fecha_es(hoy)

st.divider()

# Config: pregunta para contar SI
st.subheader("1) ¿De cuál pregunta tomamos el SI para Contabilidad?")
st.caption("Por defecto, usa la columna que contenga 'Acepta participar'. Si no la detecta, podés elegir otra.")
# candidatos típicos
prefer_candidates = ["acepta participar", "acepta_participar", "consent", "consentimiento"]

# Para cada tipo (comunidad/comercio/policial) buscamos el header correspondiente del archivo de esa delegación
def pick_file(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if lugar == delegacion_sel and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None

fname_com, head_com, data_com = pick_file("Comunidad")
fname_con, head_con, data_con = pick_file("Comercio")
fname_pol, head_pol, data_pol = pick_file("Policial")

# Selector por tipo, si existe
def col_selector(tipo_label: str, header: list[str] | None):
    if not header:
        return None
    default_idx = find_col_idx(header, prefer_candidates)
    labels = [f"[{i+1}] {header[i]}" for i in range(len(header))]
    if default_idx is None:
        default_idx = 0
    choice = st.selectbox(f"Columna para contar SI ({tipo_label}):", labels, index=default_idx, key=f"col_{tipo_label}")
    sel = labels.index(choice)
    return sel

col_si_com = col_selector("Comunidad", head_com) if head_com else None
col_si_con = col_selector("Comercio", head_con) if head_con else None
col_si_pol = col_selector("Policial", head_pol) if head_pol else None

st.divider()
st.subheader("2) Tabla (Metas manuales + cálculo automático)")

# Comunidad: buscar columna distrito
comunidad_rows = []
comunidad_metas = {}
comunidad_conteos = {}

distritos = None
if head_com and data_com:
    dist_idx = find_col_idx(head_com, ["distrito"])
    if dist_idx is not None:
        distritos = get_unique_values(head_com, data_com, dist_idx)
        # Conteo SI por distrito
        if col_si_com is not None:
            for d in distritos:
                si = 0
                for r in data_com:
                    if dist_idx < len(r) and col_si_com < len(r):
                        if str(r[dist_idx]).strip() == d and norm(r[col_si_com]) == "si":
                            si += 1
                comunidad_conteos[d] = si
    else:
        # No trae distrito -> solo 1 fila por delegación
        distritos = None
        if col_si_com is not None:
            comunidad_conteos[delegacion_sel] = count_si_in_col(head_com, data_com, col_si_com)

# Comercio
comercio_conteos = {}
if head_con and data_con and col_si_con is not None:
    comercio_conteos[delegacion_sel] = count_si_in_col(head_con, data_con, col_si_con)

# Policial
policial_conteos = {}
if head_pol and data_pol and col_si_pol is not None:
    policial_conteos[delegacion_sel] = count_si_in_col(head_pol, data_pol, col_si_pol)

# --- Metas manuales (Data Editor) ---
# Comunidad editor
st.markdown("### Comunidad")
if head_com:
    if distritos:
        df_meta_com = pd.DataFrame({"Distrito": distritos, "Meta": [0]*len(distritos)})
        # prefill con session_state
        key_meta = f"meta_com_{delegacion_sel}"
        if key_meta in st.session_state:
            prev = st.session_state[key_meta]
            # mezclar
            df_meta_com = df_meta_com.merge(prev[["Distrito", "Meta"]], on="Distrito", how="left", suffixes=("", "_prev"))
            df_meta_com["Meta"] = df_meta_com["Meta_prev"].fillna(df_meta_com["Meta"]).astype(int)
            df_meta_com = df_meta_com[["Distrito", "Meta"]]

        edited = st.data_editor(df_meta_com, use_container_width=True, num_rows="fixed", key=f"edit_{key_meta}")
        st.session_state[key_meta] = edited
        comunidad_metas = {row["Distrito"]: int(row["Meta"] or 0) for _, row in edited.iterrows()}

        comunidad_rows = build_rows("Comunidad", delegacion_sel, distritos, comunidad_conteos, comunidad_metas)
    else:
        # sin distritos
        meta_single = st.number_input("Meta Comunidad (manual):", min_value=0, value=0, step=1, key=f"meta_com_single_{delegacion_sel}")
        comunidad_metas[delegacion_sel] = int(meta_single)
        comunidad_rows = build_rows("Comunidad", delegacion_sel, None, comunidad_conteos, comunidad_metas)
else:
    st.warning("No se cargó CSV de Comunidad para esta delegación.")

df_comunidad = pd.DataFrame(comunidad_rows) if comunidad_rows else pd.DataFrame(
    columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]
)
st.dataframe(format_for_screen(df_comunidad), use_container_width=True)

# Comercio editor (1 fila)
st.markdown("### Comercio")
if head_con:
    meta_con = st.number_input("Meta Comercio (manual):", min_value=0, value=0, step=1, key=f"meta_con_{delegacion_sel}")
    comercio_metas = {delegacion_sel: int(meta_con)}
    comercio_rows = build_rows("Comercio", delegacion_sel, None, comercio_conteos, comercio_metas)
    df_comercio = pd.DataFrame(comercio_rows)
    st.dataframe(format_for_screen(df_comercio), use_container_width=True)
else:
    st.warning("No se cargó CSV de Comercio para esta delegación.")
    df_comercio = pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"])

# Policial editor (1 fila)
st.markdown("### Policial")
if head_pol:
    meta_pol = st.number_input("Meta Policial (manual):", min_value=0, value=0, step=1, key=f"meta_pol_{delegacion_sel}")
    policial_metas = {delegacion_sel: int(meta_pol)}
    policial_rows = build_rows("Policial", delegacion_sel, None, policial_conteos, policial_metas)
    df_policial = pd.DataFrame(policial_rows)
    st.dataframe(format_for_screen(df_policial), use_container_width=True)
else:
    st.warning("No se cargó CSV de Policial para esta delegación.")
    df_policial = pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"])

st.divider()
st.subheader("3) Descargar PDF")

# Generar PDF
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
    st.success("PDF generado. Usá el botón de descarga 👇")
    st.download_button(
        "⬇️ Descargar PDF",
        data=pdf_bytes,
        file_name=f"Reporte_{delegacion_sel.replace(' ', '_')}_{hoy.strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
    )

st.caption("Nota: Contabilidad sale del conteo de SI en la columna seleccionada. Metas y hora se ingresan manualmente.")
