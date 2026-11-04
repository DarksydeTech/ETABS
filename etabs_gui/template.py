"""Datos iniciales del proyecto ETABS CIXTOP.

Estos valores reproducen la plantilla ``ETABS-CIXTOP 4.0`` (hoja PROYECTO) y
viven en Python: la aplicación no abre ni necesita el libro de Excel.
"""
from __future__ import annotations

import math

APP_NAME = "ETABS CIXTOP"
APP_VERSION = "5.0"

# --- Parámetros generales -------------------------------------------------

DEFAULT_PROJECT = {
    "name": 'PROYECTO "EL ROWI"',
    "description": "Sistema de porticos de 10 pisos",
    "stories_count": 12,
    "typical_height": 2.8,
    "first_height": 3.0,
}

DEFAULT_GRID_X = {
    "spacing": 3.0,
    "coords": [0.0, 4.0, 8.5],
}

DEFAULT_GRID_Y = {
    "spacing": 2.0,
    "coords": [0.0, 2.7, 5.9, 8.7, 11.7],
}

# Grillas inclinadas tipo 1: (x1 en y_min, x2 en y_max)
DEFAULT_INCLINED_X = [{"id": "I1", "start": 11.5, "end": 12.5}]
# Grillas inclinadas tipo 2: (y1 en x_min, y2 en x_max)
DEFAULT_INCLINED_Y: list[dict] = []


# --- Materiales -----------------------------------------------------------

def concrete_modulus(fc: float) -> float:
    return math.ceil(15000.0 * math.sqrt(max(fc, 0.0)))


def steel_strength(psi_ksi: float) -> float:
    return math.ceil(psi_ksi * 1000.0 / 14.2233)


def masonry_modulus(fm: float) -> float:
    return 500.0 * fm


def _concrete(name: str, fc: float, weight: float = 2.4, poisson: float = 0.2) -> dict:
    return {
        "name": name, "kind": "Concrete", "fc": fc, "fy": 0.0, "fm": 0.0,
        "E": concrete_modulus(fc), "weight": weight, "poisson": poisson,
    }


def _rebar(name: str, fy: float) -> dict:
    return {
        "name": name, "kind": "Rebar", "fc": 0.0, "fy": fy, "fm": 0.0,
        "E": 2000000.0, "weight": 7.85, "poisson": 0.3,
    }


def _steel(name: str, fy_ksi: float) -> dict:
    return {
        "name": name, "kind": "Steel", "fc": 0.0, "fy": steel_strength(fy_ksi), "fm": 0.0,
        "E": steel_strength(29.0), "weight": 7.85, "poisson": 0.3,
    }


def _masonry(name: str, fm: float, weight: float) -> dict:
    return {
        "name": name, "kind": "Masonry", "fc": 0.0, "fy": 0.0, "fm": fm,
        "E": masonry_modulus(fm), "weight": weight, "poisson": 0.25,
    }


DEFAULT_MATERIALS = [
    _concrete("Concreto fc 140", 140),
    _concrete("Concreto fc 180", 180),
    _concrete("Concreto fc 210", 210),
    _concrete("Concreto fc 240", 240),
    _concrete("Concreto fc 250", 250),
    _concrete("Concreto fc 280", 280),
    _concrete("Concreto fc 300", 300),
    _concrete("Concreto fc 350", 350),
    _concrete("Concreto fc 400", 400, 2.45),
    _concrete("Concreto fc 500", 500, 2.5),
    _rebar("Rebar ASTM A615 Gr 40", 2800),
    _rebar("Rebar ASTM A615 Gr 60", 4200),
    _rebar("Rebar ASTM A706 Gr 60", 4200),
    _rebar("Rebar ASTM A615 Gr 75", 5200),
    _rebar("Rebar ASTM A706 Gr 80", 5500),
    _steel("Acero ASTM A36", 36),
    _steel("Acero ASTM A572 Gr 50", 50),
    _steel("Acero ASTM A992", 50),
    _steel("Acero Tubo A500 Gr B", 46),
    _steel("Acero Tubo A500 Gr C", 50),
    _steel("Acero Tubo A53 Gr B", 35),
    _steel("Acero Placa A514", 100),
    _masonry("Bloque Hormigon Pesado", 45, 1.8),
    _masonry("Bloque Hormigon Estandar", 65, 1.8),
    _masonry("Bloque Hormigon Estructural", 90, 1.9),
    _masonry("Ladrillo Arcilla Macizo", 50, 1.8),
    _masonry("Ladrillo Arcilla Perforado", 35, 1.6),
    _masonry("Tabiqueria Liviana", 25, 1.4),
]


