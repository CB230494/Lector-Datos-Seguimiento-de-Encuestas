# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import matplotlib.pyplot as plt

st.set_page_config(page_title="Dashboard de Encuestas", layout="centered")

# -------------------------
# UTILIDADES
# -------------------------
def norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.split())

def safe_html(x):
    return html.escape("" if x is None else str(x))

def pick_col(cols, candidates):
    cols_map = {norm(c): c for c in cols}
    for cand in candidates:
        if norm(cand) in cols_map:
            return cols_map[norm(cand)]
    return None

def read_excel(file):
    return pd.read_excel(file, sheet_name=0)

def fmt_pct(x):
    return f"{x:.0f}%"

# -------------------------
# CATÁLOGO BASE (Pérez Zeledón)
# -------------------------
BASE_CATALOGO = {
    "perez zeledon": [
        "San Isidro de El General", "El General", "Daniel Flores", "Rivas",
        "San Pedro", "Platanares", "Pejibaye", "Cajón",
        "Barú", "Río Nuevo", "Páramo", "La Amistad",
    ]
}

def ubicar_distrito(canton, texto):
    distritos = BASE_CATALOGO.get(norm(canton), [])
    for d in distritos:
        if norm(d) in norm(texto):
            return d
    return "NO_IDENTIFICADO"

# -------------------------
# SIDEBAR
# -------------------------
st.sidebar.header("📥 Cargar archivos")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx"])
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx"])
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx"])

st.sidebar.header("🎯 Metas")
meta_com = st.sidebar.number_input("Meta Comunidad", value=375)
meta_eco = st.sidebar.number_input("Meta Comercio", value=210)
meta_pol = st.sidebar.number_input("Meta Policial", value=90)

hora_manual = st.sidebar.text_input("Hora del corte (manual)")

meta_map = {
    "Comunidad": meta_com,
    "Comercio": meta_eco,
    "Policial": meta_pol
}

# Fecha automática
hoy = dt.datetime.now()
fecha_txt = hoy.strftime("%A, %d de %B de %Y")

# -------------------------
# PREPARAR DATOS
# -------------------------
def preparar(file, tipo):
    df = read_excel(file)
    col_canton = pick_col(df.columns, ["Cantón", "Canton"])
    col_distrito = pick_col(df.columns, ["Distrito", "district"])

    df["_Tipo"] = tipo
    df["_Canton"] = df[col_canton]
    df["_Distrito"] = df.apply(
        lambda r: ubicar_distrito(r[col_canton], r[col_distrito]), axis=1
    )
    return df[["_Tipo", "_Canton", "_Distrito"]]

data = []
if f_com: data.append(preparar(f_com, "Comunidad"))
if f_eco: data.append(preparar(f_eco, "Comercio"))
if f_pol: data.append(preparar(f_pol, "Policial"))

if not data:
    st.info("Suba al menos un archivo.")
    st.stop()

base = pd.concat(data)
agg = base.groupby(["_Tipo","_Canton","_Distrito"]).size().reset_index(name="Contabilizado")

cantones = sorted(agg["_Canton"].unique())
sel_canton = st.sidebar.selectbox("Cantón", cantones)

res = agg[agg["_Canton"] == sel_canton]

distritos = sorted(res["_Distrito"].unique())

# -------------------------
# CONSTRUIR TABLA COMPLETA
# -------------------------
rows = []
for d in distritos:
    for tipo in ["Comunidad","Comercio","Policial"]:
        count = res[(res["_Distrito"]==d) & (res["_Tipo"]==tipo)]["Contabilizado"].sum()
        meta = meta_map[tipo]
        pendiente = max(meta - count, 0)
        avance = (count/meta)*100 if meta else 0
        rows.append([d, tipo, meta, count, avance, pendiente])

df_full = pd.DataFrame(rows, columns=["Distrito","Tipo","Meta","Contabilizado","% Avance","Pendiente"])

# -------------------------
# RENDER HTML
# -------------------------
tbody = ""
for d in distritos:
    tbody += f'<tr class="section-row"><td colspan="6">{safe_html(d)}</td></tr>'
    sub = df_full[df_full["Distrito"]==d]
    for _, r in sub.iterrows():
        tbody += f"""
        <tr>
            <td><b>{r['Tipo']}</b></td>
            <td>{d}</td>
            <td class="meta">{int(r['Meta'])}</td>
            <td class="meta">{int(r['Contabilizado'])}</td>
            <td class="pct">{fmt_pct(r['% Avance'])}</td>
            <td class="pending">{int(r['Pendiente'])}</td>
        </tr>
        """

html_doc = f"""
<style>
.wrap {{ width:900px; margin:auto; font-family:sans-serif; }}
.title {{ text-align:center; font-size:36px; font-weight:900; }}
.subtitle {{ text-align:center; font-size:18px; font-weight:700; margin-bottom:10px; }}
.tbl {{ width:100%; border-collapse:collapse; }}
.tbl th,.tbl td {{ border-bottom:1px solid #ddd; padding:8px; }}
.tbl thead th {{ background:#e6e6e6; font-weight:900; }}
.section-row td {{ background:#d9d9d9; font-weight:900; }}
.meta {{ text-align:center; font-weight:800; }}
.pct {{ background:#29a36a; text-align:center; font-weight:900; }}
.pending {{ background:#6d8fc9; text-align:center; font-weight:900; }}
.footer {{ text-align:center; margin-top:10px; font-size:14px; }}
</style>

<div class="wrap">
<div class="title">Seguimiento de Encuestas</div>
<div class="subtitle">{sel_canton}</div>

<table class="tbl">
<thead>
<tr>
<th>Tipo</th>
<th>Distrito</th>
<th>Meta</th>
<th>Contabilizado</th>
<th>% Avance</th>
<th>Pendiente</th>
</tr>
</thead>
<tbody>
{tbody}
</tbody>
</table>

<div class="footer">
<div>{fecha_txt}</div>
<div><b>Hora del corte:</b> {hora_manual if hora_manual else "—"}</div>
</div>
</div>
"""

components.html(html_doc, height=1200, scrolling=True)

# -------------------------
# DESCARGAR IMAGEN
# -------------------------
def export_png():
    fig, ax = plt.subplots(figsize=(14, len(df_full)*0.35+3))
    ax.axis("off")
    ax.set_title(f"Seguimiento de Encuestas - {sel_canton}", fontsize=16, fontweight="bold")

    table_data = df_full.copy()
    table_data["% Avance"] = table_data["% Avance"].apply(lambda x: f"{x:.0f}%")
    table_data = table_data[["Distrito","Tipo","Meta","Contabilizado","% Avance","Pendiente"]]

    table = ax.table(cellText=table_data.values,
                     colLabels=table_data.columns,
                     loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1,1.4)

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()

png = export_png()

st.download_button(
    "📷 Descargar como imagen PNG",
    data=png,
    file_name=f"seguimiento_{sel_canton}.png",
    mime="image/png",
    use_container_width=True
)


