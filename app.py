# -*- coding: utf-8 -*-
import io
import datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard de Encuestas", layout="centered")

# ----------------------------
# Utilidades
# ----------------------------
def pick_col(cols, candidates):
    """Devuelve el nombre real de la primera columna que coincide (ignorando tildes/mayúsculas)."""
    import unicodedata
    def norm(s):
        s = str(s).strip().lower()
        s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
        return s
    mapping = {norm(c): c for c in cols}
    for cand in candidates:
        nc = norm(cand)
        if nc in mapping:
            return mapping[nc]
    return None


def infer_district_name(df: pd.DataFrame, canton_col: str, distrito_col: str):
    """
    Heurística Survey123: a veces el 'distrito nombre' no viene en la col Distrito,
    sino en un bloque de columnas con nombres (Merced, Carmen, etc.) donde solo 1 queda lleno.
    Buscamos la primera no vacía justo después de 'Distrito' y antes de 'Edad/Género/etc.'.
    """
    cols = list(df.columns)
    start = cols.index(distrito_col) + 1

    end_marker = pick_col(cols, ["Edad", "Genero", "Género", "Escolaridad", "Tipo de local", "Tipo de local comercial"])
    if end_marker and end_marker in cols:
        end = cols.index(end_marker)
    else:
        end = min(start + 35, len(cols))

    candidate_cols = [c for c in cols[start:end] if c not in (canton_col, distrito_col)]
    if not candidate_cols:
        return pd.Series([None] * len(df), index=df.index)

    def first_non_empty(row):
        for c in candidate_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                return str(v).strip()
        return None

    return df.apply(first_non_empty, axis=1)


def read_any_excel(uploaded_file) -> pd.DataFrame:
    return pd.read_excel(uploaded_file, sheet_name=0)


def to_excel_bytes(df: pd.DataFrame, sheet_name="reporte"):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return out.getvalue()


def fmt_pct(x):
    try:
        return f"{x:.0f}%"
    except Exception:
        return ""


# ----------------------------
# Estilos (HTML)
# ----------------------------
CSS = """
<style>
.page-wrap {
    width: 640px;
    margin: 0 auto;
}
.title {
    text-align:center;
    font-size:42px;
    font-weight:800;
    margin: 8px 0 10px 0;
}
.card {
    border: 1px solid #cfcfcf;
    border-radius: 6px;
    overflow: hidden;
    background: #ffffff;
}
.tbl {
    width:100%;
    border-collapse: collapse;
    font-size: 14px;
}
.tbl th, .tbl td {
    border-bottom: 1px solid #d9d9d9;
    padding: 10px 10px;
}
.tbl thead th {
    background: #e6e6e6;
    text-align: left;
    font-weight: 800;
}
.section-row td {
    background: #d9d9d9;
    font-weight: 800;
    border-bottom: 0;
    padding: 10px;
}
.center {
    text-align:center;
}
.pct {
    background: #29a36a;
    color: #000;
    font-weight: 800;
    text-align: center;
    border-left: 3px solid #ffffff;
    border-right: 3px solid #ffffff;
}
.pending {
    background: #6d8fc9;
    color: #000;
    font-weight: 800;
    text-align: center;
    border-left: 3px solid #ffffff;
}
.meta, .count {
    text-align:center;
    font-weight: 700;
}
.footer {
    text-align:center;
    margin-top: 14px;
    font-size: 14px;
}
.reminder {
    margin-top: 18px;
    font-size: 13px;
    font-weight: 800;
}
.small {
    font-size: 13px;
}
</style>
"""


# ----------------------------
# UI - carga y configuración
# ----------------------------
st.markdown('<div class="page-wrap">', unsafe_allow_html=True)

st.sidebar.header("📥 Carga de datos")

modo = st.sidebar.radio(
    "¿Cómo vas a cargar los datos?",
    ["Un solo Excel (incluye columna Tipo)", "Tres Excels (uno por Tipo)"],
    index=0
)

meta_comunidad = st.sidebar.number_input("Meta Comunidad", min_value=1, value=375, step=1)
meta_comercio  = st.sidebar.number_input("Meta Comercio",  min_value=1, value=210, step=1)
meta_policial  = st.sidebar.number_input("Meta Policial",  min_value=1, value=90,  step=1)

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")

