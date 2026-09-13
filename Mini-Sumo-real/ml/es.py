"""
es.py -- estrategia evolutiva (CMA-ES) sobre los parametros de la maquina de estados.

Por que CMA-ES y no un gradiente: la aptitud (ganar combates) no es derivable
respecto a los parametros, es ruidosa y tiene saltos (un umbral de distancia
cambia de estado a la maquina). CMA-ES solo necesita ordenar candidatos, y
aprende la forma del terreno: la matriz de covarianza acaba apuntando a las
combinaciones de parametros que mejoran juntas.

Cada generacion evalua la poblacion entera en una sola pasada de la GPU. La
aptitud de un candidato es

    aptitud = aptitud_simulada + lambda_humano * recompensa_humana

donde la recompensa humana sale del modelo entrenado con los votos del
usuario (ml/recompensa.py). Sin votos, lambda_humano = 0.

Los parametros viven normalizados en [0, 1] con reflexion en los bordes, asi
que la busqueda nunca sale del rango de config.PARAMS.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import time

import numpy as np
import torch

from . import config
from .banco import COLOCACIONES_REG, evaluar, rivales_estandar
from .config import APRENDIBLES, DATA
from .sim import Arena, Cfg

# ---------------------------------------------------------------------------
#  codificacion
# ---------------------------------------------------------------------------


def codifica(p: dict) -> np.ndarray:
    x = []
    for nombre, tipo, lo, hi, _ in APRENDIBLES:
        if tipo == "enum":
            x.append((p[nombre] + 0.5) / (hi - lo + 1))
        else:
            x.append((p[nombre] - lo) / (hi - lo))
    return np.array(x, dtype=np.float64)


def refleja(x: np.ndarray) -> np.ndarray:
    """R -> [0, 1] por reflexion: la frontera es un espejo, no una pared."""
    return 1.0 - np.abs(np.mod(x, 2.0) - 1.0)


def decodifica(x: np.ndarray, base: dict) -> dict:
    y = refleja(x)
    p = dict(base)
    for (nombre, tipo, lo, hi, _), v in zip(APRENDIBLES, y):
        if tipo == "enum":
            p[nombre] = int(min(hi, lo + math.floor(v * (hi - lo + 1))))
        else:
            p[nombre] = lo + v * (hi - lo)
    return config.recorta(p)


# ---------------------------------------------------------------------------
#  CMA-ES (Hansen, 2016), con actualizacion rango-uno y rango-mu
# ---------------------------------------------------------------------------


class CMAES:
    def __init__(self, x0: np.ndarray, sigma0: float, lam: int, semilla: int = 0):
        D = len(x0)
        self.D, self.lam, self.sigma = D, lam, sigma0
        self.m = x0.copy()
        mu = lam // 2
        w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
        self.w = w / w.sum()
        self.mu = mu
        self.mueff = 1.0 / np.sum(self.w ** 2)
        self.cc = (4 + self.mueff / D) / (D + 4 + 2 * self.mueff / D)
        self.cs = (self.mueff + 2) / (D + self.mueff + 5)
        self.c1 = 2 / ((D + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((D + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0.0, math.sqrt((self.mueff - 1) / (D + 1)) - 1) + self.cs
        self.chiN = math.sqrt(D) * (1 - 1 / (4 * D) + 1 / (21 * D * D))
        self.pc = np.zeros(D)
        self.ps = np.zeros(D)
        self.C = np.eye(D)
        self.B = np.eye(D)
        self.Dd = np.ones(D)
        self.gen = 0
        self.rng = np.random.default_rng(semilla)

    def pide(self) -> np.ndarray:
        z = self.rng.standard_normal((self.lam, self.D))
        self._y = z @ (self.B * self.Dd).T
        return self.m + self.sigma * self._y

    def cuenta(self, f: np.ndarray):
        """f: coste a minimizar, uno por candidato de la ultima llamada a pide()."""
        orden = np.argsort(f)
        y_sel = self._y[orden[: self.mu]]
        y_w = self.w @ y_sel
        self.m = self.m + self.sigma * y_w
        c_inv_sqrt_y = self.B @ ((self.B.T @ y_w) / self.Dd)
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * c_inv_sqrt_y
        norma = np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * (self.gen + 1)))
        hsig = float(norma / self.chiN < 1.4 + 2 / (self.D + 1))
        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y_w
        rank_mu = (y_sel * self.w[:, None]).T @ y_sel
        self.C = ((1 - self.c1 - self.cmu) * self.C
                  + self.c1 * (np.outer(self.pc, self.pc) + (1 - hsig) * self.cc * (2 - self.cc) * self.C)
                  + self.cmu * rank_mu)
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chiN - 1))
        self.sigma = min(self.sigma, 0.5)
        self.C = (self.C + self.C.T) / 2
        ev, B = np.linalg.eigh(self.C)
        self.Dd = np.sqrt(np.maximum(ev, 1e-12))
        self.B = B
        self.gen += 1


# ---------------------------------------------------------------------------
#  entrenamiento
# ---------------------------------------------------------------------------


def base_inicial(desde: str) -> dict:
    """Una version de la bitacora, WORK o el id de un candidato guardado."""
    if desde.startswith("c-"):
        from .candidatos import busca
        return config.completa(busca(desde)["params"])
    return config.params_version(desde)


def cambios(a: dict, b: dict) -> list[dict]:
    """Parametros que difieren entre dos juegos, en unidades de params.h."""
    out = []
    for nombre, tipo, lo, hi, apr in config.PARAMS:
        if not apr or a[nombre] == b[nombre]:
            continue
        d = b[nombre] - a[nombre]
        out.append({"nombre": nombre, "de": a[nombre], "a": b[nombre], "delta": d,
                    "delta_rel": d / (hi - lo) if hi > lo else 0.0})
    return sorted(out, key=lambda c: -abs(c["delta_rel"]))


def entrenar(generaciones: int = 60, poblacion: int = 384, rondas: int = 6,
             sigma0: float = 0.12, desde: str | None = None, lambda_humano: float | None = None,
             semilla: int = 0, modo: str = "robusto", nombre: str = "", log=print) -> dict:
    from .recompensa import ModeloRecompensa

    desde = desde or config.versiones_registradas()[-1]
    base = base_inicial(desde)
    torch.manual_seed(semilla)
    arena = Arena(Cfg(modo=modo, max_s=30.0))
    rivales = rivales_estandar()
    rm = ModeloRecompensa.carga()
    lam_h = lambda_humano if lambda_humano is not None else (rm.lambda_sugerida() if rm else 0.0)

    rid = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{nombre}" if nombre else "")
    carpeta = DATA / "corridas" / rid
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = {"id": rid, "desde": desde, "generaciones": generaciones, "poblacion": poblacion,
           "rondas": rondas, "sigma0": sigma0, "modo": modo, "semilla": semilla,
           "lambda_humano": lam_h, "rivales": [r.nombre for r in rivales],
           "preferencias": rm.n_datos if rm else 0,
           "asaltos_por_generacion": poblacion * len(rivales) * 3 * rondas}
    (carpeta / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    log(f"[es] corrida {rid}: {generaciones} gen x {poblacion} candidatos x "
        f"{cfg['asaltos_por_generacion'] // poblacion} asaltos; lambda_humano={lam_h:.2f}; desde {desde}")

    cma = CMAES(codifica(base), sigma0, poblacion, semilla)
    muestras_x, muestras_f = [], []
    elite: list[tuple[float, dict]] = []
    t0 = time.time()
    with open(carpeta / "log.jsonl", "w") as flog:
        for g in range(generaciones):
            X = cma.pide()
            cands = [decodifica(x, base) for x in X]
            ev = evaluar(arena, cands, rivales, COLOCACIONES_REG, rondas)
            apt_sim = ev.aptitud.cpu().numpy()
            humano = np.zeros(poblacion)
            if rm is not None and lam_h > 0:
                humano = rm.puntua(ev.rasgos).mean(dim=(1, 2, 3)).cpu().numpy()
            fit = apt_sim + lam_h * humano
            cma.cuenta(-fit)
            muestras_x.append(refleja(X))
            muestras_f.append(np.stack([apt_sim, humano], 1))
            i = int(np.argmax(fit))
            elite.append((float(fit[i]), cands[i]))
            comb = ev.combate[:, :, 0].mean(1).cpu().numpy()
            fila = {"gen": g, "t": round(time.time() - t0, 1), "aptitud_max": float(fit.max()),
                    "aptitud_media": float(fit.mean()), "sim_media": float(apt_sim.mean()),
                    "humano_media": float(humano.mean()), "combate_gana_media": float(comb.mean()),
                    "combate_gana_max": float(comb.max()), "sigma": cma.sigma,
                    "media": decodifica(cma.m, base)}
            flog.write(json.dumps(fila, ensure_ascii=False) + "\n")
            flog.flush()
            if g % 5 == 0 or g == generaciones - 1:
                log(f"[es] gen {g:3d}  aptitud max {fit.max():+.3f} media {fit.mean():+.3f}  "
                    f"combate {comb.mean():.3f} (max {comb.max():.3f})  sigma {cma.sigma:.3f}  "
                    f"{time.time() - t0:5.0f}s")

    np.savez_compressed(carpeta / "muestras.npz", x=np.concatenate(muestras_x), f=np.concatenate(muestras_f))

    # --- final: la media de la distribucion y la elite, medidas con calma -----
    elite.sort(key=lambda e: -e[0])
    finalistas = [decodifica(cma.m, base)] + [p for _, p in elite[:15]] + [base]
    ev = evaluar(arena, finalistas, rivales, COLOCACIONES_REG, rondas=48)
    humano = rm.puntua(ev.rasgos).mean(dim=(1, 2, 3)).cpu().numpy() if (rm and lam_h > 0) else np.zeros(len(finalistas))
    fit = ev.aptitud.cpu().numpy() + lam_h * humano
    orden = np.argsort(-fit[:-1])            # la base no puede ganar su propia corrida
    mejor = int(orden[0])
    campeon = finalistas[mejor]
    resumen = {
        "id": rid, "config": cfg, "segundos": round(time.time() - t0, 1),
        "base": {"params": base, "aptitud": float(fit[-1]), **ev.resumen(len(finalistas) - 1)},
        "campeon": {"params": campeon, "aptitud": float(fit[mejor]), "humano": float(humano[mejor]),
                    **ev.resumen(mejor)},
        "cambios": cambios(base, campeon),
        "direccion_media": cambios(base, decodifica(cma.m, base)),
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    from .candidatos import registra
    cid = registra(campeon, origen=rid, evaluacion=resumen["campeon"], base=desde)
    resumen["candidato"] = cid
    (carpeta / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    b, c = resumen["base"], resumen["campeon"]
    log(f"[es] fin en {resumen['segundos']:.0f}s. Campeon {cid}: combate {c['combate_gana']:.3f} "
        f"(base {b['combate_gana']:.3f}), aptitud {c['aptitud']:+.3f} (base {b['aptitud']:+.3f})")
    for ch in resumen["cambios"][:8]:
        log(f"      {ch['nombre']:20s} {ch['de']!s:>8} -> {ch['a']!s:<8}")
    return resumen
