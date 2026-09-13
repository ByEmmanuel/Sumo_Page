"""
validate.py -- el simulador de GPU contra el banco nativo en C.

Compila tests/harness.c contra la instantanea de cada version, lo corre con
varias semillas y compara las tasas de victoria, derrota y empate por rival
con las del simulador de GPU en modo banco. Un port correcto no reproduce las
mismas partidas (los generadores aleatorios son distintos), pero si las mismas
estadisticas: la diferencia tiene que caber en el error de muestreo.

    python -m ml validar [--versiones v0.1.0 v0.3.0] [--semillas 30]
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import torch

from . import config
from .config import ALGORITHMS, DATA, ROOT, VERSIONS
from .sim import Arena, Cfg, params_tensor

RIVALES_BANCO = ["static", "charger", "spinner", "mirror"]


def compila_harness(ver: str) -> Path:
    """Binario del banco nativo con el strategy.c de esa version."""
    cache = DATA / "cache" / f"harness_{ver}"
    (cache / "tests").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "tests" / "harness.c", cache / "tests" / "harness.c")
    origen = ALGORITHMS if ver == "WORK" else VERSIONS / ver / "snapshot" / "algorithms"
    shutil.copytree(origen, cache / "algorithms", dirs_exist_ok=True)
    binario = cache / "harness"
    subprocess.run(["gcc", "-std=c99", "-O2", "-I", str(cache / "algorithms"),
                    str(cache / "tests" / "harness.c"), str(cache / "algorithms" / "strategy.c"),
                    "-o", str(binario), "-lm"], check=True)
    return binario


def compila_harness_params(nombre: str, p: dict) -> Path:
    """Banco nativo con el strategy.c actual y un params.h reescrito con p.
    Sirve para medir un candidato en C antes de exportarlo: algorithms/ no se toca."""
    from .exportar import redondea, texto_params_h
    cache = DATA / "cache" / f"harness_{nombre}"
    (cache / "tests").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "tests" / "harness.c", cache / "tests" / "harness.c")
    shutil.copytree(ALGORITHMS, cache / "algorithms", dirs_exist_ok=True)
    texto, _ = texto_params_h(redondea(p))
    (cache / "algorithms" / "params.h").write_text(texto, encoding="utf-8")
    binario = cache / "harness"
    subprocess.run(["gcc", "-std=c99", "-O2", "-I", str(cache / "algorithms"),
                    str(cache / "tests" / "harness.c"), str(cache / "algorithms" / "strategy.c"),
                    "-o", str(binario), "-lm"], check=True)
    return binario


def banco_c(nombre: str, semillas: int = 30, rondas: int = 60) -> dict:
    """Un algoritmo en el banco nativo en C: la tabla oficial de `make medir`
    (semilla 12345, 60 asaltos por rival) y la media de `semillas` semillas,
    en el modo de siempre y en el del reglamento."""
    from .candidatos import algoritmo
    nombre, p = algoritmo(nombre)
    binario = compila_harness_params(nombre, p)
    out = {"algoritmo": nombre, "oficial": {}, "semillas": {}}
    for reglamento in (False, True):
        modo = "reglamento" if reglamento else "banco"
        dst = binario.parent / f"oficial_{modo}.json"
        cmd = [str(binario), "--all", "--rounds", str(rondas), "--version", nombre, "--out", str(dst)]
        if reglamento:
            cmd.append("--reglamento")
        subprocess.run(cmd, check=True, capture_output=True)
        out["oficial"][modo] = json.loads(dst.read_text())
        out["semillas"][modo] = corre_c(binario, semillas, rondas, reglamento)
    return out


def corre_c(binario: Path, semillas: int, rondas: int, reglamento: bool) -> dict:
    """Suma W/L/D por rival sobre semillas impares (--seed N usa N|1)."""
    def una(s):
        out = binario.parent / f"s{s}_{int(reglamento)}.json"
        cmd = [str(binario), "--all", "--rounds", str(rondas), "--seed", str(2 * s + 1), "--out", str(out)]
        if reglamento:
            cmd.append("--reglamento")
        subprocess.run(cmd, check=True, capture_output=True)
        return json.loads(out.read_text())["metrics"]["opponents"]

    tot = {r: [0, 0, 0] for r in RIVALES_BANCO}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for ops in ex.map(una, range(semillas)):
            for o in ops:
                t = tot[o["name"]]
                t[0] += o["wins"]; t[1] += o["losses"]; t[2] += o["draws"]
    return tot


@torch.no_grad()
def corre_gpu(arena: Arena, p: dict, por_rival: int, reglamento: bool) -> dict:
    rival = torch.repeat_interleave(torch.tensor([0, 1, 2, 3]), por_rival)   # 3 = mirror (FSM)
    n = rival.numel()
    col = (1 + torch.arange(n) % 3) if reglamento else torch.zeros(n, dtype=torch.long)
    P = params_tensor([p], n, "cuda")
    res = arena.correr(P, rival, P, col)["res"].cpu()
    tot = {}
    for i, nombre in enumerate(RIVALES_BANCO):
        r = res[i * por_rival:(i + 1) * por_rival]
        tot[nombre] = [int((r == 1).sum()), int((r == -1).sum()), int((r == 0).sum())]
    return tot


def compara(c: list[int], g: list[int]) -> list[dict]:
    nc, ng = sum(c), sum(g)
    filas = []
    for i, nombre in enumerate(("W", "L", "D")):
        pc, pg = c[i] / nc, g[i] / ng
        p = (c[i] + g[i]) / (nc + ng)
        se = math.sqrt(max(p * (1 - p), 1e-9) * (1 / nc + 1 / ng))
        z = (pg - pc) / se
        filas.append({"salida": nombre, "c": pc, "gpu": pg, "z": z,
                      "ok": abs(z) < 3.5 or abs(pg - pc) < 0.015})
    return filas


def validar(versiones: list[str] | None = None, semillas: int = 30, rondas: int = 60,
            por_rival: int = 8192) -> dict:
    versiones = versiones or config.versiones_registradas()
    informe = {"semillas_c": semillas, "rondas_c": rondas, "por_rival_gpu": por_rival, "casos": []}
    ok_total = True
    for reglamento in (False, True):
        arena = Arena(Cfg(modo="banco", max_s=60.0 if reglamento else 30.0))
        modo = "reglamento" if reglamento else "banco"
        for ver in versiones:
            binario = compila_harness(ver)
            c = corre_c(binario, semillas, rondas, reglamento)
            g = corre_gpu(arena, config.params_version(ver), por_rival, reglamento)
            print(f"\n  {ver}  modo {modo}   (C: {semillas}x{rondas} asaltos por rival, GPU: {por_rival})")
            print(f"  {'rival':9s} {'':3s} {'C':>7s} {'GPU':>7s} {'z':>6s}")
            for nombre in RIVALES_BANCO:
                for f in compara(c[nombre], g[nombre]):
                    ok_total &= f["ok"]
                    marca = "" if f["ok"] else "   <-- DIFIERE"
                    print(f"  {nombre:9s} {f['salida']:3s} {f['c']:7.3f} {f['gpu']:7.3f} {f['z']:+6.1f}{marca}")
                    informe["casos"].append({"version": ver, "modo": modo, "rival": nombre, **f})
    informe["ok"] = ok_total
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "validacion.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False))
    print(f"\n  {'VALIDADO' if ok_total else 'NO VALIDADO'}: informe en ml/data/validacion.json\n")
    return informe


if __name__ == "__main__":
    validar()
