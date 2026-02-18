# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Dashboard de Encuestas", layout="centered")

# =========================
# Utilidades
# =========================
def norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s

def safe_html(x) -> str:
    return html.escape("" if x is None else str(x))

def pick_col(cols, candidates):
    cols_map = {norm(c): c for c in cols}
    for cand in candidates:
        if norm(cand) in cols_map:
            return cols_map[norm(cand)]
    return None

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
# Catálogo base (Pérez Zeledón)
# =========================
BASE_CATALOGO = {
    "perez zeledon": [
        "San Isidro de El General", "El General", "Daniel Flores", "Rivas", "San Pedro",
        "Platanares", "Pejibaye", "Cajón", "Barú", "Río Nuevo", "Páramo", "La Amistad",
    ]
}

def build_catalog_from_upload(file) -> dict:
    if file is None:
        return {}
    name = getattr(file, "name", "").lower()
    if name.endswith(".csv"):
        cat = pd.read_csv(file)
    else:
        cat = pd.read_excel(file, sheet_name=0)

    cols = list(cat.columns)
    col_canton = pick_col(cols, ["Canton", "Cantón"])
    col_distrito = pick_col(cols, ["Distrito", "District"])
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

def ubicar_distrito(canton: str, texto: str, catalog: dict) -> str | None:
    c = norm(canton)
    t = norm(texto)
    distritos = catalog.get(c, [])
    if not distritos:
        return None

    # exacto
    for d in distritos:
        if norm(d) == t:
            return d

    # contiene
    for d in distritos:
        nd = norm(d)
        if nd and nd in t:
            return d

    return None

# =========================
# Detección de distrito (CLAVE: vuelve el método bueno)
# =========================
def infer_district_from_block(df: pd.DataFrame, distrito_col: str, valid_districts_norm: set) -> pd.Series:
    """
    Survey123: a veces exporta una columna 'Distrito' (código) y luego muchas columnas con nombres de distritos
    (Barú, Cajón, Daniel Flores...) donde solo una queda marcada/no vacía.
    Esta función:
      - Toma el rango de columnas después de 'Distrito'
      - Si esas columnas se parecen a distritos del catálogo (overlap mínimo), entonces:
          Devuelve el NOMBRE DE LA COLUMNA que está marcada en cada fila (ese es el distrito real)
      - Si no se parecen, retorna None (no inventa).
    """
    cols = list(df.columns)
    if distrito_col not in cols:
        return pd.Series([None] * len(df), index=df.index)

    start = cols.index(distrito_col) + 1
    end_marker = pick_col(cols, ["Edad", "Genero", "Género", "Escolaridad", "Ocupacion", "Ocupación"])
    end = cols.index(end_marker) if end_marker in cols else min(start + 45, len(cols))
    block_cols = cols[start:end]
    if not block_cols:
        return pd.Series([None] * len(df), index=df.index)

    # overlap con catálogo para confirmar que ese bloque SÍ son distritos
    block_norm = {norm(c) for c in block_cols}
    overlap = len(block_norm.intersection(valid_districts_norm))
    # Si hay al menos 3 coincidencias, asumimos que sí es bloque de distritos
    if overlap < 3:
        return pd.Series([None] * len(df), index=df.index)

    def first_marked_col(row):
        for c in block_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                # En estos exports, el distrito real suele estar en el NOMBRE de la columna
                return str(c).strip()
        return None

    return df.apply(first_marked_col, axis=1)

def choose_district_col(cols):
    """
    Prioriza columnas que suelen traer el NOMBRE del distrito.
    """
    preferred = [
        "distrito_label", "district_label", "nombre distrito", "distrito_nombre",
        "distrito (label)", "distrito (texto)", "distrito", "district"
    ]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    # fallback: cualquier cosa que contenga 'distrito'
    for c in cols:
        if "distrito" in norm(c) or "district" in norm(c):
            return c
    return None