hoy = dt.date.today()
fecha_txt = hoy.strftime("%A, %d de %B de %Y")
# Español básico sin depender de locale del sistema:
dias = {
    "Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves",
    "Friday":"viernes","Saturday":"sábado","Sunday":"domingo"
}
meses = {
    "January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio",
    "July":"julio","August":"agosto","September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"
}
fecha_txt = fecha_txt.replace(hoy.strftime("%A"), dias.get(hoy.strftime("%A"), hoy.strftime("%A")))
fecha_txt = fecha_txt.replace(hoy.strftime("%B"), meses.get(hoy.strftime("%B"), hoy.strftime("%B")))

# ----------------------------
# Cargar data y normalizar a: Tipo, Cantón, Distrito
# ----------------------------
data = []

if modo == "Un solo Excel (incluye columna Tipo)":
    f = st.sidebar.file_uploader("Sube el Excel", type=["xlsx", "xls"])
    if not f:
        st.info("Sube el Excel para generar el dashboard.")
        st.stop()

    df = read_any_excel(f)
    cols = list(df.columns)

    col_tipo = pick_col(cols, ["Tipo", "Encuesta", "Formulario"])
    col_canton = pick_col(cols, ["Cantón", "Canton"])
    col_distrito = pick_col(cols, ["Distrito", "District"])

    if not col_canton or not col_distrito:
        st.error("No pude detectar Cantón/Distrito en tu Excel.")
        st.stop()

    # Tipo obligatorio en este modo
    if not col_tipo:
        st.error("En este modo necesito una columna 'Tipo' (Comunidad/Comercio/Policial).")
        st.stop()

    df["_Canton_"] = df[col_canton].astype(str).str.strip()
    guessed = infer_district_name(df, col_canton, col_distrito)
    df["_Distrito_"] = guessed.where(guessed.notna(), df[col_distrito]).astype(str).str.strip()
    df["_Tipo_"] = df[col_tipo].astype(str).str.strip()

    df = df.replace({"nan": None, "None": None, "": None})
    df = df.dropna(subset=["_Canton_", "_Distrito_", "_Tipo_"])

    data.append(df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(
        columns={"_Tipo_":"Tipo","_Canton_":"Cantón","_Distrito_":"Distrito"}
    ))

else:
    f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx","xls"], key="com")
    f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx","xls"], key="eco")
    f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx","xls"], key="pol")

    if not (f_com and f_eco and f_pol):
        st.info("Sube los 3 archivos (Comunidad, Comercio y Policial).")
        st.stop()

    def prep(file, tipo_label):
        df = read_any_excel(file)
        cols = list(df.columns)
        col_canton = pick_col(cols, ["Cantón", "Canton"])
        col_distrito = pick_col(cols, ["Distrito", "District"])
        if not col_canton or not col_distrito:
            raise ValueError(f"No pude detectar Cantón/Distrito en archivo: {tipo_label}")

        df["_Canton_"] = df[col_canton].astype(str).str.strip()
        guessed = infer_district_name(df, col_canton, col_distrito)
        df["_Distrito_"] = guessed.where(guessed.notna(), df[col_distrito]).astype(str).str.strip()
        df["_Tipo_"] = tipo_label

        df = df.replace({"nan": None, "None": None, "": None})
        df = df.dropna(subset=["_Canton_", "_Distrito_"])
        return df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(
            columns={"_Tipo_":"Tipo","_Canton_":"Cantón","_Distrito_":"Distrito"}
        )

    try:
        data.append(prep(f_com, "Comunidad"))
        data.append(prep(f_eco, "Comercio"))
        data.append(prep(f_pol, "Policial"))
    except ValueError as e:
        st.error(str(e))
        st.stop()

base = pd.concat(data, ignore_index=True)

# ----------------------------
# Agregación: conteos por Tipo/Cantón/Distrito
# ----------------------------
agg = (
    base.groupby(["Tipo","Cantón","Distrito"])
        .size()
        .reset_index(name="Contabilizado")
)

# Selección Cantón/Distrito para el reporte tipo “Merced”
st.sidebar.divider()
st.sidebar.header("🎯 Selección para el dashboard")

