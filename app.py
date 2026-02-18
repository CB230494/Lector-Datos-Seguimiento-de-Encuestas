# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard de Encuestas", layout="centered")

# =========================
# 1) Normalización texto
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


# =========================
# 2) Catálogo base (incluye PZ completo)
#    + opción de subir catálogo para TODO CR
# =========================
BASE_CATALOGO = {
    # Cantón: Pérez Zeledón (San José)
    "perez zeledon": [
        "San Isidro de El General",
        "El General",
        "Daniel Flores",
        "Rivas",
        "San Pedro",
        "Platanares",
        "Pejibaye",
        "Cajón",
        "Barú",
        "Río Nuevo",
        "Páramo",
        "La Amistad",
    ],
    # Variantes comunes del nombre (por si viene con tilde/otros)
    "pérez zeledón": [
        "San Isidro de El General",
        "El General",
        "Daniel Flores",
        "Rivas",
        "San Pedro",
        "Platanares",
        "Pejibaye",
        "Cajón",
        "Barú",
        "Río Nuevo",
        "Páramo",
        "La Amistad",
    ],
}

def build_catalog_from_upload(file) -> dict:
    """
    Acepta catálogo en CSV/Excel con columnas:
    - Canton (o Cantón)
    - Distrito
    Devuelve dict norm(canton) -> lista de distritos (texto original).
    """
    if file is None:
        return {}

    name = getattr(file, "name", "").lower()
    if name.endswith(".csv"):
        cat = pd.read_csv(file)
    else:
        cat = pd.read_excel(file, sheet_name=0)

    cols = list(cat.columns)
    col_canton = pick_col(cols, ["Canton", "Cantón", "CANTON", "CANTÓN"])
    col_distrito = pick_col(cols, ["Distrito", "DISTRO", "District", "DISTRITO"])

    if not col_canton or not col_distrito:
        raise ValueError("El catálogo debe tener columnas Cantón/Canton y Distrito.")

    cat = cat[[col_canton, col_distrito]].copy()
    cat[col_canton] = cat[col_canton].astype(str).str.strip()
    cat[col_distrito] = cat[col_distrito].astype(str).str.strip()
    cat = cat.replace({"nan": None, "None": None, "": None}).dropna()

    out = {}
    for c, g in cat.groupby(col_canton):
        out[norm(c)] = sorted(g[col_distrito].unique().tolist())
    return out


# =========================
# 3) Detección distrito desde Survey123
# =========================
def infer_district_from_columns(df: pd.DataFrame, distrito_col: str) -> pd.Series:
    """
    Si Survey123 generó columnas por distrito (Merced, Cajón, etc.), normalmente van después de 'Distrito'.
    Tomamos la primera no vacía en un rango cercano.
    """
    cols = list(df.columns)
    if distrito_col not in cols:
        return pd.Series([None] * len(df), index=df.index)

    start = cols.index(distrito_col) + 1
    # corte típico
    end_marker = pick_col(cols, ["Edad", "Genero", "Género", "Escolaridad", "Ocupacion", "Ocupación"])
    end = cols.index(end_marker) if end_marker in cols else min(start + 35, len(cols))

    candidate_cols = cols[start:end]
    if not candidate_cols:
        return pd.Series([None] * len(df), index=df.index)

    def first_non_empty(row):
        for c in candidate_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                return str(v).strip()
        return None

    return df.apply(first_non_empty, axis=1)


def ubicar_distrito(canton: str, texto: str, catalog: dict) -> str | None:
    """
    Intenta mapear texto (puede ser barrio/sector) a un distrito válido del cantón.
    - match exacto
    - match por contención (si el texto contiene el nombre del distrito)
    """
    c = norm(canton)
    t = norm(texto)

    distritos = catalog.get(c, [])
    if not distritos:
        return None

    # exacto
    for d in distritos:
        if norm(d) == t:
            return d

    # contiene (por ejemplo "distrito: cajon" o textos largos)
    for d in distritos:
        if norm(d) and norm(d) in t:
            return d

    return None


# =========================
# 4) Excel helpers
# =========================
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


