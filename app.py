# ================================ PARTE 1 / 5 ============================================
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

# =========================================================
# ✅ PRECARGA METAS + DISTRITOS (D1 a D59)
# - (Tu bloque D1 a D29 va EXACTO como lo pegaste)
# - ✅ Aquí agrego al final 10 delegaciones más (Barva, Santo Domingo, Santa Barbara,
#   San Rafael, San Isidro, Belen, Flores, San Pablo, Liberia, Nicoya) con sus metas.
# =========================================================
METAS_PRELOAD = [
    # --- D1 Carmen ---
    {"Tipo":"Comunidad","Delegación":"Carmen","Cantón_real":"San José","Distrito":"Carmen","Meta":338},
    {"Tipo":"Comercio","Delegación":"Carmen","Cantón_real":"San José","Distrito":"Carmen","Meta":201},
    {"Tipo":"Policial","Delegación":"Carmen","Cantón_real":"San José","Distrito":"Carmen","Meta":None},

    # --- D2 Merced ---
    {"Tipo":"Comunidad","Delegación":"Merced","Cantón_real":"San José","Distrito":"Merced","Meta":375},
    {"Tipo":"Comercio","Delegación":"Merced","Cantón_real":"San José","Distrito":"Merced","Meta":229},
    {"Tipo":"Policial","Delegación":"Merced","Cantón_real":"San José","Distrito":"Merced","Meta":None},

    # --- D3 Hospital ---
    {"Tipo":"Comunidad","Delegación":"Hospital","Cantón_real":"San José","Distrito":"Hospital","Meta":379},
    {"Tipo":"Comercio","Delegación":"Hospital","Cantón_real":"San José","Distrito":"Hospital","Meta":254},
    {"Tipo":"Policial","Delegación":"Hospital","Cantón_real":"San José","Distrito":"Hospital","Meta":None},

    # --- D4 Catedral ---
    {"Tipo":"Comunidad","Delegación":"Catedral","Cantón_real":"San José","Distrito":"Catedral","Meta":375},
    {"Tipo":"Comercio","Delegación":"Catedral","Cantón_real":"San José","Distrito":"Catedral","Meta":226},
    {"Tipo":"Policial","Delegación":"Catedral","Cantón_real":"San José","Distrito":"Catedral","Meta":None},

    # --- D5 San Sebastian ---
    {"Tipo":"Comunidad","Delegación":"San Sebastian","Cantón_real":"San José","Distrito":"San Sebastian","Meta":381},
    {"Tipo":"Comercio","Delegación":"San Sebastian","Cantón_real":"San José","Distrito":"San Sebastian","Meta":153},
    {"Tipo":"Policial","Delegación":"San Sebastian","Cantón_real":"San José","Distrito":"San Sebastian","Meta":None},

    # --- D6 Hatillo ---
    {"Tipo":"Comunidad","Delegación":"Hatillo","Cantón_real":"San José","Distrito":"Hatillo","Meta":382},
    {"Tipo":"Comercio","Delegación":"Hatillo","Cantón_real":"San José","Distrito":"Hatillo","Meta":117},
    {"Tipo":"Policial","Delegación":"Hatillo","Cantón_real":"San José","Distrito":"Hatillo","Meta":None},

    # --- D7 Zapote ---
    {"Tipo":"Comunidad","Delegación":"Zapote","Cantón_real":"San José","Distrito":"Zapote","Meta":185},
    {"Tipo":"Comunidad","Delegación":"Zapote","Cantón_real":"San José","Distrito":"San Francisco de Dos Rios","Meta":198},
    {"Tipo":"Comercio","Delegación":"Zapote","Cantón_real":"San José","Distrito":"Zapote/San Francisco","Meta":226},
    {"Tipo":"Policial","Delegación":"Zapote","Cantón_real":"San José","Distrito":"Zapote/San Francisco","Meta":None},

    # --- D8 Pavas ---
    {"Tipo":"Comunidad","Delegación":"Pavas","Cantón_real":"San José","Distrito":"Pavas","Meta":383},
    {"Tipo":"Comercio","Delegación":"Pavas","Cantón_real":"San José","Distrito":"Pavas","Meta":244},
    {"Tipo":"Policial","Delegación":"Pavas","Cantón_real":"San José","Distrito":"Pavas","Meta":None},

    # --- D9 Uruca ---
    {"Tipo":"Comunidad","Delegación":"Uruca","Cantón_real":"San José","Distrito":"Uruca","Meta":311},
    {"Tipo":"Comunidad","Delegación":"Uruca","Cantón_real":"San José","Distrito":"Mata redonda","Meta":71},
    {"Tipo":"Comercio","Delegación":"Uruca","Cantón_real":"San José","Distrito":"Uruca","Meta":272},
    {"Tipo":"Policial","Delegación":"Uruca","Cantón_real":"San José","Distrito":"Uruca","Meta":None},

    # --- D10 Curridabat ---
    {"Tipo":"Comunidad","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Curridabat","Meta":147},
    {"Tipo":"Comunidad","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Granadilla","Meta":93},
    {"Tipo":"Comunidad","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Sanchez","Meta":33},
    {"Tipo":"Comunidad","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Tirrases","Meta":109},
    {"Tipo":"Comercio","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Curridabat","Meta":235},
    {"Tipo":"Policial","Delegación":"Curridabat","Cantón_real":"Curridabat","Distrito":"Curridabat","Meta":None},

    # --- D11 Montes de Oca ---
    {"Tipo":"Comunidad","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"San Pedro","Meta":168},
    {"Tipo":"Comunidad","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"Sabanilla","Meta":88},
    {"Tipo":"Comunidad","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"Mercedes","Meta":38},
    {"Tipo":"Comunidad","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"San Rafael","Meta":88},
    {"Tipo":"Comercio","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"Montes de Oca","Meta":261},
    {"Tipo":"Policial","Delegación":"Montes de Oca","Cantón_real":"Montes de Oca","Distrito":"Montes de Oca","Meta":None},

    # --- D12 Goicoechea ---
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Guadalupe","Meta":57},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"San Francisco","Meta":7},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Calle Blancos","Meta":64},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Mata Platano","Meta":58},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Ipis","Meta":88},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Rancho Redondo","Meta":9},
    {"Tipo":"Comunidad","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Purral","Meta":100},
    {"Tipo":"Comercio","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Goicoechea","Meta":246},
    {"Tipo":"Policial","Delegación":"Goicoechea","Cantón_real":"Goicoechea","Distrito":"Goicoechea","Meta":None},

    # --- D13 Moravia ---
    {"Tipo":"Comunidad","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"San Vicente","Meta":177},
    {"Tipo":"Comunidad","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"San Jeronimo","Meta":45},
    {"Tipo":"Comunidad","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"Paracito","Meta":17},
    {"Tipo":"Comunidad","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"Trinidad","Meta":142},
    {"Tipo":"Comercio","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"Moravia","Meta":184},
    {"Tipo":"Policial","Delegación":"Moravia","Cantón_real":"Moravia","Distrito":"Moravia","Meta":None},

    # --- D14 Tibas ---
    {"Tipo":"Comunidad","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"San Juan","Meta":109},
    {"Tipo":"Comunidad","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Cinco Esquinas","Meta":39},
    {"Tipo":"Comunidad","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Anaselmo Llorente","Meta":58},
    {"Tipo":"Comunidad","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Leon XIII","Meta":95},
    {"Tipo":"Comunidad","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Colima","Meta":82},
    {"Tipo":"Comercio","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Tibas","Meta":210},
    {"Tipo":"Policial","Delegación":"Tibas","Cantón_real":"Tibas","Distrito":"Tibas","Meta":None},

    # --- D15 Coronado ---
    {"Tipo":"Comunidad","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"San Isidro","Meta":92},
    {"Tipo":"Comunidad","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"San Rafael","Meta":46},
    {"Tipo":"Comunidad","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"Dulce Nombre","Meta":65},
    {"Tipo":"Comunidad","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"Patalillo","Meta":133},
    {"Tipo":"Comunidad","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"Cascajal","Meta":46},
    {"Tipo":"Comercio","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"Coronado","Meta":159},
    {"Tipo":"Policial","Delegación":"Coronado","Cantón_real":"Vazquez de Coronado","Distrito":"Coronado","Meta":None},

    # --- D16 Desamparados Norte ---
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Desamparados","Meta":83},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Patarrá","Meta":35},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Damas","Meta":37},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Gravilias","Meta":40},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"San Juan de Dios","Meta":58},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"San Rafael Arriba","Meta":43},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"San Rafael Abajo","Meta":60},
    {"Tipo":"Comunidad","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"San Antonio","Meta":27},
    {"Tipo":"Comercio","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Desamparados N","Meta":217},
    {"Tipo":"Policial","Delegación":"Desamparados Norte","Cantón_real":"Desamparados","Distrito":"Desamparados N","Meta":None},

    # --- D17 Desamparados Sur ---
    {"Tipo":"Comunidad","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"San Cristobal","Meta":21},
    {"Tipo":"Comunidad","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"Rosario","Meta":17},
    {"Tipo":"Comunidad","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"Los Guido","Meta":145},
    {"Tipo":"Comunidad","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"Frailes","Meta":21},
    {"Tipo":"Comunidad","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"San Miguel","Meta":179},
    {"Tipo":"Comercio","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"Desamparados S","Meta":93},
    {"Tipo":"Policial","Delegación":"Desamparados Sur","Cantón_real":"Desamparados","Distrito":"Desamparados S","Meta":None},

    # --- D18 Aserri ---
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Aserri","Meta":176},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Tarbaca","Meta":10},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Vuelta Jorco","Meta":44},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"San Gabriel","Meta":41},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Legua","Meta":10},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Monterrey","Meta":4},
    {"Tipo":"Comunidad","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Salitrillos","Meta":96},
    {"Tipo":"Comercio","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Aserri","Meta":159},
    {"Tipo":"Policial","Delegación":"Aserri","Cantón_real":"Aserri","Distrito":"Aserri","Meta":None},

    # --- D19 Acosta ---
    {"Tipo":"Comunidad","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"San Ignacio","Meta":157},
    {"Tipo":"Comunidad","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Guaitil","Meta":47},
    {"Tipo":"Comunidad","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Palmichal","Meta":92},
    {"Tipo":"Comunidad","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Cangrejal","Meta":36},
    {"Tipo":"Comunidad","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Sabanillas","Meta":46},
    {"Tipo":"Comercio","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Acosta","Meta":159},
    {"Tipo":"Policial","Delegación":"Acosta","Cantón_real":"Acosta","Distrito":"Acosta","Meta":None},

    # =====================================================
    # ✅ NUEVAS (D20 a D29)
    # =====================================================

    # --- D20 Alajuelita ---
    {"Tipo":"Comunidad","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"Alajuelita","Meta":49},
    {"Tipo":"Comunidad","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"San Josecito","Meta":52},
    {"Tipo":"Comunidad","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"San Antonio","Meta":24},
    {"Tipo":"Comunidad","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"Concepcion","Meta":33},
    {"Tipo":"Comunidad","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"San Felipe","Meta":165},
    {"Tipo":"Comercio","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"Alajuelita","Meta":159},
    {"Tipo":"Policial","Delegación":"Alajuelita","Cantón_real":"Alajuelita","Distrito":"Alajuelita","Meta":None},

    # --- D21 Escazu ---
    {"Tipo":"Comunidad","Delegación":"Escazu","Cantón_real":"Escazu","Distrito":"Escazu","Meta":70},
    {"Tipo":"Comunidad","Delegación":"Escazu","Cantón_real":"Escazu","Distrito":"San Antonio","Meta":154},
    {"Tipo":"Comunidad","Delegación":"Escazu","Cantón_real":"Escazu","Distrito":"San Rafael","Meta":159},
    {"Tipo":"Comercio","Delegación":"Escazu","Cantón_real":"Escazu","Distrito":"Escazu","Meta":287},
    {"Tipo":"Policial","Delegación":"Escazu","Cantón_real":"Escazu","Distrito":"Escazu","Meta":None},

    # --- D22 Santa Ana ---
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Santa Ana","Meta":75},
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Salitral","Meta":36},
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Pozos","Meta":128},
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Uruca","Meta":57},
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Piedades","Meta":65},
    {"Tipo":"Comunidad","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Brasil","Meta":21},
    {"Tipo":"Comercio","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Santa Ana","Meta":227},
    {"Tipo":"Policial","Delegación":"Santa Ana","Cantón_real":"Santa Ana","Distrito":"Santa Ana","Meta":None},

    # --- D23 Mora ---
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Colon","Meta":205},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Guayabo","Meta":58},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Tabarcia","Meta":48},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Piedras Negras","Meta":7},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Picagres","Meta":13},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Quitirrisí","Meta":29},
    {"Tipo":"Comunidad","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Jaris","Meta":21},
    {"Tipo":"Comercio","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Mora","Meta":77},
    {"Tipo":"Policial","Delegación":"Mora","Cantón_real":"Mora","Distrito":"Mora","Meta":None},

    # --- D24 Puriscal ---
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Santiago","Meta":120},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Mercedes Sur","Meta":71},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Barbacoas","Meta":45},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Grifo Alto","Meta":15},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"San Rafael","Meta":20},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Candelaria","Meta":18},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Desamparaditos","Meta":8},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"San Antonio","Meta":47},
    {"Tipo":"Comunidad","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Chires","Meta":36},
    {"Tipo":"Comercio","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Puriscal","Meta":98},
    {"Tipo":"Policial","Delegación":"Puriscal","Cantón_real":"Puriscal","Distrito":"Puriscal","Meta":None},

    # --- D25 Turrubares ---
    {"Tipo":"Comunidad","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"San Pablo","Meta":78},
    {"Tipo":"Comunidad","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"San Pedro","Meta":45},
    {"Tipo":"Comunidad","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"San Juan de Mata","Meta":82},
    {"Tipo":"Comunidad","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"San Luis","Meta":38},
    {"Tipo":"Comunidad","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"Carara","Meta":122},
    {"Tipo":"Comercio","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"Turrubares","Meta":9},
    {"Tipo":"Policial","Delegación":"Turrubares","Cantón_real":"Turrubares","Distrito":"Turrubares","Meta":None},

    # --- D26 Alajuela Sur ---
    {"Tipo":"Comunidad","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"Guacima","Meta":93},
    {"Tipo":"Comunidad","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"Turrucares","Meta":31},
    {"Tipo":"Comunidad","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"San Rafael","Meta":118},
    {"Tipo":"Comunidad","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"Garita","Meta":33},
    {"Tipo":"Comunidad","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"San Antonio","Meta":109},
    {"Tipo":"Comercio","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"Alajuela S","Meta":219},
    {"Tipo":"Policial","Delegación":"Alajuela Sur","Cantón_real":"Alajuela","Distrito":"Alajuela S","Meta":None},

    # --- D27 Alajuela Norte ---
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Alajuela","Meta":84},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Carrizal","Meta":17},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"San Jose","Meta":100},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"San Isidro","Meta":43},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Sabanilla","Meta":24},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Rio Segundo","Meta":26},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Desamparados","Meta":63},
    {"Tipo":"Comunidad","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Tambor","Meta":28},
    {"Tipo":"Comercio","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Alajuela N","Meta":300},
    {"Tipo":"Policial","Delegación":"Alajuela Norte","Cantón_real":"Alajuela","Distrito":"Alajuela N","Meta":None},

    # --- D28 San Ramon ---
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Ramon","Meta":43},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Santiago","Meta":29},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Juan","Meta":67},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Piedades Norte","Meta":49},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Piedades Sur","Meta":23},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Rafael","Meta":56},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Isidro","Meta":30},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Angeles","Meta":13},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Alfaro","Meta":43},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Volio","Meta":14},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Concepcion","Meta":13},
    {"Tipo":"Comunidad","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"Zapotal","Meta":3},
    {"Tipo":"Comercio","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Ramon","Meta":213},
    {"Tipo":"Policial","Delegación":"San Ramon","Cantón_real":"San Ramon","Distrito":"San Ramon","Meta":None},

    # --- D29 Grecia ---
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Grecia","Meta":73},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"San Isidro","Meta":36},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"San Jose","Meta":50},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"San Roque","Meta":66},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Tacares","Meta":49},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Puente de Piedra","Meta":65},
    {"Tipo":"Comunidad","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Bolivar","Meta":44},
    {"Tipo":"Comercio","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Grecia","Meta":230},
    {"Tipo":"Policial","Delegación":"Grecia","Cantón_real":"Grecia","Distrito":"Grecia","Meta":None},

    # =====================================================
    # ✅ NUEVAS 10 DELEGACIONES (D50 a D59) — MISMA DINÁMICA
    # =====================================================

    # --- D50 Barva ---
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"Barva","Meta":37},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"San Pedro","Meta":58},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"San Pablo","Meta":81},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"San Roque","Meta":44},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"Puente Salas","Meta":38},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"Santa Lucia","Meta":68},
    {"Tipo":"Comunidad","Delegación":"Barva","Cantón_real":"Barva","Distrito":"San Jose de la Montaña","Meta":56},
    {"Tipo":"Comercio","Delegación":"Barva","Cantón_real":"Barva","Distrito":"Barva","Meta":107},
    {"Tipo":"Policial","Delegación":"Barva","Cantón_real":"Barva","Distrito":"Barva","Meta":None},

    # --- D51 Santo Domingo ---
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Santo Domingo","Meta":38},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"San Vicente","Meta":66},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"San Miguel","Meta":65},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Santo Tomas","Meta":65},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Santa Rosa","Meta":76},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Tures","Meta":37},
    {"Tipo":"Comunidad","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Para","Meta":35},
    {"Tipo":"Comercio","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Santo Domingo","Meta":172},
    {"Tipo":"Policial","Delegación":"Santo Domingo","Cantón_real":"Santo Domingo","Distrito":"Santo Domingo","Meta":None},

    # --- D52 Santa Barbara ---
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Santa Barbara","Meta":52},
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"San Pedro","Meta":61},
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"San Juan","Meta":83},
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Jesus","Meta":103},
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Santo Domingo","Meta":32},
    {"Tipo":"Comunidad","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Puraba","Meta":49},
    {"Tipo":"Comercio","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Santa Barbara","Meta":150},
    {"Tipo":"Policial","Delegación":"Santa Barbara","Cantón_real":"Santa Barbara","Distrito":"Santa Barbara","Meta":None},

    # --- D53 San Rafael ---
    {"Tipo":"Comunidad","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"San Rafael","Meta":69},
    {"Tipo":"Comunidad","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"San Josecito","Meta":98},
    {"Tipo":"Comunidad","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"Santiago","Meta":72},
    {"Tipo":"Comunidad","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"Angeles","Meta":90},
    {"Tipo":"Comunidad","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"Concepcion","Meta":54},
    {"Tipo":"Comercio","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"San Rafael","Meta":108},
    {"Tipo":"Policial","Delegación":"San Rafael","Cantón_real":"San Rafael","Distrito":"San Rafael","Meta":None},

    # --- D54 San Isidro ---
    {"Tipo":"Comunidad","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"San Isidro","Meta":98},
    {"Tipo":"Comunidad","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"San Jose","Meta":145},
    {"Tipo":"Comunidad","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"Concepcion","Meta":50},
    {"Tipo":"Comunidad","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"San Francisco","Meta":86},
    {"Tipo":"Comercio","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"San Isidro","Meta":92},
    {"Tipo":"Policial","Delegación":"San Isidro","Cantón_real":"San Isidro","Distrito":"San Isidro","Meta":None},

    # --- D55 Belen ---
    {"Tipo":"Comunidad","Delegación":"Belen","Cantón_real":"Belen","Distrito":"San Antonio","Meta":158},
    {"Tipo":"Comunidad","Delegación":"Belen","Cantón_real":"Belen","Distrito":"Ribera","Meta":113},
    {"Tipo":"Comunidad","Delegación":"Belen","Cantón_real":"Belen","Distrito":"Asuncion","Meta":108},
    {"Tipo":"Comercio","Delegación":"Belen","Cantón_real":"Belen","Distrito":"Belen","Meta":173},
    {"Tipo":"Policial","Delegación":"Belen","Cantón_real":"Belen","Distrito":"Belen","Meta":None},

    # --- D56 Flores ---
    {"Tipo":"Comunidad","Delegación":"Flores","Cantón_real":"Flores","Distrito":"San Joaquin","Meta":133},
    {"Tipo":"Comunidad","Delegación":"Flores","Cantón_real":"Flores","Distrito":"Barrantes","Meta":41},
    {"Tipo":"Comunidad","Delegación":"Flores","Cantón_real":"Flores","Distrito":"Llorente","Meta":204},
    {"Tipo":"Comercio","Delegación":"Flores","Cantón_real":"Flores","Distrito":"Flores","Meta":112},
    {"Tipo":"Policial","Delegación":"Flores","Cantón_real":"Flores","Distrito":"Flores","Meta":None},

    # --- D57 San Pablo ---
    {"Tipo":"Comunidad","Delegación":"San Pablo","Cantón_real":"San Pablo","Distrito":"San Pablo","Meta":252},
    {"Tipo":"Comunidad","Delegación":"San Pablo","Cantón_real":"San Pablo","Distrito":"Rincon de Sabanilla","Meta":128},
    {"Tipo":"Comercio","Delegación":"San Pablo","Cantón_real":"San Pablo","Distrito":"San Pablo","Meta":86},
    {"Tipo":"Policial","Delegación":"San Pablo","Cantón_real":"San Pablo","Distrito":"San Pablo","Meta":None},

    # --- D58 Liberia ---
    {"Tipo":"Comunidad","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Liberia","Meta":322},
    {"Tipo":"Comunidad","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Cañas Dulces","Meta":20},
    {"Tipo":"Comunidad","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Mayorga","Meta":10},
    {"Tipo":"Comunidad","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Nacascolo","Meta":15},
    {"Tipo":"Comunidad","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Curubande","Meta":16},
    {"Tipo":"Comercio","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Liberia","Meta":191},
    {"Tipo":"Policial","Delegación":"Liberia","Cantón_real":"Liberia","Distrito":"Liberia","Meta":None},

    # --- D59 Nicoya ---
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Nicoya","Meta":177},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Mansion","Meta":35},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"San Antonio","Meta":46},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Quebrada Honda","Meta":16},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Samara","Meta":33},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Nosara","Meta":54},
    {"Tipo":"Comunidad","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Belen de Nosarita","Meta":20},
    {"Tipo":"Comercio","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Nicoya","Meta":132},
    {"Tipo":"Policial","Delegación":"Nicoya","Cantón_real":"Nicoya","Distrito":"Nicoya","Meta":None},
]
# ================================ PARTE 2 / 5 ============================================
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

def fecha_es(dtobj: dt.date) -> str:
    dias = {"Monday":"lunes","Tuesday":"martes","Wednesday":"miércoles","Thursday":"jueves","Friday":"viernes","Saturday":"sábado","Sunday":"domingo"}
    meses = {"January":"enero","February":"febrero","March":"marzo","April":"abril","May":"mayo","June":"junio","July":"julio","August":"agosto",
             "September":"septiembre","October":"octubre","November":"noviembre","December":"diciembre"}
    f = dtobj.strftime("%A, %d de %B de %Y")
    f = f.replace(dtobj.strftime("%A"), dias.get(dtobj.strftime("%A"), dtobj.strftime("%A")))
    f = f.replace(dtobj.strftime("%B"), meses.get(dtobj.strftime("%B"), dtobj.strftime("%B")))
    return f

def fmt_pct(x):
    try:
        return f"{x:.0f}%"
    except Exception:
        return ""

def best_match(raw: str, candidates: list[str], cutoff=0.78) -> str | None:
    if not raw:
        return None
    key = norm(raw)
    mp = {norm(x): x for x in candidates}
    if key in mp:
        return mp[key]
    m = difflib.get_close_matches(key, list(mp.keys()), n=1, cutoff=cutoff)
    return mp[m[0]] if m else None

def norm_yes_no(v) -> str | None:
    nv = norm(v)
    if nv in ("si", "sí"):
        return "SI"
    if nv == "no":
        return "NO"
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

def choose_deleg_col(cols):
    preferred = ["delegacion", "delegación", "canton", "cantón", "delegacion (label)", "cantón (label)"]
    found = pick_col(cols, preferred)
    if found:
        return found
    for c in cols:
        nc = norm(c)
        if "delegacion" in nc or "delegación" in nc or "canton" in nc or "cantón" in nc:
            return c
    return None

def choose_district_col(cols):
    preferred = [
        "distrito_label", "district_label", "nombre distrito", "distrito_nombre",
        "distrito (label)", "distrito (texto)", "distrito", "district"
    ]
    found = pick_col(cols, preferred)
    if found:
        return found
    for c in cols:
        nc = norm(c)
        if "distrito" in nc or "district" in nc:
            return c
    return None

@st.cache_data(show_spinner=False)
def load_metas_precargadas() -> pd.DataFrame:
    df = pd.DataFrame(METAS_PRELOAD).copy()
    for c in ["Tipo","Delegación","Cantón_real","Distrito"]:
        df[c] = df[c].astype(str).str.strip()
    return df

def build_catalog_from_metas(df_metas: pd.DataFrame) -> dict:
    out = {}
    tmp = df_metas[df_metas["Tipo"].isin(["Comunidad","Comercio"])].copy()
    for _, r in tmp.iterrows():
        key = norm(r["Delegación"])
        out.setdefault(key, set()).add(str(r["Distrito"]).strip())
    return {k: sorted(list(v), key=lambda x: norm(x)) for k, v in out.items()}

def ubicar_distrito(deleg: str, texto: str, catalog: dict) -> str | None:
    k = norm(deleg)
    distritos = catalog.get(k, [])
    if not distritos:
        return None

    # exacto
    t = norm(texto)
    for d in distritos:
        if norm(d) == t:
            return d

    # contiene
    for d in distritos:
        nd = norm(d)
        if nd and nd in t:
            return d

    # fuzzy
    fm = best_match(texto, distritos, cutoff=0.78)
    return fm

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
.smallnote { text-align:center; margin-top: 8px; font-size: 13px; font-weight: 800; }
</style>
"""

# =========================
# Imagen PNG del cuadro
# =========================
def build_table_image_png(title: str, distritos: list, df_full: pd.DataFrame, tipos_order: list,
                          fecha_txt: str, hora_manual: str, no_total: int) -> bytes:
    headers = ["Tipo", "Distrito", "Meta", "Contabilizado (SI)", "% Avance", "Pendiente"]

    rows = []
    row_kind = []
    for d in distritos:
        rows.append(["", d, "", "", "", ""])
        row_kind.append("section")
        sub = df_full[df_full["Distrito"] == d]
        for t in tipos_order:
            r = sub[sub["Tipo"] == t].iloc[0]
            meta = "" if pd.isna(r["Meta"]) or r["Meta"] is None else str(int(r["Meta"]))
            pct = "" if pd.isna(r["% Avance"]) or r["% Avance"] is None else fmt_pct(r["% Avance"])
            pend = "" if pd.isna(r["Pendiente"]) or r["Pendiente"] is None else str(int(r["Pendiente"]))
            rows.append([t, d, meta, str(int(r["Contabilizado"])), pct, pend])
            row_kind.append("data")

    nrows = len(rows) + 1
    fig_w = 14.5
    fig_h = max(4.5, nrows * 0.28)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.axis("off")

    ax.set_title(f"Seguimiento de Encuestas\n{title}", fontsize=18, fontweight="bold", pad=18)

    table = ax.table(cellText=rows, colLabels=headers, loc="upper center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.35)

    header_bg = "#e6e6e6"
    section_bg = "#d9d9d9"
    pct_bg = "#29a36a"
    pending_bg = "#6d8fc9"
    white = "#ffffff"

    col_widths = [0.18, 0.28, 0.12, 0.18, 0.12, 0.12]
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

    footer = f"{fecha_txt}  |  Hora del corte: {hora_manual if hora_manual else '—'}   |   NO (rechazaron): {no_total}"
    fig.text(0.5, 0.01, footer, ha="center", va="bottom", fontsize=10)

    out = io.BytesIO()
    plt.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()
    # ================================ PARTE 3 / 5 ============================================
# =========================
# Sidebar
# =========================
st.sidebar.header("📥 Carga (Excels separados)")
f_com = st.sidebar.file_uploader("Excel Comunidad", type=["xlsx", "xls"], key="f_com")
f_eco = st.sidebar.file_uploader("Excel Comercio", type=["xlsx", "xls"], key="f_eco")
f_pol = st.sidebar.file_uploader("Excel Policial", type=["xlsx", "xls"], key="f_pol")

st.sidebar.divider()
hora_manual = st.sidebar.text_input("Hora del corte (manual)", value="")
incluir_no_identificado = st.sidebar.checkbox("Incluir NO_IDENTIFICADO", value=False)

if not (f_com and f_eco and f_pol):
    st.info("Subí los 3 Excels: Comunidad + Comercio + Policial.")
    st.stop()

# =========================
# Metas + catálogo interno
# =========================
metas = load_metas_precargadas()
catalog = build_catalog_from_metas(metas)

delegaciones_pretty = sorted(metas["Delegación"].unique().tolist(), key=lambda x: norm(x))

# =========================
# Preparar archivo (SI/NO + delegación + distrito)
# =========================
def prep_file(file, tipo_label: str):
    df = read_any_excel(file)
    cols = list(df.columns)

    col_consent = choose_consent_col(cols)
    if not col_consent:
        raise ValueError(f"[{tipo_label}] No encontré columna de consentimiento (Acepta participar...).")

    col_deleg = choose_deleg_col(cols)
    if not col_deleg:
        raise ValueError(f"[{tipo_label}] No encontré columna de Cantón/Delegación.")

    df["_Consent_"] = df[col_consent].apply(norm_yes_no)
    df["_DelegRaw_"] = df[col_deleg].astype(str).str.strip()

    # corregir delegación por similitud con las precargadas
    df["_Deleg_"] = df["_DelegRaw_"].apply(lambda x: best_match(x, delegaciones_pretty, cutoff=0.75) or str(x).strip())

    if tipo_label == "Policial":
        df["_Distrito_"] = "SIN_DISTRITO"
    else:
        col_dist = choose_district_col(cols)
        if not col_dist:
            raise ValueError(f"[{tipo_label}] No encontré columna de Distrito.")
        df["_DistRaw_"] = df[col_dist].astype(str).str.strip()

        def resolver(row):
            cand = row["_DistRaw_"]
            if cand is None:
                return None
            cand = str(cand).strip()
            if cand == "" or cand.lower() in ("nan", "none"):
                return None
            mapped = ubicar_distrito(row["_Deleg_"], cand, catalog)
            return mapped if mapped else "NO_IDENTIFICADO"

        df["_Distrito_"] = df.apply(resolver, axis=1)

    df["_Tipo_"] = tipo_label
    df = df.dropna(subset=["_Consent_", "_Deleg_", "_Distrito_"])

    return df[["_Tipo_", "_Deleg_", "_Distrito_", "_Consent_"]].rename(
        columns={"_Tipo_":"Tipo","_Deleg_":"Delegación","_Distrito_":"Distrito","_Consent_":"Consent"}
    )

data, errs = [], []
try:
    data.append(prep_file(f_com, "Comunidad"))
except Exception as e:
    errs.append(str(e))
try:
    data.append(prep_file(f_eco, "Comercio"))
except Exception as e:
    errs.append(str(e))
try:
    data.append(prep_file(f_pol, "Policial"))
except Exception as e:
    errs.append(str(e))

if errs:
    st.error("Errores:\n\n- " + "\n- ".join(errs))
    st.stop()

base = pd.concat(data, ignore_index=True)

# NO total (rechazaron)
no_total = int((base["Consent"] == "NO").sum())

# solo SI contabiliza
base_si = base[base["Consent"] == "SI"].copy()

agg = base_si.groupby(["Tipo","Delegación","Distrito"]).size().reset_index(name="Contabilizado")

# =========================
# Selector delegación
# =========================
sel_deleg = st.sidebar.selectbox("Delegación para el cuadro", delegaciones_pretty, index=0)

metas_deleg = metas[metas["Delegación"] == sel_deleg].copy()
agg_deleg = agg[agg["Delegación"] == sel_deleg].copy()

# distritos base (ordenados desde metas)
distritos = sorted(metas_deleg["Distrito"].unique().tolist(), key=lambda x: norm(x))
if not incluir_no_identificado:
    distritos = [d for d in distritos if d != "NO_IDENTIFICADO"]

tipos_order = ["Comunidad", "Comercio", "Policial"]

# construir df_full (1 fila por distrito-tipo) basado en metas
rows = []
for d in distritos:
    for t in tipos_order:
        meta_row = metas_deleg[(metas_deleg["Distrito"] == d) & (metas_deleg["Tipo"] == t)]
        meta_val = meta_row["Meta"].iloc[0] if len(meta_row) else None

        cnt = int(agg_deleg[(agg_deleg["Distrito"] == d) & (agg_deleg["Tipo"] == t)]["Contabilizado"].sum())

        if meta_val is None or pd.isna(meta_val) or float(meta_val) == 0:
            avance = None
            pendiente = None
        else:
            meta_int = int(meta_val)
            pendiente = max(meta_int - cnt, 0)
            avance = (cnt / meta_int * 100) if meta_int else None

        rows.append({"Distrito": d, "Tipo": t, "Meta": meta_val, "Contabilizado": cnt, "% Avance": avance, "Pendiente": pendiente})

df_full = pd.DataFrame(rows)
# ================================ PARTE 4 / 5 ============================================
# =========================
# Render HTML (UN SOLO CUADRO)
# =========================
fecha_txt = fecha_es(dt.date.today())

tbody = ""
for d in distritos:
    tbody += f'<tr class="section-row"><td colspan="6">{safe_html(d)}</td></tr>'
    sub = df_full[df_full["Distrito"] == d]
    for t in tipos_order:
        r = sub[sub["Tipo"] == t].iloc[0]

        meta_txt = "—" if pd.isna(r["Meta"]) or r["Meta"] is None else str(int(r["Meta"]))
        cnt_txt = str(int(r["Contabilizado"]))
        pct_txt = "—" if pd.isna(r["% Avance"]) or r["% Avance"] is None else fmt_pct(r["% Avance"])
        pend_txt = "—" if pd.isna(r["Pendiente"]) or r["Pendiente"] is None else str(int(r["Pendiente"]))

        tbody += f"""
        <tr>
          <td><b>{safe_html(t)}</b></td>
          <td>{safe_html(d)}</td>
          <td class="meta">{safe_html(meta_txt)}</td>
          <td class="count">{safe_html(cnt_txt)}</td>
          <td class="pct">{safe_html(pct_txt)}</td>
          <td class="pending">{safe_html(pend_txt)}</td>
        </tr>
        """

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
            <th style="width:18%">Tipo</th>
            <th style="width:28%">Distrito</th>
            <th style="width:12%; text-align:center;">Meta</th>
            <th style="width:18%; text-align:center;">Contabilizado (SI)</th>
            <th style="width:12%; text-align:center;">% Avance</th>
            <th style="width:12%; text-align:center;">Pendiente</th>
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
      <div class="smallnote"><b>NO (rechazaron la encuesta):</b> {no_total}</div>
    </div>
  </div>
</body>
</html>
"""

height = min(320 + len(distritos) * 155, 2400)
components.html(html_doc, height=height, scrolling=True)
# ================================ PARTE 5 / 5 ============================================
# =========================
# Descargas (PNG + Excel)
# =========================
st.divider()
col1, col2 = st.columns(2)

with col1:
    png_bytes = build_table_image_png(sel_deleg, distritos, df_full, tipos_order, fecha_txt, hora_manual, no_total)
    st.download_button(
        label="📷 Descargar cuadro como imagen (PNG)",
        data=png_bytes,
        file_name=f"cuadro_encuestas_{sel_deleg}.png".replace(" ", "_"),
        mime="image/png",
        use_container_width=True
    )

with col2:
    detalle = df_full.copy()
    detalle["Delegación"] = sel_deleg
    detalle = detalle[["Delegación","Tipo","Distrito","Meta","Contabilizado","% Avance","Pendiente"]].copy()
    detalle["% Avance"] = pd.to_numeric(detalle["% Avance"], errors="coerce").round(1)
    excel_bytes = to_excel_bytes(detalle, sheet_name="seguimiento")
    st.download_button(
        label="⬇️ Descargar seguimiento (Excel)",
        data=excel_bytes,
        file_name=f"seguimiento_{sel_deleg}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
