"""
fsm.py -- algorithms/strategy.c, vectorizado.

Cada entorno de la GPU lleva su propia maquina de estados con su propio juego
de parametros, asi que una generacion entera de la estrategia evolutiva
(cientos de candidatos por decenas de asaltos) se evalua en una sola pasada.

La traduccion es literal, linea a linea, incluidas las rarezas del C:
  - aritmetica entera donde el C usa enteros (el rumbo es una division
    truncada, los tiempos son uint32);
  - en un ciclo con transicion de estado sin llamada a drive() la salida es
    (0, 0): el banco nativo pone los actuadores a cero en cada ciclo.
Todas las ramas se calculan para todos los entornos y se eligen con mascaras.

Si strategy.c cambia de estructura hay que portar el cambio aqui y validarlo
con `python -m ml validar`. PORTADOS guarda el sha256 de cada strategy.c que
este fichero reproduce; `estructura_portada()` avisa si el actual es otro.
"""

from __future__ import annotations

import hashlib
import math

import torch

from .config import ALGORITHMS, ANG_CDEG, NONE

WAIT, OPENING, SEARCH, TRACK, ATTACK, EDGE = range(6)
ESTADOS = ["WAIT", "OPENING", "SEARCH", "TRACK", "ATTACK", "EDGE_ESCAPE"]
FRONT, REAR, LEFT, RIGHT = 0b0011, 0b1100, 0b0101, 0b1010
DEG2RAD = math.pi / 180.0

PORTADOS = {
    "9e2b716aff38f90090bc5c430c61a4948e4328dbe4fbe56a1401c22d872b8e58": "v0.1.0",
    "4f94aaa6b4decc825bbbb0611e449f3bc2f3b3d40a7e053a8d9de0906e285e3c": "v0.2.0",
    "f0efeea44f81638e7bf2eb1982638c6260cb65a7e9357137ec95eb8a5501f750": "v0.3.0",
}


def estructura_portada() -> str | None:
    """Version cuya estructura reproduce este port, o None si strategy.c es otro."""
    h = hashlib.sha256((ALGORITHMS / "strategy.c").read_bytes()).hexdigest()
    return PORTADOS.get(h)


def estado_inicial(n: int, device) -> dict:
    """strategy_init(): todo a cero, estado WAIT y distancia NONE."""
    zi = lambda: torch.zeros(n, dtype=torch.long, device=device)
    zf = lambda: torch.zeros(n, dtype=torch.float32, device=device)
    zb = lambda: torch.zeros(n, dtype=torch.bool, device=device)
    return {
        "state": zi(), "t_state": zi(), "t_edge_clear": zi(),
        "esc_phase": zi(), "esc_turn": zf(), "esc_drive": zf(),
        "probing": zb(), "prev_l": zf(), "prev_r": zf(),
        "edge_events": zi(), "commit_active": zb(), "t_commit": zi(), "push_commits": zi(),
        # percepcion
        "seen": zb(), "dist": torch.full((n,), NONE, dtype=torch.long, device=device),
        "bearing": zi(), "last_seen": zi(), "contact": zb(), "line": zi(),
    }


def reinicia(S: dict, mask: torch.Tensor) -> dict:
    """strategy_init() solo en los entornos de la mascara."""
    ini = estado_inicial(mask.shape[0], mask.device)
    return {k: torch.where(mask, ini[k], v) for k, v in S.items()}


def _slew(prev, target, max_step):
    d = target - prev
    return torch.where(d > max_step, prev + max_step,
                       torch.where(d < -max_step, prev - max_step, target))


