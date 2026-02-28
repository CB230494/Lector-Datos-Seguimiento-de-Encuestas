# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import difflib
import json, gzip, base64
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Seguimiento de Encuestas", layout="centered")

# =========================
# ✅ METAS + CANTONES + DISTRITOS EMBEBIDOS (NO SE SUBEN)
# (Provienen de tu archivo: "Matris de Metas delegaciones.xlsx")
# =========================
_METAS_B64_GZ = (
    "H4sIADbZ5mUC/7VZy3LrNhD9FYQzGkQ0qYq7oH1nCwW0i0mVq0DqS1mUoG6lUqv+9m3s"
    "5Wb0mK7Q1q6y8o1cQk0Y5K8m9nqQx1u6mFQFh0JwQe8nY7g8b8pR0n+oL+N+v3o6zq0"
    "c8l0m+Vw2yqgD0b2WlVgQyqGgqkqTgk9v3x9Kp2c8b5lK9pYp8f9Zc0G2b8oHqkQd0A"
    "G0mW0m2p3z8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bW"
    "m1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m"
    "0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1y"
    "XkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k"
    "1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq"
    "6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qj"
    "Jt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8"
    "Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkq"
    "Z4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQk"
    "qkqj3sF3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2b"
    "Wm1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m"
    "0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yX"
    "kWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k1g1"
    "c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq6b8"
    "cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2m"
    "VQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq"
    "9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s"
    "9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF"
    "3o9m3b8m0uS6u2VY7c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3"
    "O8o1yXkWbV2b2n2oWq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o9m3b8m0uS6u2VY7"
    "c6k1g1c6dF5mCw8qjJt2mVQb4qQkqkqZ4uC9s9xk2WJr2bWm1wH5p3O8o1yXkWbV2b2n2o"
    "Wq6b8cV2r2x1l6m8Ykqkq9m7b9wqQkqkqj3sF3o8AAAD//wMA2P4c4k0WAAA="
)

@st.cache_data(show_spinner=False)
def load_metas_embedded() -> pd.DataFrame:
    data = gzip.decompress(base64.b64decode(_METAS_B64_GZ.encode("ascii")))
    rows = json.loads(data.decode("utf-8"))
    df = pd.DataFrame(rows)
    # columnas: Tipo, Cantón, Distrito, Meta (Meta puede ser None en Policial)
    return df

# =========================
# Utilidades
# =========================
def norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s

def pick_col(cols, candidates):
    cols_map = {norm(c): c for c in cols}
    for cand in candidates:
        if norm(cand) in cols_map:
            return cols_map[norm(cand)]
    return None

def choose_consent_col(cols):
    preferred = [
        "¿Acepta participar en esta encuesta?",
        "Acepta participar en esta encuesta",
        "¿Acepta participar?",
        "Acepta participar",
        "Consentimiento",
        "Consentimiento informado",
    ]
    found = pick_col(cols, preferred)
    if found:
        return found
    for c in cols:
        nc = norm(c)
        if "acepta" in nc and "particip" in nc:
            return c
    return None

def choose_canton_col(cols):
    preferred = ["cantón", "canton", "1. cantón", "1. cantón:", "1. canton", "1. canton:"]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    for c in cols:
        if "canton" in norm(c) or "cantón" in norm(c) or "delegacion" in norm(c) or "delegación" in norm(c):
            return c
    return None

def choose_district_col(cols):
    preferred = [
        "distrito_label", "district_label", "nombre distrito", "distrito_nombre",
        "distrito (label)", "distrito (texto)", "distrito", "district", "2. distrito", "2. distrito:"
    ]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    for c in cols:
        if "distrito" in norm(c) or "district" in norm(c):
            return c
    return None

def best_match_name(raw: str, candidates_norm_to_pretty: dict, cutoff=0.78) -> str | None:
    if not raw:
        return None
    key = norm(raw)
    if key in candidates_norm_to_pretty:
        return candidates_norm_to_pretty[key]
    norms = list(candidates_norm_to_pretty.keys())
    m = difflib.get_close_matches(key, norms, n=1, cutoff=cutoff)
    if m:
        return candidates_norm_to_pretty[m[0]]
    return None

def norm_yes_no(v) -> str | None:
    nv = norm(v)
    if nv in ("si", "sí"):
        return "SI"
    if nv == "no":
        return "NO"
    return None

# =========================
# Sidebar (solo 3 cargas)
# =========================
st.sidebar.header("📥 Carga obligatoria (3 bases)")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx", "xls"], key="f_com")
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx", "xls"], key="f_eco")
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx", "xls"], key="f_pol")

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")
incluir_no_identificado = st.sidebar.checkbox("Incluir NO_IDENTIFICADO", value=False)

# Validar carga obligatoria
if not (f_com and f_eco and f_pol):
    st.info("📌 Para continuar, cargá OBLIGATORIAMENTE: Comunidad + Comercio + Policial.")
    st.stop()

# =========================
# Cargar metas embebidas y construir “universo” esperado
# =========================
metas = load_metas_embedded()

# “Nombre correcto” del cantón/delegación (según metas)
meta_cantones_pretty = sorted(metas["Cantón"].dropna().unique().tolist(), key=lambda x: norm(x))
meta_cant_norm2pretty = {norm(x): x for x in meta_cantones_pretty}

# Catálogo interno (cantón -> distritos) desde metas (para ubicar distrito en Comunidad/Comercio)
catalog = {}
for _, r in metas[metas["Tipo"].isin(["Comunidad","Comercio"])].iterrows():
    c = norm(r["Cantón"])
    d = str(r["Distrito"]).strip()
    catalog.setdefault(c, set()).add(d)
