# app.py
# -*- coding: utf-8 -*-
import io
import re
import csv
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Conteo SI/NO - Encuestas", layout="wide")


# -----------------------------
# Utilidades
# -----------------------------
def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def normalize_cell(val: str) -> str:
    if val is None:
        return ""
    v = str(val).strip().strip("\ufeff")  # BOM
    v = v.replace("\n", " ").replace("\r", " ").strip()
    v_low = _strip_accents(v.lower())
    return v_low


def infer_tipo_lugar(filename: str, header_row_cells: list[str]) -> tuple[str, str]:
    # 1) Por nombre de archivo: Policial_Matina_2026_0.csv
    base = Path(filename).stem
    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        tipo = m.group(1).capitalize()
        lugar = m.group(2).replace("_", " ").strip()
        return tipo, lugar

    # 2) Por encabezado (3ra columna suele traer: "Encuesta policial – Matina")
    if header_row_cells:
        # Busca algo tipo: "Encuesta ... – Lugar"
        joined = " | ".join(header_row_cells[:8])  # suficiente
        # Ej: Encuesta policial – Coto Brus
        m2 = re.search(r"(?i)encuesta\s+(policial|comunidad|comercio)\s*[–-]\s*([^|,]+)", joined)
        if m2:
            tipo = m2.group(1).capitalize()
            lugar = m2.group(2).strip()
            return tipo, lugar

    return "Desconocida", base


def count_si_no_from_bytes(file_bytes: bytes, filename: str) -> dict:
    """
    Parser robusto para CSVs 'problemáticos' (encabezados con comas sin comillas).
    Estrategia: usar csv.reader (respeta comillas en respuestas) y contar tokens exactos.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    # csv.reader sobre string
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"', skipinitialspace=False)

    header = None
    rows_count = 0
    si = 0
    no = 0

    for i, row in enumerate(reader):
        if i == 0:
            header = row
            continue

        # Saltar filas vacías
        if not row or all(normalize_cell(c) == "" for c in row):
            continue

        rows_count += 1
        for cell in row:
            v = normalize_cell(cell)
            # contar SOLO exactos: si/sí/no
            if v in ("si", "sí"):   # "sí" normalmente ya queda como "si" al quitar acentos,
                si += 1             # pero lo dejo por claridad.
            elif v == "no":
                no += 1

    tipo, lugar = infer_tipo_lugar(filename, header or [])
    total = si + no
    pct_si = (si / total * 100) if total else 0.0
    pct_no = (no / total * 100) if total else 0.0

    return {
        "Archivo": filename,
        "Tipo": tipo,
        "Lugar": lugar,
        "Filas (respuestas)": rows_count,
        "SI": si,
        "NO": no,
        "Total SI+NO": total,
        "%SI": round(pct_si, 2),
        "%NO": round(pct_no, 2),
    }


# -----------------------------
# UI
# -----------------------------
st.title("📊 Conteo de respuestas SI / NO (Encuestas)")

st.write(
    "Subí uno o varios CSV y la app te devuelve el conteo de **SI** y **NO** (exactos), "
    "indicando **Tipo de encuesta** y **Lugar**."
)

files = st.file_uploader(
    "Cargar CSV (puedes seleccionar varios)",
    type=["csv"],
    accept_multiple_files=True
)

if not files:
    st.info("Subí tus CSV para generar el conteo.")
    st.stop()

results = []
for f in files:
    data = f.getvalue()
    results.append(count_si_no_from_bytes(data, f.name))

df = pd.DataFrame(results)

# Totales generales
col1, col2, col3, col4 = st.columns(4)
col1.metric("Archivos", len(df))
col2.metric("SI (total)", int(df["SI"].sum()))
col3.metric("NO (total)", int(df["NO"].sum()))
col4.metric("Filas (total)", int(df["Filas (respuestas)"].sum()))

st.subheader("Resumen por archivo")
st.dataframe(df, use_container_width=True)

# Resumen agrupado por Tipo/Lugar (por si suben varios del mismo)
st.subheader("Resumen agrupado (Tipo + Lugar)")
df_group = (
    df.groupby(["Tipo", "Lugar"], as_index=False)
      .agg({
          "Filas (respuestas)": "sum",
          "SI": "sum",
          "NO": "sum",
          "Total SI+NO": "sum"
      })
)
df_group["%SI"] = (df_group["SI"] / df_group["Total SI+NO"]).replace([pd.NA, pd.NaT], 0).fillna(0) * 100
df_group["%NO"] = (df_group["NO"] / df_group["Total SI+NO"]).replace([pd.NA, pd.NaT], 0).fillna(0) * 100
df_group["%SI"] = df_group["%SI"].round(2)
df_group["%NO"] = df_group["%NO"].round(2)

st.dataframe(df_group, use_container_width=True)

# Descargar Excel
st.subheader("Descargar")
out = io.BytesIO()
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Por_archivo")
    df_group.to_excel(writer, index=False, sheet_name="Agrupado")
out.seek(0)

st.download_button(
    "⬇️ Descargar resumen en Excel",
    data=out,
    file_name="resumen_si_no_encuestas.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)




