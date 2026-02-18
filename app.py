# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Dashboard de Encuestas", layout="centered")

# -------------------------
# Utilidades
# -------------------------
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

# -------------------------
# Catálogo base (Pérez Zeledón)
# -------------------------
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
    for d in distritos:
        if norm(d) == t:
            return d
    for d in distritos:
        nd = norm(d)
        if nd and nd in t:
            return d
    return None

# -------------------------
# Detección por bloque Survey123
# -------------------------
def infer_district_from_block(df: pd.DataFrame, distrito_col: str, valid_districts_norm: set) -> pd.Series:
    cols = list(df.columns)
    if distrito_col not in cols:
        return pd.Series([None] * len(df), index=df.index)

    start = cols.index(distrito_col) + 1
    end_marker = pick_col(cols, ["Edad", "Genero", "Género", "Escolaridad", "Ocupacion", "Ocupación"])
    end = cols.index(end_marker) if end_marker in cols else min(start + 45, len(cols))
    block_cols = cols[start:end]
    if not block_cols:
        return pd.Series([None] * len(df), index=df.index)

    block_norm = {norm(c) for c in block_cols}
    overlap = len(block_norm.intersection(valid_districts_norm))
    if overlap < 3:
        return pd.Series([None] * len(df), index=df.index)

    def first_marked_col(row):
        for c in block_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                return str(c).strip()
        return None

    return df.apply(first_marked_col, axis=1)

def choose_district_col(cols):
    preferred = [
        "distrito_label", "district_label", "nombre distrito", "distrito_nombre",
        "distrito (label)", "distrito (texto)", "distrito", "district"
    ]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    for c in cols:
        if "distrito" in norm(c) or "district" in norm(c):
            return c
    return None

# -------------------------
# CSS (un solo cuadro)
# -------------------------
CSS = """
<style>
body { font-family: sans-serif; }
.wrap { width: 920px; margin: 0 auto; }
.h1 { text-align:center; font-size:40px; font-weight:900; margin: 10px 0 4px 0; }
.h2 { text-align:center; font-size:18px; font-weight:800; margin: 0 0 14px 0; color:#333; }

.card { border: 1px solid #cfcfcf; border-radius: 6px; overflow: hidden; background: #ffffff; }
.tbl { width:100%; border-collapse: collapse; font-size: 13.5px; }
.tbl th, .tbl td { border-bottom: 1px solid #d9d9d9; padding: 9px 10px; }
.tbl thead th { background: #e6e6e6; text-align: left; font-weight: 900; }
.section-row td { background: #d9d9d9; font-weight: 900; border-bottom: 0; padding: 9px 10px; }

.meta, .count { text-align:center; font-weight: 800; }
.pct { background: #29a36a; color: #000; font-weight: 900; text-align: center; border-left: 3px solid #ffffff; border-right: 3px solid #ffffff; }
.pending { background: #6d8fc9; color: #000; font-weight: 900; text-align: center; border-left: 3px solid #ffffff; }

.footer { text-align:center; margin-top: 12px; font-size: 13px; }
.small { font-size: 13px; }
.reminder { margin-top: 16px; font-size: 12.5px; font-weight: 900; }
</style>
"""

# -------------------------
# Sidebar
# -------------------------
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
incluir_no_identificado = st.sidebar.checkbox("Incluir NO_IDENTIFICADO", value=False)

# Fecha automática
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

# -------------------------
# Preparar archivo
# -------------------------
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

    canton_mode = df["_Canton_"].mode().iloc[0] if len(df) else ""
    valid_norm = {norm(x) for x in catalog.get(norm(canton_mode), [])}

    inferred_block = infer_district_from_block(df, col_distrito, valid_norm) if valid_norm else pd.Series([None]*len(df), index=df.index)
    distrito_directo = df[col_distrito].astype(str).str.strip()
    df["_DistritoCand_"] = inferred_block.where(inferred_block.notna(), distrito_directo)

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
            return cand
        mapped = ubicar_distrito(canton, cand, catalog)
        return mapped if mapped else "NO_IDENTIFICADO"

    df["_Distrito_"] = df.apply(resolver, axis=1)
    df = df.replace({"nan": None, "None": None, "": None}).dropna(subset=["_Canton_", "_Distrito_"])
    return df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(columns={"_Tipo_":"Tipo", "_Canton_":"Cantón", "_Distrito_":"Distrito"})

# Leer archivos
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

# Cantón elegido (para hacer un solo cuadro por cantón)
cantones = sorted(agg["Cantón"].unique().tolist())
sel_canton = st.sidebar.selectbox("Cantón para el cuadro", cantones, index=0)

resumen = agg[agg["Cantón"] == sel_canton].copy()

# Lista de distritos (ordenados por total desc)
totales = (resumen.groupby("Distrito")["Contabilizado"].sum()).to_dict()
distritos = sorted(resumen["Distrito"].unique().tolist(), key=lambda d: totales.get(d, 0), reverse=True)
if not incluir_no_identificado:
    distritos = [d for d in distritos if d != "NO_IDENTIFICADO"]

# Construir una fila por (Distrito, Tipo)
rows = []
for d in distritos:
    for t in tipos_order:
        cnt = int(resumen[(resumen["Distrito"] == d) & (resumen["Tipo"] == t)]["Contabilizado"].sum())
        meta = meta_map[t]
        pendiente = max(meta - cnt, 0)
        avance = (cnt / meta * 100) if meta else 0
        rows.append({
            "Distrito": d, "Tipo": t, "Meta": meta, "Contabilizado": cnt,
            "% Avance": avance, "Pendiente": pendiente
        })

df_full = pd.DataFrame(rows)

# -------------------------
# Render: UN SOLO CUADRO (HTML)
# -------------------------
tbody = ""
for d in distritos:
    tbody += f'<tr class="section-row"><td colspan="6">{safe_html(d)}</td></tr>'
    sub = df_full[df_full["Distrito"] == d]
    for t in tipos_order:
        r = sub[sub["Tipo"] == t].iloc[0]
        tbody += f"""
        <tr>
          <td><b>{safe_html(t)}</b></td>
          <td>{safe_html(d)}</td>
          <td class="meta">{int(r['Meta'])}</td>
          <td class="count">{int(r['Contabilizado'])}</td>
          <td class="pct">{safe_html(fmt_pct(r['% Avance']))}</td>
          <td class="pending">{int(r['Pendiente'])}</td>
        </tr>
        """

html_doc = f"""
<!doctype html>
<html>
<head>{CSS}</head>
<body>
  <div class="wrap">
    <div class="h1">Seguimiento de encuestas</div>
    <div class="h2">{safe_html(sel_canton)}</div>

    <div class="card">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width:18%">Tipo</th>
            <th style="width:28%">Distrito</th>
            <th style="width:12%; text-align:center;">Meta</th>
            <th style="width:14%; text-align:center;">Contabilizado</th>
            <th style="width:14%; text-align:center;">% Avance</th>
            <th style="width:14%; text-align:center;">Pendiente</th>
          </tr>
        </thead>
        <tbody>
          {tbody}
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

# altura dinámica (3 filas por distrito + 1 encabezado por distrito)
height = min(300 + len(distritos) * 135, 2400)
components.html(html_doc, height=height, scrolling=True)

# -------------------------
# Descarga
# -------------------------
st.divider()
st.subheader("⬇️ Descargar seguimiento completo")

detalle = agg.copy()
detalle["Meta"] = detalle["Tipo"].map({"Comunidad": meta_map["Comunidad"], "Comercio": meta_map["Comercio"], "Policial": meta_map["Policial"]}).astype(int)
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
