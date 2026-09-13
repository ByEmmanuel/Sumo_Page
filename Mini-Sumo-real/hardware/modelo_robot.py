#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modelo_robot.py -- Gelatina Nuclear construido con componentes reales.

Fuente unica del robot fisico: cada pieza con su material, geometria,
posicion y masa. De aqui salen, sin editar nada a mano:
  - webots/protos/GelatinaNuclear.proto   visual, colisiones, masa, CdM, inercia
  - hardware/BOM.md                       lista de materiales y presupuesto de masa

    python3 hardware/modelo_robot.py

Marco del robot (ENU): x adelante, y a babor, z arriba. Origen en el suelo,
eje de las ruedas en x = -0.010. Unidades SI (m, kg).
"""
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ motor --
V_BAT = 7.4                              # LiPo 2S, tension nominal
RPM_6V, STALL_KGCM_6V = 650.0, 0.74      # Pololu #3063 (HPCB 6V, 51.45:1) a 6 V
MAX_VEL = 150.0 # techo numérico; la velocidad real la calcula el HAL
# referencia anterior: RPM_6V * V_BAT / 6.0 * 2.0 * math.pi / 60.0     # rad/s en la rueda
MAX_TORQUE = 0.25 # techo numérico para frenada inversa; ver real/parameters.json
# referencia anterior: STALL_KGCM_6V * 0.0980665 * V_BAT / 6.0       # N*m de bloqueo

MASA_TOTAL = 0.495                       # reglamento (p. 3): "por debajo" de 500 g; 5 g de margen de bascula
CDM_X_OBJETIVO = -0.014                  # 4 mm tras el eje: carga sobre las ruedas
RHO_W = 18000.0                          # aleacion de tungsteno W-Ni-Fe, kg/m3
TH_PALA = 0.60                           # inclinacion de la pala, rad (34 grados)
Z0 = 0.0361                              # cara superior de la PCB

MAT = {
    # Metalicidad moderada a proposito: el dohyo no tiene mapa de entorno y un
    # metal PBR puro solo refleja el fondo oscuro (se veria gris plomo).
    "aluminio":   "baseColor 0.86 0.87 0.89 metalness 0.55 roughness 0.35",
    "inox":       "baseColor 0.82 0.83 0.85 metalness 0.60 roughness 0.22",
    "acero":      "baseColor 0.62 0.63 0.65 metalness 0.60 roughness 0.35",
    "acero_neg":  "baseColor 0.08 0.08 0.09 metalness 0.5 roughness 0.40",
    "lata":       "baseColor 0.85 0.86 0.88 metalness 0.60 roughness 0.30",
    "laton":      "baseColor 0.80 0.66 0.36 metalness 0.60 roughness 0.30",
    "cobre":      "baseColor 0.93 0.55 0.33 metalness 0.60 roughness 0.30",
    "tungsteno":  "baseColor 0.42 0.43 0.45 metalness 0.50 roughness 0.50",
    "pla_color":  "baseColor IS color metalness 0 roughness 0.55",
    "pla_negro":  "baseColor 0.05 0.05 0.06 metalness 0 roughness 0.60",
    "pla_gris":   "baseColor 0.82 0.82 0.80 metalness 0 roughness 0.50",
    "silicona":   "baseColor 0.035 0.035 0.04 metalness 0 roughness 0.92",
    "fr4":        "baseColor 0.04 0.22 0.10 metalness 0 roughness 0.40",
    "pcb_azul":   "baseColor 0.04 0.18 0.52 metalness 0 roughness 0.40",
    "chip":       "baseColor 0.03 0.03 0.03 metalness 0 roughness 0.35",
    "lipo":       "baseColor 0.10 0.24 0.62 metalness 0.1 roughness 0.30",
    "etiqueta":   "baseColor 0.80 0.80 0.82 metalness 0.6 roughness 0.35",
    "amarillo":   "baseColor 0.95 0.72 0.05 metalness 0 roughness 0.45",
    "blanco":     "baseColor 0.93 0.93 0.90 metalness 0 roughness 0.50",
    "rojo":       "baseColor 0.80 0.05 0.05 metalness 0 roughness 0.50",
    "ptfe":       "baseColor 0.95 0.95 0.93 metalness 0 roughness 0.30",
    "epoxi":      "baseColor 0.04 0.04 0.06 metalness 0 roughness 0.15",
}

piezas = []    # todo lo que va rigido al chasis


def caja(n, mat, c, s, m=0.0, roty=0.0, vis=True):
    piezas.append(dict(n=n, mat=mat, forma="caja", c=c, s=s, m=m, roty=roty, vis=vis))


def cil(n, mat, c, r, h, eje="y", m=0.0, sx=1.0, vis=True):
    piezas.append(dict(n=n, mat=mat, forma="cil", c=c, r=r, h=h, eje=eje, m=m, sx=sx, vis=vis))


def esf(n, mat, c, r, m=0.0, vis=True):
    piezas.append(dict(n=n, mat=mat, forma="esf", c=c, r=r, m=m, vis=vis))


def masa(n, c, m, s=(0.01, 0.01, 0.01)):
    caja(n, None, c, s, m=m, vis=False)


# ------------------------------------------------------------- estructura --
caja("placa base Al 6061 2 mm", "aluminio", (-0.010, 0, 0.005), (0.080, 0.068, 0.002), 0.0294)
for sg in (1, -1):
    caja("pared lateral PLA", "pla_color", (-0.010, sg * 0.033, 0.0205), (0.080, 0.002, 0.029), 0.0040)
caja("pared trasera PLA", "pla_color", (-0.049, 0, 0.0205), (0.002, 0.064, 0.029), 0.0030)
caja("barra de sensores PLA", "pla_color", (0.029, 0, 0.026), (0.010, 0.064, 0.018), 0.0086)
caja("pala inox 1.5 mm", "inox", (0.0366, 0, 0.0093), (0.030, 0.098, 0.0015), 0.0348, roty=TH_PALA)
esf("patin trasero PTFE", "ptfe", (-0.046, 0, 0.004), 0.004, 0.0015)

# ---------------------------------------------------------------- motores --
for sg in (1, -1):
    caja("reductora 51.45:1", "acero", (-0.010, sg * 0.0265, 0.021), (0.010, 0.009, 0.012), 0.0035)
    cil("motor (lata)", "lata", (-0.010, sg * 0.01525, 0.021), 0.006, 0.0135, "y", 0.0055, sx=10 / 12)
    caja("tapa del motor", "pla_negro", (-0.010, sg * 0.00725, 0.021), (0.010, 0.0025, 0.012), 0.0005)
    for dx in (-0.0025, 0.0025):
        caja("borne", "cobre", (-0.010 + dx, sg * 0.0058, 0.0255), (0.0015, 0.0008, 0.003))
    cil("eje D 3 mm", "acero", (-0.010, sg * 0.036, 0.021), 0.0015, 0.010, "y")
    caja("soporte del motor", "pla_negro", (-0.010, sg * 0.0265, 0.021), (0.014, 0.0035, 0.016), 0.0010)
    cil("cable rojo", "rojo", (-0.0125, sg * 0.0065, 0.031), 0.0006, 0.008, "z")
    cil("cable negro", "pla_negro", (-0.0075, sg * 0.0065, 0.031), 0.0006, 0.008, "z")

# ---------------------------------------------------------------- energia --
caja("LiPo 2S 300 mAh", "lipo", (-0.040, 0, 0.027), (0.016, 0.046, 0.014), 0.0200)
caja("etiqueta LiPo", "etiqueta", (-0.040, 0, 0.027), (0.0162, 0.014, 0.0142))

# ------------------------------------------------------------ electronica --
caja("PCB FR4 1.6 mm", "fr4", (-0.009, 0, 0.0353), (0.078, 0.068, 0.0016), 0.0157)
caja("STM32F411 (UFQFPN48)", "chip", (-0.002, 0.012, Z0 + 0.0003), (0.007, 0.007, 0.0006))
caja("TB6612FNG (SSOP24)", "chip", (0.012, -0.012, Z0 + 0.0006), (0.0053, 0.0078, 0.0012))
caja("MPU-6050 (QFN24)", "chip", (-0.012, -0.010, Z0 + 0.00045), (0.004, 0.004, 0.0009))
caja("AMS1117-3.3 (SOT-223)", "chip", (0.016, 0.016, Z0 + 0.0008), (0.0065, 0.0035, 0.0016))
caja("cristal 8 MHz", "acero", (-0.010, 0.020, Z0 + 0.0004), (0.0032, 0.0025, 0.0008))
caja("interruptor", "pla_negro", (-0.040, -0.024, Z0 + 0.00175), (0.0085, 0.0036, 0.0035))
caja("palanca", "blanco", (-0.040, -0.024, Z0 + 0.0045), (0.0015, 0.0015, 0.0025))
caja("conector XT30", "amarillo", (-0.036, 0.022, Z0 + 0.0025), (0.010, 0.005, 0.005))
for y in (-0.024, -0.012, 0.0, 0.012, 0.024):
    caja("JST-SH ToF", "blanco", (0.024, y, Z0 + 0.0015), (0.003, 0.0045, 0.003))
for x in (-0.045, 0.027):
    for y in (-0.030, 0.030):
        cil("tornillo M2", "acero_neg", (x, y, Z0 + 0.0006), 0.0019, 0.0012, "z")
for sg in (1, -1):
    caja("soporte QTR delantero", "pla_negro", (0.022, sg * 0.039, 0.0101), (0.008, 0.010, 0.0016), 0.00073)
    caja("soporte QTR trasero", "pla_negro", (-0.042, sg * 0.039, 0.0101), (0.008, 0.010, 0.0016), 0.00073)

masa("componentes de la PCB", (-0.004, 0, 0.037), 0.0050)
masa("pulsador de arranque", (-0.044, 0.010, 0.042), 0.0010)
masa("cableado", (-0.015, 0, 0.030), 0.0040)
masa("tornilleria", (-0.009, 0, 0.030), 0.0030)
DIST = [("d_l60", 0.030, 0.036, 1.0472), ("d_l30", 0.037, 0.020, 0.5236), ("d_c", 0.037, 0.0, 0.0),
        ("d_r30", 0.037, -0.020, -0.5236), ("d_r60", 0.030, -0.036, -1.0472)]
for n, x, y, _ in DIST:
    masa(f"VL53L0X {n}", (x, y, 0.026), 0.0005)
# Las esquinas delanteras van TRAS la pala: debajo de ella no cabe un sensor.
LINEA = [("l_fl", 0.022, 0.040), ("l_fr", 0.022, -0.040), ("l_rl", -0.042, 0.040), ("l_rr", -0.042, -0.040)]
MASA_RUEDA = 0.014                      # llanta PLA 4 g + neumatico de silicona 10 g

# ------------------------------------------------------------ mecanica ------
def I_local(p):
    m = p["m"]
    if p["forma"] == "esf":
        i = 0.4 * m * p["r"] ** 2
        return [[i, 0, 0], [0, i, 0], [0, 0, i]]
    if p["forma"] == "cil" and p["sx"] == 1.0:
        a, t = 0.5 * m * p["r"] ** 2, m / 12.0 * (3 * p["r"] ** 2 + p["h"] ** 2)
        d = {"x": (a, t, t), "y": (t, a, t), "z": (t, t, a)}[p["eje"]]
        return [[d[0], 0, 0], [0, d[1], 0], [0, 0, d[2]]]
    if p["forma"] == "cil":   # lata aplanada: se aproxima por su caja envolvente
        s = (2 * p["r"] * p["sx"], p["h"], 2 * p["r"]) if p["eje"] == "y" else (2 * p["r"],) * 3
    else:
        s = p["s"]
    I = [[m / 12 * (s[1] ** 2 + s[2] ** 2), 0, 0], [0, m / 12 * (s[0] ** 2 + s[2] ** 2), 0],
         [0, 0, m / 12 * (s[0] ** 2 + s[1] ** 2)]]
    th = p.get("roty", 0.0)
    if th:
        c, s_ = math.cos(th), math.sin(th)
        R = [[c, 0, s_], [0, 1, 0], [-s_, 0, c]]
        I = [[sum(R[i][k] * I[k][l] * R[j][l] for k in range(3) for l in range(3)) for j in range(3)]
             for i in range(3)]
    return I


def propiedades(ps):
    M = sum(p["m"] for p in ps)
    cdm = [sum(p["m"] * p["c"][i] for p in ps) / M for i in range(3)]
    I = [[0.0] * 3 for _ in range(3)]
    for p in ps:
        if p["m"] <= 0:
            continue
        Il = I_local(p)
        d = [p["c"][i] - cdm[i] for i in range(3)]
        d2 = sum(v * v for v in d)
        for i in range(3):
            for j in range(3):
                I[i][j] += Il[i][j] + p["m"] * ((d2 if i == j else 0.0) - d[i] * d[j])
    return M, cdm, I


def dimensiona_lastre():
    """Placa de tungsteno en el suelo del chasis (8 mm x 60 mm): su masa cierra
    MASA_TOTAL y su posicion en x lleva el CdM total a CDM_X_OBJETIVO."""
    m_cuerpo = MASA_TOTAL - 2 * MASA_RUEDA
    m0 = sum(p["m"] for p in piezas)
    mx0 = sum(p["m"] * p["c"][0] for p in piezas)
    m_w = m_cuerpo - m0
    x_cuerpo = (CDM_X_OBJETIVO * MASA_TOTAL - 2 * MASA_RUEDA * (-0.010)) / m_cuerpo
    x_w = (x_cuerpo * m_cuerpo - mx0) / m_w
    largo = m_w / (RHO_W * 0.060 * 0.008)
    # Hueco en el suelo del chasis: del patin trasero (x = -0.041) a la barra
    # de sensores y la pala (x = 0.024). La bateria va encima, bajo la PCB.
    x0, x1 = x_w - largo / 2, x_w + largo / 2
    assert -0.041 <= x0 and x1 <= 0.024, f"el lastre no cabe: x de {x0:.4f} a {x1:.4f} m"
    caja("lastre de tungsteno", "tungsteno", (x_w, 0, 0.010), (largo, 0.060, 0.008), m_w)
    return m_w, largo


def rueda_inercia():
    r1, r2, h = 0.0165, 0.021, 0.015
    mt, mh = 0.010, 0.004
    eje = 0.5 * mt * (r1 ** 2 + r2 ** 2) + 0.5 * mh * r1 ** 2
    trans = mt / 12 * (3 * (r1 ** 2 + r2 ** 2) + h ** 2) + mh / 12 * (3 * r1 ** 2 + h ** 2)
    return eje + 1.8e-5, trans # inercia de rotor reflejada, supuesto documentado


def pala_colision():
    """Caja de 3 mm alineada con la cara superior de la pala visual. Se recorta
    por delante para que su arista mas baja quede a 1 mm del suelo."""
    th = TH_PALA
    n = (math.sin(th), math.cos(th))
    u = (math.cos(th), -math.sin(th))
    trasero = (0.0366 - 0.015 * u[0] - 0.00075 * n[0], 0.0093 - 0.015 * u[1] - 0.00075 * n[1])
    largo = (trasero[1] - 0.0015 * math.cos(th) - 0.001) / math.sin(th)
    largo = min(largo, 0.030)
    cx, cz = trasero[0] + largo / 2 * u[0], trasero[1] + largo / 2 * u[1]
    return (cx, cz), largo
