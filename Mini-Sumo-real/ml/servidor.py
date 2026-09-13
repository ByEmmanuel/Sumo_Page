"""
servidor.py -- interfaz local del laboratorio de aprendizaje (puerto 8765).

La interfaz reutiliza el diseno de la web de codex/: web/codex.css es una
copia de solo lectura de codex/web/style.css (codex/ no se modifica). Muestra
las versiones y sus cambios, los entrenamientos, la liga, la direccion de
mejora y el tablero de tareas, y es donde el usuario vota las comparaciones
A/B que alimentan el modelo de recompensa.

Solo escucha en 127.0.0.1. Las escrituras exigen JSON y mismo origen.

    ml/.venv/bin/python -m ml servidor        # http://localhost:8765
"""

from __future__ import annotations

import errno
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import candidatos, feedback
from .config import DATA, ML, ROOT, VERSIONS

WEB = ML / "web"
TAREAS = ROOT.parent / "Tareas" / "tareas.json"
ESTATICOS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/lab.css": ("lab.css", "text/css"),
    "/codex.css": ("codex.css", "text/css"),
}
NOMBRE = re.compile(r"^[\w.\-]+$")


def _json(p, defecto=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def estado() -> dict:
    manifest = _json(VERSIONS / "manifest.json", {"versions": []})
    campos = ("version", "parent", "iteration", "created_at", "kind", "title", "verdict", "metrics", "tags")
    versiones = [{k: v.get(k) for k in campos} for v in manifest["versions"]]
    corridas = []
    base = DATA / "corridas"
    for d in sorted(base.glob("*"), reverse=True) if base.exists() else []:
        res = _json(d / "resumen.json")
        corridas.append({
            "id": d.name, "config": _json(d / "config.json", {}), "terminada": res is not None,
            "campeon": None if res is None else {"candidato": res.get("candidato"),
                                                  "combate_gana": res["campeon"].get("combate_gana"),
                                                  "aptitud": res["campeon"]["aptitud"]},
            "base": None if res is None else {"combate_gana": res["base"].get("combate_gana"),
                                               "aptitud": res["base"]["aptitud"]},
        })
    pares = feedback.carga_pares()
    return {
        "versiones": versiones,
        "candidatos": [{"id": c["id"], "creado": c["creado"], "origen": c["origen"], "base": c["base"],
                        "combate_gana": c["evaluacion"].get("combate_gana"),
                        "aptitud": c["evaluacion"].get("aptitud")} for c in candidatos.carga()],
        "corridas": corridas,
        "liga": _json(DATA / "liga.json"),
        "recompensa": _json(DATA / "recompensa.json"),
        "pares": {"pendientes": sum(p["estado"] == "pendiente" for p in pares),
                  "votados": sum(p["estado"] == "votado" for p in pares)},
        "votos": len(feedback.votos()),
        "validacion": (_json(DATA / "validacion.json", {}) or {}).get("ok"),
        "tareas": (_json(TAREAS, {}) or {}).get("tareas", []),
        "etiquetas": feedback.ETIQUETAS,
    }


def version(v: str) -> dict:
    manifest = _json(VERSIONS / "manifest.json", {"versions": []})
    e = next((x for x in manifest["versions"] if x["version"] == v), None)
    if e is None:
        raise LookupError("Versión no encontrada.")
    diff = VERSIONS / v / "diff.patch"
    return {**e, "diff": diff.read_text(encoding="utf-8", errors="replace") if diff.exists() else ""}


def corrida(rid: str) -> dict:
    d = DATA / "corridas" / rid
    if not d.is_dir():
        raise LookupError("Corrida no encontrada.")
    log = d / "log.jsonl"
    filas = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []
    for f in filas:
        f.pop("media", None)
    return {"id": rid, "config": _json(d / "config.json", {}), "log": filas, "resumen": _json(d / "resumen.json")}


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def envia(self, estado_http: int, cuerpo, tipo: str = "application/json; charset=utf-8"):
        if not isinstance(cuerpo, bytes):
            cuerpo = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(estado_http)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        try:
            ruta = urlparse(self.path).path
            if ruta == "/api/estado":
                return self.envia(200, estado())
            if ruta == "/api/pares":
                return self.envia(200, [p for p in feedback.carga_pares() if p["estado"] == "pendiente"])
            partes = ruta.strip("/").split("/")
            if len(partes) == 3 and partes[0] == "api" and NOMBRE.match(partes[2]):
                if partes[1] == "clip":
                    return self.envia(200, feedback.carga_clip(partes[2]))
                if partes[1] == "version":
                    return self.envia(200, version(partes[2]))
                if partes[1] == "corrida":
                    return self.envia(200, corrida(partes[2]))
            if ruta in ESTATICOS:
                nombre, tipo = ESTATICOS[ruta]
                return self.envia(200, (WEB / nombre).read_bytes(), tipo + "; charset=utf-8")
            raise LookupError("Recurso no encontrado.")
        except (LookupError, FileNotFoundError, KeyError) as e:
            self.envia(404, {"error": str(e)})
        except ValueError as e:
            self.envia(400, {"error": str(e)})

    def do_POST(self):
        origen = self.headers.get("Origin")
        if (origen and origen != "http://" + self.headers.get("Host", "")) or \
                self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.envia(403, {"error": "Origen o formato no permitido."})
        try:
            largo = int(self.headers.get("Content-Length", 0))
            if not 0 < largo <= 100_000:
                raise ValueError("Tamaño de solicitud no permitido.")
            d = json.loads(self.rfile.read(largo))
            etiquetas = [e for e in d.get("etiquetas", []) if isinstance(e, str)][:10]
            nota = str(d.get("nota", ""))[:2000]
            if self.path == "/api/voto":
                return self.envia(201, feedback.registra_voto(str(d["par"]), str(d["preferencia"]),
                                                              etiquetas, nota, fuente="web"))
            if self.path == "/api/valoracion":
                return self.envia(201, feedback.registra_valoracion(str(d["clip"]), str(d["valor"]),
                                                                    etiquetas, nota, fuente="web"))
            raise LookupError("Recurso no encontrado.")
        except (KeyError, LookupError) as e:
            self.envia(404, {"error": str(e)})
        except (ValueError, TypeError) as e:
            self.envia(400, {"error": str(e)})


def sirve(puerto: int = 8765):
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        print(f"El puerto {puerto} ya está en uso: lo más probable es que el laboratorio ya esté abierto.\n"
              f"  Ábrelo en http://localhost:{puerto}\n"
              f"  o arranca otro con: python -m ml servidor --puerto {puerto + 1}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Laboratorio de aprendizaje -> http://localhost:{puerto}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
