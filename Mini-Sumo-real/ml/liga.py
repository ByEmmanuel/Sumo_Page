"""
liga.py -- ranking de algoritmos y direccion de mejora.

Responde a tres preguntas y lo deja en data/liga.json:

1. Quien pelea mejor. Todos contra todos en la GPU (versiones de la bitacora
   y candidatos), en las tres colocaciones del reglamento. Con la probabilidad
   de ganar cada combate se ajusta un rating de Bradley-Terry por maxima
   verosimilitud, en escala Elo.

2. Quien le gusta mas al usuario. Los votos A/B entre clips de dos algoritmos
   dan otro rating Bradley-Terry, hecho solo con votos.

3. Hacia donde se inclinan las mejores versiones. Un modelo sustituto (una
   red pequena entrenada en la GPU) aprende parametros -> aptitud con todas
   las muestras de todas las corridas de CMA-ES. Su gradiente en el campeon
   dice que parametros conviene subir o bajar, y su tamano medio sobre las
   mejores muestras, cuanto importa cada uno. La recompensa humana, en
   cambio, vive en el espacio de los rasgos: su pendiente (recompensa.json)
   dice que conductas prefiere el usuario.
"""

from __future__ import annotations

import datetime as _dt
import json
import math

import numpy as np
import torch
import torch.nn as nn

from . import candidatos, config
from .banco import COLOCACIONES_REG, Rival, evaluar
from .config import APRENDIBLES, DATA
from .sim import FSM, Arena, Cfg

FICHERO = DATA / "liga.json"
ELO = 400.0 / math.log(10.0)


def algoritmos(max_candidatos: int = 8) -> list[tuple[str, dict]]:
    out = [(v, config.params_version(v)) for v in config.versiones_registradas()]
    # un candidato ya exportado vive en la liga como su version, no dos veces
    vivos = [c for c in candidatos.carga() if not c.get("version")]
    for c in vivos[-max_candidatos:]:
        out.append((c["id"], config.completa(c["params"])))
    return out


