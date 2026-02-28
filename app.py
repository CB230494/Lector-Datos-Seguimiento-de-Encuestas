# -*- coding: utf-8 -*-
import io
import datetime as dt
import unicodedata
import html
import difflib

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
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "—"
        return f"{float(x):.0f}%"
    except Exception:
        return "—"

def fecha_es(dtobj: dt.date) -> str:
    dias = {"Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves","Friday":"viernes","Saturday":"sábado","Sunday":"domingo"}
    meses = {"January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio","July":"julio","August":"agosto",
             "September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"}
    f = dtobj.strftime("%A, %d de %B de %Y")
    f = f.replace(dtobj.strftime("%A"), dias.get(dtobj.strftime("%A"), dtobj.strftime("%A")))
    f = f.replace(dtobj.strftime("%B"), meses.get(dtobj.strftime("%B"), dtobj.strftime("%B")))
    return f


# =========================
# Matching "inteligente" de nombres (Cantón/Delegación)
# =========================
def best_match_name(raw_name: str, canonical_names: list[str], cutoff=0.62) -> str:
    """
    Retorna el nombre canónico más parecido. Si no alcanza cutoff, devuelve el raw_name original (limpio).
    """
    raw = "" if raw_name is None else str(raw_name).strip()
    if not raw:
        return raw

    raw_n = norm(raw)
    canon_norm = {norm(c): c for c in canonical_names}

    # exacto por normalización
    if raw_n in canon_norm:
        return canon_norm[raw_n]

    # fuzzy
    matches = difflib.get_close_matches(raw_n, list(canon_norm.keys()), n=1, cutoff=cutoff)
    if matches:
        return canon_norm[matches[0]]

    return raw


# =========================
# Consentimiento (SI/NO)
# =========================
def find_consent_col(cols: list[str]) -> str | None:
    # Busca columnas típicas de consentimiento / participación
    candidates = [
        "consentimiento", "consent", "acepta", "aceptacion", "aceptación",
        "participa", "participar", "autorizacion", "autorización",
        "desea participar", "desea completar", "permite", "acuerdo"
    ]
    # match directo por "pick_col"
    c = pick_col(cols, candidates)
    if c:
        return c

    # fallback: buscar por contains
    for col in cols:
        n = norm(col)
        if any(k in n for k in ["consent", "consentimiento", "acepta", "particip", "autoriz"]):
            return col
    return None

def is_no_value(v) -> bool:
    s = norm(v)
    return s in ("no", "n", "false", "0", "rechazo", "rechaza", "no acepto", "no acepta")

def is_yes_value(v) -> bool:
    s = norm(v)
    return s in ("si", "sí", "s", "true", "1", "acepto", "acepta", "de acuerdo", "autorizo", "autorizado")

def consent_counts(df: pd.DataFrame) -> tuple[int, int, pd.Series]:
    """
    Retorna (yes_count, no_count, mask_yes)
    Si no existe columna, asume todo como YES.
    """
    col = find_consent_col(list(df.columns))
    if not col:
        mask_yes = pd.Series([True] * len(df), index=df.index)
        return len(df), 0, mask_yes

    ser = df[col]
    no_mask = ser.apply(is_no_value)
    yes_mask = ser.apply(is_yes_value)

    # Si hay valores raros: lo tratamos como YES por defecto (para no botar encuestas por texto inesperado)
    mask_yes = (~no_mask)
    yes_count = int(mask_yes.sum())
    no_count = int(no_mask.sum())
    return yes_count, no_count, mask_yes


# =========================
# Catálogo + Metas precargadas (D01..D39)
# - Comunidad: meta por distrito
# - Comercio: meta por delegación
# - Policial: SIN meta
# =========================
DELEGACIONES = [
    "Carmen", "Merced", "Hospital", "Catedral", "San Sebastian", "Hatillo", "Zapote", "Pavas", "Uruca",
    "Curridabat", "Montes de Oca", "Goicoechea", "Moravia", "Tibas", "Coronado",
    "Desamparados Norte", "Desamparados Sur", "Aserri", "Acosta", "Alajuelita", "Escazu", "Santa Ana",
    "Mora", "Puriscal", "Turrubares", "Alajuela Sur", "Alajuela Norte", "San Ramon", "Grecia",
    "San Mateo", "Atenas", "Naranjo", "Palmares", "Poas", "Orotina", "Sarchi", "Cartago", "Paraiso", "La Union"
]

