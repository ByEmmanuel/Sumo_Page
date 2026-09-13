"""
python -m ml -- aprendizaje por refuerzo con retroalimentacion humana en GPU.

Desde Mini-Sumo/, con el entorno de ml/.venv:

    ml/.venv/bin/python -m ml validar            # GPU contra el banco nativo en C
    ml/.venv/bin/python -m ml entrenar           # CMA-ES en la GPU
    ml/.venv/bin/python -m ml evaluar c-001      # metricas de un algoritmo
    ml/.venv/bin/python -m ml pares c-001 v0.3.0 # preguntas A/B para el usuario
    ml/.venv/bin/python -m ml servidor           # interfaz de votos en :8765
    ml/.venv/bin/python -m ml recompensa         # reentrena el modelo con los votos
    ml/.venv/bin/python -m ml liga               # ranking y direccion de mejora
    ml/.venv/bin/python -m ml ciclo              # una vuelta completa del ciclo
    ml/.venv/bin/python -m ml exportar c-001     # candidato -> algorithms/params.h
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _en_su_entorno():
    """`python -m ml` con cualquier python se relanza con ml/.venv, que es donde
    estan PyTorch y numpy. GN_ML_VENV evita relanzarse dos veces."""
    ml = Path(__file__).resolve().parent
    venv = ml / ".venv"
    py = venv / "bin" / "python"
    if os.environ.get("GN_ML_VENV") or not py.exists() or Path(sys.prefix).resolve() == venv.resolve():
        return
    os.environ["GN_ML_VENV"] = "1"
    os.environ["PYTHONPATH"] = str(ml.parent) + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.execv(str(py), [str(py), "-m", "ml", *sys.argv[1:]])


def _evaluar(a):
    import torch
    from .banco import COLOCACIONES_REG, evaluar, rivales_estandar
    from .candidatos import algoritmo
    from .sim import Arena, Cfg

    nombre, p = algoritmo(a.algoritmo)
    arena = Arena(Cfg(modo=a.modo, max_s=a.max_s))
    torch.manual_seed(a.semilla)
    ev = evaluar(arena, [p], rivales_estandar(), COLOCACIONES_REG, a.rondas)
    r = ev.resumen(0)
    print(f"\n  {nombre}   modo {a.modo}   {a.rondas} asaltos por rival y colocacion")
    print(f"  {'rival':9s} {'frente':>7s} {'lado':>7s} {'espalda':>8s}   {'combate: gana / pierde':>24s}")
    for f in r["rivales"]:
        c = f["colocaciones"]
        print(f"  {f['nombre']:9s} {c['frente']['gana']:7.0%} {c['lado']['gana']:7.0%} "
              f"{c['espalda']['gana']:8.0%}   {f['combate']['gana']:10.1%} / {f['combate']['pierde']:.1%}")
    print(f"\n  combate ganado de media {r['combate_gana']:.1%}, perdido {r['combate_pierde']:.1%}; "
          f"auto-salidas {r['auto_salidas']:.1%}; aptitud {r['aptitud']:+.3f}\n")
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))


def main(argv=None):
    _en_su_entorno()
    ap = argparse.ArgumentParser(prog="python -m ml", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validar", help="compara el simulador de GPU con tests/harness.c")
    p.add_argument("--versiones", nargs="*")
    p.add_argument("--semillas", type=int, default=30)

    p = sub.add_parser("entrenar", help="estrategia evolutiva sobre params.h")
    p.add_argument("--generaciones", type=int, default=60)
    p.add_argument("--poblacion", type=int, default=384)
    p.add_argument("--rondas", type=int, default=6, help="asaltos por rival y colocacion")
    p.add_argument("--sigma", type=float, default=0.12)
    p.add_argument("--desde", help="version, WORK o candidato de partida (por defecto la ultima version)")
    p.add_argument("--lambda-humano", type=float, help="peso de la recompensa humana (por defecto, el sugerido)")
    p.add_argument("--semilla", type=int, default=0)
    p.add_argument("--modo", choices=["robusto", "banco"], default="robusto")
    p.add_argument("--nombre", default="")

    p = sub.add_parser("evaluar", help="metricas de un algoritmo contra el banco de rivales")
    p.add_argument("algoritmo")
    p.add_argument("--rondas", type=int, default=64)
    p.add_argument("--modo", choices=["robusto", "banco"], default="robusto")
    p.add_argument("--max-s", type=float, default=30.0)
    p.add_argument("--semilla", type=int, default=0)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("pares", help="genera comparaciones A/B para votar")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--rondas", type=int, default=4)
    p.add_argument("--max", type=int, default=12)

    p = sub.add_parser("votar", help="vota un par desde la terminal")
    p.add_argument("par")
    p.add_argument("preferencia", choices=["a", "b", "igual", "ninguno"])
    p.add_argument("--etiqueta", action="append", default=[])
    p.add_argument("--nota", default="")

    sub.add_parser("recompensa", help="reentrena el modelo de recompensa con los votos")
    sub.add_parser("liga", help="ranking de algoritmos y direccion de mejora")

    p = sub.add_parser("servidor", help="interfaz local de votos y seguimiento")
    p.add_argument("--puerto", type=int, default=8765)

    p = sub.add_parser("ciclo", help="recompensa -> entrenar -> pares -> liga")
    p.add_argument("--generaciones", type=int, default=60)
    p.add_argument("--poblacion", type=int, default=384)

    p = sub.add_parser("exportar", help="escribe un candidato en algorithms/params.h")
    p.add_argument("algoritmo")
    p.add_argument("--simular", action="store_true", help="muestra el diff sin escribir")

    p = sub.add_parser("banco-c", help="mide un algoritmo en el banco nativo en C (sin tocar algorithms/)")
    p.add_argument("algoritmo")
    p.add_argument("--semillas", type=int, default=30)

    p = sub.add_parser("ppo", help="entrena una politica neuronal con PPO")
    p.add_argument("--iteraciones", type=int, default=400)
    p.add_argument("--entornos", type=int, default=4096)
    p.add_argument("--horizonte", type=int, default=128)
    p.add_argument("--lambda-humano", type=float)
    p.add_argument("--nombre", default="")

    p = sub.add_parser("ppo-evaluar", help="combates de una politica contra el banco de rivales")
    p.add_argument("politica")
    p.add_argument("--rondas", type=int, default=32)
    p.add_argument("--modo", choices=["robusto", "banco"], default="robusto")

    p = sub.add_parser("ppo-exportar", help="escribe el actor como C99 y lo compara con PyTorch")
    p.add_argument("politica")

    a = ap.parse_args(argv)
    if a.cmd == "validar":
        from .validate import validar
        sys.exit(0 if validar(a.versiones, a.semillas)["ok"] else 1)
    elif a.cmd == "entrenar":
        from .es import entrenar
        entrenar(a.generaciones, a.poblacion, a.rondas, a.sigma, a.desde, a.lambda_humano,
                 a.semilla, a.modo, a.nombre)
    elif a.cmd == "evaluar":
        _evaluar(a)
    elif a.cmd == "pares":
        from .feedback import genera_pares
        genera_pares(a.a, a.b, a.rondas, a.max)
    elif a.cmd == "votar":
        from .feedback import registra_voto
        print(registra_voto(a.par, a.preferencia, a.etiqueta, a.nota))
    elif a.cmd == "recompensa":
        from .recompensa import entrena
        entrena()
    elif a.cmd == "liga":
        from .liga import actualiza
        actualiza()
    elif a.cmd == "servidor":
        from .servidor import sirve
        sirve(a.puerto)
    elif a.cmd == "ciclo":
        from .ciclo import vuelta
        vuelta(a.generaciones, a.poblacion)
    elif a.cmd == "exportar":
        from .exportar import exporta
        exporta(a.algoritmo, escribir=not a.simular)
    elif a.cmd == "banco-c":
        from .validate import banco_c
        r = banco_c(a.algoritmo, a.semillas)
        for modo in ("banco", "reglamento"):
            m = r["oficial"][modo]["metrics"]
            extra = f", combate {m['match_win_rate']:.3f}" if "match_win_rate" in m else ""
            print(f"  {r['algoritmo']} modo {modo}: {m['wins']}W {m['losses']}L {m['draws']}D "
                  f"(win rate {m['win_rate']:.3f}, auto-salidas {m['self_outs']}{extra})")
    elif a.cmd == "ppo":
        from .ppo import entrenar as ppo_entrenar
        ppo_entrenar(a.iteraciones, a.entornos, a.horizonte, lambda_humano=a.lambda_humano, nombre=a.nombre)
    elif a.cmd == "ppo-evaluar":
        from .ppo import evaluar as ppo_evaluar
        ppo_evaluar(a.politica, a.rondas, a.modo)
    elif a.cmd == "ppo-exportar":
        from .ppo import exporta_c
        exporta_c(a.politica)


if __name__ == "__main__":
    main()
