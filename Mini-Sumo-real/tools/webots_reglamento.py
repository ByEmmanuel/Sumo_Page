#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webots_reglamento.py -- tanda de Webots sin ventana contra el banco de rivales.

Lanza un Webots por rival en paralelo (puertos 1260-1263), cada uno con su
copia temporal del mundo, y junta los resultados en
runs/webots_<version>_<colocacion>.json con el mismo esquema que el banco
nativo. Mundos y controladores temporales se borran al terminar: dohyo.wbt no
se toca.

    python3 tools/webots_reglamento.py --version v0.3.0                 # version congelada
    python3 tools/webots_reglamento.py --version c-001                  # lo que hay en algorithms/
    python3 tools/webots_reglamento.py --version v0.3.0 --colocacion banco

Si --version es una version de la bitacora, Gelatina lleva un controlador
compilado desde su instantanea; si no, el de algorithms/ (el arbol de trabajo).
Rivales: static, charger y spinner (controlador oponente) y v0.3.0 congelada.
--colocacion reglamento (por defecto): frente, lado y espaldas a 5 cm.
--colocacion banco: la diagonal a 36 cm de las metricas antiguas de Webots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLDS = ROOT / "webots" / "worlds"
CTRL = ROOT / "webots" / "controllers"
RUNS = ROOT / "runs"
PUERTOS = [1300, 1301, 1302, 1303]
ENV = dict(os.environ, WEBOTS_HOME=os.environ.get("WEBOTS_HOME", "/usr/local/webots"))