# =========================
# 5) Estilo HTML (como tu imagen)
# =========================
CSS = """
<style>
.page-wrap { width: 680px; margin: 0 auto; }
.title { text-align:center; font-size:42px; font-weight:800; margin: 8px 0 10px 0; }
.card { border: 1px solid #cfcfcf; border-radius: 6px; overflow: hidden; background: #ffffff; }
.tbl { width:100%; border-collapse: collapse; font-size: 14px; }
.tbl th, .tbl td { border-bottom: 1px solid #d9d9d9; padding: 10px 10px; }
.tbl thead th { background: #e6e6e6; text-align: left; font-weight: 800; }
.section-row td { background: #d9d9d9; font-weight: 800; border-bottom: 0; padding: 10px; }
.center { text-align:center; }
.pct { background: #29a36a; color: #000; font-weight: 800; text-align: center; border-left: 3px solid #ffffff; border-right: 3px solid #ffffff; }
.pending { background: #6d8fc9; color: #000; font-weight: 800; text-align: center; border-left: 3px solid #ffffff; }
.meta, .count { text-align:center; font-weight: 700; }
.footer { text-align:center; margin-top: 14px; font-size: 14px; }
.reminder { margin-top: 18px; font-size: 13px; font-weight: 800; }
.small { font-size: 13px; }
.badge { display:inline-block; padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight:700; background:#f2f2f2; border:1px solid #ddd; }
</style>
"""

# =========================
# UI
# =========================
st.markdown('<div class="page-wrap">', unsafe_allow_html=True)
st.markdown(CSS, unsafe_allow_html=True)

st.sidebar.header("📥 Carga (por Excel separado)")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx", "xls"], key="f_com")
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx", "xls"], key="f_eco")
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx", "xls"], key="f_pol")

