#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gnver — Versionador de algoritmos de Gelatina Nuclear.

No es un sustituto de git: es una BITACORA SEMANTICA de algoritmos.
Cada version responde a: que cambio, POR QUE, que espero que mejore,
y que resultado dio en el ring. El objetivo es poder leer la evolucion
del razonamiento de la IA a lo largo de las n iteraciones.

Uso rapido:
    python3 tools/gnver.py init
    python3 tools/gnver.py check
    python3 tools/gnver.py new --from-json versions/_draft.json
    python3 tools/gnver.py list
    python3 tools/gnver.py show v0.1.0
    python3 tools/gnver.py diff v0.1.0 v0.2.0
    python3 tools/gnver.py metrics v0.1.0 --from runs/v0.1.0/results.json
    python3 tools/gnver.py site
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "versions"
MANIFEST = VERSIONS / "manifest.json"
TRACKED = VERSIONS / "tracked.json"

DEFAULT_TRACKED = [
    "algorithms",
    "webots/controllers/gelatina_nuclear",
]

KINDS = [
    "baseline",      # primera implementacion de algo
    "tuning",        # solo cambian parametros numericos
    "new-behavior",  # nuevo estado / nueva capacidad
    "refactor",      # misma conducta, otro codigo
    "bugfix",        # correccion de un fallo observado
    "experiment",    # prueba que puede revertirse
    "revert",        # vuelta atras explicita
]