def percibe(S: dict, P: dict, dist: torch.Tensor, line: torch.Tensor, t: torch.Tensor) -> dict:
    """perceive(): centroide ponderado del rival, histeresis y contacto frontal."""
    ang = torch.tensor(ANG_CDEG, dtype=torch.long, device=dist.device)
    bits = torch.tensor([1, 2, 4, 8], dtype=torch.long, device=dist.device)
    dvm = P["dist_valid_max_mm"][:, None]
    valid = (dist != NONE) & (dist <= dvm)
    w = torch.where(valid, dvm - dist + 1, 0)
    w_sum = w.sum(1)
    w_ang = (w * ang).sum(1)
    nearest = torch.where(valid, dist, NONE).amin(1)
    seen_now = w_sum > 0
    bearing_now = torch.div(w_ang, w_sum.clamp(min=1), rounding_mode="trunc")

    hold = (~seen_now) & (S["last_seen"] != 0) & ((t - S["last_seen"]) < P["target_hold_ms"])
    S = dict(S)
    S["seen"] = seen_now | hold
    S["dist"] = torch.where(seen_now, nearest, torch.where(hold, S["dist"], NONE))
    S["bearing"] = torch.where(seen_now, bearing_now, S["bearing"])
    S["last_seen"] = torch.where(seen_now, t, S["last_seen"])
    b = S["bearing"]
    S["contact"] = seen_now & (nearest <= P["dist_contact_mm"]) & (b.abs() <= P["contact_cone_cdeg"])
    S["line"] = (line.long() * bits).sum(1)
    return S


