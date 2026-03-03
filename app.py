# app.py
# -*- coding: utf-8 -*-
"""
📊 Conteo SI/NO por pregunta (columna) para encuestas (Policial / Comercio / Comunidad)

✅ Lee 1 o muchos CSV (ArcGIS Survey123 incluidos, aunque el header tenga comas raras)
✅ Detecta columnas binarias (mayoría SI/NO) y te deja elegir cuál contar por archivo
✅ Identifica Tipo y Lugar desde el nombre del archivo (ej: Policial_Guarco_2026_0.csv)
✅ Muestra resumen por archivo + resumen agrupado por Tipo/Lugar/Pregunta
✅ Exporta resumen a Excel

Instalar:
    pip install streamlit pandas openpyxl

Ejecutar:
    streamlit run app.py
"""

import io
import re
import csv
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Conteo SI/NO - Encuestas", layout="wide")


# -----------------------------
# Normalización / utilidades
# -----------------------------
def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def normalize_cell(val) -> str:
    """Normaliza cualquier celda a texto simple, sin acentos y en minúscula."""
    if val is None:
        return ""
    v = str(val).strip().strip("\ufeff")  # BOM
    v = v.replace("\n", " ").replace("\r", " ").strip()
    v_low = _strip_accents(v.lower())
    return v_low


def infer_tipo_lugar(filename: str, header_row_cells: list[str]) -> tuple[str, str]:
    """
    Intenta inferir Tipo/Lugar:
    1) Por nombre de archivo: Policial_Guarco_2026_0.csv
    2) Por encabezado: "Encuesta policial – Guarco"
    """
    base = Path(filename).stem

    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        tipo = m.group(1).capitalize()
        lugar = m.group(2).replace("_", " ").strip()
        return tipo, lugar

    if header_row_cells:
        joined = " | ".join(header_row_cells[:12])
        m2 = re.search(r"(?i)encuesta\s+(policial|comunidad|comercio)\s*[–-]\s*([^|,]+)", joined)
        if m2:
            tipo = m2.group(1).capitalize()
            lugar = m2.group(2).strip()
            return tipo, lugar

    return "Desconocida", base


