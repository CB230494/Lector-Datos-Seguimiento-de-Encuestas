# app.py
# -*- coding: utf-8 -*-

import io
import re
import csv
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

st.set_page_config(page_title="Sembremos Seguridad - Reporte", layout="wide")


# -----------------------------
# Normalización fuerte
# -----------------------------
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().strip("\ufeff")
    s = s.replace("\n", " ").replace("\r", " ")
    s = strip_accents(s).lower().strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("sí", "si").replace("si.", "si").replace("no.", "no")
    return s


def is_yes(v) -> bool:
    return norm(v) == "si"


def is_no(v) -> bool:
    return norm(v) == "no"


def pretty_title(s: str) -> str:
    if s is None:
        return ""
    t = str(s).strip().replace("_", " ").replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower().title()


# -----------------------------
# Fecha en español
# -----------------------------
SPANISH_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
SPANISH_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es(dt: datetime) -> str:
    wd = SPANISH_WEEKDAYS[dt.weekday()]
    month = SPANISH_MONTHS[dt.month - 1]
    return f"{wd}, {dt.day} de {month} de {dt.year}"


# -----------------------------
# Inferir tipo/lugar por filename
# -----------------------------
def infer_tipo_lugar(filename: str):
    base = Path(filename).stem
    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        return m.group(1).capitalize(), m.group(2).replace("_", " ").strip()
    parts = base.split("_")
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[1].replace("_", " ").strip()
    return "Desconocida", base


# -----------------------------
# CSV robusto + ALINEACIÓN filas
# -----------------------------
def parse_csv_robusto(file_bytes: bytes):
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"', skipinitialspace=False)

    rows = []
    for row in reader:
        if not row:
            continue
        if all(norm(c) == "" for c in row):
            continue
        rows.append(row)

    if not rows:
        return [], []

    header = rows[0]
    data = rows[1:]
    ncols = len(header)

    fixed = []
    for r in data:
        if len(r) > ncols:
            r = r[:ncols]
        elif len(r) < ncols:
            r = r + ([""] * (ncols - len(r)))
        fixed.append(r)

    return header, fixed


# -----------------------------
# Detectar columna Distrito (sin confundir preguntas)
# -----------------------------
def clean_header_token(h: str) -> str:
    x = norm(h)
    x = re.sub(r"^\s*\d+\s*[\.\)\-:]+\s*", "", x).strip()
    x = x.rstrip(":").strip()
    return x


def find_district_col(header: list[str], data: list[list[str]]):
    candidates = []
    for i, h in enumerate(header):
        ch = clean_header_token(h)
        if ch in ("distrito", "district"):
            candidates.append(i)

    if not candidates:
        return None

    def score(col):
        vals = [data[r][col] for r in range(min(len(data), 200))]
        good = 0
        for v in vals:
            vv = str(v).strip()
            if norm(vv) == "":
                continue
            if "?" in vv or ":" in vv:
                continue
            if len(vv) > 35:
                continue
            if re.match(r"^\d+\s*[\.\)]", vv):
                continue
            good += 1
        return good

    best = max(candidates, key=score)
    return best


def get_unique_values(data, col_idx: int) -> list[str]:
    vals = set()
    for r in data:
        v = r[col_idx]
        if norm(v) != "":
            vals.add(str(v).strip())
    return sorted(list(vals), key=lambda x: strip_accents(x.lower()))


