"""
banco.py -- evaluar juegos de parametros contra un conjunto de rivales en la GPU.

Una evaluacion es una rejilla candidato x rival x colocacion x asalto que se
juega entera en una sola pasada del simulador. Con `compartir`, todos los
candidatos juegan los mismos asaltos (misma colocacion, mismo jitter y misma
aleatorizacion de dominio): la comparacion entre ellos es mas limpia porque
la suerte del sorteo es comun a todos.

La aptitud sigue al reglamento: lo que cuenta es ganar el combate a tres
rondas (frente, lado, espalda), no un asalto suelto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import torch

from . import config
from .config import DATA, RIVALES
from .sim import CHARGER, FSM, RASGOS, SPINNER, STATIC, Arena, params_tensor

COLOCACIONES_REG = (1, 2, 3)


@dataclass
class Rival:
    nombre: str
    tipo: int
    params: dict | None = None


def rivales_estandar(con_liga: bool = True) -> list[Rival]:
    """Los tres rivales de guion, las versiones de la bitacora y los campeones
    que ya salieron de entrenamientos anteriores (la liga)."""
    out = [Rival("static", STATIC), Rival("charger", CHARGER), Rival("spinner", SPINNER)]
    juegos = []
    for ver in config.versiones_registradas():
        juegos.append((ver, config.params_version(ver)))
    if con_liga:
        from .candidatos import carga
        exportados = {c["id"] for c in carga() if c.get("version")}
        liga = DATA / "liga.json"
        if liga.exists():
            for c in json.loads(liga.read_text()).get("campeones", [])[-3:]:
                if c["id"] not in exportados:            # ya esta como version
                    juegos.append((c["id"], config.completa(c["params"])))
    # dos versiones con los mismos parametros (v0.1.1 solo arreglo el Makefile)
    # son el mismo rival: contarlo dos veces le daria doble peso en la aptitud
    vistos = {}
    for nombre, p in juegos:
        vistos[json.dumps(p, sort_keys=True)] = (nombre, p)
    out += [Rival(n, FSM, p) for n, p in vistos.values()]
    return out


def combate(pw, pd, pl):
    """sim.probabilidad_combate para tensores con la colocacion en la ultima dimension."""
    P = {(0, 0): torch.ones_like(pw[..., 0])}
    W = torch.zeros_like(pw[..., 0]); L = torch.zeros_like(W); D = torch.zeros_like(W)
    for r in range(3):
        Q = {}
        for (i, j), p in P.items():
            for (di, dj), q in (((1, 0), pw[..., r]), ((0, 0), pd[..., r]), ((0, 1), pl[..., r])):
                Q[(i + di, j + dj)] = Q.get((i + di, j + dj), 0.0) + p * q
        P = {}
        for (i, j), p in Q.items():
            if i == 2:
                W = W + p
            elif j == 2:
                L = L + p
            else:
                P[(i, j)] = p
    for (i, j), p in P.items():
        if i > j:
            W = W + p
        elif j > i:
            L = L + p
        else:
            W = W + p * pw[..., 0]
            L = L + p * pl[..., 0]
            D = D + p * pd[..., 0]
    return W, D, L


@dataclass
class Evaluacion:
    candidatos: int
    rivales: list[str]
    colocaciones: tuple
    rondas: int
    res: torch.Tensor          # [K, R, C, n] +1 / 0 / -1
    razon: torch.Tensor        # [K, R, C, n]
    t_fin: torch.Tensor        # [K, R, C, n]
    rasgos: torch.Tensor       # [K, R, C, n, F]
    aptitud: torch.Tensor      # [K]
    combate: torch.Tensor      # [K, R, 3] gana / jueces / pierde
    extra: dict = field(default_factory=dict)

    def resumen(self, k: int) -> dict:
        """Metricas legibles de un candidato."""
        res, raz = self.res[k], self.razon[k]
        out = {"aptitud": float(self.aptitud[k]), "rivales": []}
        for i, nombre in enumerate(self.rivales):
            r = res[i]
            fila = {"nombre": nombre, "asaltos": int(r.numel()),
                    "gana": float((r == 1).float().mean()), "pierde": float((r == -1).float().mean()),
                    "empata": float((r == 0).float().mean()),
                    "auto_salidas": int((raz[i] == 3).sum()),
                    "colocaciones": {}}
            for j, c in enumerate(self.colocaciones):
                rc = r[j]
                fila["colocaciones"][config.COLOCACIONES[c]] = {
                    "gana": float((rc == 1).float().mean()), "pierde": float((rc == -1).float().mean())}
            if self.colocaciones == COLOCACIONES_REG:
                w, d, l = self.combate[k, i].tolist()
                fila["combate"] = {"gana": w, "jueces": d, "pierde": l}
            out["rivales"].append(fila)
        tot = res.flatten()
        out["gana"] = float((tot == 1).float().mean())
        out["pierde"] = float((tot == -1).float().mean())
        out["auto_salidas"] = float((raz.flatten() == 3).float().mean())
        if self.colocaciones == COLOCACIONES_REG:
            out["combate_gana"] = float(self.combate[k, :, 0].mean())
            out["combate_pierde"] = float(self.combate[k, :, 2].mean())
        out["rasgos"] = dict(zip(RASGOS, self.rasgos[k].reshape(-1, len(RASGOS)).mean(0).tolist()))
        return out


def puntuacion_asalto(res, razon, t_fin, max_s):
    """+1 gana, 0 empata, -1 pierde; -0,25 extra por salirse solo; hasta +0,25
    por ganar rapido."""
    s = res.float()
    s = s - 0.25 * (razon == 3).float()
    s = s + 0.25 * (res == 1).float() * (1.0 - t_fin / max_s)
    return s


@torch.no_grad()
def evaluar(arena: Arena, candidatos: list[dict], rivales: list[Rival],
            colocaciones=COLOCACIONES_REG, rondas: int = 8, compartir: bool = True,
            registrar: torch.Tensor | None = None) -> Evaluacion:
    K, R, C = len(candidatos), len(rivales), len(colocaciones)
    S = R * C * rondas                                  # asaltos por candidato
    dev = arena.dev
    Pm = params_tensor(candidatos, S, dev)
    relleno = config.params_version(config.versiones_registradas()[-1])
    juegos_riv = [r.params or relleno for r in rivales]
    Pf = params_tensor([juegos_riv[i] for _ in range(K) for i in range(R)], C * rondas, dev)
    tipo = torch.tensor([r.tipo for r in rivales]).repeat_interleave(C * rondas).repeat(K)
    col = torch.tensor(colocaciones).repeat_interleave(rondas).repeat(R).repeat(K)

    out = arena.correr(Pm, tipo, Pf, col, registrar=registrar, compartir=S if compartir else None)
    forma = (K, R, C, rondas)
    res = out["res"].view(forma)
    razon = out["razon"].view(forma)
    t_fin = out["t_fin"].view(forma)
    rasgos = out["rasgos"].view(*forma, -1)

    score = puntuacion_asalto(res, razon, t_fin, arena.cfg.max_s)
    if tuple(colocaciones) == COLOCACIONES_REG:
        pw = (res == 1).float().mean(-1)
        pd = (res == 0).float().mean(-1)
        pl = (res == -1).float().mean(-1)
        W, D, L = combate(pw, pd, pl)                   # [K, R]
        comb = torch.stack([W, D, L], dim=-1)
        aptitud = (W - L).mean(1) + 0.25 * score.mean(dim=(1, 2, 3))
    else:
        comb = torch.zeros(K, R, 3, device=dev)
        aptitud = score.mean(dim=(1, 2, 3))
    ev = Evaluacion(K, [r.nombre for r in rivales], tuple(colocaciones), rondas,
                    res, razon, t_fin, rasgos, aptitud, comb)
    if "trayectoria" in out:
        ev.extra["trayectoria"] = out["trayectoria"]
    return ev
