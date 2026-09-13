"""
candidatos.py -- los juegos de parametros que salen de los entrenamientos.

Un candidato no es una version: es una propuesta. Se convierte en version de
la bitacora cuando se exporta a algorithms/params.h, se mide en el banco y en
Webots, y se registra con gnver. Hasta entonces vive aqui, con su origen (que
corrida lo produjo y desde que version) y su evaluacion.
"""

from __future__ import annotations

import datetime as _dt
import json

from . import config
from .config import DATA

FICHERO = DATA / "candidatos.json"


def carga() -> list[dict]:
    if not FICHERO.exists():
        return []
    return json.loads(FICHERO.read_text(encoding="utf-8"))


def _guarda(cs: list[dict]):
    DATA.mkdir(parents=True, exist_ok=True)
    FICHERO.write_text(json.dumps(cs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def registra(params: dict, origen: str, evaluacion: dict, base: str) -> str:
    cs = carga()
    cid = f"c-{len(cs) + 1:03d}"
    cs.append({
        "id": cid,
        "creado": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "origen": origen,
        "base": base,
        "params": params,
        "evaluacion": evaluacion,
    })
    _guarda(cs)
    return cid


def marca_exportado(cid: str, version: str):
    """El candidato ya es una version de la bitacora."""
    cs = carga()
    for c in cs:
        if c["id"] == cid:
            c["version"] = version
    _guarda(cs)


def busca(cid: str) -> dict:
    for c in carga():
        if c["id"] == cid:
            return c
    raise KeyError(f"no existe el candidato {cid}")


def algoritmo(nombre: str) -> tuple[str, dict]:
    """Nombre -> (nombre, parametros completos). Acepta versiones, WORK y candidatos."""
    if nombre.startswith("c-"):
        return nombre, config.completa(busca(nombre)["params"])
    return nombre, config.params_version(nombre)