# Comunidad (por distrito)
METAS_COMUNIDAD = {
    "Carmen": {"Carmen": 338},
    "Merced": {"Merced": 375},
    "Hospital": {"Hospital": 379},
    "Catedral": {"Catedral": 375},
    "San Sebastian": {"San Sebastian": 381},
    "Hatillo": {"Hatillo": 382},
    "Zapote": {"Zapote": 185, "San Francisco": 198},
    "Pavas": {"Pavas": 383},
    "Uruca": {"Uruca": 311, "Mata redonda": 71},

    "Curridabat": {"Curridabat": 147, "Granadilla": 93, "Sanchez": 33, "Tirrases": 109},
    "Montes de Oca": {"San Pedro": 168, "Sabanilla": 88, "Mercedes": 38, "San Rafael": 88},
    "Goicoechea": {"Guadalupe": 57, "San Francisco": 7, "Calle Blancos": 64, "Mata Platano": 58, "Ipis": 88, "Rancho Redondo": 9, "Purral": 100},
    "Moravia": {"San Vicente": 177, "San Jeronimo": 45, "Paracito": 17, "Trinidad": 142},
    "Tibas": {"San Juan": 109, "Cinco Esquinas": 39, "Anaselmo Llorente": 58, "Leon XIII": 95, "Colima": 82},
    "Coronado": {"San Isidro": 92, "San Rafael": 46, "Dulce Nombre": 65, "Patalillo": 133, "Cascajal": 46},
    "Desamparados Norte": {"Desamparados": 83, "Patarra": 35, "Damas": 37, "Gravilias": 40, "San Juan de Dios": 58, "San Rafael Arriba": 43, "San Rafael Abajo": 60, "San Antonio": 27},
    "Desamparados Sur": {"San Cristobal": 21, "Rosario": 17, "Los Guido": 145, "Frailes": 21, "San Miguel": 179},
    "Aserri": {"Aserri": 176, "Tarbaca": 10, "Vuelta Jorco": 44, "San Gabriel": 41, "Legua": 10, "Monterrey": 4, "Salitrillos": 96},
    "Acosta": {"San Ignacio": 157, "Guaitil": 47, "Palmichal": 92, "Cangrejal": 36, "Sabanillas": 46},
    "Alajuelita": {"Alajuelita": 49, "San Josecito": 52, "San Antonio": 24, "Concepcion": 33, "San Felipe": 165},
    "Escazu": {"Escazu": 70, "San Antonio": 154, "San Rafael": 159},
    "Santa Ana": {"Santa Ana": 75, "Salitral": 36, "Pozos": 128, "Uruca": 57, "Piedades": 65, "Brasil": 21},
    "Mora": {"Colon": 205, "Guayabo": 58, "Tabarcia": 48, "Piedras Negras": 7, "Picagres": 13, "Quitirisi": 29, "Jaris": 21},
    "Puriscal": {"Santiago": 120, "Mercedes Sur": 71, "Barbacoas": 45, "Grifo Alto": 15, "San Rafael": 20, "Candelaria": 18, "Desamparaditos": 8, "San Antonio": 47, "Chires": 36},
    "Turrubares": {"San Pablo": 78, "San Pedro": 45, "San Juan de Mata": 82, "San Luis": 38, "Carara": 122},
    "Alajuela Sur": {"Guacima": 93, "Turrucares": 31, "San Rafael": 118, "Garita": 33, "San Antonio": 109},
    "Alajuela Norte": {"Alajuela": 84, "Carrizal": 17, "San Jose": 100, "San Isidro": 43, "Sabanilla": 24, "Rio Segundo": 26, "Desamparados": 63, "Tambor": 28},
    "San Ramon": {"San Ramon": 43, "Santiago": 29, "San Juan": 67, "Piedades Norte": 49, "Piedades Sur": 23, "San Rafael": 56, "San Isidro": 30, "Angeles": 13, "Alfaro": 43, "Volio": 14, "Concepcion": 13, "Zapotal": 3},
    "Grecia": {"Grecia": 73, "San Isidro": 36, "San Jose": 50, "San Roque": 66, "Tacares": 49, "Puente de Piedra": 65, "Bolivar": 44},
    "San Mateo": {"San Mateo": 148, "Desmonte": 62, "Jesus Maria": 79, "Labrador": 77},
    "Atenas": {"Atenas": 97, "Jesus": 57, "Mercedes": 50, "San Isidro": 46, "Concepcion": 55, "San Jose": 30, "Santa Eulalia": 33, "Escobal": 13},
    "Naranjo": {"Naranjo": 128, "San Miguel": 46, "San Jose": 28, "Cirri Sur": 43, "San Jeronimo": 32, "San Juan": 29, "Rosario": 37, "Palmitos": 39},
    "Palmares": {"Palmares": 33, "Zaragoza": 91, "Buenos Aires": 81, "Santiago": 31, "Candelaria": 23, "Esquipulas": 77, "Granja": 45},
    "Poas": {"San Pedro": 85, "San Juan": 62, "San Rafael": 74, "Carrillos": 126, "Sabana Redonda": 34},
    "Orotina": {"Orotina": 158, "Mastate": 36, "Hacienda Vieja": 20, "Coyolar": 123, "Ceiba": 42},
    "Sarchi": {"Sarcho Norte": 134, "Sarchi Sur": 112, "Toro Amarillo": 7, "San Pedro": 76, "Rodriguez": 49},
    "Cartago": {"Oriental": 34, "Occidental": 30, "Carmen": 57, "San Nicolas": 88, "Aguacaliente": 107, "Tierra Blanca": 17, "Dulce Nombre": 35, "Llano Grande": 15},
    "Paraiso": {"Paraiso": 112, "Santiago": 39, "Orosi": 62, "Cachi": 36, "Llanos de Santa Lucia": 119, "Birrisito": 14},
    "La Union": {"Tres Rios": 29, "San Diego": 85, "San Juan": 53, "San Rafael": 54, "Concepcion": 65, "Dulce Nombre": 31, "San Ramon": 15, "Rio Azul": 51},
}

