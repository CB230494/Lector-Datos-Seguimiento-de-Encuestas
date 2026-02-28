# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import matplotlib.pyplot as plt

st.set_page_config(page_title="Seguimiento de Encuestas", layout="centered")

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

def fecha_es(dtobj: dt.date) -> str:
    dias = {"Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves","Friday":"viernes","Saturday":"sábado","Sunday":"domingo"}
    meses = {"January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio","July":"julio","August":"agosto",
             "September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"}
    f = dtobj.strftime("%A, %d de %B de %Y")
    f = f.replace(dtobj.strftime("%A"), dias.get(dtobj.strftime("%A"), dtobj.strftime("%A")))
    f = f.replace(dtobj.strftime("%B"), meses.get(dtobj.strftime("%B"), dtobj.strftime("%B")))
    return f

# =========================
# Catálogo oficial Cantón → Distritos (SNIT / DTA)
# =========================
DTA_SNT_URL = "https://files.snitcr.go.cr/boletines/DTA-TABLA%20POR%20PROVINCIA-CANT%C3%93N-DISTRITO%202022V3.xlsx"

@st.cache_data(show_spinner=False)
def load_catalog_from_dta_url(url: str) -> dict:
    """
    Intenta cargar el catálogo oficial (Cantón->Distritos) desde el Excel DTA (SNIT).
    Devuelve dict con llave norm(cantón) y lista de distritos (texto original).
    """
    df = pd.read_excel(url, sheet_name=0)
    cols = list(df.columns)
    col_canton = pick_col(cols, ["CANTON", "CANTÓN", "Cantón", "Canton"])
    col_distrito = pick_col(cols, ["DISTRITO", "Distrito", "District"])
    if not col_canton or not col_distrito:
        # si cambia el formato, intentamos búsqueda por contiene
        for c in cols:
            if "canton" in norm(c) or "cantón" in norm(c):
                col_canton = c
            if "distrito" in norm(c) or "district" in norm(c):
                col_distrito = c
    if not col_canton or not col_distrito:
        raise ValueError("No se detectaron columnas Cantón/Distrito en el DTA.")

    df = df[[col_canton, col_distrito]].copy()
    df[col_canton] = df[col_canton].astype(str).str.strip()
    df[col_distrito] = df[col_distrito].astype(str).str.strip()
    df = df.replace({"nan": None, "None": None, "": None}).dropna()

    out = {}
    for c, g in df.groupby(col_canton):
        out[norm(c)] = sorted(g[col_distrito].unique().tolist(), key=lambda x: norm(x))
    return out

# =========================
# Catálogo base (fallback mínimo)
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
        out[norm(c)] = sorted(g[col_distrito].unique().tolist(), key=lambda x: norm(x))
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
# Detección “BUENA” de Survey123 (por bloque)
# =========================
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

    # validar que el bloque realmente parece ser “distritos”
    block_norm = {norm(c) for c in block_cols}
    overlap = len(block_norm.intersection(valid_districts_norm))
    if overlap < 3:
        return pd.Series([None] * len(df), index=df.index)

    def first_marked_col(row):
        for c in block_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                return str(c).strip()  # el nombre de la columna es el distrito real
        return None

    return df.apply(first_marked_col, axis=1)

def choose_district_col(cols):
    preferred = [
        "distrito_label", "district_label", "nombre distrito", "distrito_nombre",
        "distrito (label)", "distrito (texto)", "distrito", "district", "2. Distrito:", "2. Distrito"
    ]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    for c in cols:
        if "distrito" in norm(c) or "district" in norm(c):
            return c
    return None

def choose_canton_col(cols):
    preferred = ["cantón", "canton", "1. Cantón:", "1. Canton:", "1. Cantón", "1. Canton"]
    for p in preferred:
        found = pick_col(cols, [p])
        if found:
            return found
    for c in cols:
        if "canton" in norm(c) or "cantón" in norm(c):
            return c
    return None