def make(d: Path):
    r = subprocess.run(["make", "-C", str(d)], env=ENV, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[webots] no compila {d.name}:\n{r.stdout}{r.stderr}")


def congelado(ver: str, prefijo: str) -> str:
    """Controlador temporal con la maquina de estados de una version de la bitacora."""
    nombre = prefijo + ver.replace(".", "")
    d = CTRL / nombre
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    snap = ROOT / "versions" / ver / "snapshot"
    for f in ("main.c", "hal_webots.c", "hal.h"):
        shutil.copy(snap / "webots" / "controllers" / "gelatina_nuclear" / f, d / f)
    for f in ("strategy.c", "strategy.h", "params.h", "sumo_types.h"):
        shutil.copy(snap / "algorithms" / f, d / f)
    (d / "Makefile").write_text("C_SOURCES = main.c hal_webots.c strategy.c\n"
                                "CFLAGS += -std=c99 -Wall -Wextra -O2\n"
                                "include $(WEBOTS_HOME)/resources/Makefile.include\n")
    make(d)
    return nombre


def _args(lista: list[str]) -> str:
    if not lista:
        return "controllerArgs []"
    return "controllerArgs [\n" + "".join(f'    "{a}"\n' for a in lista) + "  ]"


def mundo(tag, yo, controlador_rival, args_rival, args_arbitro) -> Path:
    txt = (WORLDS / "dohyo.wbt").read_text(encoding="utf-8")
    i_yo, i_riv, i_arb = txt.index("DEF GELATINA "), txt.index("DEF RIVAL "), txt.index("DEF ARBITRO ")
    gel, riv, arb = txt[i_yo:i_riv], txt[i_riv:i_arb], txt[i_arb:]
    if yo != "gelatina_nuclear":
        gel = gel.replace("{\n", "{\n  controller \"" + yo + "\"\n", 1)
    riv = re.sub(r'controller "[^"]*"', f'controller "{controlador_rival}"', riv, count=1)
    riv = re.sub(r"controllerArgs \[[^\]]*\]", _args(args_rival), riv, count=1)
    arb = re.sub(r"controllerArgs \[[^\]]*\]", _args(args_arbitro), arb, count=1)
    ruta = WORLDS / f"_lote_{tag}.wbt"
    ruta.write_text(txt[:i_yo] + gel + riv + arb, encoding="utf-8")
    return ruta


def una(tag, yo, controlador, args_rival, version, colocacion, rondas, puerto, limite_s) -> dict:
    out = RUNS / f"_tmp_lote_{tag}.json"
    out.unlink(missing_ok=True)
    w = mundo(tag, yo, controlador, args_rival,
              ["--rounds", str(rondas), "--rival", tag, "--colocacion", colocacion,
               "--version", version, "--out", f"../../../runs/{out.name}"])
    log_path = RUNS / f"_tmp_lote_{tag}.log"
    log = open(log_path, "w")
    p = subprocess.Popen(["webots", "--batch", "--mode=fast", "--no-rendering", "--minimize",
                          "--stdout", "--stderr", f"--port={puerto}", str(w)],
                         stdout=log, stderr=subprocess.STDOUT, env=ENV)
    t0 = time.time()
    datos = None
    while time.time() - t0 < limite_s and p.poll() is None:
        time.sleep(2)
        if out.exists():
            try:
                datos = json.loads(out.read_text())
                break
            except ValueError:
                pass                                  # a medio escribir
    p.terminate()
    try:
        p.wait(15)
    except subprocess.TimeoutExpired:
        p.kill()
    log.close()
    for f in (w, WORLDS / f"._lote_{tag}.wbproj", WORLDS / f"._lote_{tag}.jpg", out):
        f.unlink(missing_ok=True)
    if datos is None:
        print(f"[webots] {tag}: sin resultado en {limite_s} s; mira {log_path.relative_to(ROOT)}")
        return {}
    razones = {}
    for linea in log_path.read_text(errors="replace").splitlines():
        m = re.search(r"\[arbitro\] asalto +\d+/\d+ +(\w+) +(.+?) +([+-]\d) ", linea)
        if m:
            razones.setdefault(m.group(1), {}).setdefault(m.group(2).strip(), 0)
            razones[m.group(1)][m.group(2).strip()] += 1
    log_path.unlink(missing_ok=True)
    mt = datos["metrics"]
    print(f"[webots] {tag:8s} {time.time() - t0:5.0f} s  {mt['wins']}W {mt['losses']}L {mt['draws']}D  "
          f"auto-salidas {mt['self_outs']}" + (f"  combate {mt['match_win_rate']:.3f}" if "match_win_rate" in mt else ""))
    return mt["opponents"][0] | {"avg_win_time_s": mt["avg_win_time_s"], "self_outs": mt["self_outs"],
                                 "reasons": razones}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="version congelada, o etiqueta de algorithms/")
    ap.add_argument("--colocacion", choices=["reglamento", "banco"], default="reglamento")
    ap.add_argument("--rondas", type=int, default=30, help="asaltos por rival (multiplo de 3)")
    ap.add_argument("--limite", type=int, default=1500, help="segundos maximos por Webots")
    a = ap.parse_args()

    make(CTRL / "arbitro")
    make(CTRL / "oponente")
    temporales = []
    if (ROOT / "versions" / a.version / "snapshot").exists():
        yo = congelado(a.version, "_yo_")
        temporales.append(yo)
    else:
        make(CTRL / "gelatina_nuclear")
        yo = "gelatina_nuclear"
    rival_fsm = congelado("v0.3.0", "_rival_")
    temporales.append(rival_fsm)
    rivales = [("static", "oponente", ["static"]), ("charger", "oponente", ["charger"]),
               ("spinner", "oponente", ["spinner"]), ("v0.3.0", rival_fsm, [])]
    print(f"[webots] {a.version} ({'congelada' if yo != 'gelatina_nuclear' else 'algorithms/'}): "
          f"{a.rondas} asaltos por rival, colocacion {a.colocacion}, puertos {PUERTOS[0]}-{PUERTOS[len(rivales) - 1]}")
    try:
        with ThreadPoolExecutor(len(rivales)) as ex:
            ops = list(ex.map(lambda ir: una(ir[1][0], yo, ir[1][1], ir[1][2], a.version, a.colocacion,
                                             a.rondas, PUERTOS[ir[0]], a.limite), enumerate(rivales)))
    finally:
        for t in temporales:
            shutil.rmtree(CTRL / t, ignore_errors=True)
    ops = [o for o in ops if o]
    if not ops:
        sys.exit("[webots] ningun Webots dio resultado")
    tot = {k: sum(o[k] for o in ops) for k in ("rounds", "wins", "losses", "draws", "self_outs")}
    t_med = sum(o["avg_win_time_s"] * o["wins"] for o in ops) / max(tot["wins"], 1)
    for o in ops:
        o.pop("avg_win_time_s")
        o.pop("self_outs")
    metrics = {**tot, "win_rate": round(tot["wins"] / max(tot["rounds"], 1), 3),
               "avg_win_time_s": round(t_med, 2), "opponents": ops}
    if a.colocacion == "reglamento":
        metrics["match_win_rate"] = round(sum(o["match"]["win"] for o in ops) / len(ops), 3)
    salida = RUNS / f"webots_{a.version}_{a.colocacion}.json"
    salida.write_text(json.dumps({"version": a.version, "engine": "webots", "mode": a.colocacion,
                                  "round_max_s": 60 if a.colocacion == "reglamento" else 30,
                                  "metrics": metrics}, indent=2, ensure_ascii=False) + "\n")
    extra = f", combate ganado de media {metrics['match_win_rate']:.3f}" if "match_win_rate" in metrics else ""
    print(f"[webots] {a.version}: {tot['wins']}W {tot['losses']}L {tot['draws']}D, "
          f"auto-salidas {tot['self_outs']}{extra} -> {salida.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