# Comercio (por delegación)
METAS_COMERCIO = {
    "Carmen": 201,
    "Merced": 229,
    "Hospital": 254,
    "Catedral": 226,
    "San Sebastian": 153,
    "Hatillo": 117,
    "Zapote": 226,
    "Pavas": 244,
    "Uruca": 272,

    "Curridabat": 235,
    "Montes de Oca": 261,
    "Goicoechea": 246,
    "Moravia": 184,
    "Tibas": 210,
    "Coronado": 159,
    "Desamparados Norte": 217,
    "Desamparados Sur": 93,
    "Aserri": 159,
    "Acosta": 159,
    "Alajuelita": 159,
    "Escazu": 287,
    "Santa Ana": 227,
    "Mora": 77,
    "Puriscal": 98,
    "Turrubares": 9,
    "Alajuela Sur": 219,
    "Alajuela Norte": 300,
    "San Ramon": 213,
    "Grecia": 230,
    "San Mateo": 19,
    "Atenas": 94,
    "Naranjo": 175,
    "Palmares": 124,
    "Poas": 90,
    "Orotina": 69,
    "Sarchi": 74,
    "Cartago": 282,
    "Paraiso": 120,
    "La Union": 215,
}

# Catálogo final (para Comunidad)
CATALOGO = {norm(k): sorted(list(v.keys()), key=lambda x: x.lower()) for k, v in METAS_COMUNIDAD.items()}

def ubicar_distrito(delegacion: str, texto: str) -> str | None:
    dkey = norm(delegacion)
    t = norm(texto)
    distritos = CATALOGO.get(dkey, [])
    if not distritos:
        return None

    # exacto
    for d in distritos:
        if norm(d) == t:
            return d

    # contiene
    for d in distritos:
        nd = norm(d)
        if nd and (nd in t or t in nd):
            return d

    # fuzzy
    dn = [norm(x) for x in distritos]
    matches = difflib.get_close_matches(t, dn, n=1, cutoff=0.70)
    if matches:
        idx = dn.index(matches[0])
        return distritos[idx]

    return None