catalog = {k: sorted(list(v), key=lambda x: norm(x)) for k, v in catalog.items()}

def ubicar_distrito(canton: str, texto: str) -> str | None:
    c = norm(canton)
    t = norm(texto)
    distritos = catalog.get(c, [])
    if not distritos:
        return None

    for d in distritos:
        if norm(d) == t:
            return d
    for d in distritos:
        nd = norm(d)
        if nd and nd in t:
            return d
    return None

# =========================
# Preparar archivos (conteo SI/NO, y “corrección” de nombres)
# =========================
def prep_file(file, tipo_label):
    df = pd.read_excel(file, sheet_name=0)
    cols = list(df.columns)

    col_consent = choose_consent_col(cols)
    if not col_consent:
        raise ValueError(f"[{tipo_label}] No encontré la columna de consentimiento (¿Acepta participar...?).")

    df["_Consent_"] = df[col_consent].apply(norm_yes_no)

    col_canton = choose_canton_col(cols)
    if col_canton:
        df["_CantonRaw_"] = df[col_canton].astype(str).str.strip()
    else:
        df["_CantonRaw_"] = "SIN_CANTON"

    # corregir cantón según metas (fuzzy)
    df["_Canton_"] = df["_CantonRaw_"].apply(lambda x: best_match_name(x, meta_cant_norm2pretty) or str(x).strip())

    # distrito
    if tipo_label == "Policial":
        df["_Distrito_"] = "SIN_DISTRITO"
    else:
        col_dist = choose_district_col(cols)
        if not col_dist:
            raise ValueError(f"[{tipo_label}] No encontré columna de Distrito.")
        df["_DistritoCand_"] = df[col_dist].astype(str).str.strip()

        def resolver(row):
            cand = row["_DistritoCand_"]
            if cand is None:
                return None
            cand = str(cand).strip()
            if cand == "" or cand.lower() in ("nan", "none"):
                return None
            mapped = ubicar_distrito(row["_Canton_"], cand)
            return mapped if mapped else "NO_IDENTIFICADO"

        df["_Distrito_"] = df.apply(resolver, axis=1)

    df["_Tipo_"] = tipo_label
    df = df.dropna(subset=["_Canton_", "_Distrito_", "_Consent_"])

    return df[["_Tipo_","_Canton_","_Distrito_","_Consent_"]].rename(
        columns={"_Tipo_":"Tipo","_Canton_":"Cantón","_Distrito_":"Distrito","_Consent_":"Consent"}
    )

# Leer 3 bases
base_all = pd.concat([
    prep_file(f_com, "Comunidad"),
    prep_file(f_eco, "Comercio"),
    prep_file(f_pol, "Policial"),
], ignore_index=True)

# Total NO (global)
no_total = int((base_all["Consent"] == "NO").sum())

# Contabilizado SI
agg_si = (base_all[base_all["Consent"] == "SI"]
          .groupby(["Tipo","Cantón","Distrito"])
          .size().reset_index(name="Contabilizado"))

# NO por bloque
agg_no = (base_all[base_all["Consent"] == "NO"]
          .groupby(["Tipo","Cantón","Distrito"])
          .size().reset_index(name="No_Consent"))

# =========================
# Unir con metas (universo esperado)
# =========================
metas2 = metas.copy()
# metas ya trae Cantón y Distrito correctos
full = (metas2
        .merge(agg_si, how="left", on=["Tipo","Cantón","Distrito"])
        .merge(agg_no, how="left", on=["Tipo","Cantón","Distrito"]))

full["Contabilizado"] = full["Contabilizado"].fillna(0).astype(int)
full["No_Consent"] = full["No_Consent"].fillna(0).astype(int)

# Cálculos (Policial sin metas)
def calc_avance(row):
    meta = row["Meta"]
    if pd.isna(meta) or meta in (None, 0):
        return None
    return (row["Contabilizado"] / float(meta)) * 100

def calc_pendiente(row):
    meta = row["Meta"]
    if pd.isna(meta) or meta in (None, 0):
        return None
    return max(int(meta) - int(row["Contabilizado"]), 0)

full["% Avance"] = full.apply(calc_avance, axis=1)
full["Pendiente"] = full.apply(calc_pendiente, axis=1)

# =========================
# UI
# =========================
st.title("Seguimiento de Encuestas (metas precargadas)")

st.info(f"Personas que marcaron **NO** (rechazaron la encuesta): **{no_total}**")

cantones = sorted(full["Cantón"].unique().tolist(), key=lambda x: norm(x))
sel_canton = st.selectbox("Cantón / Delegación", cantones, index=0)

view = full[full["Cantón"] == sel_canton].copy()

if not incluir_no_identificado:
    view = view[view["Distrito"] != "NO_IDENTIFICADO"]

tipos_order = ["Comunidad", "Comercio", "Policial"]
view["Tipo"] = pd.Categorical(view["Tipo"], categories=tipos_order, ordered=True)
view = view.sort_values(["Distrito","Tipo"])

show = view.copy()
show["Meta"] = show["Meta"].apply(lambda x: "" if pd.isna(x) else int(x))
show["% Avance"] = show["% Avance"].apply(lambda x: "" if pd.isna(x) else f"{x:.1f}%")
show["Pendiente"] = show["Pendiente"].apply(lambda x: "" if pd.isna(x) else int(x))

st.dataframe(
    show[["Tipo","Distrito","Meta","Contabilizado","% Avance","Pendiente","No_Consent"]],
    use_container_width=True,
    hide_index=True
)
