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
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

st.set_page_config(page_title="Sembremos Seguridad - Reporte", layout="wide")


# -----------------------------
# Normalización fuerte
# -----------------------------
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def normalize_visible_text(v) -> str:
    """
    Normaliza texto visible sin perder ñ, tildes ni caracteres especiales.
    """
    if v is None:
        return ""
    s = str(v).strip().strip("\ufeff")
    s = s.replace("\n", " ").replace("\r", " ")
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm(v) -> str:
    if v is None:
        return ""
    s = normalize_visible_text(v)
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
    t = normalize_visible_text(s)
    t = t.replace("_", " ").replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t.title()


# -----------------------------
# Normalización ROBUSTA de lugar/distrito
# -----------------------------
def normalize_place_key(v) -> str:
    """
    Clave robusta para comparar distritos/delegaciones sin romper el texto visible.
    """
    if v is None:
        return ""

    s = normalize_visible_text(v)
    s = strip_accents(s).casefold().strip()
    s = re.split(r"\s*[,;/\-]\s*", s)[0].strip()
    s = re.sub(r"\s+", " ", s).strip(" .,:;-/")

    alias_map = {
        "la uruca": "uruca",
        "uruca": "uruca",
        "zapote": "zapote",
        "san jose de la montana": "san jose de la montana",
        "para": "para",
        "la ribera": "la ribera",
        "ribera": "la ribera",
        "canas": "canas",
        "anaselmo llorente": "anselmo llorente",
        "anselmo llorente": "anselmo llorente",
        "pacuare": "pacuare",
        "pacuarito": "pacuare",
        "Vara Blanca": " Vara Blanca",
        "varablanca": "Vara Blanca",
    }

    return alias_map.get(s, s)


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
    base = normalize_visible_text(Path(filename).stem)
    m = re.match(r"(?i)^(policial|comunidad|comercio)_(.+?)_(\d{4}).*", base)
    if m:
        tipo = m.group(1).capitalize()
        lugar = normalize_visible_text(m.group(2).replace("_", " ").strip())
        return tipo, lugar

    parts = base.split("_")
    if len(parts) >= 2:
        tipo = normalize_visible_text(parts[0]).capitalize()
        lugar = normalize_visible_text(parts[1].replace("_", " ").strip())
        return tipo, lugar

    return "Desconocida", normalize_visible_text(base)


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
# Detectar columna Distrito
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
            vv = normalize_visible_text(v)
            if norm(vv) == "":
                continue
            if "?" in vv or ":" in vv:
                continue
            if len(vv) > 60:
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
            vals.add(normalize_visible_text(v))
    return sorted(list(vals), key=lambda x: strip_accents(x.lower()))


# -----------------------------
# Ubicar SI/NO
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
# Deduplicación
# =========================================================
def detect_datetime_col(header: list[str], data: list[list[str]]) -> int | None:
    if not header or not data:
        return None

    best_i = None
    best_hits = 0

    sample = data[:300]
    for j in range(len(header)):
        vals = [row[j] for row in sample if j < len(row)]
        dt = pd.to_datetime(pd.Series(vals), errors="coerce")
        hits = int(dt.notna().sum())
        if hits > best_hits:
            best_hits = hits
            best_i = j

    if best_hits >= 5:
        return best_i
    return None


def dedupe_within_minutes(header: list[str], data: list[list[str]], minutes: int = 5) -> tuple[list[list[str]], int]:
    dt_col = detect_datetime_col(header, data)
    if dt_col is None:
        return data, 0

    rows = []
    for idx, r in enumerate(data):
        raw_dt = r[dt_col] if dt_col < len(r) else ""
        dt = pd.to_datetime(raw_dt, errors="coerce")
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
# Catálogo de metas
# =========================================================
@st.cache_data
def load_catalog(path: str = "catalogo_metas.xlsx") -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=[
            "Delegacion", "Tipo", "Distrito", "Meta",
            "Delegacion_key", "Distrito_key"
        ])

    df = pd.read_excel(path)

    df["Delegacion"] = df["Delegacion"].astype(str).apply(normalize_visible_text).apply(pretty_title)
    df["Tipo"] = df["Tipo"].astype(str).apply(normalize_visible_text).apply(pretty_title)
    df["Distrito"] = df["Distrito"].astype(str).apply(normalize_visible_text).apply(pretty_title)
    df["Meta"] = pd.to_numeric(df["Meta"], errors="coerce").fillna(0).astype(int)

    df = df[df["Delegacion"].apply(norm) != ""]
    df = df[df["Tipo"].apply(norm) != ""]
    df = df[df["Distrito"].apply(norm) != ""]

    df["Delegacion_key"] = df["Delegacion"].apply(normalize_place_key)
    df["Distrito_key"] = df["Distrito"].apply(normalize_place_key)

    return df.reset_index(drop=True)