# -----------------------------
# Parser robusto CSV
# -----------------------------
def parse_csv_rows(file_bytes: bytes):
    """
    Lee CSV con csv.reader (robusto ante comillas y contenido con comas).
    Importante: no convertimos directo a DataFrame porque algunos CSV de Survey123
    traen encabezados/filas con longitudes diferentes.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"', skipinitialspace=False)

    rows = []
    for row in reader:
        if not row:
            continue
        if all(normalize_cell(c) == "" for c in row):
            continue
        rows.append(row)

    if not rows:
        return [], []

    header = rows[0]
    data = rows[1:]
    return header, data


def get_binary_columns(header, data, min_ratio=0.60, min_hits=5):
    """
    Detecta columnas donde una proporción grande de valores no-vacíos son exactamente 'si' o 'no'.

    - min_ratio: porcentaje mínimo de celdas válidas que deben ser si/no (0.60 = 60%)
    - min_hits: mínimo de ocurrencias si/no para considerarla columna relevante
    """
    if not data:
        return []

    max_len = max(len(r) for r in data) if data else len(header)
    cols = max(len(header), max_len)

    bin_cols = []
    for j in range(cols):
        hits = 0
        total = 0
        for r in data:
            if j >= len(r):
                continue
            v = normalize_cell(r[j])
            if v == "":
                continue
            total += 1
            if v in ("si", "no"):
                hits += 1

        if total > 0 and hits >= min_hits and (hits / total) >= min_ratio:
            bin_cols.append(j)

    return bin_cols


def count_si_no_in_column(header, data, col_idx: int):
    """Cuenta SI/NO exactos en una columna específica."""
    si = 0
    no = 0
    filas = 0

    for r in data:
        filas += 1
        if col_idx >= len(r):
            continue
        v = normalize_cell(r[col_idx])

        # SOLO exactos
        if v == "si":
            si += 1
        elif v == "no":
            no += 1

    col_name = header[col_idx] if col_idx < len(header) else f"Columna {col_idx+1}"
    return si, no, filas, col_name


def safe_label(s: str, max_len=90) -> str:
    s = str(s).replace("\n", " ").replace("\r", " ").strip()
    if len(s) > max_len:
        s = s[:max_len - 3] + "..."
    return s


# -----------------------------
# UI
# -----------------------------
st.title("📊 Conteo de respuestas SI / NO (por pregunta)")

st.write(
    "Subí uno o varios CSV y elegí la **pregunta/columna** a contar. "
    "La app cuenta **solo SI/NO exactos** (no cuenta textos como 'no_se_aplica', etc.)."
)

files = st.file_uploader(
    "Cargar CSV (puedes seleccionar varios)",
    type=["csv"],
    accept_multiple_files=True
)

if not files:
    st.info("Subí tus CSV para generar el conteo.")
    st.stop()

st.divider()

results = []

# Parámetros de detección (por si querés ajustar)
with st.expander("⚙️ Ajustes de detección (opcional)"):
    min_ratio = st.slider("Proporción mínima SI/NO para detectar columna binaria", 0.30, 0.95, 0.60, 0.05)
    min_hits = st.number_input("Mínimo de SI/NO para considerar la columna", min_value=1, max_value=1000, value=5, step=1)

st.caption("Tip: si una columna tiene pocos registros, bajá el mínimo de ocurrencias (min_hits).")

# Procesar cada archivo
for f in files:
    data_bytes = f.getvalue()
    header, data_rows = parse_csv_rows(data_bytes)

    tipo, lugar = infer_tipo_lugar(f.name, header or [])

    st.markdown(f"## 📌 {f.name}")
    st.write(f"**Tipo:** {tipo}  |  **Lugar:** {lugar}")

    if not header:
        st.error("Este CSV viene vacío o no pude leer el encabezado.")
        continue

    # Detectar columnas binarias
    bin_cols = get_binary_columns(header, data_rows, min_ratio=min_ratio, min_hits=int(min_hits))

    # Construir lista de opciones: primero columnas binarias, luego (opcional) todas
    options = []
    for j in bin_cols:
        nm = header[j] if j < len(header) else f"Columna {j+1}"
        options.append((j, nm))

    # Si no detecta ninguna, permitir escoger cualquier columna para no quedar bloqueado
    allow_all = st.checkbox("Mostrar TODAS las columnas (si no aparece la que querés)", key=f"all_{f.name}")
    if allow_all:
        # Agregar todas las columnas que no estén ya
        existing = {idx for idx, _ in options}
        for j in range(len(header)):
            if j not in existing:
                options.append((j, header[j]))

    if not options:
        st.warning("No detecté columnas binarias. Activá 'Mostrar TODAS las columnas' y elegí manualmente.")
        st.divider()
        continue

    labels = [f"[{idx+1}] {safe_label(nm)}" for idx, nm in options]
    choice = st.selectbox("Elegí la pregunta/columna a contar (SI/NO):", labels, key=f"col_{f.name}")
    sel_idx = options[labels.index(choice)][0]

    si, no, filas, col_name = count_si_no_in_column(header, data_rows, sel_idx)

    total = si + no
    pct_si = (si / total * 100) if total else 0.0
    pct_no = (no / total * 100) if total else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SI", si)
    c2.metric("NO", no)
    c3.metric("Total (SI+NO)", total)
    c4.metric("% SI", f"{pct_si:.2f}%")

    results.append({
        "Archivo": f.name,
        "Tipo": tipo,
        "Lugar": lugar,
        "Pregunta/Columna": col_name,
        "Filas (respuestas)": filas,
        "SI": si,
        "NO": no,
        "Total SI+NO": total,
        "%SI": round(pct_si, 2),
        "%NO": round(pct_no, 2),
    })

    st.divider()

if not results:
    st.error("No se generaron resultados. Revisá que los CSV tengan datos y que estés eligiendo una columna correcta.")
    st.stop()

df = pd.DataFrame(results)

# Totales generales
st.subheader("📌 Totales generales (según columnas seleccionadas)")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Archivos procesados", len(df))
col2.metric("SI (total)", int(df["SI"].sum()))
col3.metric("NO (total)", int(df["NO"].sum()))
col4.metric("Total (SI+NO)", int(df["Total SI+NO"].sum()))

st.subheader("📄 Resumen por archivo")
st.dataframe(df, use_container_width=True)

# Agrupado
st.subheader("🧾 Resumen agrupado (Tipo + Lugar + Pregunta)")
df_group = (
    df.groupby(["Tipo", "Lugar", "Pregunta/Columna"], as_index=False)
      .agg({
          "Filas (respuestas)": "sum",
          "SI": "sum",
          "NO": "sum",
          "Total SI+NO": "sum"
      })
)

df_group["%SI"] = (df_group["SI"] / df_group["Total SI+NO"]).fillna(0) * 100
df_group["%NO"] = (df_group["NO"] / df_group["Total SI+NO"]).fillna(0) * 100
df_group["%SI"] = df_group["%SI"].round(2)
df_group["%NO"] = df_group["%NO"].round(2)

st.dataframe(df_group, use_container_width=True)

# Export Excel
st.subheader("⬇️ Descargar resumen en Excel")
out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Por_archivo")
    df_group.to_excel(writer, index=False, sheet_name="Agrupado")
out.seek(0)

st.download_button(
    "Descargar Excel",
    data=out,
    file_name="resumen_si_no_encuestas.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
