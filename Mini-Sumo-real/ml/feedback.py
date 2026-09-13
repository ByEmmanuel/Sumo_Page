"""
feedback.py -- repeticiones de asaltos y votos del usuario.

Un clip es un asalto grabado: que algoritmo lucho, contra quien, en que
colocacion, como acabo, sus rasgos y la trayectoria completa para verlo en la
web. Un par es una pregunta al usuario: el MISMO asalto (mismo rival, misma
colocacion, mismo sorteo de dominio) jugado por dos algoritmos distintos. Asi
la unica diferencia entre los dos clips es el algoritmo.

Que pares se preguntan: primero los que acaban distinto (uno gana y el otro
no), despues los que el modelo de recompensa no sabe ordenar (maxima
discrepancia entre sus redes), y nunca mas de dos por rival y colocacion.

Ficheros:
    data/clips/<id>.json      un clip
    data/pares.json           las preguntas, pendientes y respondidas
    data/preferencias.jsonl   los votos, uno por linea, nunca se reescriben
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets

import torch

from . import config
from .banco import COLOCACIONES_REG, evaluar, rivales_estandar
from .candidatos import algoritmo
from .config import DATA
from .sim import RASGOS, RAZONES, Arena, Cfg

CLIPS = DATA / "clips"
PARES = DATA / "pares.json"
VOTOS = DATA / "preferencias.jsonl"
PREFERENCIAS = ("a", "b", "igual", "ninguno")
ETIQUETAS = ["agresivo", "prudente", "se sale solo", "empuja bien", "gira de más",
             "buena apertura", "pierde el frente", "brusco", "suave", "lento"]


def ahora() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def carga_pares() -> list[dict]:
    return json.loads(PARES.read_text(encoding="utf-8")) if PARES.exists() else []


def _guarda_pares(ps: list[dict]):
    DATA.mkdir(parents=True, exist_ok=True)
    PARES.write_text(json.dumps(ps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def carga_clip(cid: str) -> dict:
    return json.loads((CLIPS / f"{cid}.json").read_text(encoding="utf-8"))


def _clip(cid, algo, rival, col, res, razon, t_fin, rasgos, frames, dt) -> dict:
    fin = frames[:, 9].nonzero()
    corte = int(fin[0]) + 15 if len(fin) else frames.shape[0]
    f = frames[:corte].tolist()
    f = [[round(v, 4) for v in fila[:8]] + [int(fila[8]), int(fila[9])] for fila in f]
    return {"id": cid, "algoritmo": algo, "rival": rival, "colocacion": config.COLOCACIONES[col],
            "resultado": int(res), "razon": RAZONES[int(razon)], "t_fin": round(float(t_fin), 3),
            "rasgos": dict(zip(RASGOS, [round(v, 4) for v in rasgos])), "vector": list(rasgos),
            "dt": dt, "columnas": ["me_x", "me_y", "me_th", "fo_x", "fo_y", "fo_th",
                                    "cmd_l", "cmd_r", "estado", "fin"], "frames": f}


@torch.no_grad()
def genera_pares(a: str, b: str, rondas: int = 4, maximo: int = 12, modo: str = "robusto",
                 log=print) -> list[str]:
    from .recompensa import ModeloRecompensa

    na, pa = algoritmo(a)
    nb, pb = algoritmo(b)
    arena = Arena(Cfg(modo=modo, max_s=30.0, compilar=False))
    rivales = rivales_estandar(con_liga=False)
    R, C = len(rivales), len(COLOCACIONES_REG)
    S = R * C * rondas
    cada = 3
    ev = evaluar(arena, [pa, pb], rivales, COLOCACIONES_REG, rondas, compartir=True,
                 registrar=torch.arange(2 * S, device=arena.dev))
    traj = ev.extra["trayectoria"].cpu()
    res = ev.res.reshape(2, S).cpu()
    razon = ev.razon.reshape(2, S).cpu()
    t_fin = ev.t_fin.reshape(2, S).cpu()
    ras = ev.rasgos.reshape(2, S, -1).cpu()

    prio = (res[0] != res[1]).float() * 2.0 + 0.1 * torch.rand(S)
    rm = ModeloRecompensa.carga()
    if rm is not None:
        prio += rm.incertidumbre(ras).sum(0).cpu()
    cuenta, elegidas = {}, []
    for s in torch.argsort(prio, descending=True).tolist():
        riv, col = s // (C * rondas), (s // rondas) % C
        if cuenta.get((riv, col), 0) >= 2:
            continue
        cuenta[(riv, col)] = cuenta.get((riv, col), 0) + 1
        elegidas.append(s)
        if len(elegidas) >= maximo:
            break

    CLIPS.mkdir(parents=True, exist_ok=True)
    pares = carga_pares()
    nuevos = []
    for s in elegidas:
        riv, col = s // (C * rondas), COLOCACIONES_REG[(s // rondas) % C]
        ids = []
        for k, algo in ((0, na), (1, nb)):
            cid = f"{algo}-{rivales[riv].nombre}-{config.COLOCACIONES[col]}-{secrets.token_hex(3)}"
            clip = _clip(cid, algo, rivales[riv].nombre, col, res[k, s], razon[k, s], t_fin[k, s],
                         ras[k, s].tolist(), traj[k * S + s], cada * config.DT_S)
            (CLIPS / f"{cid}.json").write_text(json.dumps(clip, separators=(",", ":")))
            ids.append(cid)
        if secrets.randbelow(2):          # que el lado de la pantalla no delate al algoritmo
            ids.reverse()
        pid = f"p-{len(pares) + 1:04d}"
        pares.append({"id": pid, "a": ids[0], "b": ids[1], "rival": rivales[riv].nombre,
                      "colocacion": config.COLOCACIONES[col], "algoritmos": [na, nb],
                      "creado": ahora(), "estado": "pendiente"})
        nuevos.append(pid)
    _guarda_pares(pares)
    log(f"[pares] {len(nuevos)} comparaciones nuevas entre {na} y {nb} "
        f"({sum(int(res[0, s] != res[1, s]) for s in elegidas)} con resultado distinto)")
    return nuevos


def registra_voto(pid: str, preferencia: str, etiquetas=(), nota: str = "", fuente: str = "cli") -> dict:
    if preferencia not in PREFERENCIAS:
        raise ValueError(f"preferencia invalida: {preferencia} (usa {', '.join(PREFERENCIAS)})")
    pares = carga_pares()
    par = next((p for p in pares if p["id"] == pid), None)
    if par is None:
        raise KeyError(f"no existe el par {pid}")
    voto = {"fecha": ahora(), "tipo": "par", "par": pid, "a": par["a"], "b": par["b"],
            "preferencia": preferencia, "etiquetas": list(etiquetas), "nota": nota, "fuente": fuente}
    with open(VOTOS, "a", encoding="utf-8") as f:
        f.write(json.dumps(voto, ensure_ascii=False) + "\n")
    par["estado"] = "votado"
    par["voto"] = preferencia
    _guarda_pares(pares)
    return voto


def registra_valoracion(cid: str, valor: str, etiquetas=(), nota: str = "", fuente: str = "cli") -> dict:
    if valor not in ("bueno", "malo"):
        raise ValueError("valor invalido: usa bueno o malo")
    carga_clip(cid)
    voto = {"fecha": ahora(), "tipo": "valoracion", "clip": cid, "valor": valor,
            "etiquetas": list(etiquetas), "nota": nota, "fuente": fuente}
    with open(VOTOS, "a", encoding="utf-8") as f:
        f.write(json.dumps(voto, ensure_ascii=False) + "\n")
    return voto


def votos() -> list[dict]:
    if not VOTOS.exists():
        return []
    return [json.loads(l) for l in VOTOS.read_text(encoding="utf-8").splitlines() if l.strip()]


def datos_entrenamiento():
    """Votos -> (pares [(rasgos_a, rasgos_b, y)], sueltos [(rasgos, y)])."""
    vec = lambda cid: torch.tensor(carga_clip(cid)["vector"], dtype=torch.float32)
    pares, sueltos = [], []
    for v in votos():
        if v["tipo"] == "par":
            if v["preferencia"] == "ninguno":            # los dos malos
                sueltos += [(vec(v["a"]), 0.0), (vec(v["b"]), 0.0)]
            else:
                y = {"a": 1.0, "b": 0.0, "igual": 0.5}[v["preferencia"]]
                pares.append((vec(v["a"]), vec(v["b"]), y))
        elif v["tipo"] == "valoracion":
            sueltos.append((vec(v["clip"]), 1.0 if v["valor"] == "bueno" else 0.0))
    return pares, sueltos


def rasgos_referencia() -> torch.Tensor:
    """Rasgos de todos los clips grabados: fijan la escala del modelo."""
    return torch.tensor([json.loads(p.read_text())["vector"] for p in CLIPS.glob("*.json")],
                        dtype=torch.float32)