# =========================
# CSS Dashboard (visible)
# =========================
CSS = """
<style>
body { font-family: sans-serif; }
.page-wrap { width: 720px; margin: 0 auto; }
.title { text-align:center; font-size:42px; font-weight:800; margin: 8px 0 10px 0; }
.subtitle { text-align:center; font-size:18px; font-weight:700; margin-top:-4px; margin-bottom:12px; color:#333; }
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
</style>
"""

# =========================
# Sidebar
# =========================
st.sidebar.header("📥 Carga (Excels separados)")
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
ver_no_identificados = st.sidebar.checkbox("Mostrar NO_IDENTIFICADO en selector", value=False)

# Fecha automática en español
hoy = dt.date.today()
dias = {"Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves","Friday":"viernes","Saturday":"sábado","Sunday":"domingo"}
meses = {"January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio","July":"julio","August":"agosto",
         "September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"}
fecha_txt = hoy.strftime("%A, %d de %B de %Y")
fecha_txt = fecha_txt.replace(hoy.strftime("%A"), dias.get(hoy.strftime("%A"), hoy.strftime("%A")))
fecha_txt = fecha_txt.replace(hoy.strftime("%B"), meses.get(hoy.strftime("%B"), hoy.strftime("%B")))

# Catálogo final
catalog = dict(BASE_CATALOGO)
if cat_file is not None:
    try:
        uploaded_catalog = build_catalog_from_upload(cat_file)
        for k, v in uploaded_catalog.items():
            catalog[k] = v
        st.sidebar.success("Catálogo cargado ✅")
    except Exception as e:
        st.sidebar.error(f"Catálogo inválido: {e}")

meta_map = {"Comunidad": int(meta_comunidad), "Comercio": int(meta_comercio), "Policial": int(meta_policial)}
tipos_order = ["Comunidad", "Comercio", "Policial"]

# =========================
# Preparar archivo (con BLOQUE + fallback)
# =========================
def prep_file(file, tipo_label):
    df = read_any_excel(file)
    cols = list(df.columns)

    col_canton = pick_col(cols, ["Cantón", "Canton"])
    if not col_canton:
        raise ValueError(f"[{tipo_label}] No encontré columna Cantón/Canton.")

    col_distrito = choose_district_col(cols)
    if not col_distrito:
        raise ValueError(f"[{tipo_label}] No encontré columna de Distrito.")

    df["_Tipo_"] = tipo_label
    df["_Canton_"] = df[col_canton].astype(str).str.strip()

    # Cantón más frecuente para decidir catálogo y detectar bloque
    canton_mode = df["_Canton_"].mode().iloc[0] if len(df) else ""
    valid_norm = {norm(x) for x in catalog.get(norm(canton_mode), [])}

    # 1) Intento “bueno”: inferir por bloque (si aplica)
    inferred_block = infer_district_from_block(df, col_distrito, valid_norm) if valid_norm else pd.Series([None]*len(df), index=df.index)

    # 2) Fallback: usar la columna distrito directa
    distrito_directo = df[col_distrito].astype(str).str.strip()

    df["_DistritoCand_"] = inferred_block.where(inferred_block.notna(), distrito_directo)

    # 3) Mapeo contra catálogo si existe
    def resolver(row):
        canton = row["_Canton_"]
        cand = row["_DistritoCand_"]
        if cand is None:
            return None
        cand = str(cand).strip()
        if cand == "" or cand.lower() in ("nan", "none"):
            return None

        ckey = norm(canton)
        if ckey not in catalog:
            return cand  # no hay catálogo, dejamos el texto
        mapped = ubicar_distrito(canton, cand, catalog)
        return mapped if mapped else "NO_IDENTIFICADO"

    df["_Distrito_"] = df.apply(resolver, axis=1)

    df = df.replace({"nan": None, "None": None, "": None}).dropna(subset=["_Canton_", "_Distrito_"])
    return df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(columns={"_Tipo_":"Tipo", "_Canton_":"Cantón", "_Distrito_":"Distrito"})