def bradley_terry(victorias: np.ndarray, prior: float = 0.05) -> np.ndarray:
    """victorias[i, j] = veces (o masa de probabilidad) que i gano a j."""
    n = victorias.shape[0]
    w = torch.tensor(victorias, dtype=torch.float64)
    r = torch.zeros(n, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([r], max_iter=200, line_search_fn="strong_wolfe")

    def cierre():
        opt.zero_grad()
        d = r[:, None] - r[None, :]
        nll = -(w * torch.nn.functional.logsigmoid(d)).sum() + prior * (r ** 2).sum()
        nll.backward()
        return nll

    opt.step(cierre)
    r = r.detach()
    return (r - r.mean()).numpy()


@torch.no_grad()
def todos_contra_todos(algos, rondas: int = 32, modo: str = "robusto", semilla: int = 0):
    torch.manual_seed(semilla)
    arena = Arena(Cfg(modo=modo, max_s=30.0))
    rivales = [Rival(n, FSM, p) for n, p in algos]
    ev = evaluar(arena, [p for _, p in algos], rivales, COLOCACIONES_REG, rondas)
    comb = ev.combate.cpu().numpy()                 # [K, R, 3]: gana, jueces, pierde
    n = len(algos)
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                # i contra j jugando i de Gelatina, y j contra i al reves
                W[i, j] += comb[i, j, 0] + 0.5 * comb[i, j, 1] + comb[j, i, 2] + 0.5 * comb[j, i, 1]
    return W * rondas, comb


def rating_humano(nombres: list[str]):
    from .feedback import carga_clip, votos
    idx = {n: i for i, n in enumerate(nombres)}
    V = np.zeros((len(nombres), len(nombres)))
    n_votos = 0
    for v in votos():
        if v["tipo"] != "par" or v["preferencia"] == "ninguno":
            continue
        a, b = carga_clip(v["a"])["algoritmo"], carga_clip(v["b"])["algoritmo"]
        if a not in idx or b not in idx or a == b:
            continue
        ia, ib = idx[a], idx[b]
        pa = {"a": 1.0, "b": 0.0, "igual": 0.5}[v["preferencia"]]
        V[ia, ib] += pa
        V[ib, ia] += 1.0 - pa
        n_votos += 1
    if n_votos == 0:
        return None, 0
    return bradley_terry(V, prior=0.5), n_votos


class Sustituto(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, 128), nn.SiLU(), nn.Linear(128, 128), nn.SiLU(), nn.Linear(128, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def direccion(punto: dict, log=print, device: str = "cuda") -> dict | None:
    """Gradiente del modelo sustituto en `punto` (parametros completos)."""
    from .es import codifica
    xs, fs = [], []
    for f in sorted((DATA / "corridas").glob("*/muestras.npz")):
        m = np.load(f)
        if m["x"].shape[1] != len(APRENDIBLES):
            continue
        xs.append(m["x"])
        fs.append(m["f"][:, 0])                       # aptitud simulada, comparable entre corridas
    if not xs:
        return None
    X = torch.tensor(np.concatenate(xs), dtype=torch.float32, device=device)
    Y = torch.tensor(np.concatenate(fs), dtype=torch.float32, device=device)
    mu, sd = Y.mean(), Y.std().clamp(min=1e-6)
    Yn = (Y - mu) / sd
    g = torch.Generator(device="cpu").manual_seed(0)
    perm = torch.randperm(len(X), generator=g).to(device)
    corte = max(1, len(X) // 10)
    te, tr = perm[:corte], perm[corte:]
    torch.manual_seed(0)
    red = Sustituto(X.shape[1]).to(device)
    opt = torch.optim.AdamW(red.parameters(), lr=2e-3, weight_decay=1e-4)
    for paso in range(3000):
        b = tr[torch.randint(len(tr), (4096,), device=device)]
        perdida = ((red(X[b]) - Yn[b]) ** 2).mean()
        opt.zero_grad()
        perdida.backward()
        opt.step()
    with torch.no_grad():
        r2 = 1.0 - ((red(X[te]) - Yn[te]) ** 2).mean().item() / Yn[te].var().item()

    x0 = torch.tensor(codifica(punto), dtype=torch.float32, device=device).clamp(0, 1).requires_grad_(True)
    red(x0[None]).sum().backward()
    grad = x0.grad.cpu().numpy() * float(sd)          # aptitud por unidad normalizada
    top = X[torch.argsort(Y, descending=True)[: max(64, len(X) // 10)]].clone().requires_grad_(True)
    red(top).sum().backward()
    importancia = (top.grad.abs().mean(0).cpu().numpy() * float(sd))
    filas = []
    for (nombre, tipo, lo, hi, _), gi, imp in zip(APRENDIBLES, grad, importancia):
        paso = 0.05 * (hi - lo)                        # un 5 % del rango
        filas.append({"nombre": nombre, "gradiente": float(gi), "importancia": float(imp),
                      "sentido": "subir" if gi > 0 else "bajar",
                      "paso_sugerido": float(np.sign(gi) * paso) if tipo != "enum" else 0.0,
                      "ganancia_por_paso": float(abs(gi) * 0.05)})
    filas.sort(key=lambda f: -f["importancia"])
    log(f"[liga] sustituto: {len(X):,} muestras, R^2 fuera de muestra {r2:.2f}")
    return {"muestras": int(len(X)), "r2": r2, "parametros": filas}


def actualiza(log=print, rondas: int = 32) -> dict:
    algos = algoritmos()
    nombres = [n for n, _ in algos]
    log(f"[liga] {len(algos)} algoritmos, todos contra todos ({rondas} asaltos por colocacion)")
    W, comb = todos_contra_todos(algos, rondas)
    r_sim = bradley_terry(W)
    r_hum, n_votos = rating_humano(nombres)
    anterior = json.loads(FICHERO.read_text()) if FICHERO.exists() else {}
    campeones = anterior.get("campeones", [])

    tabla = []
    for i, n in enumerate(nombres):
        fila = {"id": n, "tipo": "candidato" if n.startswith("c-") else "version",
                "elo": round(1500 + r_sim[i] * ELO, 1),
                "elo_humano": None if r_hum is None else round(1500 + r_hum[i] * ELO, 1),
                "gana_combate_medio": float(np.mean([comb[i, j, 0] for j in range(len(algos)) if j != i]))}
        tabla.append(fila)
    orden = sorted(tabla, key=lambda f: -f["elo"])
    mejor = orden[0]
    ultima_version = next(f for f in tabla[::-1] if f["tipo"] == "version")
    if mejor["tipo"] == "candidato" and mejor["elo"] > ultima_version["elo"] + 10 \
            and mejor["id"] not in [c["id"] for c in campeones]:
        campeones.append({"id": mejor["id"], "params": dict(algos[nombres.index(mejor["id"])][1]),
                          "elo": mejor["elo"], "fecha": _dt.datetime.now().astimezone().isoformat(timespec="seconds")})
        log(f"[liga] {mejor['id']} entra en la liga de campeones (Elo {mejor['elo']:.0f} "
            f"frente a {ultima_version['id']} {ultima_version['elo']:.0f})")

    d = direccion(algos[nombres.index(mejor["id"])][1], log)
    humano = json.loads((DATA / "recompensa.json").read_text()) if (DATA / "recompensa.json").exists() else None
    liga = {
        "fecha": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "rondas": rondas, "algoritmos": orden, "matriz_combate": comb[:, :, 0].round(3).tolist(),
        "nombres": nombres, "votos_entre_algoritmos": n_votos, "campeones": campeones,
        "direccion": d, "preferencias_humanas": humano,
    }
    FICHERO.write_text(json.dumps(liga, indent=2, ensure_ascii=False))
    log(f"  {'algoritmo':10s} {'Elo':>7s} {'Elo humano':>11s} {'gana combate':>13s}")
    for f in orden:
        eh = "-" if f["elo_humano"] is None else f"{f['elo_humano']:.0f}"
        log(f"  {f['id']:10s} {f['elo']:7.0f} {eh:>11s} {f['gana_combate_medio']:13.1%}")
    if d:
        log("  la GPU se inclina hacia:")
        for p in d["parametros"][:6]:
            log(f"      {'+' if p['gradiente'] > 0 else '-'} {p['nombre']:20s} importancia {p['importancia']:.3f}")
    return liga