# =========================
# Detección “por bloque” (si el excel viene Survey123 con columnas-distrito)
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
.smallnote { text-align:center; margin-top: 4px; font-size: 12px; color:#333; }
</style>
"""


# =========================
# Imagen PNG del cuadro
# =========================
def build_table_image_png(sel_deleg: str, distritos: list, df_full: pd.DataFrame, tipos_order: list,
                          fecha_txt: str, hora_manual: str) -> bytes:
    headers = ["Tipo", "Distrito", "Meta", "Contabilizado", "% Avance", "Pendiente", "NO (consent.)"]

    rows = []
    row_kind = []
    for d in distritos:
        rows.append(["", d, "", "", "", "", ""])
        row_kind.append("section")
        sub = df_full[df_full["Distrito"] == d]
        for t in tipos_order:
            r = sub[sub["Tipo"] == t].iloc[0]
            meta_txt = "—" if pd.isna(r["Meta"]) else str(int(r["Meta"]))
            pend_txt = "—" if pd.isna(r["Pendiente"]) else str(int(r["Pendiente"]))
            rows.append([
                t, d,
                meta_txt,
                str(int(r["Contabilizado"])),
                fmt_pct(r["% Avance"]) if not pd.isna(r["% Avance"]) else "—",
                pend_txt,
                str(int(r["No_Consent"]))
            ])
            row_kind.append("data")

    nrows = len(rows) + 1
    fig_w = 15.5
    fig_h = max(4.5, nrows * 0.28)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.axis("off")

    ax.set_title(f"Seguimiento de Encuestas\n{sel_deleg}", fontsize=18, fontweight="bold", pad=18)

    table = ax.table(cellText=rows, colLabels=headers, loc="upper center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(9.7)
    table.scale(1, 1.35)

    header_bg = "#e6e6e6"
    section_bg = "#d9d9d9"
    pct_bg = "#29a36a"
    pending_bg = "#6d8fc9"
    white = "#ffffff"

    col_widths = [0.14, 0.25, 0.10, 0.13, 0.12, 0.12, 0.14]
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
                if c in (2, 3, 4, 5, 6):
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
# Sidebar (solo carga de 3 exceles)
# =========================
st.sidebar.header("📥 Carga (Excels separados)")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx", "xls"], key="f_com")
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx", "xls"], key="f_eco")
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx", "xls"], key="f_pol")

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")
incluir_no_identificado = st.sidebar.checkbox("Incluir NO_IDENTIFICADO (solo Comunidad)", value=False)

tipos_order = ["Comunidad", "Comercio", "Policial"]
fecha_txt = fecha_es(dt.date.today())


# =========================
# Preparar archivo (por tipo)
# - filtra NO consentimiento (no se contabiliza)
# - devuelve también conteos NO para mostrar
# =========================
def prep_file(file, tipo_label):
    df = read_any_excel(file)
    cols = list(df.columns)

    # Consentimiento
    yes_count, no_count, mask_yes = consent_counts(df)
    df_yes = df[mask_yes].copy()

    # Delegación/Cantón base (donde se está realizando)
    col_canton = pick_col(cols, ["Cantón", "Canton", "Delegacion", "Delegación", "Lugar", "Sede"])
    if not col_canton:
        raise ValueError(f"[{tipo_label}] No encontré columna Cantón/Canton (o Delegación/Lugar/Sede).")

    # Normalizar delegación por similitud
    raw_deleg = df_yes[col_canton].astype(str).str.strip()
    canon = [d for d in DELEGACIONES]
    df_yes["_DelegRaw_"] = raw_deleg
    df_yes["_Delegacion_"] = df_yes["_DelegRaw_"].apply(lambda x: best_match_name(x, canon, cutoff=0.62))

    # Por tipo:
    # - Comunidad: usa distritos y metas por distrito (catálogo precargado)
    # - Comercio: sin distritos -> distrito = delegación
    # - Policial: sin distritos -> distrito = delegación
    if tipo_label in ("Comercio", "Policial"):
        out = df_yes[["_Delegacion_"]].copy()
        out["Tipo"] = tipo_label
        out["Distrito"] = out["_Delegacion_"]
        out["Delegación"] = out["_Delegacion_"]
        out = out[["Tipo", "Delegación", "Distrito"]]
        return out, no_count

    # Comunidad: intentar leer distrito
    col_distrito = choose_district_col(cols)
    if not col_distrito:
        raise ValueError(f"[{tipo_label}] No encontré columna de Distrito.")

    # Intento por bloque (Survey123)
    # Tomamos el modo de delegación para sacar distritos válidos
    deleg_mode = df_yes["_Delegacion_"].mode().iloc[0] if len(df_yes) else ""
    valid_norm = {norm(x) for x in CATALOGO.get(norm(deleg_mode), [])}

    inferred_block = infer_district_from_block(df_yes, col_distrito, valid_norm) if valid_norm else pd.Series([None]*len(df_yes), index=df_yes.index)
    distrito_directo = df_yes[col_distrito].astype(str).str.strip()
    df_yes["_DistritoCand_"] = inferred_block.where(inferred_block.notna(), distrito_directo)

    def resolver(row):
        deleg = row["_Delegacion_"]
        cand = row["_DistritoCand_"]
        if cand is None:
            return None
        cand = str(cand).strip()
        if cand == "" or cand.lower() in ("nan", "none"):
            return None

        # si no hay catálogo para esa delegación, dejamos texto
        if norm(deleg) not in CATALOGO:
            return cand

        mapped = ubicar_distrito(deleg, cand)
        return mapped if mapped else "NO_IDENTIFICADO"

    df_yes["_Distrito_"] = df_yes.apply(resolver, axis=1)
    df_yes = df_yes.replace({"nan": None, "None": None, "": None}).dropna(subset=["_Delegacion_", "_Distrito_"])

    out = df_yes.copy()
    out["Tipo"] = "Comunidad"
    out["Delegación"] = out["_Delegacion_"]
    out["Distrito"] = out["_Distrito_"]
    return out[["Tipo", "Delegación", "Distrito"]], no_count


# =========================
# Leer archivos
# =========================
data = []
no_map = {"Comunidad": 0, "Comercio": 0, "Policial": 0}
errs = []

if f_com:
    try:
        d, nno = prep_file(f_com, "Comunidad")
        data.append(d)
        no_map["Comunidad"] = int(nno)
    except Exception as e:
        errs.append(str(e))

if f_eco:
    try:
        d, nno = prep_file(f_eco, "Comercio")
        data.append(d)
        no_map["Comercio"] = int(nno)
    except Exception as e:
        errs.append(str(e))

if f_pol:
    try:
        d, nno = prep_file(f_pol, "Policial")
        data.append(d)
        no_map["Policial"] = int(nno)
    except Exception as e:
        errs.append(str(e))

if errs:
    st.error("Errores:\n\n- " + "\n- ".join(errs))
    st.stop()

if not data:
    st.info("Subí al menos 1 Excel (Comunidad / Comercio / Policial).")
    st.stop()

base = pd.concat(data, ignore_index=True)


# =========================
# Agregación
# =========================
agg = base.groupby(["Tipo", "Delegación", "Distrito"]).size().reset_index(name="Contabilizado")

# Delegación seleccionada (precargada)
sel_deleg = st.sidebar.selectbox("Delegación para el cuadro", DELEGACIONES, index=0)

resumen = agg[agg["Delegación"] == sel_deleg].copy()

# distritos a mostrar:
# - Comunidad: según catálogo precargado (o lo que venga si no existe)
# - Comercio/Policial: un solo distrito = delegación
distritos = []

if norm(sel_deleg) in CATALOGO:
    distritos = CATALOGO[norm(sel_deleg)].copy()
else:
    # fallback a lo que exista en data
    distritos = sorted(resumen["Distrito"].unique().tolist())

# Si NO_IDENTIFICADO se excluye
if not incluir_no_identificado:
    distritos = [d for d in distritos if d != "NO_IDENTIFICADO"]

# =========================
# Construir df_full (1 fila por distrito-tipo)
# =========================
rows = []
for d in distritos:
    for t in tipos_order:
        cnt = int(resumen[(resumen["Distrito"] == d) & (resumen["Tipo"] == t)]["Contabilizado"].sum())

        if t == "Comunidad":
            meta = METAS_COMUNIDAD.get(sel_deleg, {}).get(d, None)
        elif t == "Comercio":
            # Comercio sin distritos: lo mostramos SOLO en distrito=delegación
            meta = METAS_COMERCIO.get(sel_deleg, None) if d == sel_deleg else None
            # Si el excel vino con distrito=delegación (por nuestra lógica), el cnt estará ahí:
            if d != sel_deleg:
                cnt = 0
        else:
            meta = None
            if d != sel_deleg:
                cnt = 0

        if meta is None:
            pendiente = None
            avance = None
        else:
            pendiente = max(int(meta) - int(cnt), 0)
            avance = (cnt / meta * 100) if meta else 0.0

        no_consent = int(no_map.get(t, 0)) if (d == distritos[0] and t == "Comunidad") else 0
        # Para no repetir el NO en todas las filas, lo ponemos solo una vez por tipo (en primera sección)
        if t == "Comercio" and d == (sel_deleg if sel_deleg in distritos else distritos[0]):
            no_consent = int(no_map.get("Comercio", 0))
        if t == "Policial" and d == (sel_deleg if sel_deleg in distritos else distritos[0]):
            no_consent = int(no_map.get("Policial", 0))

        rows.append({
            "Distrito": d,
            "Tipo": t,
            "Meta": meta if meta is not None else pd.NA,
            "Contabilizado": cnt,
            "% Avance": avance if avance is not None else pd.NA,
            "Pendiente": pendiente if pendiente is not None else pd.NA,
            "No_Consent": no_consent
        })

df_full = pd.DataFrame(rows)

# Asegurar que Comercio/Policial aparezcan aunque el distrito sea delegación y no esté en catálogo
if sel_deleg not in distritos:
    distritos = [sel_deleg] + distritos


# =========================
# Render HTML (UN SOLO CUADRO + fecha/hora)
# =========================
tbody = ""
for d in distritos:
    tbody += f'<tr class="section-row"><td colspan="7">{safe_html(d)}</td></tr>'
    sub = df_full[df_full["Distrito"] == d]
    for t in tipos_order:
        r = sub[sub["Tipo"] == t].iloc[0]

        meta_txt = "—" if pd.isna(r["Meta"]) else str(int(r["Meta"]))
        pend_txt = "—" if pd.isna(r["Pendiente"]) else str(int(r["Pendiente"]))
        pct_txt = "—" if pd.isna(r["% Avance"]) else fmt_pct(r["% Avance"])

        tbody += f"""
        <tr>
          <td><b>{safe_html(t)}</b></td>
          <td>{safe_html(d)}</td>
          <td class="meta">{safe_html(meta_txt)}</td>
          <td class="count">{int(r['Contabilizado'])}</td>
          <td class="pct">{safe_html(pct_txt)}</td>
          <td class="pending">{safe_html(pend_txt)}</td>
          <td class="count">{int(r['No_Consent'])}</td>
        </tr>
        """

total_no = int(no_map.get("Comunidad", 0) + no_map.get("Comercio", 0) + no_map.get("Policial", 0))

html_doc = f"""
<!doctype html>
<html>
<head>{CSS}</head>
<body>
  <div class="wrap">
    <div class="h1">Seguimiento de Encuestas</div>
    <div class="h2">{safe_html(sel_deleg)}</div>

    <div class="card">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width:16%">Tipo</th>
            <th style="width:24%">Distrito</th>
            <th style="width:10%; text-align:center;">Meta</th>
            <th style="width:14%; text-align:center;">Contabilizado</th>
            <th style="width:12%; text-align:center;">% Avance</th>
            <th style="width:12%; text-align:center;">Pendiente</th>
            <th style="width:12%; text-align:center;">NO (consent.)</th>
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

    <div class="smallnote">
      <b>NO por consentimiento:</b>
      Comunidad={int(no_map.get("Comunidad",0))} |
      Comercio={int(no_map.get("Comercio",0))} |
      Policial={int(no_map.get("Policial",0))} |
      <b>Total={total_no}</b>
    </div>
  </div>
</body>
</html>
"""

height = min(360 + len(distritos) * 140, 2400)
components.html(html_doc, height=height, scrolling=True)


# =========================
# Descargas
# =========================
st.divider()
col1, col2 = st.columns(2)

with col1:
    png_bytes = build_table_image_png(sel_deleg, distritos, df_full, tipos_order, fecha_txt, hora_manual)
    st.download_button(
        "📷 Descargar cuadro como imagen (PNG)",
        data=png_bytes,
        file_name=f"cuadro_encuestas_{sel_deleg}.png".replace(" ", "_"),
        mime="image/png",
        use_container_width=True
    )

with col2:
    detalle = agg.copy()

    # Meter metas
    def meta_for_row(row):
        t = row["Tipo"]
        deleg = row["Delegación"]
        dist = row["Distrito"]
        if t == "Comunidad":
            return METAS_COMUNIDAD.get(deleg, {}).get(dist, pd.NA)
        if t == "Comercio":
            return METAS_COMERCIO.get(deleg, pd.NA)
        return pd.NA

    detalle["Meta"] = detalle.apply(meta_for_row, axis=1)

    def pendiente_for_row(row):
        if pd.isna(row["Meta"]):
            return pd.NA
        return max(int(row["Meta"]) - int(row["Contabilizado"]), 0)

    def pct_for_row(row):
        if pd.isna(row["Meta"]) or int(row["Meta"]) == 0:
            return pd.NA
        return round(float(row["Contabilizado"]) / float(row["Meta"]) * 100.0, 1)

    detalle["Pendiente"] = detalle.apply(pendiente_for_row, axis=1)
    detalle["% Avance"] = detalle.apply(pct_for_row, axis=1)

    excel_bytes = to_excel_bytes(detalle.sort_values(["Delegación", "Distrito", "Tipo"]), sheet_name="seguimiento")
    st.download_button(
        "⬇️ Descargar seguimiento (Excel)",
        data=excel_bytes,
        file_name="seguimiento_encuestas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