TEXT_EXT = {".c", ".h", ".cpp", ".hpp", ".py", ".md", ".txt", ".json", ".mk"}


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def die(msg: str, code: int = 1):
    print(f"[gnver] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg: str):
    print(f"[gnver] {msg}")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def tracked_paths() -> list[str]:
    return load_json(TRACKED, {"paths": DEFAULT_TRACKED})["paths"]


def iter_tracked_files() -> list[Path]:
    """Devuelve los ficheros fuente vigilados, ordenados y relativos a ROOT."""
    out: list[Path] = []
    for rel in tracked_paths():
        base = ROOT / rel
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            for f in base.rglob("*"):
                if not f.is_file() or f.is_symlink():
                    continue  # los enlaces a algorithms/ ya se versionan en su origen
                if any(part.startswith((".", "__pycache__", "build")) for part in f.parts):
                    continue
                if f.suffix.lower() in TEXT_EXT or f.name == "Makefile":
                    out.append(f)
    return sorted(set(out), key=lambda p: str(p.relative_to(ROOT)))


def fingerprint() -> dict[str, str]:
    return {str(f.relative_to(ROOT)): sha256_file(f) for f in iter_tracked_files()}


def manifest() -> dict:
    m = load_json(MANIFEST)
    if m is None:
        die("no hay manifest. Ejecuta: python3 tools/gnver.py init")
    return m


def find_version(m: dict, ver: str) -> dict | None:
    ver = ver if ver.startswith("v") else "v" + ver
    for e in m["versions"]:
        if e["version"] == ver:
            return e
    return None


def latest(m: dict) -> dict | None:
    return m["versions"][-1] if m["versions"] else None


def bump(ver: str, level: str) -> str:
    mt = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", ver)
    if not mt:
        die(f"version no semantica: {ver}")
    a, b, c = (int(x) for x in mt.groups())
    if level == "major":
        return f"v{a + 1}.0.0"
    if level == "minor":
        return f"v{a}.{b + 1}.0"
    return f"v{a}.{b}.{c + 1}"


def count_lines(p: Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------

def snapshot_dir(ver: str) -> Path:
    return VERSIONS / ver / "snapshot"


def read_snapshot(ver: str) -> dict[str, str]:
    base = snapshot_dir(ver)
    files: dict[str, str] = {}
    if not base.exists():
        return files
    for f in base.rglob("*"):
        if f.is_file():
            files[str(f.relative_to(base))] = f.read_text(encoding="utf-8", errors="replace")
    return files


def read_working() -> dict[str, str]:
    return {
        str(f.relative_to(ROOT)): f.read_text(encoding="utf-8", errors="replace")
        for f in iter_tracked_files()
    }


def make_diff(old: dict[str, str], new: dict[str, str], old_tag: str, new_tag: str) -> tuple[str, dict]:
    chunks: list[str] = []
    added = removed = 0
    touched: list[str] = []
    for path in sorted(set(old) | set(new)):
        a = old.get(path, "").splitlines(keepends=True)
        b = new.get(path, "").splitlines(keepends=True)
        if a == b:
            continue
        touched.append(path)
        d = list(difflib.unified_diff(
            a, b,
            fromfile=f"{old_tag}/{path}",
            tofile=f"{new_tag}/{path}",
            n=3,
        ))
        for line in d:
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        chunks.append("".join(d))
    return "\n".join(chunks), {"added": added, "removed": removed, "files": len(touched), "touched": touched}


# --------------------------------------------------------------------------
# comandos
# --------------------------------------------------------------------------

def cmd_init(args):
    if MANIFEST.exists() and not args.force:
        die("ya existe versions/manifest.json (usa --force para reiniciar)")
    save_json(TRACKED, {
        "paths": DEFAULT_TRACKED,
        "_comment": "Rutas cuyo contenido se versiona. Cualquier cambio aqui exige una version nueva.",
    })
    save_json(MANIFEST, {
        "project": "Gelatina Nuclear",
        "class": "Mini-sumo 10x10 cm / 500 g",
        "created": now_iso(),
        "schema": 1,
        "versions": [],
    })
    info("bitacora inicializada en versions/")


def cmd_check(args):
    """Falla si hay cambios en los ficheros vigilados que no esten versionados."""
    m = manifest()
    last = latest(m)
    cur = fingerprint()
    if last is None:
        if cur:
            print("[gnver] SIN VERSIONAR: no existe ninguna version y ya hay codigo vigilado.")
            for p in cur:
                print(f"    + {p}")
            sys.exit(2)
        info("limpio (sin codigo todavia)")
        return
    prev = {f["path"]: f["sha256"] for f in last["files"]}
    added = sorted(set(cur) - set(prev))
    gone = sorted(set(prev) - set(cur))
    mod = sorted(p for p in set(cur) & set(prev) if cur[p] != prev[p])
    if not (added or gone or mod):
        info(f"limpio: el arbol coincide con {last['version']}")
        return
    print(f"[gnver] SIN VERSIONAR respecto a {last['version']}:")
    for p in added:
        print(f"    + {p}")
    for p in mod:
        print(f"    ~ {p}")
    for p in gone:
        print(f"    - {p}")
    print("\n  -> crea una version antes de seguir:")
    print("     python3 tools/gnver.py new --from-json versions/_draft.json")
    sys.exit(2)


def cmd_new(args):
    m = manifest()
    last = latest(m)

    meta_in: dict = {}
    if args.from_json:
        meta_in = load_json(Path(args.from_json)) or {}
    for key in ("title", "summary", "rationale", "hypothesis", "kind", "author"):
        val = getattr(args, key, None)
        if val:
            meta_in[key] = val
    if args.tag:
        meta_in.setdefault("tags", []).extend(args.tag)

    missing = [k for k in ("title", "summary", "rationale") if not meta_in.get(k)]
    if missing:
        die("faltan campos obligatorios en la version: " + ", ".join(missing))
    kind = meta_in.get("kind", "experiment")
    if kind not in KINDS:
        die(f"kind invalido '{kind}'. Validos: {', '.join(KINDS)}")

    ver = args.version or (bump(last["version"], args.bump) if last else "v0.1.0")
    if find_version(m, ver):
        die(f"la version {ver} ya existe")

    files = iter_tracked_files()
    if not files:
        die("no hay ficheros vigilados que versionar (revisa versions/tracked.json)")

    new_files = read_working()
    old_files = read_snapshot(last["version"]) if last else {}
    patch, stat = make_diff(old_files, new_files, last["version"] if last else "vacio", ver)

    if last and stat["files"] == 0 and not args.allow_empty:
        die("no hay cambios respecto a la version anterior (usa --allow-empty si es intencionado)")

    vdir = VERSIONS / ver
    snap = vdir / "snapshot"
    if snap.exists():
        shutil.rmtree(snap)
    for f in files:
        rel = f.relative_to(ROOT)
        dst = snap / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    (vdir / "diff.patch").write_text(patch, encoding="utf-8")

    entry = {
        "version": ver,
        "parent": last["version"] if last else None,
        "iteration": (last["iteration"] + 1) if last else 1,
        "created_at": now_iso(),
        "author": meta_in.get("author", "claude-opus-5"),
        "kind": kind,
        "title": meta_in["title"],
        "summary": meta_in["summary"],
        "rationale": meta_in["rationale"],
        "hypothesis": meta_in.get("hypothesis", ""),
        "expected_effect": meta_in.get("expected_effect", ""),
        "risks": meta_in.get("risks", ""),
        "notes_real_robot": meta_in.get("notes_real_robot", ""),
        "tags": meta_in.get("tags", []),
        "params_changed": meta_in.get("params_changed", []),
        "states": meta_in.get("states", []),
        "diff_stat": stat,
        "files": [
            {
                "path": str(f.relative_to(ROOT)),
                "sha256": sha256_file(f),
                "lines": count_lines(f),
            }
            for f in files
        ],
        "metrics": meta_in.get("metrics", {
            "rounds": 0, "wins": 0, "losses": 0, "draws": 0,
            "win_rate": None, "avg_win_time_s": None, "self_outs": 0,
            "opponents": {},
        }),
        "verdict": meta_in.get("verdict", "pendiente"),
    }
    m["versions"].append(entry)
    save_json(MANIFEST, m)
    save_json(vdir / "meta.json", entry)

    info(f"creada {ver}  ({stat['added']}+ / {stat['removed']}- en {stat['files']} fichero(s))")
    info(f"  {entry['title']}")
    if args.from_json and Path(args.from_json).name.startswith("_"):
        Path(args.from_json).unlink(missing_ok=True)
    if not args.no_site:
        build_site()


def cmd_list(args):
    m = manifest()
    if not m["versions"]:
        info("todavia no hay versiones")
        return
    print(f"\n  {'VERSION':<10} {'IT':>3} {'TIPO':<13} {'W/L/D':>9}  TITULO")
    print("  " + "-" * 78)
    for e in m["versions"]:
        mt = e.get("metrics") or {}
        wld = f"{mt.get('wins', 0)}/{mt.get('losses', 0)}/{mt.get('draws', 0)}"
        if not mt.get("rounds"):
            wld = "-"
        print(f"  {e['version']:<10} {e['iteration']:>3} {e['kind']:<13} {wld:>9}  {e['title'][:44]}")
    print()


def cmd_show(args):
    m = manifest()
    e = find_version(m, args.version)
    if not e:
        die(f"version desconocida: {args.version}")
    print(f"\n  {e['version']}   iteracion {e['iteration']}   [{e['kind']}]   {e['created_at']}")
    print(f"  {e['title']}")
    print("  " + "=" * 76)
    for label, key in (("QUE CAMBIO", "summary"), ("POR QUE", "rationale"),
                       ("HIPOTESIS", "hypothesis"), ("EFECTO ESPERADO", "expected_effect"),
                       ("RIESGOS", "risks"), ("NOTA ROBOT REAL", "notes_real_robot")):
        if e.get(key):
            print(f"\n  {label}:\n    " + e[key].replace("\n", "\n    "))
    if e.get("params_changed"):
        print("\n  PARAMETROS:")
        for p in e["params_changed"]:
            print(f"    {p['name']:<28} {str(p.get('from')):>10} -> {str(p.get('to')):<10}  {p.get('reason', '')}")
    mt = e.get("metrics") or {}
    if mt.get("rounds"):
        print(f"\n  RESULTADOS: {mt['rounds']} asaltos  "
              f"{mt['wins']}W {mt['losses']}L {mt['draws']}D  "
              f"win rate {mt.get('win_rate')}  auto-salidas {mt.get('self_outs', 0)}")
    ds = e["diff_stat"]
    print(f"\n  DIFF: +{ds['added']} -{ds['removed']} en {ds['files']} fichero(s)")
    for t in ds.get("touched", []):
        print(f"    ~ {t}")
    print()


def cmd_diff(args):
    a = read_snapshot(args.a) if args.a != "WORK" else read_working()
    b = read_snapshot(args.b) if args.b != "WORK" else read_working()
    patch, stat = make_diff(a, b, args.a, args.b)
    print(patch or "(sin diferencias)")
    print(f"\n[gnver] +{stat['added']} -{stat['removed']} en {stat['files']} fichero(s)")


def cmd_metrics(args):
    m = manifest()
    e = find_version(m, args.version)
    if not e:
        die(f"version desconocida: {args.version}")
    if args.from_file:
        data = load_json(Path(args.from_file))
        if data is None:
            die(f"no existe {args.from_file}")
        # --campo permite guardar una medida adicional (reglamento, Webots)
        # sin pisar "metrics", que es la tabla oficial de siempre.
        e[args.campo] = data.get("metrics", data)
        if args.campo != "metrics":
            e[args.campo]["engine"] = data.get("engine", "")
            e[args.campo]["mode"] = data.get("mode", "")
    else:
        mt = e.setdefault("metrics", {})
        for k in ("rounds", "wins", "losses", "draws", "self_outs"):
            v = getattr(args, k)
            if v is not None:
                mt[k] = v
        if mt.get("rounds"):
            mt["win_rate"] = round(mt.get("wins", 0) / mt["rounds"], 3)
    if args.verdict:
        e["verdict"] = args.verdict
    save_json(MANIFEST, m)
    save_json(VERSIONS / e["version"] / "meta.json", e)
    info(f"metricas actualizadas en {e['version']}: {e['metrics']}")
    build_site()


def build_site():
    script = ROOT / "tools" / "build_site.py"
    if not script.exists():
        return
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr, file=sys.stderr)
        die("fallo al generar el sitio")
    print(r.stdout.strip())


def cmd_site(args):
    build_site()


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(prog="gnver", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="inicializa la bitacora")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("check", help="avisa si hay codigo sin versionar (codigo de salida 2)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("new", help="registra una version nueva")
    p.add_argument("--from-json", help="fichero JSON con los metadatos de la version")
    p.add_argument("--version", help="fuerza un numero de version concreto")
    p.add_argument("--bump", choices=["major", "minor", "patch"], default="patch")
    p.add_argument("--title")
    p.add_argument("--summary")
    p.add_argument("--rationale")
    p.add_argument("--hypothesis")
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--author")
    p.add_argument("--tag", action="append")
    p.add_argument("--allow-empty", action="store_true")
    p.add_argument("--no-site", action="store_true")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("list", help="lista las versiones")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="detalle de una version")
    p.add_argument("version")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("diff", help="diff entre dos versiones (o WORK para el arbol actual)")
    p.add_argument("a")
    p.add_argument("b", nargs="?", default="WORK")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("metrics", help="carga resultados de combate en una version")
    p.add_argument("version")
    p.add_argument("--from", dest="from_file")
    p.add_argument("--campo", default="metrics",
                   help="clave de la entrada donde guardar: metrics (tabla oficial), "
                        "metrics_reglamento, metrics_webots...")
    p.add_argument("--rounds", type=int)
    p.add_argument("--wins", type=int)
    p.add_argument("--losses", type=int)
    p.add_argument("--draws", type=int)
    p.add_argument("--self-outs", dest="self_outs", type=int)
    p.add_argument("--verdict", choices=["pendiente", "mejora", "neutro", "regresion", "descartada"])
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("site", help="regenera la pagina web de la bitacora")
    p.set_defaults(func=cmd_site)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