def get_catalog_df(catalogo: pd.DataFrame, delegacion: str, tipo: str) -> pd.DataFrame:
    if catalogo is None or catalogo.empty:
        return pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Distrito_key"])

    d_key = normalize_place_key(delegacion)
    t = pretty_title(tipo)

    out = catalogo[
        (catalogo["Delegacion_key"] == d_key) &
        (catalogo["Tipo"] == t)
    ].copy()

    if out.empty:
        return pd.DataFrame(columns=["Tipo", "Distrito", "Meta", "Distrito_key"])

    return out[["Tipo", "Distrito", "Meta", "Distrito_key"]].sort_values("Distrito").reset_index(drop=True)


def get_catalog_delegacion_display(catalogo: pd.DataFrame, delegacion: str) -> str:
    """
    Devuelve el nombre oficial del catálogo para mostrarlo bonito.
    Ej: si viene 'Canas' desde el archivo, devuelve 'Cañas'.
    """
    if catalogo is None or catalogo.empty:
        return pretty_title(delegacion)

    d_key = normalize_place_key(delegacion)
    m = catalogo[catalogo["Delegacion_key"] == d_key]

    if not m.empty:
        return str(m.iloc[0]["Delegacion"])

    return pretty_title(delegacion)


def merge_base_with_catalog(df_base: pd.DataFrame, df_cat: pd.DataFrame, tipo: str) -> pd.DataFrame:
    if df_base is None or df_base.empty:
        df_base = pd.DataFrame(columns=["Distrito", "SI", "NO", "Distrito_key"])
    else:
        df_base = df_base.copy()
        df_base["Distrito"] = df_base["Distrito"].apply(pretty_title)
        df_base["Distrito_key"] = df_base["Distrito"].apply(normalize_place_key)

    if df_cat is None or df_cat.empty:
        out = df_base.copy()
        out["Tipo"] = pretty_title(tipo)
        out["Meta"] = 0
        out["SI"] = pd.to_numeric(out.get("SI", 0), errors="coerce").fillna(0).astype(int)
        out["NO"] = pd.to_numeric(out.get("NO", 0), errors="coerce").fillna(0).astype(int)
        if "Distrito_key" not in out.columns:
            out["Distrito_key"] = out["Distrito"].apply(normalize_place_key)
        return out[["Tipo", "Distrito", "Meta", "SI", "NO", "Distrito_key"]].sort_values("Distrito").reset_index(drop=True)

    cat = df_cat.copy()
    if "Distrito_key" not in cat.columns:
        cat["Distrito_key"] = cat["Distrito"].apply(normalize_place_key)

    base_agg = (
        df_base.groupby("Distrito_key", as_index=False)
        .agg({
            "Distrito": "first",
            "SI": "sum",
            "NO": "sum"
        })
    )

    out = cat.merge(base_agg[["Distrito_key", "SI", "NO"]], on="Distrito_key", how="left")
    out["Tipo"] = pretty_title(tipo)
    out["Meta"] = pd.to_numeric(out["Meta"], errors="coerce").fillna(0).astype(int)
    out["SI"] = pd.to_numeric(out["SI"], errors="coerce").fillna(0).astype(int)
    out["NO"] = pd.to_numeric(out["NO"], errors="coerce").fillna(0).astype(int)

    return out[["Tipo", "Distrito", "Meta", "SI", "NO", "Distrito_key"]].sort_values("Distrito").reset_index(drop=True)


