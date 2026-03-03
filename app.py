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

# -------------------------------------------------------
# NORMALIZACIÓN FUERTE
# -------------------------------------------------------

def normalize(val):
    if val is None:
        return ""
    v = str(val).strip()
    v = unicodedata.normalize("NFD", v)
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    v = v.lower().strip()
    return v


def is_yes(val):
    v = normalize(val)
    return v in ["si", "sí"]


# -------------------------------------------------------
# FECHA EN ESPAÑOL
# -------------------------------------------------------

MESES = [
    "enero","febrero","marzo","abril","mayo","junio",
    "julio","agosto","septiembre","octubre","noviembre","diciembre"
]

DIAS = [
    "lunes","martes","miércoles","jueves","viernes","sábado","domingo"
]

def fecha_es(dt):
    return f"{DIAS[dt.weekday()]}, {dt.day} de {MESES[dt.month-1]} de {dt.year}"


# -------------------------------------------------------
# PARSE CSV
# -------------------------------------------------------

def parse_csv(file_bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"')
    rows = [r for r in reader if r]
    if not rows:
        return [], []
    return rows[0], rows[1:]


# -------------------------------------------------------
# DETECTAR COLUMNA DISTRITO (MUY ESTRICTO)
# -------------------------------------------------------

def find_district_column(header):
    """
    SOLO acepta encabezados exactos tipo:
    distrito
    nombre_distrito
    district
    """
    for i, h in enumerate(header):
        h_norm = normalize(h)

        if h_norm in ["distrito", "nombre_distrito", "district"]:
            return i

    return None


# -------------------------------------------------------
# DETECTAR MEJOR COLUMNA SI
# -------------------------------------------------------

def find_best_yes_column(header, data):
    # Preferir consentimiento
    for i, h in enumerate(header):
        if "acepta" in normalize(h) or "consent" in normalize(h):
            return i

    # Si no, buscar la que más SI tenga
    best = 0
    best_count = -1

    for i in range(len(header)):
        count = 0
        for r in data:
            if i < len(r) and is_yes(r[i]):
                count += 1
        if count > best_count:
            best_count = count
            best = i

    return best


# -------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------

st.title("📄 Reporte por Delegación")

files = st.file_uploader("Cargar CSV", type=["csv"], accept_multiple_files=True)

if not files:
    st.stop()

logo_path = "001.png" if Path("001.png").exists() else None

data_por_tipo = {}

for f in files:
    header, data = parse_csv(f.getvalue())

    nombre = Path(f.name).stem
    partes = nombre.split("_")
    tipo = partes[0].capitalize()
    lugar = partes[1].capitalize()

    data_por_tipo[tipo] = (header, data, lugar)

delegacion = list(data_por_tipo.values())[0][2]
hora_manual = st.text_input("Hora (manual):")

hoy = datetime.now()
fecha_str = fecha_es(hoy)

# -------------------------------------------------------
# PROCESAR CADA TIPO
# -------------------------------------------------------

def procesar_tipo(tipo):

    if tipo not in data_por_tipo:
        return pd.DataFrame(columns=["Tipo","Distrito","Meta","Contabilidad","% Avance","Pendiente"])

    header, data, lugar = data_por_tipo[tipo]

    col_yes = find_best_yes_column(header, data)
    col_dist = find_district_column(header)

    if tipo == "Comunidad" and col_dist is not None:

        distritos = {}
        for r in data:
            if col_dist < len(r):
                d = r[col_dist]
                d_clean = str(d).strip().replace("_"," ").title()
                if d_clean not in distritos:
                    distritos[d_clean] = 0
                if col_yes < len(r) and is_yes(r[col_yes]):
                    distritos[d_clean] += 1

        df = pd.DataFrame({
            "Tipo": "Comunidad",
            "Distrito": list(distritos.keys()),
            "Meta": 0,
            "Contabilidad": list(distritos.values())
        })

    else:
        cont = sum(1 for r in data if col_yes < len(r) and is_yes(r[col_yes]))

        df = pd.DataFrame([{
            "Tipo": tipo,
            "Distrito": lugar,
            "Meta": 0,
            "Contabilidad": cont
        }])

    # META MANUAL
    for i in range(len(df)):
        df.at[i,"Meta"] = st.number_input(
            f"Meta {tipo} - {df.at[i,'Distrito']}",
            min_value=0,
            value=0,
            key=f"{tipo}_{i}"
        )

    # CÁLCULOS
    df["% Avance"] = df.apply(
        lambda r: (r["Contabilidad"]/r["Meta"]) if r["Meta"]>0 else 0,
        axis=1
    )
    df["Pendiente"] = df.apply(
        lambda r: max(r["Meta"] - r["Contabilidad"],0),
        axis=1
    )

    df["% Avance"] = df["% Avance"].apply(lambda x: f"{int(round(x*100))}%")

    return df


st.subheader("Comunidad")
df_com = procesar_tipo("Comunidad")
st.dataframe(df_com)

st.subheader("Comercio")
df_con = procesar_tipo("Comercio")
st.dataframe(df_con)

st.subheader("Policial")
df_pol = procesar_tipo("Policial")
st.dataframe(df_pol)

st.caption("Contabilidad = conteo de SI. Meta y hora son manuales.")
