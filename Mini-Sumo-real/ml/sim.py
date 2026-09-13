"""
sim.py -- el dohyo en la GPU.

Port vectorizado de tests/harness.c: la misma cinematica 2D, los mismos
sensores y la misma resolucion de empuje, con N asaltos a la vez. Cada
entorno tiene su rival, su colocacion y su juego de parametros.

Dos modos:
  - "banco": identico a harness.c. Sirve para validar el port contra el C.
  - "robusto": aleatoriza lo que el banco fija y Webots demostro que varia:
    velocidad maxima (1,2 m/s en el banco, 1,575 en Webots), agarre, ruido
    y perdidas del ToF, retardo de los motores y el efecto de la pala blanca
    (los IR de linea delanteros ven la pala del rival como el borde). Lo que
    se aprende aqui no puede depender de un numero exacto del banco.

Colocaciones: 0 = diagonal del banco (36 cm), 1 = frente a frente, 2 = de
lado en sentidos opuestos y 3 = de espaldas, las tres a 5 cm (reglamento,
paginas 10 y 11).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch

from . import fsm
from .config import (ANG_CDEG, ARM_STEP, BODY_R, CONTACT_D, CORNER_OFF, DIST_NOISE_MM,
                     DIST_RANGE_M, DT_MS, DT_S, NONE, OUT_R, REG_CENTROS, RING_LINE_R,
                     SENSOR_OFF, TOUCH_D, TRACK_M, V_MAX, pasos)

STATIC, CHARGER, SPINNER, FSM = range(4)
RAZONES = ["", "rival fuera", "expulsado", "auto-salida", "doble salida", "tiempo agotado"]
RASGOS = [
    "resultado", "auto_salida", "expulsado", "t_fin", "t_primer_contacto",
    "frac_contacto", "empuje", "frac_riesgo_borde", "velocidad", "frac_giro_sitio",
    "brusquedad", "bordes_por_s", "ventaja_final", "agresividad",
]
ANG_RAD = [float(np.float32(c) / np.float32(100.0) * np.float32(math.pi / 180.0)) for c in ANG_CDEG]


@dataclass(frozen=True)
class Cfg:
    modo: str = "banco"        # "banco" | "robusto"
    max_s: float = 30.0        # limite del asalto (el banco usa 30 s)
    compilar: bool = True


# ==========================================================================
#  Piezas del paso
# ==========================================================================

def sentir(xa, ya, tha, xb, yb, ruido_mm, caida, pala):
    """sense() de harness.c para el robot A mirando al B."""
    dev = xa.device
    ang = tha[:, None] + torch.tensor(ANG_RAD, device=dev)
    dx, dy = torch.cos(ang), torch.sin(ang)
    ox = xa[:, None] + SENSOR_OFF * dx
    oy = ya[:, None] + SENSOR_OFF * dy
    mx, my = ox - xb[:, None], oy - yb[:, None]
    b = mx * dx + my * dy
    c = mx * mx + my * my - BODY_R * BODY_R
    disc = b * b - c
    hit = ~((c > 0.0) & (b > 0.0)) & (disc >= 0.0)
    t = torch.clamp(-b - torch.sqrt(torch.clamp(disc, min=0.0)), min=0.0)
    hit = hit & (t <= DIST_RANGE_M)
    mm = t * 1000.0 + (torch.rand_like(t) * 2.0 - 1.0) * ruido_mm[:, None]
    d = torch.where(hit, torch.floor(torch.clamp(mm, min=0.0)).long(), NONE)
    d = torch.where(torch.rand_like(t) < caida[:, None], NONE, d)

    cx = torch.tensor([CORNER_OFF, CORNER_OFF, -CORNER_OFF, -CORNER_OFF], device=dev)
    cy = torch.tensor([CORNER_OFF, -CORNER_OFF, CORNER_OFF, -CORNER_OFF], device=dev)
    ct, st = torch.cos(tha)[:, None], torch.sin(tha)[:, None]
    wx = xa[:, None] + cx * ct - cy * st
    wy = ya[:, None] + cx * st + cy * ct
    line = torch.sqrt(wx * wx + wy * wy) >= RING_LINE_R

    # pala del rival bajo los IR delanteros: se lee como banda blanca
    rel = torch.atan2(yb - ya, xb - xa) - tha
    rel = torch.remainder(rel + math.pi, 2 * math.pi) - math.pi
    dcen = torch.sqrt((xb - xa) ** 2 + (yb - ya) ** 2)
    blanco = pala & (dcen < TOUCH_D + 0.01) & (rel.abs() < 0.6)
    line = torch.cat([line[:, :2] | blanco[:, None], line[:, 2:]], dim=1)
    return d, line


def rival_guion(E, dist, line, armed):
    """opponent_act() de harness.c: static, charger y spinner."""
    kind = E["rival"]
    lf = line[:, 0] | line[:, 1]
    lr = line[:, 2] | line[:, 3]
    ang = torch.tensor(ANG_CDEG, device=dist.device, dtype=torch.float32)

    sp_l = torch.where(lf | lr, -0.6, -0.5)
    sp_r = torch.where(lf | lr, -0.6, 0.5)

    is_ch = armed & (kind == CHARGER)
    ph = torch.where(is_ch & lf, 1, E["ch_phase"])
    tt = torch.where(is_ch & lf, 0.0, E["ch_t"])
    atras = is_ch & (ph == 1)
    tt = torch.where(atras, tt + DT_S, tt)
    bl = torch.where(tt < 0.30, -0.8, -0.6)
    br = torch.where(tt < 0.30, -0.8, 0.6)
    ph = torch.where(atras & (tt > 0.70), 0, ph)
    valid = dist != NONE
    bi = torch.where(valid, dist, NONE).argmin(1)
    turn = ang[bi] / 6000.0 * 0.55
    hay = valid.any(1)
    fl = torch.where(hay, 0.95 - turn, -0.45)
    fr = torch.where(hay, 0.95 + turn, 0.45)
    ch_l = torch.where(atras, bl, torch.where(lr, 0.9, fl))
    ch_r = torch.where(atras, br, torch.where(lr, 0.9, fr))

    l = torch.where(kind == CHARGER, ch_l, torch.where(kind == SPINNER, sp_l, 0.0))
    r = torch.where(kind == CHARGER, ch_r, torch.where(kind == SPINNER, sp_r, 0.0))
    l = torch.where(armed, l, 0.0)
    r = torch.where(armed, r, 0.0)
    return l, r, ph, tt


def _integra(x, y, th, cl, cr, vmax):
    vl, vr = cl * vmax, cr * vmax
    v = 0.5 * (vl + vr)
    w = (vr - vl) / TRACK_M
    th = th + w * DT_S
    return x + v * torch.cos(th) * DT_S, y + v * torch.sin(th) * DT_S, th


def fisica(E, lm, rm, lf, rf):
    """integrate() de los dos, resolve_push(), arbitraje y rasgos del asalto."""
    E = dict(E)
    k = E["k"]
    armed = k >= ARM_STEP
    t_s = (k - ARM_STEP).float() * DT_S

    # retardo de motor de primer orden (alfa = 1 en el banco: sin retardo)
    a = E["alfa"]
    cl_m = torch.where(a >= 1.0, lm, E["me_cl"] + a * (lm - E["me_cl"]))
    cr_m = torch.where(a >= 1.0, rm, E["me_cr"] + a * (rm - E["me_cr"]))
    cl_f = torch.where(a >= 1.0, lf, E["fo_cl"] + a * (lf - E["fo_cl"]))
    cr_f = torch.where(a >= 1.0, rf, E["fo_cr"] + a * (rf - E["fo_cr"]))

    r_fo_antes = torch.sqrt(E["fo_x"] ** 2 + E["fo_y"] ** 2)
    mx, my, mth = _integra(E["me_x"], E["me_y"], E["me_th"], cl_m, cr_m, E["vmax_me"])
    fx, fy, fth = _integra(E["fo_x"], E["fo_y"], E["fo_th"], cl_f, cr_f, E["vmax_fo"])

    # --- resolve_push(me, foe) ----------------------------------------------
    dx, dy = fx - mx, fy - my
    d = torch.sqrt(dx * dx + dy * dy)
    toca = d < TOUCH_D
    diminuto = d < 1e-5
    dx = torch.where(diminuto, 1.0, dx)
    dy = torch.where(diminuto, 0.0, dy)
    d = torch.where(diminuto, 1e-5, d)
    nx, ny = dx / d, dy / d
    pen = TOUCH_D - d
    va = 0.5 * (cl_m + cr_m) * E["vmax_me"]
    vb = 0.5 * (cl_f + cr_f) * E["vmax_fo"]
    ta = torch.clamp(va * (torch.cos(mth) * nx + torch.sin(mth) * ny), min=0.0) * E["grip_me"]
    tb = torch.clamp(vb * (torch.cos(fth) * -nx + torch.sin(fth) * -ny), min=0.0) * E["grip_fo"]
    tot = ta + tb + 0.02
    sb, sa = ta / tot, tb / tot
    rest = 1.0 - sa - sb
    fx = torch.where(toca, fx + nx * pen * (sb + rest * 0.5), fx)
    fy = torch.where(toca, fy + ny * pen * (sb + rest * 0.5), fy)
    mx = torch.where(toca, mx - nx * pen * (sa + rest * 0.5), mx)
    my = torch.where(toca, my - ny * pen * (sa + rest * 0.5), my)

    # --- arbitro ---------------------------------------------------------------
    sx, sy = fx - mx, fy - my
    dcen = torch.sqrt(sx * sx + sy * sy)
    contacto = dcen < CONTACT_D
    E["last_contact"] = torch.where(contacto, t_s, E["last_contact"])
    r_me = torch.sqrt(mx * mx + my * my)
    r_fo = torch.sqrt(fx * fx + fy * fy)
    me_out, fo_out = r_me > OUT_R, r_fo > OUT_R
    vivo = armed & ~E["done"]
    nuevo = ~E["done"] & (me_out | fo_out)
    res_n = torch.where(me_out & fo_out, 0, torch.where(fo_out, 1, -1))
    empujado = (t_s - E["last_contact"]) < 0.40
    raz_n = torch.where(me_out & fo_out, 4, torch.where(fo_out, 1, torch.where(empujado, 2, 3)))
    E["res"] = torch.where(nuevo, res_n, E["res"])
    E["razon"] = torch.where(nuevo, raz_n, E["razon"])
    E["t_fin"] = torch.where(nuevo, t_s, E["t_fin"])
    E["r_me_fin"] = torch.where(nuevo, r_me, E["r_me_fin"])
    E["r_fo_fin"] = torch.where(nuevo, r_fo, E["r_fo_fin"])
    E["done"] = E["done"] | nuevo

    # --- rasgos del asalto (solo mientras esta vivo) ---------------------------
    fv = vivo.float()
    E["f_armado"] = E["f_armado"] + fv
    E["f_contacto"] = E["f_contacto"] + (vivo & contacto).float()
    E["f_primer"] = torch.where(vivo & contacto & (E["f_primer"] < 0), t_s, E["f_primer"])
    E["f_empuje"] = E["f_empuje"] + torch.where(vivo & contacto, torch.clamp(r_fo - r_fo_antes, min=0.0), 0.0)
    E["f_riesgo"] = E["f_riesgo"] + (vivo & (r_me > 0.33)).float()
    v_me = 0.5 * (cl_m + cr_m) * E["vmax_me"]
    E["f_vel"] = E["f_vel"] + fv * v_me.abs() / V_MAX
    giro = ((cl_m + cr_m).abs() * 0.5 < 0.15) & ((cl_m - cr_m).abs() > 0.5)
    E["f_giro"] = E["f_giro"] + (vivo & giro).float()
    E["f_dcmd"] = E["f_dcmd"] + fv * ((lm - E["me_cmd_l"]).abs() + (rm - E["me_cmd_r"]).abs())
    ux, uy = sx / dcen.clamp(min=1e-4), sy / dcen.clamp(min=1e-4)
    E["f_aprox"] = E["f_aprox"] + fv * torch.clamp(v_me * (torch.cos(mth) * ux + torch.sin(mth) * uy), min=0.0) / V_MAX

    E.update(me_x=mx, me_y=my, me_th=mth, me_cl=cl_m, me_cr=cr_m,
             fo_x=fx, fo_y=fy, fo_th=fth, fo_cl=cl_f, fo_cr=cr_f,
             me_cmd_l=lm, me_cmd_r=rm, k=k + 1)
    return E


def observa(E):
    """Sensores de los dos robots con las posiciones de antes de mover."""
    d_me, l_me = sentir(E["me_x"], E["me_y"], E["me_th"], E["fo_x"], E["fo_y"],
                        E["ruido"], E["caida"], E["pala"])
    d_fo, l_fo = sentir(E["fo_x"], E["fo_y"], E["fo_th"], E["me_x"], E["me_y"],
                        E["ruido"], E["caida"], E["pala"])
    return d_me, l_me, d_fo, l_fo


def mueve_rival(E, Pf, d_fo, l_fo):
    """El rival decide: guion (static, charger, spinner) o maquina de estados."""
    k = E["k"]
    armed = k >= ARM_STEP
    t_ms = k * DT_MS
    Sf, lff, rff = fsm.paso(E["Sf"], Pf, d_fo, l_fo, t_ms, armed)
    lo, ro, ph, tt = rival_guion(E, d_fo, l_fo, armed)
    es_fsm = E["rival"] == FSM
    E = dict(E)
    E["Sf"], E["ch_phase"], E["ch_t"] = Sf, ph, tt
    return E, torch.where(es_fsm, lff, lo), torch.where(es_fsm, rff, ro)


def paso_fsm(E, Pm, Pf):
    """Un ciclo completo con la maquina de estados al mando de Gelatina."""
    d_me, l_me, d_fo, l_fo = observa(E)
    k = E["k"]
    Sm, lm, rm = fsm.paso(E["Sm"], Pm, d_me, l_me, k * DT_MS, k >= ARM_STEP)
    E = dict(E)
    E["Sm"] = Sm
    line_now = l_me.any(1)
    E["f_bordes"] = E["f_bordes"] + ((k >= ARM_STEP) & ~E["done"] & line_now & ~E["f_linea"]).float()
    E["f_linea"] = line_now
    E, lf, rf = mueve_rival(E, Pf, d_fo, l_fo)
    return fisica(E, lm, rm, lf, rf)


# ==========================================================================
#  Colocacion y estado inicial
# ==========================================================================

def sorteo(n: int, dev, compartir: int | None = None):
    """Generador de uniformes [n]. Con compartir=S los S primeros valores se
    repiten en cada bloque de S entornos: todos los candidatos juegan el mismo
    sorteo de colocacion y de dominio."""
    if compartir:
        return lambda: torch.rand(compartir, device=dev).repeat(n // compartir)
    return lambda: torch.rand(n, device=dev)


def coloca(colocacion: torch.Tensor, u=None):
    """Posiciones de salida. Devuelve (me_x, me_y, me_th, fo_x, fo_y, fo_th)."""
    n, dev = colocacion.shape[0], colocacion.device
    u = u or sorteo(n, dev)
    sym = lambda a: (u() * 2.0 - 1.0) * a

    # banco: diagonal a 36 cm, mirandose, con el jitter de harness.c
    idx = torch.arange(n, device=dev)
    base = torch.where(idx % 2 == 0, 0.0, math.pi / 2.0)
    r0 = 0.18 + sym(0.02)
    b_mx, b_my = r0 * torch.cos(base), r0 * torch.sin(base)
    b_mth = base + math.pi + sym(0.25)
    b_fth = base + sym(0.25)

    # reglamento: en la cruz, 15 cm entre centros, orientacion global libre
    phi = u() * 2.0 * math.pi
    ux, uy = torch.cos(phi), torch.sin(phi)
    lado = colocacion == 2
    ax, ay = torch.where(lado, -uy, ux), torch.where(lado, ux, uy)
    h = 0.5 * REG_CENTROS
    r_mx, r_my = h * ax + sym(0.003), h * ay + sym(0.003)
    r_fx, r_fy = -h * ax + sym(0.003), -h * ay + sym(0.003)
    frente = colocacion == 1
    r_mth = torch.where(frente, phi + math.pi, phi) + sym(0.05)
    r_fth = torch.where(frente, phi, phi + math.pi) + sym(0.05)

    banco = colocacion == 0
    return (torch.where(banco, b_mx, r_mx), torch.where(banco, b_my, r_my),
            torch.where(banco, b_mth, r_mth), torch.where(banco, -b_mx, r_fx),
            torch.where(banco, -b_my, r_fy), torch.where(banco, b_fth, r_fth))


def estado_inicial(rival: torch.Tensor, colocacion: torch.Tensor, modo: str,
                   compartir: int | None = None) -> dict:
    n, dev = rival.shape[0], rival.device
    z = torch.zeros(n, device=dev)
    zi = torch.zeros(n, dtype=torch.long, device=dev)
    rnd = sorteo(n, dev, compartir)
    mx, my, mth, fx, fy, fth = coloca(colocacion, rnd)
    E = dict(
        me_x=mx, me_y=my, me_th=mth, me_cl=z.clone(), me_cr=z.clone(),
        fo_x=fx, fo_y=fy, fo_th=fth, fo_cl=z.clone(), fo_cr=z.clone(),
        me_cmd_l=z.clone(), me_cmd_r=z.clone(),
        rival=rival.clone(), ch_phase=zi.clone(), ch_t=z.clone(),
        done=torch.zeros(n, dtype=torch.bool, device=dev), res=zi.clone(), razon=zi.clone(),
        t_fin=z.clone(), last_contact=torch.full((n,), -99.0, device=dev),
        r_me_fin=z.clone(), r_fo_fin=z.clone(),
        f_armado=z.clone(), f_contacto=z.clone(), f_primer=torch.full((n,), -1.0, device=dev),
        f_empuje=z.clone(), f_riesgo=z.clone(), f_vel=z.clone(), f_giro=z.clone(),
        f_dcmd=z.clone(), f_aprox=z.clone(), f_bordes=z.clone(),
        f_linea=torch.zeros(n, dtype=torch.bool, device=dev),
        k=torch.zeros((), dtype=torch.long, device=dev),
        Sm=fsm.estado_inicial(n, dev), Sf=fsm.estado_inicial(n, dev),
    )
    if modo == "robusto":
        u = lambda lo, hi: lo + (hi - lo) * rnd()
        tau = u(0.0, 0.04)
        E.update(vmax_me=u(1.05, 1.65), vmax_fo=u(1.05, 1.65),
                 grip_me=u(0.85, 1.15), grip_fo=u(0.85, 1.15),
                 ruido=u(3.0, 15.0), caida=u(0.0, 0.03),
                 pala=rnd() < 0.5, alfa=DT_S / (tau + DT_S))
    else:
        one = torch.ones(n, device=dev)
        E.update(vmax_me=one * V_MAX, vmax_fo=one * V_MAX, grip_me=one.clone(), grip_fo=one.clone(),
                 ruido=one * DIST_NOISE_MM, caida=z.clone(),
                 pala=torch.zeros(n, dtype=torch.bool, device=dev), alfa=one.clone())
    return E


def params_tensor(juegos: list[dict], reps: int | list[int], device) -> dict:
    """Juegos de parametros -> dict de tensores [N], repitiendo cada juego."""
    if isinstance(reps, int):
        reps = [reps] * len(juegos)
    out = {}
    for nombre in juegos[0]:
        vals = [j[nombre] for j in juegos]
        entero = isinstance(vals[0], int)
        base = torch.tensor(vals, dtype=torch.long if entero else torch.float32, device=device)
        out[nombre] = torch.repeat_interleave(base, torch.tensor(reps, device=device))
    return out


# ==========================================================================
#  El ring
# ==========================================================================

class Arena:
    def __init__(self, cfg: Cfg = Cfg(), device: str = "cuda"):
        self.cfg = cfg
        self.dev = torch.device(device)
        self._paso = torch.compile(paso_fsm, dynamic=False) if cfg.compilar else paso_fsm

    @torch.no_grad()
    def correr(self, Pm: dict, rival: torch.Tensor, Pf: dict, colocacion: torch.Tensor,
               registrar: torch.Tensor | None = None, cada: int = 3,
               compartir: int | None = None) -> dict:
        """Juega N asaltos a la vez hasta que acaban o se agota el tiempo."""
        E = estado_inicial(rival.to(self.dev), colocacion.to(self.dev), self.cfg.modo, compartir)
        total = pasos(self.cfg.max_s)
        cuadros = []
        for k in range(total):
            if registrar is not None and k % cada == 0:
                cuadros.append(torch.stack([
                    E["me_x"][registrar], E["me_y"][registrar], E["me_th"][registrar],
                    E["fo_x"][registrar], E["fo_y"][registrar], E["fo_th"][registrar],
                    E["me_cmd_l"][registrar], E["me_cmd_r"][registrar],
                    E["Sm"]["state"][registrar].float(), E["done"][registrar].float(),
                ], dim=1))
            E = self._paso(E, Pm, Pf)
            if k % 128 == 127 and bool(E["done"].all()):
                break
        return self._cierra(E, cuadros)

    def _cierra(self, E, cuadros) -> dict:
        tiempo = ~E["done"]
        r_me = torch.sqrt(E["me_x"] ** 2 + E["me_y"] ** 2)
        r_fo = torch.sqrt(E["fo_x"] ** 2 + E["fo_y"] ** 2)
        out = {
            "res": torch.where(tiempo, 0, E["res"]),
            "razon": torch.where(tiempo, 5, E["razon"]),
            "t_fin": torch.where(tiempo, self.cfg.max_s, E["t_fin"]),
            "bordes": E["Sm"]["edge_events"],
            "compromisos": E["Sm"]["push_commits"],
            "rasgos": rasgos(E, self.cfg.max_s, torch.where(tiempo, r_me, E["r_me_fin"]),
                             torch.where(tiempo, r_fo, E["r_fo_fin"])),
        }
        if cuadros:
            out["trayectoria"] = torch.stack(cuadros, dim=1)   # [n_reg, T, 10]
        return out


def rasgos(E, max_s, r_me_fin, r_fo_fin) -> torch.Tensor:
    """Resumen interpretable de un asalto: lo que ve el modelo de recompensa."""
    n = E["f_armado"].clamp(min=1.0)
    t_fin = torch.where(E["done"], E["t_fin"], max_s)
    res = torch.where(E["done"], E["res"], 0).float()
    raz = torch.where(E["done"], E["razon"], 5)
    primer = torch.where(E["f_primer"] < 0, max_s, E["f_primer"])
    cols = [
        res,
        (raz == 3).float(),
        (raz == 2).float(),
        t_fin / max_s,
        primer / max_s,
        E["f_contacto"] / n,
        E["f_empuje"],
        E["f_riesgo"] / n,
        E["f_vel"] / n,
        E["f_giro"] / n,
        E["f_dcmd"] / n,
        E["f_bordes"] / t_fin.clamp(min=0.1),
        r_fo_fin - r_me_fin,
        E["f_aprox"] / n,
    ]
    return torch.stack(cols, dim=1)


def probabilidad_combate(pw, pd, pl):
    """Combate a 3 rondas del reglamento (paginas 8 y 13) a partir de las
    probabilidades por ronda de cada colocacion (frente, lado, espalda).
    Gana quien llega a dos Yuko; al final, quien tenga mas; con igualdad,
    ronda extra de frente y, si tambien es empate, deciden los jueces.
    Devuelve (gana, jueces, pierde)."""
    P = {(0, 0): 1.0}
    W = L = D = 0.0
    for r in range(3):
        Q = {}
        for (i, j), p in P.items():
            for (di, dj), q in (((1, 0), pw[r]), ((0, 0), pd[r]), ((0, 1), pl[r])):
                Q[(i + di, j + dj)] = Q.get((i + di, j + dj), 0.0) + p * q
        P = {}
        for (i, j), p in Q.items():
            if i == 2:
                W += p
            elif j == 2:
                L += p
            else:
                P[(i, j)] = p
    for (i, j), p in P.items():
        if i > j:
            W += p
        elif j > i:
            L += p
        else:
            W += p * pw[0]
            L += p * pl[0]
            D += p * pd[0]
    return W, D, L