# --- Secciones de viga y columna -----------------------------------------

# count_key se usa para los contadores editables de la plantilla (F114..K118).
DEFAULT_SECTION_GROUPS = [
    {"prefix": "VS_CONC", "count_key": "vs_conc", "material": "Concreto fc 180",
     "element": "Viga Secundaria", "geometry": "Rectangular", "d": 40, "bf": 40, "tw": 0, "tf": 0},
    {"prefix": "VP_CONC", "count_key": "vp_conc", "material": "Concreto fc 180",
     "element": "Viga Principal", "geometry": "Rectangular", "d": 40, "bf": 40, "tw": 0, "tf": 0},
    {"prefix": "VB_CONC", "count_key": "vb_conc", "material": "Concreto fc 180",
     "element": "Viga de Borde", "geometry": "Rectangular", "d": 20, "bf": 20, "tw": 0, "tf": 0},
    {"prefix": "COL_CONC", "count_key": "col_conc", "material": "Concreto fc 180",
     "element": "Columna", "geometry": "Rectangular", "d": 40, "bf": 40, "tw": 0, "tf": 0},
    {"prefix": "VP_STEEL_I", "count_key": "vp_steel_i", "material": "Acero ASTM A36",
     "element": "Viga Principal", "geometry": "Perfil_I", "d": 40, "bf": 20, "tw": 0.8, "tf": 1.2},
    {"prefix": "VS_STEEL_I", "count_key": "vs_steel_i", "material": "Acero ASTM A36",
     "element": "Viga Secundaria", "geometry": "Perfil_I", "d": 30, "bf": 15, "tw": 0.6, "tf": 1.0},
    {"prefix": "VS_HSS", "count_key": "vs_hss", "material": "Acero ASTM A36",
     "element": "Viga Secundaria", "geometry": "Tubo_Rectangular", "d": 40, "bf": 40, "tw": 1, "tf": 1},
    {"prefix": "COL_STEEL_I", "count_key": "col_steel_i", "material": "Acero ASTM A36",
     "element": "Columna", "geometry": "Perfil_I", "d": 40, "bf": 30, "tw": 1, "tf": 1.6},
    {"prefix": "COL_HSS", "count_key": "col_hss", "material": "Acero ASTM A36",
     "element": "Columna", "geometry": "Tubo_Rectangular", "d": 40, "bf": 40, "tw": 1, "tf": 1},
]

DEFAULT_SECTION_COUNTS = {
    "vs_conc": 1, "vp_conc": 1, "vb_conc": 1, "col_conc": 6,
    "vp_steel_i": 0, "vs_steel_i": 0, "vs_hss": 0, "col_steel_i": 0, "col_hss": 0,
}

GEOMETRY_OPTIONS = [
    "Rectangular", "Circular", "Perfil_I", "Tubo_Rectangular",
    "Tubo_Circular", "Tipo_T", "Tipo_L",
]