# Leer los archivos cargados
data, errs = [], []
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
    st.error("Errores:\n\n- " + "\n- ".join(errs))
    st.stop()
if not data:
    st.info("Subí al menos 1 Excel.")
    st.stop()

base = pd.concat(data, ignore_index=True)
agg = base.groupby(["Tipo","Cantón","Distrito"]).size().reset_index(name="Contabilizado")

# =========================
# Selector cantón/distrito
# =========================
st.sidebar.divider()
st.sidebar.header("📍 Selección")
cantones = sorted(agg["Cantón"].unique().tolist())
sel_canton = st.sidebar.selectbox("Cantón", cantones, index=0)

d_all = agg.loc[agg["Cantón"] == sel_canton, "Distrito"].unique().tolist()
if not ver_no_identificados:
    d_all = [d for d in d_all if d != "NO_IDENTIFICADO"]
distritos = sorted(d_all)
sel_distrito = st.sidebar.selectbox("Distrito", distritos, index=0)

# =========================
# Desglose por distritos (restaurado)
# =========================
st.subheader(f"📌 Desglose por distritos — {sel_canton}")

resumen = agg[agg["Cantón"] == sel_canton].copy()
resumen_pivot = resumen.pivot_table(
    index=["Distrito"],
    columns="Tipo",
    values="Contabilizado",
    aggfunc="sum",
    fill_value=0
).reset_index()

for t in tipos_order:
    if t not in resumen_pivot.columns:
        resumen_pivot[t] = 0

resumen_pivot["Total"] = resumen_pivot["Comunidad"] + resumen_pivot["Comercio"] + resumen_pivot["Policial"]
st.dataframe(resumen_pivot.sort_values("Total", ascending=False), use_container_width=True, hide_index=True)

ni_total = int(resumen.loc[resumen["Distrito"] == "NO_IDENTIFICADO", "Contabilizado"].sum())
if ni_total > 0:
    st.warning(f"⚠️ Hay {ni_total} registros en NO_IDENTIFICADO (normalmente vienen como barrio/sector o columna incorrecta).")

st.divider()

# =========================
# Dashboard (1 distrito) visible
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

rows_html = ""
for _, r in rep.iterrows():
    rows_html += f"""
    <tr class="section-row"><td colspan="6">{safe_html(r['Tipo'])}</td></tr>
    <tr>
      <td></td>
      <td>{safe_html(r['Distrito'])}</td>
      <td class="meta">{int(r['Meta'])}</td>
      <td class="count">{int(r['Contabilizado'])}</td>
      <td class="pct">{safe_html(fmt_pct(r['% Avance']))}</td>
      <td class="pending">{int(r['Pendiente'])}</td>
    </tr>
    """

dashboard_html = f"""
<!doctype html>
<html>
<head>{CSS}</head>
<body>
  <div class="page-wrap">
    <div class="title">{safe_html(sel_distrito)}</div>
    <div class="subtitle">{safe_html(sel_canton)}</div>

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
          {rows_html}
        </tbody>
      </table>
    </div>

    <div class="footer">
      <div class="small">{safe_html(fecha_txt)}</div>
      <div class="small" style="margin-top:6px;"><b>Hora del corte:</b> {safe_html(hora_manual) if hora_manual else "—"}</div>
      <div class="reminder">
        Recordatorio: Al alcanzar la meta de las encuestas, se debe realizar un oficio dirigido a la Comisionada Hannia Cubillo,
        indicando que se ha alcanzado la meta. Dicho oficio se deberá subir a la carpeta compartida de Sembremos Seguridad,
        propiamente a la denominada "Recolección".
      </div>
    </div>
  </div>
</body>
</html>
"""
components.html(dashboard_html, height=760, scrolling=False)

# =========================
# Descarga
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