# -----------------------------
# Construir tablas base
# -----------------------------
def build_base_comunidad(header, data, col_yesno):
    dist_col = find_district_col(header, data)

    if dist_col is None:
        si = sum(1 for r in data if is_yes(r[col_yesno]))
        no = sum(1 for r in data if is_no(r[col_yesno]))
        return pd.DataFrame([{
            "Tipo": "Comunidad",
            "Distrito": "TOTAL (Delegación)",
            "Distrito_key": normalize_place_key("TOTAL (Delegación)"),
            "SI": si,
            "NO": no
        }])

    acc = {}

    for r in data:
        raw_d = r[dist_col] if dist_col < len(r) else ""
        d_show = pretty_title(raw_d)
        d_key = normalize_place_key(raw_d)

        if d_key == "":
            continue

        if "?" in str(raw_d):
            continue
        if re.match(r"^\d+\.", str(raw_d).strip()):
            continue

        if d_key not in acc:
            acc[d_key] = {"Distrito": d_show, "SI": 0, "NO": 0}

        if is_yes(r[col_yesno]):
            acc[d_key]["SI"] += 1
        elif is_no(r[col_yesno]):
            acc[d_key]["NO"] += 1

    rows = []
    for k, v in acc.items():
        rows.append({
            "Tipo": "Comunidad",
            "Distrito": v["Distrito"],
            "Distrito_key": k,
            "SI": v["SI"],
            "NO": v["NO"]
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["Tipo", "Distrito", "Distrito_key", "SI", "NO"])

    df = df.sort_values("Distrito").reset_index(drop=True)
    return df


def build_base_from_totals(tipo: str, distrito: str, si: int, no: int) -> pd.DataFrame:
    return pd.DataFrame([{
        "Tipo": pretty_title(tipo),
        "Distrito": pretty_title(distrito),
        "Distrito_key": normalize_place_key(distrito),
        "SI": int(si),
        "NO": int(no)
    }])


def apply_meta_calc_auto(df_base: pd.DataFrame, count_no_for_total: bool = False) -> pd.DataFrame:
    df = df_base.copy()
    df["Meta"] = pd.to_numeric(df.get("Meta", 0), errors="coerce").fillna(0).astype(int)
    df["SI"] = pd.to_numeric(df.get("SI", 0), errors="coerce").fillna(0).astype(int)
    df["NO"] = pd.to_numeric(df.get("NO", 0), errors="coerce").fillna(0).astype(int)

    if count_no_for_total:
        df["Contabilidad"] = (df["SI"] + df["NO"]).astype(int)
    else:
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

    keep_cols = ["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO"]
    if "Distrito_key" in df.columns:
        keep_cols.append("Distrito_key")

    return df[keep_cols]


# -----------------------------
# Tabla editable
# -----------------------------
def editable_report_table(df: pd.DataFrame, key: str, place_label: str = "Distrito") -> pd.DataFrame:
    if df is None or df.empty:
        return df

    df = df.copy()

    extra_cols = []
    if "Distrito_key" in df.columns:
        extra_cols.append("Distrito_key")

    editor_df = df[["Tipo", "Distrito", "Meta", "Contabilidad"] + extra_cols].copy()
    editor_df = editor_df.rename(columns={"Distrito": place_label})

    edited = st.data_editor(
        editor_df[["Tipo", place_label, "Meta", "Contabilidad"]],
        use_container_width=True,
        num_rows="fixed",
        key=key,
        column_config={
            "Tipo": st.column_config.TextColumn("Tipo"),
            place_label: st.column_config.TextColumn(place_label),
            "Meta": st.column_config.NumberColumn("Meta", min_value=0, step=1),
            "Contabilidad": st.column_config.NumberColumn("Contabilidad", min_value=0, step=1),
        },
        disabled=[]
    )

    edited = edited.rename(columns={place_label: "Distrito"})

    edited["Tipo"] = edited["Tipo"].astype(str)
    edited["Distrito"] = edited["Distrito"].astype(str).apply(normalize_visible_text)
    edited["Meta"] = pd.to_numeric(edited["Meta"], errors="coerce").fillna(0).astype(int)
    edited["Contabilidad"] = pd.to_numeric(edited["Contabilidad"], errors="coerce").fillna(0).astype(int)

    edited["Pendiente"] = (edited["Meta"] - edited["Contabilidad"]).clip(lower=0).astype(int)
    edited["% Avance"] = edited.apply(
        lambda r: f"{round((r['Contabilidad'] / r['Meta']) * 100):.0f}%"
        if r["Meta"] > 0 else "0%",
        axis=1
    )

    edited["SI"] = edited["Contabilidad"].astype(int)

    if "NO" in df.columns:
        edited["NO"] = pd.to_numeric(df["NO"], errors="coerce").fillna(0).astype(int).values
    else:
        edited["NO"] = 0

    if "Distrito_key" in df.columns:
        edited["Distrito_key"] = df["Distrito_key"].values
    else:
        edited["Distrito_key"] = edited["Distrito"].apply(normalize_place_key)

    show_df = edited[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente"]].copy()
    show_df = show_df.rename(columns={"Distrito": place_label})

    st.dataframe(show_df, use_container_width=True)

    return edited[["Tipo", "Distrito", "Meta", "Contabilidad", "% Avance", "Pendiente", "SI", "NO", "Distrito_key"]]


# -----------------------------
# PDF
# -----------------------------
def build_pdf_bytes(
    delegacion_label: str,
    hora_reporte: str,
    fecha_str: str,
    logo_path: str | None,
    df_com: pd.DataFrame,
    df_con: pd.DataFrame,
    df_pol: pd.DataFrame
) -> bytes:
    buff = io.BytesIO()
    doc = SimpleDocTemplate(
        buff,
        pagesize=letter,
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=28
    )
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

    def make_table(df: pd.DataFrame, place_label: str):
        cols = ["Tipo", place_label, "Meta", "Contabilidad", "% Avance", "Pendiente"]
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

        tbl = Table(
            data,
            colWidths=[62, 210, 55, 78, 58, 62],
            repeatRows=1
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return tbl

    def section(title: str, df: pd.DataFrame, place_label: str = "Distrito", keep_block: bool = False):
        if df is None or df.empty:
            block = [
                Paragraph(f"<b>{title}</b>", styles["Heading2"]),
                Spacer(1, 4),
                Paragraph("No hay registros.", styles["Normal"]),
                Spacer(1, 12),
            ]
            if keep_block:
                story.append(KeepTogether(block))
            else:
                story.extend(block)
            return

        tbl = make_table(df, place_label)

        block = [
            Paragraph(f"<b>{title}</b>", styles["Heading2"]),
            Spacer(1, 4),
            tbl,
            Spacer(1, 12),
        ]

        if keep_block:
            story.append(KeepTogether(block))
        else:
            story.extend(block)

    section("Comunidad", df_com, place_label="Distrito", keep_block=False)
    section("Comercio", df_con, place_label="Delegación", keep_block=True)
    section("Policial", df_pol, place_label="Delegación", keep_block=True)

    doc.build(story)
    buff.seek(0)
    return buff.getvalue()


# -----------------------------
# UI
# -----------------------------
st.title("📄 Reporte por Delegación (Comunidad / Comercio / Policial)")
st.caption("Metas y distritos salen automáticos desde el catálogo. Contabilidad = SI (automático).")

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

# Mapa para mostrar nombre oficial del catálogo
lugares_display_map = {}
for l in lugares:
    lugares_display_map[l] = get_catalog_delegacion_display(catalogo, l)

lugares_ordenados = sorted(lugares, key=lambda x: strip_accents(lugares_display_map[x].lower()))

delegacion_sel_raw = st.selectbox(
    "Delegación (Lugar):",
    lugares_ordenados,
    format_func=lambda x: lugares_display_map.get(x, x)
)

delegacion_sel = get_catalog_delegacion_display(catalogo, delegacion_sel_raw)

hora_reporte = st.text_input("Hora del reporte:", value="")
fecha_str = fecha_es(datetime.now())
delegacion_label = f"Delegación: {delegacion_sel}"


def pick(tipo_needed: str):
    for (fname, tipo, lugar, header, data) in parsed:
        if normalize_place_key(lugar) == normalize_place_key(delegacion_sel_raw) and tipo.lower() == tipo_needed.lower():
            return fname, header, data
    return None, None, None


fname_com, h_com, d_com = pick("Comunidad")
fname_con, h_con, d_con = pick("Comercio")
fname_pol, h_pol, d_pol = pick("Policial")


# =========================================================
# Filtros opcionales
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
# 1) Ubicar SI/NO
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
# 2) Reporte automático
# =========================================================
st.divider()
st.subheader("2) Reporte (automático)")

# -----------------------------
# Comunidad
# -----------------------------
st.markdown("### Comunidad")
df_cat_com = get_catalog_df(catalogo, delegacion_sel, "Comunidad")

if h_com and d_com and col_com is not None:
    base_com = build_base_comunidad(h_com, d_com, col_com)
else:
    base_com = pd.DataFrame(columns=["Tipo", "Distrito", "Distrito_key", "SI", "NO"])

base_com = merge_base_with_catalog(base_com, df_cat_com, "Comunidad")
df_comunidad = apply_meta_calc_auto(base_com)
df_comunidad = editable_report_table(
    df_comunidad,
    key=f"editor_comunidad_{delegacion_sel}",
    place_label="Distrito"
)

# -----------------------------
# Comercio
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
df_comercio = editable_report_table(
    df_comercio,
    key=f"editor_comercio_{delegacion_sel}",
    place_label="Delegación"
)

# -----------------------------
# Policial
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
df_policial = apply_meta_calc_auto(base_pol, count_no_for_total=True)
df_policial = editable_report_table(
    df_policial,
    key=f"editor_policial_{delegacion_sel}",
    place_label="Delegación"
)


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

st.caption(
    "Listo: ahora la app compara por clave robusta y muestra el nombre oficial del catálogo. "
    "Ejemplos: Cañas, Pará, San José de la Montaña, La Ribera, Uruca y Zapote."
)