cantones = sorted(agg["Cantón"].unique().tolist())
sel_canton = st.sidebar.selectbox("Cantón", cantones, index=0 if cantones else None)

distritos = sorted(agg.loc[agg["Cantón"] == sel_canton, "Distrito"].unique().tolist())
sel_distrito = st.sidebar.selectbox("Distrito", distritos, index=0 if distritos else None)

if not sel_canton or not sel_distrito:
    st.warning("No hay Cantón/Distrito disponibles con los datos cargados.")
    st.stop()

# Metas por tipo (como tu ejemplo)
meta_map = {"Comunidad": int(meta_comunidad), "Comercio": int(meta_comercio), "Policial": int(meta_policial)}

# Filtrar a 1 distrito para el dashboard estilo reporte
sub = agg[(agg["Cantón"] == sel_canton) & (agg["Distrito"] == sel_distrito)].copy()

# Asegurar que existan las 3 filas aunque alguna tenga 0
tipos_order = ["Comunidad", "Comercio", "Policial"]
rows = []
for t in tipos_order:
    cnt = int(sub.loc[sub["Tipo"] == t, "Contabilizado"].sum()) if (sub["Tipo"] == t).any() else 0
    meta = meta_map[t]
    pendiente = max(meta - cnt, 0)
    avance = (cnt / meta * 100) if meta else 0
    rows.append({"Tipo": t, "Distrito": sel_distrito, "Meta": meta, "Contabilizado": cnt, "% Avance": avance, "Pendiente": pendiente})

rep = pd.DataFrame(rows)

# ----------------------------
# Render (HTML similar al ejemplo)
# ----------------------------
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(f'<div class="title">{sel_distrito}</div>', unsafe_allow_html=True)

header_html = """
<div class="card">
  <table class="tbl">
    <thead>
      <tr>
        <th style="width:22%">Tipo</th>
        <th style="width:20%">Distrito</th>
        <th class="center" style="width:12%">Meta</th>
        <th class="center" style="width:16%">Contabilizado</th>
        <th class="center" style="width:15%">% Avance</th>
        <th class="center" style="width:15%">Pendiente</th>
      </tr>
    </thead>
    <tbody>
"""

body_parts = []
for _, r in rep.iterrows():
    body_parts.append(
        f"""
        <tr class="section-row"><td colspan="6">{r['Tipo']}</td></tr>
        <tr>
          <td></td>
          <td>{r['Distrito']}</td>
          <td class="meta">{int(r['Meta'])}</td>
          <td class="count">{int(r['Contabilizado'])}</td>
          <td class="pct">{fmt_pct(r['% Avance'])}</td>
          <td class="pending">{int(r['Pendiente'])}</td>
        </tr>
        """
    )

footer_html = """
    </tbody>
  </table>
</div>
"""

st.markdown(header_html + "\n".join(body_parts) + footer_html, unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="footer">
      <div class="small">{fecha_txt}</div>
      <div class="small" style="margin-top:6px;"><b>Hora del corte:</b> {hora_manual if hora_manual else "—"}</div>
      <div class="reminder">
        Recordatorio: Al alcanzar la meta de las encuestas, se debe realizar un oficio dirigido a la Comisionada Hannia Cubillo,
        indicando que se ha alcanzado la meta. Dicho oficio se deberá subir a la carpeta compartida de Sembremos Seguridad,
        propiamente a la denominada "Recolección".
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# Descarga de reporte detallado (opcional)
# ----------------------------
st.divider()
st.subheader("⬇️ Descargar detalle (Cantón/Distrito/Tipo)")

detalle = agg.copy()
detalle["Meta"] = detalle["Tipo"].map(meta_map).fillna(0).astype(int)
detalle["Pendiente"] = (detalle["Meta"] - detalle["Contabilizado"]).clip(lower=0)
detalle["% Avance"] = (detalle["Contabilizado"] / detalle["Meta"] * 100).round(1)

excel_bytes = to_excel_bytes(detalle.sort_values(["Cantón","Distrito","Tipo"]), sheet_name="seguimiento")
st.download_button(
    "Descargar Excel (seguimiento completo)",
    data=excel_bytes,
    file_name="seguimiento_encuestas.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.markdown("</div>", unsafe_allow_html=True)