st.sidebar.divider()
st.sidebar.header("🗂️ Catálogo Cantón → Distritos (opcional)")
cat_file = st.sidebar.file_uploader("Subir catálogo (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="cat")

st.sidebar.divider()
st.sidebar.header("🎯 Metas")
meta_comunidad = st.sidebar.number_input("Meta Comunidad", min_value=1, value=375, step=1)
meta_comercio  = st.sidebar.number_input("Meta Comercio",  min_value=1, value=210, step=1)
meta_policial  = st.sidebar.number_input("Meta Policial",  min_value=1, value=90,  step=1)

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")

# fecha automática en español
hoy = dt.date.today()
dias = {"Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves","Friday":"viernes","Saturday":"sábado","Sunday":"domingo"}
meses = {"January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio","July":"julio","August":"agosto",
         "September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"}
fecha_txt = hoy.strftime("%A, %d de %B de %Y")
fecha_txt = fecha_txt.replace(hoy.strftime("%A"), dias.get(hoy.strftime("%A"), hoy.strftime("%A")))
fecha_txt = fecha_txt.replace(hoy.strftime("%B"), meses.get(hoy.strftime("%B"), hoy.strftime("%B")))

# construir catálogo final
catalog = dict(BASE_CATALOGO)
if cat_file is not None:
    try:
        uploaded_catalog = build_catalog_from_upload(cat_file)
        # merge: el catálogo subido manda (override) por cantón
        for k, v in uploaded_catalog.items():
            catalog[k] = v
        st.sidebar.success("Catálogo cargado ✅")
    except Exception as e:
        st.sidebar.error(f"Catálogo inválido: {e}")

# =========================
# Preparación por archivo
# =========================
def prep_file(file, tipo_label):
    df = read_any_excel(file)
    cols = list(df.columns)

    col_canton = pick_col(cols, ["Cantón", "Canton"])
    if not col_canton:
        raise ValueError(f"[{tipo_label}] No encontré columna Cantón/Canton.")

    # Columna Distrito “base” (puede ser código o nombre)
    col_distrito = pick_col(cols, ["Distrito", "District"])
    if not col_distrito:
        # si no existe, igual intentamos por otras etiquetas frecuentes
        col_distrito = pick_col(cols, ["Nombre Distrito", "Distrito (nombre)", "distrito_nombre"])

    if not col_distrito:
        raise ValueError(f"[{tipo_label}] No encontré columna Distrito/District.")

    df["_Tipo_"] = tipo_label
    df["_Canton_"] = df[col_canton].astype(str).str.strip()

    # 1) intento directo con columna distrito
    distrito_raw = df[col_distrito].astype(str).str.strip()

    # 2) intento por columnas “por distrito” si aplica
    inferred = infer_district_from_columns(df, col_distrito)

    # prioridad: inferred (si existe) sino distrito_raw
    df["_Distrito_Candidato_"] = inferred.where(inferred.notna(), distrito_raw)

    # 3) ubicar contra catálogo (si hay catálogo para ese cantón)
    def resolver(row):
        canton = row["_Canton_"]
        cand = row["_Distrito_Candidato_"]
        if cand is None or str(cand).strip() == "" or str(cand).lower() in ("nan","none"):
            return None

        # si el cantón no está en catálogo, devolvemos el candidato (para no perder datos)
        if norm(canton) not in catalog:
            return str(cand).strip()

        mapped = ubicar_distrito(canton, cand, catalog)
        return mapped if mapped else "NO_IDENTIFICADO"

    df["_Distrito_"] = df.apply(resolver, axis=1)

    # limpieza
    df = df.replace({"nan": None, "None": None, "": None})
    df = df.dropna(subset=["_Canton_", "_Distrito_"])

    return df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(
        columns={"_Tipo_":"Tipo", "_Canton_":"Cantón", "_Distrito_":"Distrito"}
    )

data = []
errs = []
if f_com:
    try: data.append(prep_file(f_com, "Comunidad"))
    except Exception as e: errs.append(str(e))
if f_eco:
    try: data.append(prep_file(f_eco, "Comercio"))
    except Exception as e: errs.append(str(e))
if f_pol:
    try: data.append(prep_file(f_pol, "Policial"))
    except Exception as e: errs.append(str(e))

if errs:
    st.error("Errores leyendo archivos:\n\n- " + "\n- ".join(errs))
    st.stop()

if not data:
    st.info("Subí al menos 1 Excel (Comunidad/Comercio/Policial).")
    st.stop()

base = pd.concat(data, ignore_index=True)

# =========================
# Agregación y métricas
# =========================
agg = (
    base.groupby(["Tipo","Cantón","Distrito"])
        .size()
        .reset_index(name="Contabilizado")
)

meta_map = {"Comunidad": int(meta_comunidad), "Comercio": int(meta_comercio), "Policial": int(meta_policial)}
tipos_order = ["Comunidad","Comercio","Policial"]

# =========================
# Selector cantón/distrito
# =========================
st.sidebar.divider()
st.sidebar.header("📍 Selección")
cantones = sorted(agg["Cantón"].unique().tolist())
sel_canton = st.sidebar.selectbox("Cantón", cantones, index=0)

# Ocultar NO_IDENTIFICADO del selector de distrito (pero queda en resumen/descarga si querés)
distritos_all = agg.loc[agg["Cantón"] == sel_canton, "Distrito"].unique().tolist()
distritos = sorted([d for d in distritos_all if d != "NO_IDENTIFICADO"])
if not distritos:
    distritos = sorted(distritos_all)

sel_distrito = st.sidebar.selectbox("Distrito", distritos, index=0)

# =========================
# Resumen por cantón
# =========================
st.subheader(f"📌 Resumen por cantón: {sel_canton}")

resumen = agg[agg["Cantón"] == sel_canton].copy()
resumen["Meta"] = resumen["Tipo"].map(meta_map).astype(int)
resumen["Pendiente"] = (resumen["Meta"] - resumen["Contabilizado"]).clip(lower=0)
resumen["% Avance"] = (resumen["Contabilizado"] / resumen["Meta"] * 100).round(1)

pivot = resumen.pivot_table(
    index=["Cantón","Distrito"],
    columns="Tipo",
    values="Contabilizado",
    aggfunc="sum",
    fill_value=0
).reset_index()

for t in tipos_order:
    if t not in pivot.columns:
        pivot[t] = 0

pivot["Total Contabilizado"] = pivot["Comunidad"] + pivot["Comercio"] + pivot["Policial"]
pivot["Total Meta"] = meta_map["Comunidad"] + meta_map["Comercio"] + meta_map["Policial"]
pivot["% Total"] = (pivot["Total Contabilizado"] / pivot["Total Meta"] * 100).round(1)
pivot["Faltan Total"] = (pivot["Total Meta"] - pivot["Total Contabilizado"]).clip(lower=0)

st.dataframe(pivot.sort_values(["Distrito"]), use_container_width=True, hide_index=True)

st.markdown(
    f'<span class="badge">Si aparece <b>NO_IDENTIFICADO</b>, es porque el texto (p.ej. barrio/sector) no calzó con un distrito válido del catálogo.</span>',
    unsafe_allow_html=True
)

st.divider()

# =========================
# Dashboard estilo imagen
# =========================
sub = agg[(agg["Cantón"] == sel_canton) & (agg["Distrito"] == sel_distrito)].copy()

rows = []
for t in tipos_order:
    cnt = int(sub.loc[sub["Tipo"] == t, "Contabilizado"].sum()) if (sub["Tipo"] == t).any() else 0
    meta = meta_map[t]
    pendiente = max(meta - cnt, 0)
    avance = (cnt / meta * 100) if meta else 0
    rows.append({"Tipo": t, "Distrito": sel_distrito, "Meta": meta, "Contabilizado": cnt, "% Avance": avance, "Pendiente": pendiente})
rep = pd.DataFrame(rows)

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
body = []
for _, r in rep.iterrows():
    body.append(
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
st.markdown(header_html + "\n".join(body) + footer_html, unsafe_allow_html=True)

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

# =========================
# Descargas
# =========================
st.divider()
st.subheader("⬇️ Descargar seguimiento completo")

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