# -----------------------------
# Ubicar SI/NO: ranking de columnas
# -----------------------------
def rank_yesno_columns(header: list[str], data: list[list[str]], top_k: int = 8) -> pd.DataFrame:
    rows = []
    for j in range(len(header)):
        si = 0
        no = 0
        filled = 0
        for r in data:
            v = r[j]
            if norm(v) == "":
                continue
            filled += 1
            if is_yes(v):
                si += 1
            elif is_no(v):
                no += 1
        hits = si + no
        ratio = (hits / filled) if filled > 0 else 0.0
        rows.append({
            "idx": j,
            "columna": header[j],
            "SI": si,
            "NO": no,
            "SI+NO": hits,
            "no_vacias": filled,
            "ratio_SI_NO": ratio
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(["SI+NO", "ratio_SI_NO"], ascending=[False, False]).head(top_k).reset_index(drop=True)
    return df


def choose_default_yesno_col(header: list[str], data: list[list[str]]) -> int:
    prefer = ["acepta", "consent", "consentimiento"]
    best_pref = None
    best_hits = -1

    for j, h in enumerate(header):
        hn = norm(h)
        if any(p in hn for p in prefer):
            si = sum(1 for r in data if is_yes(r[j]))
            no = sum(1 for r in data if is_no(r[j]))
            if (si + no) > best_hits:
                best_hits = si + no
                best_pref = j

    if best_pref is not None and best_hits > 0:
        return best_pref

    ranked = rank_yesno_columns(header, data, top_k=1)
    if len(ranked) == 0:
        return 0
    return int(ranked.loc[0, "idx"])


# =========================================================
# ✅ Deduplicación (≤ X minutos)
# =========================================================
def detect_datetime_col(header: list[str], data: list[list[str]]) -> int | None:
    """Devuelve el índice de la columna con más valores parseables como datetime."""
    if not header or not data:
        return None

    best_i = None
    best_hits = 0

    sample = data[:300]
    for j in range(len(header)):
        vals = [row[j] for row in sample if j < len(row)]
        dt = pd.to_datetime(pd.Series(vals), errors="coerce", infer_datetime_format=True)
        hits = int(dt.notna().sum())
        if hits > best_hits:
            best_hits = hits
            best_i = j

    if best_hits >= 5:
        return best_i
    return None


def dedupe_within_minutes(header: list[str], data: list[list[str]], minutes: int = 5) -> tuple[list[list[str]], int]:
    """
    Elimina respuestas duplicadas (mismas respuestas) dentro de un lapso de X minutos.
    - Usa una columna de fecha/hora detectada automáticamente.
    - Firma = todas las columnas normalizadas EXCEPTO la de fecha/hora.
    """
    dt_col = detect_datetime_col(header, data)
    if dt_col is None:
        return data, 0

    rows = []
    for idx, r in enumerate(data):
        raw_dt = r[dt_col] if dt_col < len(r) else ""
        dt = pd.to_datetime(raw_dt, errors="coerce", infer_datetime_format=True)
        rows.append((idx, dt.to_pydatetime() if pd.notna(dt) else None, r))

    valid = [x for x in rows if x[1] is not None]
    invalid = [x for x in rows if x[1] is None]

    valid.sort(key=lambda x: x[1])

    last_time_by_sig = {}
    keep_indices = set()

    window = timedelta(minutes=minutes)
    removed = 0

    for idx, dt, r in valid:
        sig = tuple(norm(r[j]) for j in range(len(r)) if j != dt_col)
        if sig in last_time_by_sig and (dt - last_time_by_sig[sig]) <= window:
            removed += 1
            continue
        last_time_by_sig[sig] = dt
        keep_indices.add(idx)

    for idx, _, _ in invalid:
        keep_indices.add(idx)

    filtered = [data[i] for i in range(len(data)) if i in keep_indices]
    return filtered, removed


# =========================================================
# ✅ Catálogo de metas (Excel)
# - Debe existir: catalogo_metas.xlsx (misma carpeta)
# - Columnas: Delegacion | Tipo | Distrito | Meta
# =========================================================
@st.cache_data
def load_catalog(path: str = "catalogo_metas.xlsx") -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=["Delegacion", "Tipo", "Distrito", "Meta"])

    df = pd.read_excel(path)
    # Normalización mínima
    df["Delegacion"] = df["Delegacion"].astype(str).str.strip().apply(pretty_title)
    df["Tipo"] = df["Tipo"].astype(str).str.strip().apply(pretty_title)
    df["Distrito"] = df["Distrito"].astype(str).str.strip().apply(pretty_title)
    df["Meta"] = pd.to_numeric(df["Meta"], errors="coerce").fillna(0).astype(int)

    # Quitar filas vacías
    df = df[df["Delegacion"].apply(norm) != ""]
    df = df[df["Tipo"].apply(norm) != ""]
    df = df[df["Distrito"].apply(norm) != ""]

    return df.reset_index(drop=True)


def get_catalog_df(catalogo: pd.DataFrame, delegacion: str, tipo: str) -> pd.DataFrame:
    if catalogo is None or catalogo.empty:
        return pd.DataFrame(columns=["Tipo", "Distrito", "Meta"])

    d = pretty_title(delegacion)
    t = pretty_title(tipo)

    out = catalogo[(catalogo["Delegacion"] == d) & (catalogo["Tipo"] == t)].copy()
    if out.empty:
        return pd.DataFrame(columns=["Tipo", "Distrito", "Meta"])

    return out[["Tipo", "Distrito", "Meta"]].sort_values("Distrito").reset_index(drop=True)


def merge_base_with_catalog(df_base: pd.DataFrame, df_cat: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """
    Devuelve TODOS los distritos del catálogo (aunque CSV no traiga datos),
    rellenando SI/NO con 0 si no aparecen.
    df_base esperado: Tipo, Distrito, SI, NO
    df_cat  esperado: Tipo, Distrito, Meta
    """
    if df_base is None or df_base.empty:
        df_base = pd.DataFrame(columns=["Distrito", "SI", "NO"])
    else:
        df_base = df_base.copy()
        df_base["Distrito"] = df_base["Distrito"].apply(pretty_title)

    if df_cat is None or df_cat.empty:
        out = df_base.copy()
        out["Tipo"] = pretty_title(tipo)
        out["Meta"] = 0
        out["SI"] = pd.to_numeric(out.get("SI", 0), errors="coerce").fillna(0).astype(int)
        out["NO"] = pd.to_numeric(out.get("NO", 0), errors="coerce").fillna(0).astype(int)
        return out[["Tipo", "Distrito", "Meta", "SI", "NO"]].sort_values("Distrito").reset_index(drop=True)

    out = df_cat.merge(df_base[["Distrito", "SI", "NO"]], on="Distrito", how="left")
    out["Tipo"] = pretty_title(tipo)
    out["Meta"] = pd.to_numeric(out["Meta"], errors="coerce").fillna(0).astype(int)
    out["SI"] = pd.to_numeric(out["SI"], errors="coerce").fillna(0).astype(int)
    out["NO"] = pd.to_numeric(out["NO"], errors="coerce").fillna(0).astype(int)

    return out.sort_values("Distrito").reset_index(drop=True)


# -----------------------------
# Construir tablas base (SI/NO ya calculados)
# -----------------------------
def build_base_comunidad(header, data, col_yesno):
    dist_col = find_district_col(header, data)

    if dist_col is None:
        si = sum(1 for r in data if is_yes(r[col_yesno]))
        no = sum(1 for r in data if is_no(r[col_yesno]))
        return pd.DataFrame([{"Tipo": "Comunidad", "Distrito": "TOTAL (Delegación)", "SI": si, "NO": no}])

    distritos_raw = get_unique_values(data, dist_col)

    si_map = {pretty_title(d): 0 for d in distritos_raw}
    no_map = {pretty_title(d): 0 for d in distritos_raw}

    for r in data:
        d = pretty_title(r[dist_col])
        if norm(d) == "":
            continue
        if d not in si_map:
            si_map[d] = 0
            no_map[d] = 0

        if is_yes(r[col_yesno]):
            si_map[d] += 1
        elif is_no(r[col_yesno]):
            no_map[d] += 1

    df = pd.DataFrame({
        "Tipo": "Comunidad",
        "Distrito": list(si_map.keys()),
        "SI": list(si_map.values()),
        "NO": [no_map[k] for k in si_map.keys()]
    }).sort_values("Distrito").reset_index(drop=True)

    df = df[~df["Distrito"].str.contains(r"\?", regex=True)]
    df = df[~df["Distrito"].str.contains(r"^\d+\.", regex=True)]

    return df


def build_base_from_totals(tipo: str, distrito: str, si: int, no: int) -> pd.DataFrame:
    return pd.DataFrame([{
        "Tipo": pretty_title(tipo),
        "Distrito": pretty_title(distrito),
        "SI": int(si),
        "NO": int(no)
    }])


def apply_meta_calc_auto(df_base: pd.DataFrame) -> pd.DataFrame:
    """
    - Meta viene del catálogo (automática)
    - Contabilidad = SI (automática)
    - % Avance y Pendiente se calculan
    """
    df = df_base.copy()
    df["Meta"] = pd.to_numeric(df.get("Meta", 0), errors="coerce").fillna(0).astype(int)
    df["SI"] = pd.to_numeric(df.get("SI", 0), errors="coerce").fillna(0).astype(int)
    df["NO"] = pd.to_numeric(df.get("NO", 0), errors="coerce").fillna(0).astype(int)

    df["Contabilidad"] = df["SI"].astype(int)

    df["% Avance"] = df.apply(
        lambda r: (r["Contabilidad"] / r["Meta"]) if r["Meta"] > 0 else 0.0,
        axis=1
    )
    df["Pendiente"] = df.apply(
        lambda r: max(int(r["Meta"]) - int(r["Contabilidad"]), 0),
        axis=1
    )
    df["% Avance"] = df["% Avance"].apply(lambda x: f"{int(round(float(x) * 100))}%")

    return df[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO"]]


def editable_report_table(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """
    Permite editar directamente los recuadros visibles del reporte.
    Recalcula automáticamente % Avance y Pendiente cuando se modifica
    Meta o Contabilidad.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Solo estas columnas se editan
    editor_df = df[["Tipo", "Distrito", "Meta", "Contabilidad"]].copy()

    edited = st.data_editor(
        editor_df,
        use_container_width=True,
        num_rows="fixed",
        key=key,
        column_config={
            "Tipo": st.column_config.TextColumn("Tipo"),
            "Distrito": st.column_config.TextColumn("Distrito"),
            "Meta": st.column_config.NumberColumn("Meta", min_value=0, step=1),
            "Contabilidad": st.column_config.NumberColumn("Contabilidad", min_value=0, step=1),
        },
        disabled=[]
    )

    # Normalizar
    edited["Tipo"] = edited["Tipo"].astype(str)
    edited["Distrito"] = edited["Distrito"].astype(str)
    edited["Meta"] = pd.to_numeric(edited["Meta"], errors="coerce").fillna(0).astype(int)
    edited["Contabilidad"] = pd.to_numeric(edited["Contabilidad"], errors="coerce").fillna(0).astype(int)

    # Recalcular automáticamente
    edited["Pendiente"] = (edited["Meta"] - edited["Contabilidad"]).clip(lower=0).astype(int)
    edited["% Avance"] = edited.apply(
        lambda r: f"{round((r['Contabilidad'] / r['Meta']) * 100):.0f}%"
        if r["Meta"] > 0 else "0%",
        axis=1
    )

    # Columnas internas
    edited["SI"] = edited["Contabilidad"].astype(int)

    if "NO" in df.columns:
        edited["NO"] = pd.to_numeric(df["NO"], errors="coerce").fillna(0).astype(int).values
    else:
        edited["NO"] = 0

    # Mostrar resultado recalculado abajo
    st.dataframe(
        edited[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]],
        use_container_width=True
    )

    return edited[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO"]]
# -----------------------------
# PDF
# -----------------------------
def build_pdf_bytes(delegacion_label: str, hora_reporte: str, fecha_str: str, logo_path: str | None,
                    df_com: pd.DataFrame, df_con: pd.DataFrame, df_pol: pd.DataFrame) -> bytes:
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=letter, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()

    cell = ParagraphStyle("cell", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11)
    head = ParagraphStyle("head", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11)

    story = []

    if logo_path and Path(logo_path).exists():
        img = RLImage(logo_path, width=2.8 * inch, height=2.8 * inch)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>{delegacion_label}</b>", styles["Title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Hora del reporte:</b> {hora_reporte or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fecha:</b> {fecha_str}", styles["Normal"]))
    story.append(Spacer(1, 10))

    def section(title: str, df: pd.DataFrame):
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        story.append(Spacer(1, 4))

        if df is None or df.empty:
            story.append(Paragraph("No hay registros.", styles["Normal"]))
            story.append(Spacer(1, 12))
            return

        cols = ["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]
        data = [[Paragraph(c, head) for c in cols]]

        for _, r in df.iterrows():
            data.append([
                Paragraph(str(r["Tipo"]), cell),
                Paragraph(str(r["Distrito"]), cell),
                Paragraph(str(int(pd.to_numeric(r["Meta"], errors="coerce"))), cell),
                Paragraph(str(int(pd.to_numeric(r["Contabilidad"], errors="coerce"))), cell),
                Paragraph(str(r["% Avance"]), cell),
                Paragraph(str(int(pd.to_numeric(r["Pendiente"], errors="coerce"))), cell),
            ])

        tbl = Table(data, colWidths=[62, 210, 55, 78, 58, 62])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        story.append(tbl)
        story.append(Spacer(1, 12))

    section("Comunidad", df_com)
    section("Comercio", df_con)
    section("Policial", df_pol)

    doc.build(story)
    buff.seek(0)
    return buff.getvalue()


# -----------------------------
# UI
# -----------------------------
st.title("📄 Reporte por Delegación (Comunidad / Comercio / Policial)")
st.caption("Metas y distritos salen automáticos desde el catálogo. Contabilidad = SI (automático).")

# ✅ Cargar catálogo
CAT_PATH = "catalogo_metas.xlsx"
catalogo = load_catalog(CAT_PATH)

if catalogo.empty:
    st.error(f"No encontré el catálogo '{CAT_PATH}'. Colocalo en la misma carpeta que este app.py.")
    st.stop()

files = st.file_uploader("Cargá los CSV (pueden ser varios)", type=["csv"], accept_multiple_files=True)
if not files:
    st.stop()

logo_path = "001.png" if Path("001.png").exists() else None

parsed = []
lugares = set()
for f in files:
    header, data = parse_csv_robusto(f.getvalue())
    tipo, lugar = infer_tipo_lugar(f.name)
    parsed.append((f.name, tipo, lugar, header, data))
    lugares.add(lugar)

lugares = sorted(list(lugares), key=lambda x: strip_accents(x.lower()))
delegacion_sel = st.selectbox("Delegación (Lugar):", lugares)

hora_reporte = st.text_input("Hora del reporte:", value="")
fecha_str = fecha_es(datetime.now())
delegacion_label = f"Delegación: {pretty_title(delegacion_sel)}"


def pick(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if lugar == delegacion_sel and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None


fname_com, h_com, d_com = pick("Comunidad")
fname_con, h_con, d_con = pick("Comercio")
fname_pol, h_pol, d_pol = pick("Policial")


# =========================================================
# ✅ Filtros opcionales (deduplicación por tipo)
# =========================================================
st.divider()
st.subheader("0) Filtros opcionales")

cA, cB, cC = st.columns(3)
dedupe_com = cA.checkbox("Eliminar duplicadas (Comunidad) ≤ 5 min", value=False)
dedupe_con = cB.checkbox("Eliminar duplicadas (Comercio) ≤ 5 min", value=False)
dedupe_pol = cC.checkbox("Eliminar duplicadas (Policial) ≤ 5 min", value=False)

removed_info = {"Comunidad": 0, "Comercio": 0, "Policial": 0}

if h_com and d_com and dedupe_com:
    d_com, removed = dedupe_within_minutes(h_com, d_com, minutes=5)
    removed_info["Comunidad"] = removed
if h_con and d_con and dedupe_con:
    d_con, removed = dedupe_within_minutes(h_con, d_con, minutes=5)
    removed_info["Comercio"] = removed
if h_pol and d_pol and dedupe_pol:
    d_pol, removed = dedupe_within_minutes(h_pol, d_pol, minutes=5)
    removed_info["Policial"] = removed

if any(v > 0 for v in removed_info.values()):
    st.info(
        f"Duplicadas eliminadas: Comunidad={removed_info['Comunidad']}, "
        f"Comercio={removed_info['Comercio']}, Policial={removed_info['Policial']}."
    )


# =========================================================
# 1) Ubicar los SI/NO (antes de cálculos)
# =========================================================
st.divider()
st.subheader("1) ✅ Ubicar los SI/NO (antes del reporte)")

def ui_pick_yesno(tipo_label: str, header, data):
    if not header:
        st.info(f"No hay CSV de {tipo_label} para esta delegación. Se usará SI=0, NO=0.")
        return None

    ranked = rank_yesno_columns(header, data, top_k=8)
    default_idx = choose_default_yesno_col(header, data)

    st.markdown(f"**{tipo_label}:** columnas candidatas (top 8)")
    st.dataframe(ranked[["idx", "columna", "SI", "NO", "SI+NO", "ratio_SI_NO"]], use_container_width=True)

    labels = [f"[{i+1}] {header[i]}" for i in range(len(header))]
    choice = st.selectbox(
        f"Columna SI/NO a usar ({tipo_label}):",
        labels,
        index=default_idx,
        key=f"yesno_{tipo_label}_{delegacion_sel}"
    )
    col = labels.index(choice)

    si_total = sum(1 for r in data if is_yes(r[col]))
    no_total = sum(1 for r in data if is_no(r[col]))

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{tipo_label} - SI", si_total)
    c2.metric(f"{tipo_label} - NO", no_total)
    c3.metric(f"{tipo_label} - SI+NO", si_total + no_total)

    return col


col_com = ui_pick_yesno("Comunidad", h_com, d_com) if h_com else None
st.divider()
col_con = ui_pick_yesno("Comercio", h_con, d_con) if h_con else None
st.divider()
col_pol = ui_pick_yesno("Policial", h_pol, d_pol) if h_pol else None


# =========================================================
# 2) Reporte automático (Metas + Distritos desde catálogo)
# =========================================================
st.divider()
st.subheader("2) Reporte (automático)")

# -----------------------------
# Comunidad (por distrito real)
# -----------------------------
st.markdown("### Comunidad")
df_cat_com = get_catalog_df(catalogo, delegacion_sel, "Comunidad")

if h_com and d_com and col_com is not None:
    base_com = build_base_comunidad(h_com, d_com, col_com)  # Tipo, Distrito, SI, NO
else:
    base_com = pd.DataFrame(columns=["Tipo", "Distrito", "SI", "NO"])

base_com = merge_base_with_catalog(base_com, df_cat_com, "Comunidad")
df_comunidad = apply_meta_calc_auto(base_com)
df_comunidad = editable_report_table(df_comunidad, key=f"editor_comunidad_{delegacion_sel}")

# -----------------------------
# Comercio (1 fila desde catálogo)
# -----------------------------
st.markdown("### Comercio")
df_cat_con = get_catalog_df(catalogo, delegacion_sel, "Comercio")

si_con = 0
no_con = 0
if h_con and d_con and col_con is not None:
    si_con = sum(1 for r in d_con if is_yes(r[col_con]))
    no_con = sum(1 for r in d_con if is_no(r[col_con]))

if not df_cat_con.empty:
    distrito_con = df_cat_con.iloc[0]["Distrito"]
else:
    distrito_con = delegacion_sel

base_con = build_base_from_totals("Comercio", distrito_con, si_con, no_con)
base_con = merge_base_with_catalog(base_con, df_cat_con, "Comercio")
df_comercio = apply_meta_calc_auto(base_con)
df_comercio = editable_report_table(df_comercio, key=f"editor_comercio_{delegacion_sel}")

# -----------------------------
# Policial (1 fila desde catálogo)
# -----------------------------
st.markdown("### Policial")
df_cat_pol = get_catalog_df(catalogo, delegacion_sel, "Policial")

si_pol = 0
no_pol = 0
if h_pol and d_pol and col_pol is not None:
    si_pol = sum(1 for r in d_pol if is_yes(r[col_pol]))
    no_pol = sum(1 for r in d_pol if is_no(r[col_pol]))

if not df_cat_pol.empty:
    distrito_pol = df_cat_pol.iloc[0]["Distrito"]
else:
    distrito_pol = delegacion_sel

base_pol = build_base_from_totals("Policial", distrito_pol, si_pol, no_pol)
base_pol = merge_base_with_catalog(base_pol, df_cat_pol, "Policial")
df_policial = apply_meta_calc_auto(base_pol)
df_policial = editable_report_table(df_policial, key=f"editor_policial_{delegacion_sel}")


# =========================================================
# 3) PDF
# =========================================================
st.divider()
st.subheader("3) PDF")

if st.button("📄 Generar PDF"):
    pdf = build_pdf_bytes(
        delegacion_label=delegacion_label,
        hora_reporte=hora_reporte,
        fecha_str=fecha_str,
        logo_path=logo_path,
        df_com=df_comunidad,
        df_con=df_comercio,
        df_pol=df_policial
    )
    st.download_button(
        "⬇️ Descargar PDF",
        data=pdf,
        file_name=f"Reporte_{delegacion_sel.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Listo: distritos + metas vienen del catálogo. Si editás Meta o Contabilidad, ahora % Avance y Pendiente se recalculan automáticamente.")