def section_properties(geometry: str, d: float, bf: float, tw: float, tf: float) -> tuple[float, float]:
    """Área (cm²) e inercia I33 (cm⁴), según las fórmulas de la plantilla."""
    try:
        d, bf, tw, tf = float(d), float(bf), float(tw or 0), float(tf or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    if geometry == "Rectangular":
        return d * bf, bf * d ** 3 / 12.0
    if geometry == "Circular":
        return math.pi * d ** 2 / 4.0, math.pi * d ** 4 / 64.0
    if geometry == "Tipo_L":
        area = d * tw + (bf - tw) * tf
        return area, 0.0
    if geometry == "Tipo_T":
        return bf * tf + (d - tf) * tw, 0.0
    if geometry == "Perfil_I":
        area = 2 * bf * tf + (d - 2 * tf) * tw
        inertia = (tw * (d - 2 * tf) ** 3 + 2 * (bf * tf ** 3 + 12 * bf * tf * ((d - tf) / 2) ** 2)) / 12.0
        return area, inertia
    if geometry == "Tubo_Rectangular":
        area = d * bf - (d - 2 * tf) * (bf - 2 * tw)
        inertia = (bf * d ** 3 - (bf - 2 * tw) * (d - 2 * tf) ** 3) / 12.0
        return area, inertia
    if geometry == "Tubo_Circular":
        area = math.pi * d ** 2 / 4.0 - math.pi * (d - 2 * tw) ** 2 / 4.0
        inertia = math.pi * (d ** 4 - (d - 2 * tw) ** 4) / 64.0
        return area, inertia
    return 0.0, 0.0


def section_modifiers(element: str) -> tuple[float, float]:
    """f22 / f33 de la plantilla (Q/R)."""
    element = (element or "").strip().lower()
    if element == "columna":
        return 0.7, 0.7
    if element == "viga de borde":
        return 1.0, 1.0
    if element:
        return 1.0, 0.35
    return 1.0, 1.0


# --- Losas y muros --------------------------------------------------------

DEFAULT_SLABS = [
    {"name": "Losa_1", "material": "Concreto fc 280", "model_type": "Shell-Thin",
     "slab_type": "Slab", "thickness": 20.0, "carpet": 0.0, "rib_top": 0.0,
     "rib_bottom": 0.0, "spacing_1": 0.0, "spacing_2": 0.0,
     "mods": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]},
]

DEFAULT_WALLS = [
    {"name": "Wall_1", "material": "Concreto fc 280", "model_type": "Shell-Thick",
     "thickness": 20.0,
     "mods": [1.0, 1.0, 1.0, 0.6, 0.6, 0.6, 1.0]},
]

MODEL_TYPES = ["Shell-Thin", "Shell-Thick", "Membrane", "Layered"]
SLAB_TYPES = ["Slab", "Drop", "Stiff", "Ribbed", "Waffle", "Mat", "Footing"]

# mods = f11, f22, f12, m11, m22, m12, v13/v23
SLAB_MOD_LABELS = ["f11", "f22", "f12", "m11", "m22", "m12", "v13/v23"]

WALL_MOD_LABELS = ["f11", "f22", "f12", "m11", "m22", "m12", "v13/v23"]

# --- Cargas ---------------------------------------------------------------

DEFAULT_PATTERNS = [
    {"name": "CM", "type": "Dead", "self_weight": 1.0,
     "description": "Carga muerta: peso propio + acabados + tabiqueria"},
    {"name": "CV", "type": "Live", "self_weight": 0.0,
     "description": "Carga viva de entrepiso - E.020"},
    {"name": "CVT", "type": "RoofLive", "self_weight": 0.0,
     "description": "Carga viva de techo - E.020"},
]

DEFAULT_SEISMIC = {
    "Z": 0.45, "U": 1.0, "S": 1.05, "Tp": 0.6, "TL": 2.0,
    "R": 7.0, "T": 0.5, "eccentricity": 0.05,
    "patterns": [
        {"name": "SX", "type": "Quake", "direction": "X", "lateral": "User Coefficient"},
        {"name": "SY", "type": "Quake", "direction": "Y", "lateral": "User Coefficient"},
    ],
}