def paso(S: dict, P: dict, dist: torch.Tensor, line: torch.Tensor,
         t: torch.Tensor, armed: torch.Tensor):
    """strategy_step() para N maquinas. Devuelve (S, izquierda, derecha)."""
    S = percibe(S, P, dist, line, t)
    armed = armed.expand_as(S["state"])
    un = ~armed

    # --- 0. sin permiso de arranque: WAIT, rampa a cero ---------------------
    st = S["state"]
    S["t_state"] = torch.where(un & (st != WAIT), t, S["t_state"])
    st = torch.where(un, WAIT, st)
    S["prev_l"] = torch.where(un, 0.0, S["prev_l"])
    S["prev_r"] = torch.where(un, 0.0, S["prev_r"])

    w2o = armed & (st == WAIT)
    st = torch.where(w2o, OPENING, st)
    S["t_state"] = torch.where(w2o, t, S["t_state"])

    # --- 1. borde, salvo empuje comprometido ---------------------------------
    lockout = t < S["t_edge_clear"]
    linea = S["line"] != 0
    commit = S["commit_active"] & ~(armed & ~linea)
    cl = armed & linea & S["contact"]
    newc = cl & ~commit
    commit = commit | newc
    S["t_commit"] = torch.where(newc, t, S["t_commit"])
    S["push_commits"] = S["push_commits"] + newc.long()
    S["commit_active"] = commit
    comp = cl & ((t - S["t_commit"]) < P["push_commit_ms"])

    S["t_state"] = torch.where(comp & (st != ATTACK), t, S["t_state"])
    st = torch.where(comp, ATTACK, st)

    esc = armed & ~comp & linea & ~lockout & (st != EDGE)
    m = S["line"]
    front, rear = (m & FRONT) != 0, (m & REAR) != 0
    left, right = (m & LEFT) != 0, (m & RIGHT) != 0
    e_drive = torch.where(rear & ~front, 1.0, -1.0)
    paridad = torch.where((S["edge_events"] & 1) != 0, 1.0, -1.0)
    e_turn = torch.where(left & ~right, -1.0, torch.where(right & ~left, 1.0, paridad))
    S["esc_drive"] = torch.where(esc, e_drive, S["esc_drive"])
    S["esc_turn"] = torch.where(esc, e_turn, S["esc_turn"])
    S["esc_phase"] = torch.where(esc, 0, S["esc_phase"])
    S["edge_events"] = S["edge_events"] + esc.long()
    st = torch.where(esc, EDGE, st)
    S["t_state"] = torch.where(esc, t, S["t_state"])

    # --- 2. switch: todas las ramas a la vez -----------------------------------
    ins = t - S["t_state"]
    seen, dist_t, brg = S["seen"], S["dist"], S["bearing"]
    brad = brg.float() / 100.0 * DEG2RAD

    mE = armed & (st == EDGE)
    ph0 = S["esc_phase"] == 0
    fE = torch.where(ph0, S["esc_drive"] * P["v_escape"], 0.0)
    tE = torch.where(ph0, S["esc_turn"] * 0.15, S["esc_turn"] * P["v_escape"])

    mO = armed & (st == OPENING)
    op = P["opening"]
    fO = torch.where(op == 3, 0.10, P["v_opening"])
    tO = torch.where(op == 1, 0.45, torch.where(op == 2, -0.45, torch.where(op == 3, 0.70, 0.0)))

    mS = armed & (st == SEARCH)
    mSg = mS & ~seen
    pr = S["probing"]
    dirS = torch.where(brg >= 0, 1.0, -1.0)
    fS = torch.where(pr, P["v_search"], P["v_search"] * (1.0 + P["search_turn_ratio"]))
    tS = torch.where(pr, 0.0, dirS * P["v_search"])

    mT = armed & (st == TRACK)
    mTg = mT & seen & (dist_t > P["dist_attack_mm"])
    tT = torch.clamp(P["track_kp"] * brad, -P["track_max_diff"], P["track_max_diff"])

    mA = armed & (st == ATTACK)
    mAg = mA & seen & (dist_t <= P["dist_track_mm"])
    tA = torch.clamp(P["track_kp"] * brad * P["attack_kp_scale"],
                     -P["attack_max_diff"], P["attack_max_diff"])

    mW = armed & (st == WAIT)

    fwd = torch.where(mE, fE, torch.where(mO, fO, torch.where(mSg, fS, torch.where(
        mTg, P["v_track"], torch.where(mAg, P["v_attack"], 0.0)))))
    turn = torch.where(mE, tE, torch.where(mO, tO, torch.where(mSg, tS, torch.where(
        mTg, tT, torch.where(mAg, tA, 0.0)))))
    drives = mE | mO | mSg | mTg | mAg | mW

    # --- drive(): mezclador, rampa y zona muerta -----------------------------
    max_step = P["slew_per_s"] * (P["dt_ms"].float() / 1000.0)
    l = _slew(S["prev_l"], torch.clamp(fwd - turn, -1.0, 1.0), max_step)
    r = _slew(S["prev_r"], torch.clamp(fwd + turn, -1.0, 1.0), max_step)
    S["prev_l"] = torch.where(drives, l, S["prev_l"])
    S["prev_r"] = torch.where(drives, r, S["prev_r"])
    l = torch.where(l.abs() < P["deadband"], 0.0, l)
    r = torch.where(r.abs() < P["deadband"], 0.0, r)
    izq = torch.where(drives, l, 0.0)
    der = torch.where(drives, r, 0.0)

    # --- transiciones posteriores al drive() de cada rama -------------------
    tst = S["t_state"]
    probing = S["probing"]
    # EDGE_ESCAPE
    e0 = mE & ph0 & (ins >= P["escape_back_ms"])
    e1 = mE & ~ph0 & (ins >= P["escape_turn_ms"])
    S["esc_phase"] = torch.where(e0, 1, S["esc_phase"])
    S["t_edge_clear"] = torch.where(e1, t + P["escape_lockout_ms"], S["t_edge_clear"])
    # OPENING
    o1 = mO & seen & (dist_t <= P["dist_track_mm"])
    o2 = mO & ~o1 & (ins >= P["opening_ms"])
    # SEARCH
    s1 = mS & seen
    s2 = mSg & pr & (ins >= P["search_probe_ms"])
    s3 = mSg & ~pr & (ins >= P["search_spin_ms"])
    # TRACK
    k1 = mT & ~seen
    k2 = mT & seen & (dist_t <= P["dist_attack_mm"])
    # ATTACK
    a1 = mA & ~seen
    a2 = mA & seen & (dist_t > P["dist_track_mm"])

    a_search = e1 | o2 | k1 | a1
    a_track = o1 | s1 | a2
    a_attack = k2
    st = torch.where(a_search, SEARCH, torch.where(a_track, TRACK, torch.where(a_attack, ATTACK, st)))
    reloj = e0 | e1 | o1 | o2 | s1 | s2 | s3 | k1 | k2 | a1 | a2
    S["t_state"] = torch.where(reloj, t, tst)
    S["probing"] = (probing | s3) & ~(e1 | k1 | a1 | s2)
    S["state"] = st
    return S, izq, der
