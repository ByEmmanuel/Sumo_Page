"""
config.py -- constantes del banco y espacio de parametros de la estrategia.

La geometria y la fisica son las de tests/harness.c, numero a numero: el
simulador de GPU tiene que dar las mismas estadisticas que el banco nativo
para que una mejora medida aqui signifique algo alli.

Los parametros salen de algorithms/params.h. PARAMS dice cuales se aprenden y
en que rango; los de proteccion del hardware (dt, rampa, zona muerta) no.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

ML = Path(__file__).resolve().parent
ROOT = ML.parent                      # Mini-Sumo/
ALGORITHMS = ROOT / "algorithms"
VERSIONS = ROOT / "versions"
# GN_ML_DATA desvia los datos (votos, clips, corridas) a otra carpeta: las
# pruebas no deben mezclarse con los votos reales del usuario.
DATA = Path(os.environ.get("GN_ML_DATA", ML / "data"))

# ---- tests/harness.c ------------------------------------------------------
RING_R = 0.385          # radio del dohyo (77 cm de diametro, reglamento)
RING_LINE_R = 0.360     # radio interior de la banda blanca (2,5 cm)
BODY_R = 0.055          # radio equivalente del robot de 10 x 10 cm
CORNER_OFF = 0.045      # sensores de linea en las esquinas
SENSOR_OFF = 0.035      # los de distancia miran desde aqui
V_MAX = 1.20            # m/s a consigna 1.0 en el banco
TRACK_M = 0.085         # SUMO_TRACK_M
DT_S = 0.008
DT_MS = 8
DIST_RANGE_M = 1.2
DIST_NOISE_MM = 6.0
NONE = 0xFFFF
ANG_CDEG = [6000, 3000, 0, -3000, -6000]


def pasos(segundos: float) -> int:
    """(int)(X / DT_S) calculado en float32, como lo hace el C."""
    return int(np.float32(segundos) / np.float32(DT_S))


ARM_S = 0.20
ARM_STEP = pasos(ARM_S)
_f = np.float32
OUT_R = float(_f(RING_R) + _f(BODY_R) * _f(0.35))        # out_of_ring() del banco
CONTACT_D = float(_f(2.0) * _f(BODY_R) + _f(0.012))       # separa expulsion de auto-salida
TOUCH_D = float(_f(2.0) * _f(BODY_R))                      # resolve_push()

# ---- reglamento (Extras/Reglamento de MINISUMO II .pdf) --------------------
REG_SEPARACION = 0.05    # 5 cm entre las caras enfrentadas
REG_LADO = 0.10          # robot de 10 x 10 cm
REG_CENTROS = REG_LADO + REG_SEPARACION    # 15 cm entre centros
COLOCACIONES = ["banco", "frente", "lado", "espalda"]   # 0 = diagonal del banco
RIVALES = ["static", "charger", "spinner", "fsm"]

# ---- parametros de params.h ------------------------------------------------
#   nombre, tipo, minimo, maximo, se_aprende
PARAMS = [
    ("dt_ms",              "int",   8,     8,    False),
    ("dist_valid_max_mm",  "int",   300,   1190, True),
    ("dist_attack_mm",     "int",   60,    500,  True),
    ("dist_track_mm",      "int",   300,   1190, True),
    ("target_hold_ms",     "int",   0,     800,  True),
    ("v_attack",           "float", 0.5,   1.0,  True),
    ("v_track",            "float", 0.3,   1.0,  True),
    ("v_search",           "float", 0.2,   1.0,  True),
    ("v_escape",           "float", 0.4,   1.0,  True),
    ("v_opening",          "float", 0.0,   1.0,  True),
    ("track_kp",           "float", 0.2,   4.0,  True),
    ("track_max_diff",     "float", 0.1,   1.0,  True),
    ("attack_kp_scale",    "float", 0.0,   2.0,  True),
    ("attack_max_diff",    "float", 0.0,   1.0,  True),
    ("escape_back_ms",     "int",   60,    800,  True),
    ("escape_turn_ms",     "int",   60,    900,  True),
    ("escape_lockout_ms",  "int",   0,     600,  True),
    ("dist_contact_mm",    "int",   20,    150,  True),
    ("contact_cone_cdeg",  "int",   500,   6000, True),
    ("push_commit_ms",     "int",   0,     2000, True),
    ("search_spin_ms",     "int",   100,   1500, True),
    ("search_probe_ms",    "int",   0,     1000, True),
    ("search_turn_ratio",  "float", -1.0,  0.0,  True),
    ("opening",            "enum",  0,     3,    True),
    ("opening_ms",         "int",   0,     1500, True),
    ("slew_per_s",         "float", 25.0,  25.0, False),   # protege el puente en H
    ("deadband",           "float", 0.04,  0.04, False),
]
NOMBRES = [p[0] for p in PARAMS]
APRENDIBLES = [p for p in PARAMS if p[4]]
TIPO = {p[0]: p[1] for p in PARAMS}
ENTEROS = {p[0] for p in PARAMS if p[1] in ("int", "enum")}

APERTURAS = {"OPENING_CHARGE": 0, "OPENING_ARC_L": 1, "OPENING_ARC_R": 2, "OPENING_SCAN": 3}
APERTURAS_INV = {v: k for k, v in APERTURAS.items()}

# Campos que no existian en versiones antiguas, con el valor que reproduce su
# conducta: v0.1.0 no tenia empuje comprometido (ventana de 0 ms) y v0.1.0 y
# v0.2.0 usaban 0,35 y +-0,30 escritos a mano en ATTACK.
LEGADO = {
    "attack_kp_scale": 0.35,
    "attack_max_diff": 0.30,
    "dist_contact_mm": 60,
    "contact_cone_cdeg": 2500,
    "push_commit_ms": 0,
}

_ASIG = re.compile(r"^\s*p\.(\w+)\s*=\s*([^;]+);", re.MULTILINE)


def lee_params_h(path: Path) -> dict:
    """Extrae los valores de sumo_params_default() de un params.h."""
    return lee_params_texto(path.read_text(encoding="utf-8"))


def lee_params_texto(texto: str) -> dict:
    out = {}
    for nombre, valor in _ASIG.findall(texto):
        v = valor.strip()
        if v in APERTURAS:
            out[nombre] = APERTURAS[v]
        else:
            v = v.rstrip("fF")
            out[nombre] = int(v) if TIPO.get(nombre) in ("int", "enum") else float(v)
    return out


def completa(p: dict) -> dict:
    """Rellena los campos que falten con su valor de legado."""
    q = dict(LEGADO)
    q.update(p)
    faltan = [n for n in NOMBRES if n not in q]
    if faltan:
        raise ValueError("faltan parametros: " + ", ".join(faltan))
    return {n: q[n] for n in NOMBRES}


def params_version(ver: str) -> dict:
    """Parametros de una version de la bitacora, o de WORK (el arbol actual)."""
    if ver == "WORK":
        return completa(lee_params_h(ALGORITHMS / "params.h"))
    return completa(lee_params_h(VERSIONS / ver / "snapshot" / "algorithms" / "params.h"))


def versiones_registradas() -> list[str]:
    import json
    m = json.loads((VERSIONS / "manifest.json").read_text(encoding="utf-8"))
    return [v["version"] for v in m["versions"]]


def recorta(p: dict) -> dict:
    """Aplica rangos, redondeo de enteros y la restriccion track > attack."""
    q = {}
    for nombre, tipo, lo, hi, _ in PARAMS:
        v = min(max(p[nombre], lo), hi)
        q[nombre] = int(round(v)) if tipo in ("int", "enum") else float(v)
    if q["dist_track_mm"] <= q["dist_attack_mm"]:
        q["dist_track_mm"] = min(1190, q["dist_attack_mm"] + 40)
    if q["dist_valid_max_mm"] < q["dist_track_mm"]:
        q["dist_valid_max_mm"] = q["dist_track_mm"]
    return q