DEFAULT_MASS_SOURCE = {
    "name": "MsSrc1",
    "include_self": False,
    "include_added": False,
    "include_loads": True,
    "factors": [{"pattern": "CM", "factor": 1.0},
                {"pattern": "CV", "factor": 0.5},
                {"pattern": "CVT", "factor": 0.25}],
}

DEFAULT_COMBOS = [
    {"name": "1.4CM+1.7CV", "type": "Linear Add",
     "factors": {"CM": 1.4, "CV": 1.7, "CVT": 1.7}, "notes": "Gravitacional"},
    {"name": "1.25(CM+CV)+SX", "type": "Linear Add",
     "factors": {"CM": 1.25, "CV": 1.25, "CVT": 1.25, "SX": 1.0}, "notes": "Sismo X (+)"},
    {"name": "1.25(CM+CV)-SX", "type": "Linear Add",
     "factors": {"CM": 1.25, "CV": 1.25, "CVT": 1.25, "SX": -1.0}, "notes": "Sismo X (-)"},
    {"name": "1.25(CM+CV)+SY", "type": "Linear Add",
     "factors": {"CM": 1.25, "CV": 1.25, "CVT": 1.25, "SY": 1.0}, "notes": "Sismo Y (+)"},
    {"name": "1.25(CM+CV)-SY", "type": "Linear Add",
     "factors": {"CM": 1.25, "CV": 1.25, "CVT": 1.25, "SY": -1.0}, "notes": "Sismo Y (-)"},
    {"name": "0.9CM+SX", "type": "Linear Add",
     "factors": {"CM": 0.9, "SX": 1.0}, "notes": "Volcamiento X (+)"},
    {"name": "0.9CM-SX", "type": "Linear Add",
     "factors": {"CM": 0.9, "SX": -1.0}, "notes": "Volcamiento X (-)"},
    {"name": "0.9CM+SY", "type": "Linear Add",
     "factors": {"CM": 0.9, "SY": 1.0}, "notes": "Volcamiento Y (+)"},
    {"name": "0.9CM-SY", "type": "Linear Add",
     "factors": {"CM": 0.9, "SY": -1.0}, "notes": "Volcamiento Y (-)"},
    {"name": "ENVOLVENTE", "type": "Envelope", "factors": {}, "notes": "Envolvente de diseno"},
]


def seismic_coefficient(seismic: dict) -> float:
    Z = float(seismic.get("Z", 0) or 0)
    U = float(seismic.get("U", 0) or 0)
    S = float(seismic.get("S", 0) or 0)
    T = float(seismic.get("T", 0) or 0)
    Tp = float(seismic.get("Tp", 0) or 0)
    TL = float(seismic.get("TL", 0) or 0)
    R = float(seismic.get("R", 1) or 1)
    if T <= 0:
        C = 2.5
    elif T < Tp:
        C = 2.5
    elif T < TL:
        C = 2.5 * Tp / T
    else:
        C = 2.5 * Tp * TL / (T * T)
    return Z * U * C * S / R


def seismic_k(seismic: dict) -> float:
    T = float(seismic.get("T", 0) or 0)
    return 1.0 if T <= 0.5 else min(0.75 + 0.5 * T, 2.0)


def frame_section_defaults(group: dict, index: int) -> dict:
    element = group["element"]
    f22, f33 = section_modifiers(element)
    area, inertia = section_properties(
        group["geometry"], group["d"], group["bf"], group["tw"], group["tf"])
    return {
        "name": f"{group['prefix']}_{index}",
        "material": group["material"],
        "element": element,
        "geometry": group["geometry"],
        "d": float(group["d"]),
        "bf": float(group["bf"]),
        "tw": float(group["tw"]),
        "tf": float(group["tf"]),
        "f22": f22,
        "f33": f33,
        "area": area,
        "inertia": inertia,
        "rebar_cover": 4.0,
    }