def infer_canton_from_survey_title(cols) -> str | None:
    """
    Si no hay columna Cantón, intenta inferirlo desde columnas tipo:
    'Encuesta comunidad – Alajuela Sur' / 'Encuesta policial – Alajuela Norte'
    """
    for c in cols:
        nc = str(c)
        if "encuesta" in norm(nc) and ("–" in nc or "-" in nc):
            # parte después del guion largo (–) o normal (-)
            if "–" in nc:
                parts = nc.split("–", 1)
            else:
                parts = nc.split("-", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None

# =========================
# Consentimiento Sí/No
# =========================
def choose_consent_col(cols):
    # En tus 3 excels viene exactamente así:
    # "¿Acepta participar en esta encuesta?"
    preferred = [
        "¿Acepta participar en esta encuesta?",
        "Acepta participar en esta encuesta",
        "Consentimiento",
        "Consentimiento informado",
        "¿Acepta participar?",
        "Acepta participar"
    ]
    found = pick_col(cols, preferred)
    if found:
        return found

    # fallback: buscar cualquier columna que contenga "acepta" y "particip"
    for c in cols:
        nc = norm(c)
        if "acepta" in nc and "particip" in nc:
            return c
    return None

def is_yes(v) -> bool:
    nv = norm(v)
    return nv in ("si", "sí", "s i", "s\u00ed")

def is_no(v) -> bool:
    nv = norm(v)
    return nv == "no"

# =========================
# CSS (un solo cuadro)
# =========================
CSS = """
<style>
body { font-family: sans-serif; }
.wrap { width: 920px; margin: 0 auto; }
.h1 { text-align:center; font-size:44px; font-weight:900; margin: 10px 0 4px 0; }
.h2 { text-align:center; font-size:18px; font-weight:800; margin: 0 0 14px 0; color:#333; }

.card { border: 1px solid #cfcfcf; border-radius: 6px; overflow: hidden; background: #ffffff; }
.tbl { width:100%; border-collapse: collapse; font-size: 13.5px; }
.tbl th, .tbl td { border-bottom: 1px solid #d9d9d9; padding: 9px 10px; }
.tbl thead th { background: #e6e6e6; text-align: left; font-weight: 900; }
.section-row td { background: #d9d9d9; font-weight: 900; border-bottom: 0; padding: 9px 10px; }

.meta, .count { text-align:center; font-weight: 800; }
.pct { background: #29a36a; color: #000; font-weight: 900; text-align: center; border-left: 3px solid #ffffff; border-right: 3px solid #ffffff; }
.pending { background: #6d8fc9; color: #000; font-weight: 900; text-align: center; border-left: 3px solid #ffffff; }

.footer { text-align:center; margin-top: 10px; font-size: 13px; }
.smallbox { border:1px solid #d9d9d9; border-radius:6px; padding:10px; background:#fafafa; }
</style>
"""

# =========================
# Imagen PNG del cuadro
# =========================
def build_table_image_png(sel_canton: str, distritos: list, df_full: pd.DataFrame, tipos_order: list,
                          fecha_txt: str, hora_manual: str) -> bytes:
    headers = ["Tipo", "Distrito", "Meta", "Contabilizado", "% Avance", "Pendiente"]

    rows = []
    row_kind = []
    for d in distritos:
        rows.append(["", d, "", "", "", ""])  # sección
        row_kind.append("section")
        sub = df_full[df_full["Distrito"] == d]
        for t in tipos_order:
            r = sub[sub["Tipo"] == t].iloc[0]
            rows.append([
                t, d,
                str(int(r["Meta"])),
                str(int(r["Contabilizado"])),
                fmt_pct(r["% Avance"]),
                str(int(r["Pendiente"]))
            ])
            row_kind.append("data")

    nrows = len(rows) + 1
    fig_w = 14.5
    fig_h = max(4.5, nrows * 0.28)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.axis("off")

    ax.set_title(f"Seguimiento de Encuestas\n{sel_canton}", fontsize=18, fontweight="bold", pad=18)

    table = ax.table(cellText=rows, colLabels=headers, loc="upper center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.35)

    header_bg = "#e6e6e6"
    section_bg = "#d9d9d9"
    pct_bg = "#29a36a"
    pending_bg = "#6d8fc9"
    white = "#ffffff"

    col_widths = [0.15, 0.30, 0.12, 0.14, 0.14, 0.15]
    for col, w in enumerate(col_widths):
        for r in range(nrows):
            table[r, col].set_width(w)

    for c in range(len(headers)):
        cell = table[0, c]
        cell.set_facecolor(header_bg)
        cell.set_text_props(weight="bold")
        cell.set_edgecolor("#d9d9d9")

    for i, kind in enumerate(row_kind, start=1):
        if kind == "section":
            for c in range(len(headers)):
                cell = table[i, c]
                cell.set_facecolor(section_bg)
                cell.set_edgecolor(white)
                if c == 1:
                    cell.set_text_props(weight="bold")
                else:
                    cell.get_text().set_text("")
        else:
            for c in range(len(headers)):
                cell = table[i, c]
                cell.set_edgecolor("#d9d9d9")
                if c in (2, 3, 4, 5):
                    cell._loc = "center"
                    cell.get_text().set_ha("center")
                    cell.get_text().set_fontweight("bold")
                if c == 4:
                    cell.set_facecolor(pct_bg)
                elif c == 5:
                    cell.set_facecolor(pending_bg)
                else:
                    cell.set_facecolor(white)
                if c == 0:
                    cell.set_text_props(weight="bold")

    footer = f"{fecha_txt}  |  Hora del corte: {hora_manual if hora_manual else '—'}"
    fig.text(0.5, 0.01, footer, ha="center", va="bottom", fontsize=10)

    out = io.BytesIO()
    plt.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()

# =========================
# Sidebar
# =========================
st.sidebar.header("📥 Carga (Excels separados)")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx", "xls"], key="f_com")
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx", "xls"], key="f_eco")
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx", "xls"], key="f_pol")

st.sidebar.divider()
st.sidebar.header("🗂️ Catálogo Cantón → Distritos")
use_official = st.sidebar.checkbox("Usar catálogo oficial (DTA SNIT) por defecto", value=True)

cat_file = st.sidebar.file_uploader("O subir catálogo manual (CSV/XLSX)", type=["csv", "xlsx", "xls"], key="cat")

st.sidebar.divider()
st.sidebar.header("🎯 Metas")
meta_comunidad = st.sidebar.number_input("Meta Comunidad", min_value=1, value=375, step=1)
meta_comercio  = st.sidebar.number_input("Meta Comercio",  min_value=1, value=210, step=1)
meta_policial  = st.sidebar.number_input("Meta Policial",  min_value=1, value=90,  step=1)

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")
incluir_no_identificado = st.sidebar.checkbox("Incluir NO_IDENTIFICADO", value=False)

meta_map = {"Comunidad": int(meta_comunidad), "Comercio": int(meta_comercio), "Policial": int(meta_policial)}
tipos_order = ["Comunidad", "Comercio", "Policial"]

fecha_txt = fecha_es(dt.date.today())

# =========================
# Construir catálogo final
# =========================
catalog = dict(BASE_CATALOGO)

if use_official:
    try:
        official = load_catalog_from_dta_url(DTA_SNT_URL)
        catalog.update(official)
        st.sidebar.success("Catálogo oficial DTA cargado ✅")
    except Exception as e:
        st.sidebar.warning(f"No se pudo cargar DTA oficial (se usa fallback). Detalle: {e}")

if cat_file is not None:
    try:
        uploaded_catalog = build_catalog_from_upload(cat_file)
        catalog.update(uploaded_catalog)
        st.sidebar.success("Catálogo manual cargado ✅")
    except Exception as e:
        st.sidebar.error(f"Catálogo inválido: {e}")

# =========================
# Preparar archivo (Consentimiento + BLOQUE + fallback)
# =========================
def prep_file(file, tipo_label):
    df = read_any_excel(file)
    cols = list(df.columns)

    # ---- Consentimiento (Sí/No) ----
    col_consent = choose_consent_col(cols)
    if not col_consent:
        raise ValueError(f"[{tipo_label}] No encontré la columna de consentimiento (¿Acepta participar...?).")

    # Conteo Sí/No
    consent_series = df[col_consent].astype(str).map(lambda x: norm(x))
    n_si = int((consent_series == "si").sum())
    n_no = int((consent_series == "no").sum())
    n_total = int(len(df))

    # Filtrar SOLO los "SI" para contabilizar avance
    df = df[consent_series == "si"].copy()

    # ---- Cantón ----
    col_canton = choose_canton_col(cols)
    if col_canton:
        df["_Canton_"] = df[col_canton].astype(str).str.strip()
    else:
        # fallback por título de encuesta si no viene pregunta Cantón (pasa en Policial)
        inferred = infer_canton_from_survey_title(cols)
        if not inferred:
            raise ValueError(f"[{tipo_label}] No encontré columna Cantón ni pude inferir cantón desde el título de la encuesta.")
        df["_Canton_"] = inferred

    # ---- Distrito ----
    if tipo_label == "Policial":
        # en policial NO hay distritos: lo dejamos fijo
        df["_Distrito_"] = "SIN_DISTRITO"
    else:
        col_distrito = choose_district_col(cols)
        if not col_distrito:
            raise ValueError(f"[{tipo_label}] No encontré columna de Distrito.")

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
                return cand  # sin catálogo, dejamos el texto tal cual
            mapped = ubicar_distrito(canton, cand, catalog)
            return mapped if mapped else "NO_IDENTIFICADO"

        df["_Distrito_"] = df.apply(resolver, axis=1)

    df["_Tipo_"] = tipo_label
    df = df.replace({"nan": None, "None": None, "": None}).dropna(subset=["_Canton_", "_Distrito_"])

    out_df = df[["_Tipo_", "_Canton_", "_Distrito_"]].rename(
        columns={"_Tipo_":"Tipo", "_Canton_":"Cantón", "_Distrito_":"Distrito"}
    )

    stats = {
        "Tipo": tipo_label,
        "Total filas (Excel)": n_total,
        "Consentimiento SI": n_si,
        "Consentimiento NO": n_no,
        "Usadas (solo SI)": int(len(out_df)),
        "Col consentimiento": col_consent,
        "Cantón (col/fallback)": col_canton if col_canton else "INFERIDO (título encuesta)"
    }
    return out_df, stats

# =========================
# Leer archivos
# =========================
data, errs, stats_all = [], [], []

if f_com:
    try:
        df_ok, stt = prep_file(f_com, "Comunidad")
        data.append(df_ok); stats_all.append(stt)
    except Exception as e:
        errs.append(str(e))

if f_eco:
    try:
        df_ok, stt = prep_file(f_eco, "Comercio")
        data.append(df_ok); stats_all.append(stt)
    except Exception as e:
        errs.append(str(e))

if f_pol:
    try:
        df_ok, stt = prep_file(f_pol, "Policial")
        data.append(df_ok); stats_all.append(stt)
    except Exception as e:
        errs.append(str(e))

if errs:
    st.error("Errores:\n\n- " + "\n- ".join(errs))
    st.stop()

if not data:
    st.info("Subí al menos 1 Excel.")
    st.stop()

# =========================
# Mostrar resumen Sí/No (y recordar que NO se descartan)
# =========================
st.sidebar.divider()
st.sidebar.subheader("✅ Consentimiento (Sí/No)")
stats_df = pd.DataFrame(stats_all)
if len(stats_df):
    st.sidebar.dataframe(
        stats_df[["Tipo","Consentimiento SI","Consentimiento NO","Usadas (solo SI)"]],
        use_container_width=True,
        hide_index=True
    )
    st.sidebar.caption("Los 'NO' se muestran aquí, pero NO se contabilizan en el avance.")

# =========================
# Agregación principal (YA filtrada por SI)
# =========================
base = pd.concat(data, ignore_index=True)
agg = base.groupby(["Tipo","Cantón","Distrito"]).size().reset_index(name="Contabilizado")

# Cantón seleccionado (para el cuadro)
cantones = sorted(agg["Cantón"].unique().tolist())
sel_canton = st.sidebar.selectbox("Cantón para el cuadro", cantones, index=0)

resumen = agg[agg["Cantón"] == sel_canton].copy()

# distritos ordenados por total desc
totales = (resumen.groupby("Distrito")["Contabilizado"].sum()).to_dict()
distritos = sorted(resumen["Distrito"].unique().tolist(), key=lambda d: totales.get(d, 0), reverse=True)

if not incluir_no_identificado:
    distritos = [d for d in distritos if d != "NO_IDENTIFICADO"]

# Construir df_full (1 fila por distrito-tipo)
rows = []
for d in distritos:
    for t in tipos_order:
        cnt = int(resumen[(resumen["Distrito"] == d) & (resumen["Tipo"] == t)]["Contabilizado"].sum())
        meta = meta_map[t]
        pendiente = max(meta - cnt, 0)
        avance = (cnt / meta * 100) if meta else 0
        rows.append({"Distrito": d, "Tipo": t, "Meta": meta, "Contabilizado": cnt, "% Avance": avance, "Pendiente": pendiente})
df_full = pd.DataFrame(rows)

# =========================
# Render HTML (UN SOLO CUADRO + fecha/hora)
# =========================
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
    <div class="h1">Seguimiento de Encuestas</div>
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
      <div>{safe_html(fecha_txt)}</div>
      <div><b>Hora del corte:</b> {safe_html(hora_manual) if hora_manual else "—"}</div>
    </div>
  </div>
</body>
</html>
"""

height = min(320 + len(distritos) * 135, 2400)
components.html(html_doc, height=height, scrolling=True)

# =========================
# Descargas
# =========================
st.divider()
col1, col2 = st.columns(2)

with col1:
    png_bytes = build_table_image_png(sel_canton, distritos, df_full, tipos_order, fecha_txt, hora_manual)
    st.download_button(
        "📷 Descargar cuadro como imagen (PNG)",
        data=png_bytes,
        file_name=f"cuadro_encuestas_{sel_canton}.png".replace(" ", "_"),
        mime="image/png",
        use_container_width=True
    )

with col2:
    detalle = agg.copy()
    detalle["Meta"] = detalle["Tipo"].map(meta_map).fillna(0).astype(int)
    detalle["Pendiente"] = (detalle["Meta"] - detalle["Contabilizado"]).clip(lower=0)
    detalle["% Avance"] = (detalle["Contabilizado"] / detalle["Meta"] * 100).round(1)

    # Agregar hoja/resumen de consentimiento por tipo
    resumen_consent = pd.DataFrame(stats_all)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        detalle.sort_values(["Cantón","Distrito","Tipo"]).to_excel(writer, index=False, sheet_name="seguimiento")
        resumen_consent.to_excel(writer, index=False, sheet_name="consentimiento")
    excel_bytes = out.getvalue()

    st.download_button(
        "⬇️ Descargar seguimiento (Excel)",
        data=excel_bytes,
        file_name="seguimiento_encuestas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
