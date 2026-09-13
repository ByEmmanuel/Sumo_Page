"""
exportar.py -- un candidato a algorithms/params.h, listo para gnver.

Reescribe solo los valores de sumo_params_default(): comentarios y estructura
quedan intactos, asi que el diff de la bitacora son exactamente los numeros
que cambiaron (invariante 2 del proyecto). Los decimales se redondean a dos,
como el resto de params.h; lo que se mide despues es lo redondeado.

Deja ademas versions/_draft.json con el origen del candidato, sus metricas y
la tabla de parametros. El porque (rationale) y la hipotesis los escribe quien
registra la version: gnver no acepta una entrada sin ellos.
"""

from __future__ import annotations

import difflib
import json
import re

from . import config
from .candidatos import algoritmo, busca
from .config import ALGORITHMS, APERTURAS_INV, TIPO, VERSIONS


def formatea(nombre: str, v) -> str:
    if TIPO[nombre] == "enum":
        return APERTURAS_INV[int(v)]
    if TIPO[nombre] == "int":
        return str(int(v))
    return f"{float(v):.2f}f"


def redondea(p: dict) -> dict:
    return {n: (round(float(v), 2) if TIPO[n] == "float" else int(v)) for n, v in p.items()}


def texto_params_h(p: dict, texto: str | None = None) -> tuple[str, list[dict]]:
    """params.h con los valores de p. Devuelve (texto nuevo, tabla de cambios)."""
    texto = texto if texto is not None else (ALGORITHMS / "params.h").read_text(encoding="utf-8")
    actual = config.completa(config.lee_params_texto(texto))
    nuevo = texto
    tabla = []
    for n, v in p.items():
        if n not in actual or formatea(n, actual[n]) == formatea(n, v):
            continue
        patron = re.compile(rf"^(\s*p\.{n}\s*=\s*)([^;]+)(;)", re.MULTILINE)
        if not patron.search(nuevo):
            raise ValueError(f"{n} no aparece en params.h")
        nuevo = patron.sub(lambda m: m.group(1) + formatea(n, v) + m.group(3), nuevo)
        tabla.append({"name": n, "from": formatea(n, actual[n]).rstrip("f"),
                      "to": formatea(n, v).rstrip("f"), "reason": ""})
    return nuevo, tabla


def exporta(nombre: str, escribir: bool = True, log=print) -> dict:
    nombre, p = algoritmo(nombre)
    p = redondea(p)
    ruta = ALGORITHMS / "params.h"
    texto = ruta.read_text(encoding="utf-8")
    nuevo, tabla = texto_params_h(p, texto)
    diff = "".join(difflib.unified_diff(texto.splitlines(True), nuevo.splitlines(True),
                                        "params.h", f"params.h ({nombre})"))
    log(diff or "[exportar] params.h ya tiene esos valores")
    if escribir and diff:
        ruta.write_text(nuevo, encoding="utf-8")
        borrador = {
            "kind": "tuning",
            "author": "claude-opus-5 + rlhf-gpu",
            "title": "",
            "summary": "",
            "rationale": "",
            "hypothesis": "",
            "tags": ["tuning", "ml", "cma-es", "reglamento"],
            "params_changed": tabla,
            "_origen": busca(nombre) if nombre.startswith("c-") else {"version": nombre},
        }
        (VERSIONS / "_draft.json").write_text(json.dumps(borrador, indent=2, ensure_ascii=False))
        log(f"[exportar] params.h reescrito con {nombre} ({len(tabla)} parametros). "
            "Borrador en versions/_draft.json: completa title, summary, rationale e hypothesis.")
    return {"params": p, "cambios": tabla, "diff": diff}
