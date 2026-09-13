#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py -- genera site/index.html a partir de versions/ y ml/data/.

La pagina es autocontenida: lleva dentro el manifiesto, los diffs, el estado
del aprendizaje en GPU y el tablero de tareas, asi que funciona abierta con
doble clic (file://) y tambien publicada.
Se regenera sola cada vez que gnver crea una version o carga metricas.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "versions"
SITE = ROOT / "site"
ML = ROOT / "ml" / "data"
TAREAS = ROOT.parent / "Tareas" / "tareas.json"


def _json(p: Path, defecto=None):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto
    except (OSError, ValueError):
        return defecto


def datos_ml() -> dict:
    """Resumen del aprendizaje en GPU. Vacio si ml/data no existe."""
    out: dict = {}
    liga = _json(ML / "liga.json")
    if liga:
        d = liga.get("direccion") or {}
        out["liga"] = {"fecha": liga.get("fecha"), "rondas": liga.get("rondas"),
                       "algoritmos": liga.get("algoritmos", []),
                       "campeones": [c["id"] for c in liga.get("campeones", [])],
                       "direccion": {"r2": d.get("r2"), "muestras": d.get("muestras"),
                                     "parametros": (d.get("parametros") or [])[:10]} if d else None}
    corridas = []
    for c in sorted((ML / "corridas").glob("*")) if (ML / "corridas").exists() else []:
        cfg, res = _json(c / "config.json", {}), _json(c / "resumen.json")
        if not res or "humo" in c.name:
            continue
        log = []
        for linea in (c / "log.jsonl").read_text().splitlines() if (c / "log.jsonl").exists() else []:
            f = json.loads(linea)
            log.append([f["gen"], round(f["combate_gana_max"], 4), round(f["combate_gana_media"], 4)])
        corridas.append({
            "id": c.name, "desde": cfg.get("desde"), "generaciones": cfg.get("generaciones"),
            "poblacion": cfg.get("poblacion"), "asaltos_por_generacion": cfg.get("asaltos_por_generacion"),
            "lambda_humano": cfg.get("lambda_humano"), "segundos": res.get("segundos"),
            "candidato": res.get("candidato"),
            "base_combate": res["base"].get("combate_gana"), "campeon_combate": res["campeon"].get("combate_gana"),
            "cambios": res.get("cambios", [])[:8], "log": log,
        })
    out["corridas"] = corridas
    out["asaltos_gpu"] = sum((c["generaciones"] or 0) * (c["asaltos_por_generacion"] or 0) for c in corridas)
    val = _json(ML / "validacion.json")
    if val:
        casos = val.get("casos", [])
        out["validacion"] = {"ok": val.get("ok"), "casos": len(casos),
                             "z_max": round(max((abs(c["z"]) for c in casos), default=0.0), 1),
                             "versiones": sorted({c["version"] for c in casos})}
    out["recompensa"] = _json(ML / "recompensa.json")
    pares = _json(ML / "pares.json", []) or []
    out["pares"] = {"pendientes": sum(p["estado"] == "pendiente" for p in pares),
                    "votados": sum(p["estado"] == "votado" for p in pares)}
    votos = ML / "preferencias.jsonl"
    out["votos"] = sum(1 for l in votos.read_text().splitlines() if l.strip()) if votos.exists() else 0
    politicas = []
    for p in sorted((ML / "politicas").glob("p-*")) if (ML / "politicas").exists() else []:
        ev = _json(p / "evaluacion_robusto.json")
        if not ev or "humo" in p.name:
            continue
        cfg = _json(p / "config.json", {})
        politicas.append({"id": p.name, "pasos": cfg.get("iteraciones", 0) * cfg.get("entornos", 0) * cfg.get("horizonte", 0),
                          "combate_gana": ev.get("combate_gana"), "combate_pierde": ev.get("combate_pierde"),
                          "rivales": [{"nombre": r["nombre"], "gana": r["combate"]["gana"]} for r in ev.get("rivales", [])],
                          "c": _json(p / "exportacion.json")})
    out["politicas"] = politicas
    out["asaltos_gpu"] += sum(p["pasos"] for p in politicas) // 1000     # pasos de 8 ms, no asaltos: aparte
    out["pasos_ppo"] = sum(p["pasos"] for p in politicas)
    return out


def datos_tareas() -> list:
    t = _json(TAREAS, {}) or {}
    campos = ("id", "texto", "estado", "prioridad", "responsable", "padre", "criterio")
    out = []
    for x in t.get("tareas", []):
        fila = {k: x.get(k) for k in campos}
        fila["evidencia"] = x["evidencia"][-1]["texto"] if x.get("evidencia") else ""
        out.append(fila)
    return out


def collect() -> dict:
    manifest = json.loads((VERSIONS / "manifest.json").read_text(encoding="utf-8"))
    for v in manifest["versions"]:
        d = VERSIONS / v["version"] / "diff.patch"
        v["diff"] = d.read_text(encoding="utf-8", errors="replace") if d.exists() else ""
    manifest["ml"] = datos_ml()
    manifest["tareas"] = datos_tareas()
    return manifest


HTML = r"""<meta charset="utf-8">
<title>Bitácora Gelatina Nuclear</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
/* ==========================================================================
   Gelatina Nuclear -- bitacora de algoritmos
   Identidad: placa de instrumento de taller. Rotulacion condensada para la
   estructura, serif de cuaderno para el razonamiento, monoespaciada para todo
   lo que escupe la maquina. Neutros sesgados al verde del esmalte de maquina
   herramienta, azul pizarra como color estructural, y semantica aparte.
   Las series de las graficas tienen tokens propios (--serie-1/2), validados
   contra las placas de los dos temas; la semantica (mejora/regresion) no se
   usa nunca para una serie.
   ========================================================================== */
:root{
  --fondo:#E3E6E1;
  --placa:#F1F3EF;
  --placa-alt:#E9ECE6;
  --hueco:#D6DAD3;
  --regla:#C3C8BF;
  --regla-fuerte:#A8AFA3;
  --tinta:#1C2220;
  --tinta-media:#4C544E;
  --tinta-suave:#6E766F;
  --azul:#33506E;
  --azul-vivo:#2B6FA8;
  --serie-1:#2B6FA8;
  --serie-2:#C4551F;
  --mejora:#2C6F4C;
  --regresion:#A8412A;
  --neutro:#8A6A12;
  --mejora-fondo:#DCE9E0;
  --regresion-fondo:#F2DFD8;
  --neutro-fondo:#EFE6CF;
  --azul-fondo:#DDE4EC;
  --add-fondo:#DDEBDF;
  --add-tinta:#1F5537;
  --del-fondo:#F3DFDA;
  --del-tinta:#8C3A24;
  --sombra:0 1px 2px rgba(28,34,32,.09), 0 8px 22px -14px rgba(28,34,32,.35);
  --r:3px;
  color-scheme:light dark;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --fondo:#141816;
    --placa:#1D2321;
    --placa-alt:#232A27;
    --hueco:#111513;
    --regla:#333B37;
    --regla-fuerte:#48524D;
    --tinta:#E6EAE5;
    --tinta-media:#A8B1AB;
    --tinta-suave:#808A84;
    --azul:#8FB2D6;
    --azul-vivo:#6FA8DC;
    --serie-1:#3987E5;
    --serie-2:#D95926;
    --mejora:#63BE8E;
    --regresion:#E08064;
    --neutro:#D4AC48;
    --mejora-fondo:#1B2E23;
    --regresion-fondo:#331E18;
    --neutro-fondo:#2E2717;
    --azul-fondo:#1B2632;
    --add-fondo:#16301F;
    --add-tinta:#84D2A4;
    --del-fondo:#331B15;
    --del-tinta:#EE9679;
    --sombra:0 1px 2px rgba(0,0,0,.4), 0 10px 26px -16px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --fondo:#141816; --placa:#1D2321; --placa-alt:#232A27; --hueco:#111513;
  --regla:#333B37; --regla-fuerte:#48524D;
  --tinta:#E6EAE5; --tinta-media:#A8B1AB; --tinta-suave:#808A84;
  --azul:#8FB2D6; --azul-vivo:#6FA8DC; --serie-1:#3987E5; --serie-2:#D95926;
  --mejora:#63BE8E; --regresion:#E08064; --neutro:#D4AC48;
  --mejora-fondo:#1B2E23; --regresion-fondo:#331E18; --neutro-fondo:#2E2717;
  --azul-fondo:#1B2632;
  --add-fondo:#16301F; --add-tinta:#84D2A4; --del-fondo:#331B15; --del-tinta:#EE9679;
  --sombra:0 1px 2px rgba(0,0,0,.4), 0 10px 26px -16px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  background:var(--fondo);
  color:var(--tinta);
  font-family:"Source Serif 4",Georgia,"Times New Roman",serif;
  font-size:16px; line-height:1.6;
  margin:0; padding:0;
  -webkit-font-smoothing:antialiased;
}
.envoltorio{max-width:1240px; margin:0 auto; padding-inline:20px; padding-block:0 64px}

h1,h2,h3,.rotulo,.pestana,.chip,.tecla{
  font-family:Oswald,"Arial Narrow",Haettenschweiler,sans-serif;
  font-weight:600; letter-spacing:.02em;
}
.rotulo{
  font-size:11px; text-transform:uppercase; letter-spacing:.14em;
  color:var(--tinta-suave); font-weight:500;
}
code,pre,.dato,.mono{font-family:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.dato{font-variant-numeric:tabular-nums}

/* ---------------------------------------------------------------- cabecera */
.cabecera{
  border-bottom:2px solid var(--regla-fuerte);
  padding-block:28px 22px;
  display:flex; flex-wrap:wrap; gap:28px; align-items:flex-start;
  justify-content:space-between;
}
.marca{display:flex; gap:18px; align-items:center; min-width:0}
.marca h1{
  margin:2px 0 0; font-size:clamp(30px,5vw,44px); line-height:.98;
  text-transform:uppercase; letter-spacing:.005em; font-weight:700;
  text-wrap:balance;
}
.marca .sub{margin:6px 0 0; color:var(--tinta-media); font-size:14px}
.ring{flex:0 0 auto; width:76px; height:76px}

.mando{display:flex; flex-direction:column; align-items:flex-end; gap:14px}
.botonera{display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end}
.tecla{
  background:var(--placa); color:var(--tinta-media);
  border:1px solid var(--regla); border-radius:var(--r);
  padding:7px 13px; font-size:11px; text-transform:uppercase; letter-spacing:.12em;
  cursor:pointer; line-height:1; text-decoration:none;
}
.tecla:hover{border-color:var(--regla-fuerte); color:var(--tinta)}
.tecla:focus-visible{outline:2px solid var(--azul-vivo); outline-offset:2px}

.marcadores{display:flex; flex-wrap:wrap; gap:26px}
.marcador{display:flex; flex-direction:column; gap:3px}
.marcador .cifra{
  font-family:Oswald,sans-serif; font-weight:600; font-size:27px; line-height:1;
}
.marcador .fuente{font-family:"JetBrains Mono",monospace; font-size:10.5px; color:var(--tinta-suave)}

/* ------------------------------------------------------------------ curva */
.curva{
  margin-top:26px; background:var(--placa); border:1px solid var(--regla);
  border-radius:var(--r); padding:20px 22px 14px;
}
.curva header,.bloque-cab{display:flex; justify-content:space-between; align-items:baseline; gap:16px; flex-wrap:wrap}
.curva h2{margin:0; font-size:15px; text-transform:uppercase; letter-spacing:.1em}
.curva .nota{font-size:13px; color:var(--tinta-suave); font-style:italic; margin:0; max-width:70ch}
.lienzo{width:100%; height:auto; display:block; margin-top:10px; overflow:visible}
.lienzo text{font-family:"JetBrains Mono",monospace; font-size:11px; fill:var(--tinta-suave)}
.lienzo text.valor{fill:var(--tinta); font-weight:700; font-size:12.5px}
.lienzo text.ver{font-family:Oswald,sans-serif; font-size:11.5px; letter-spacing:.04em}
.leyenda{display:flex; gap:18px; flex-wrap:wrap; font-family:"JetBrains Mono",monospace; font-size:11.5px; color:var(--tinta-media); margin-top:10px}
.leyenda span{display:inline-flex; align-items:center; gap:7px}
.leyenda i{display:inline-block; width:18px; height:2px; border-radius:1px}
.leyenda i.s1{background:var(--serie-1)} .leyenda i.s2{background:var(--serie-2)}

.juez{margin-top:16px; padding-top:14px; border-top:1px solid var(--regla)}
.juez table td.gordo{font-family:Oswald,sans-serif; font-size:20px; font-weight:600; line-height:1.1}

/* -------------------------------------------------------------- estructura */
.disposicion{display:grid; grid-template-columns:250px minmax(0,1fr); gap:28px; margin-top:28px; align-items:start}
@media (max-width:860px){ .disposicion{grid-template-columns:1fr} }

/* ---------------------------------------------------------------- historia */
.historia{border-left:2px solid var(--regla); padding-left:0; display:flex; flex-direction:column}
.historia > .rotulo{padding:0 0 10px 16px}
.hito{
  position:relative; display:block; width:100%; text-align:left;
  background:none; border:0; border-radius:0;
  padding:11px 12px 12px 16px; cursor:pointer; color:inherit;
  font-family:inherit; border-bottom:1px solid var(--regla);
}
.hito::before{
  content:""; position:absolute; left:-6px; top:18px;
  width:9px; height:9px; border-radius:50%;
  background:var(--fondo); border:2px solid var(--regla-fuerte);
}
.hito:hover{background:var(--placa-alt)}
.hito[aria-current="true"]{background:var(--placa)}
.hito[aria-current="true"]::before{background:var(--azul-vivo); border-color:var(--azul-vivo)}
.hito:focus-visible{outline:2px solid var(--azul-vivo); outline-offset:-2px}
.hito .ver{font-family:Oswald,sans-serif; font-weight:600; font-size:16px; letter-spacing:.03em}
.hito .tit{display:block; font-size:13.5px; color:var(--tinta-media); line-height:1.35; margin-top:2px}
.hito .fila{display:flex; align-items:center; gap:8px; flex-wrap:wrap}

/* ------------------------------------------------------------------ chips */
.chip{
  display:inline-block; font-size:10px; text-transform:uppercase; letter-spacing:.1em;
  padding:2.5px 7px; border-radius:2px; line-height:1.4; font-weight:600;
  background:var(--hueco); color:var(--tinta-media); white-space:nowrap;
}
.chip.baseline,.chip.refactor{background:var(--azul-fondo); color:var(--azul)}
.chip.tuning,.chip.experiment{background:var(--neutro-fondo); color:var(--neutro)}
.chip.nuevo{background:var(--mejora-fondo); color:var(--mejora)}
.chip.bugfix,.chip.revert{background:var(--regresion-fondo); color:var(--regresion)}
.chip.v-mejora,.chip.e-hecha{background:var(--mejora-fondo); color:var(--mejora)}
.chip.v-regresion{background:var(--regresion-fondo); color:var(--regresion)}
.chip.v-pendiente,.chip.e-en_curso{background:var(--neutro-fondo); color:var(--neutro)}
.chip.e-pendiente{background:var(--azul-fondo); color:var(--azul)}

/* --------------------------------------------------------------- expediente */
.expediente{min-width:0; display:flex; flex-direction:column; gap:22px}
.titular{border-bottom:2px solid var(--regla-fuerte); padding-bottom:16px}
.titular .linea{display:flex; align-items:baseline; gap:12px; flex-wrap:wrap}
.titular .num{font-family:Oswald,sans-serif; font-weight:700; font-size:34px; letter-spacing:.01em; line-height:1}
.titular h2{margin:8px 0 0; font-size:23px; font-weight:600; line-height:1.2; text-wrap:balance; text-transform:none; letter-spacing:0}
.titular .meta{margin:9px 0 0; font-size:13px; color:var(--tinta-suave)}

.bloque{background:var(--placa); border:1px solid var(--regla); border-radius:var(--r); padding:20px 22px; min-width:0}
.bloque h3{
  margin:0 0 12px; font-size:11px; text-transform:uppercase; letter-spacing:.14em;
  color:var(--tinta-suave); font-weight:500;
}
.bloque p.explica{margin:0 0 14px; font-size:14.5px; color:var(--tinta-media); max-width:66ch; line-height:1.55}
.razonamiento{display:grid; gap:18px}
@media (min-width:720px){ .razonamiento{grid-template-columns:1fr 1fr} }
.razonamiento .campo{display:flex; flex-direction:column; gap:5px; min-width:0}
.razonamiento .campo p{margin:0; font-size:15.5px; max-width:62ch; line-height:1.62}
.razonamiento .campo.ancho{grid-column:1/-1}

table{width:100%; border-collapse:collapse; font-size:13.5px}
.tabla-envoltorio{overflow-x:auto}
th{
  text-align:left; font-family:Oswald,sans-serif; font-weight:500; font-size:10.5px;
  text-transform:uppercase; letter-spacing:.11em; color:var(--tinta-suave);
  padding:0 12px 7px 0; border-bottom:1px solid var(--regla); white-space:nowrap;
}
td{padding:8px 12px 8px 0; border-bottom:1px solid var(--regla); vertical-align:top}
tr:last-child td{border-bottom:0}
td.num,th.num{font-family:"JetBrains Mono",monospace; font-variant-numeric:tabular-nums; white-space:nowrap}
th.num{font-family:Oswald,sans-serif}
.flecha{color:var(--tinta-suave); padding-inline:4px}
.de{color:var(--del-tinta)} .a{color:var(--add-tinta); font-weight:700}
.cero{color:var(--regresion); font-weight:700}

/* --------------------------------------------------------------- metricas */
.rivales{display:flex; flex-direction:column; gap:11px}
.rival{display:grid; grid-template-columns:88px minmax(0,1fr) 96px; gap:12px; align-items:center}
@media (max-width:520px){ .rival{grid-template-columns:74px minmax(0,1fr) 78px; gap:8px} }
.rival .nom{font-family:Oswald,sans-serif; font-size:13px; letter-spacing:.04em; text-transform:uppercase; color:var(--tinta-media)}
.barra{height:14px; background:var(--hueco); border-radius:1px; overflow:hidden}
.barra span{display:block; height:100%; background:var(--azul-vivo)}
.rival .cifra{font-family:"JetBrains Mono",monospace; font-size:12.5px; font-variant-numeric:tabular-nums; text-align:right; color:var(--tinta-media)}

/* ------------------------------------------------------------------- diff */
.diff-cab{display:flex; justify-content:space-between; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:12px}
.recuento{font-family:"JetBrains Mono",monospace; font-size:12.5px; font-variant-numeric:tabular-nums}
.recuento .mas{color:var(--add-tinta); font-weight:700}
.recuento .menos{color:var(--del-tinta); font-weight:700}
pre.diff{
  margin:0; background:var(--placa-alt); border:1px solid var(--regla); border-radius:var(--r);
  font-size:12.5px; line-height:1.55; overflow-x:auto; max-height:560px; overflow-y:auto;
  padding:0; tab-size:2;
}
pre.diff .l{display:block; padding:0 14px; white-space:pre}
pre.diff .l.mas{background:var(--add-fondo); color:var(--add-tinta)}
pre.diff .l.menos{background:var(--del-fondo); color:var(--del-tinta)}
pre.diff .l.trozo{background:var(--azul-fondo); color:var(--azul); font-weight:700}
pre.diff .l.arch{color:var(--tinta-suave); font-weight:700; padding-top:8px}
.vacio{font-style:italic; color:var(--tinta-suave); font-size:14px; margin:0}

.ficheros{display:flex; flex-direction:column; gap:0}
.fichero{display:flex; justify-content:space-between; align-items:baseline; gap:14px; padding:7px 0; border-bottom:1px solid var(--regla); font-size:13px; flex-wrap:wrap}
.fichero:last-child{border-bottom:0}
.fichero .ruta{font-family:"JetBrains Mono",monospace; font-size:12.5px; word-break:break-all}
.fichero .ruta.tocado{color:var(--azul-vivo); font-weight:700}
.fichero .der{font-family:"JetBrains Mono",monospace; font-size:11.5px; color:var(--tinta-suave); font-variant-numeric:tabular-nums; white-space:nowrap}

/* --------------------------------------------------- aprendizaje en GPU */
.seccion{margin-top:52px}
.seccion-cab{border-bottom:2px solid var(--regla-fuerte); padding-bottom:16px; margin-bottom:22px; display:grid; gap:8px}
.seccion-cab h2{margin:0; font-size:clamp(24px,3.4vw,30px); text-transform:uppercase; letter-spacing:.02em; line-height:1}
.seccion-cab .entradilla{margin:4px 0 0; font-size:16px; color:var(--tinta-media); max-width:72ch; line-height:1.6}
.seccion .marcadores{margin-bottom:22px}
.rejilla{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px; align-items:start}
.rejilla .ancho{grid-column:1/-1}
@media (max-width:900px){ .rejilla{grid-template-columns:1fr} }
.ciclo{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0; margin:0 0 22px; padding:0; border:1px solid var(--regla); border-radius:var(--r); background:var(--placa)}
.ciclo li{list-style:none; padding:14px 16px; border-left:1px solid var(--regla); display:grid; gap:4px}
.ciclo li:first-child{border-left:0}
.ciclo b{font-family:Oswald,sans-serif; font-weight:600; font-size:14px; letter-spacing:.03em}
.ciclo span{font-size:13px; color:var(--tinta-media); line-height:1.45}
.ciclo code{font-size:11.5px; color:var(--azul)}
@media (max-width:760px){ .ciclo{grid-template-columns:1fr 1fr} .ciclo li:nth-child(3){border-left:0} .ciclo li:nth-child(n+3){border-top:1px solid var(--regla)} }
pre.orden{margin:10px 0 0; padding:10px 12px; background:var(--placa-alt); border:1px solid var(--regla); border-radius:var(--r); font-size:12px; overflow-x:auto}
.elo-barra{display:block; height:6px; background:var(--hueco); border-radius:1px; margin-top:6px; min-width:80px}
.elo-barra span{display:block; height:100%; background:var(--serie-1); border-radius:0 2px 2px 0}
details.tabla{margin-top:10px}
details.tabla summary{cursor:pointer; font-family:"JetBrains Mono",monospace; font-size:11.5px; color:var(--tinta-suave)}

/* --------------------------------------------------------------- tareas */
.tarea{display:grid; grid-template-columns:62px minmax(0,1fr) auto; gap:12px; padding:10px 0; border-bottom:1px solid var(--regla); align-items:baseline}
.tarea:last-child{border-bottom:0}
.tarea .id{font-family:"JetBrains Mono",monospace; font-size:12.5px; color:var(--tinta-suave)}
.tarea .txt{font-size:15px; line-height:1.45}
.tarea .txt small{display:block; font-size:13px; color:var(--tinta-suave); margin-top:3px; line-height:1.45}
.tarea.hija .txt{padding-left:18px; border-left:2px solid var(--regla)}
@media (max-width:560px){ .tarea{grid-template-columns:52px minmax(0,1fr)} .tarea .chip{grid-column:2; justify-self:start} }

.pie{margin-top:44px; padding-top:18px; border-top:1px solid var(--regla); font-size:13px; color:var(--tinta-suave)}
.pie code{font-size:12.5px; background:var(--hueco); padding:1px 5px; border-radius:2px}

@media (prefers-reduced-motion: reduce){ *{transition:none !important; animation:none !important} }
</style>

<div class="envoltorio">
  <header class="cabecera">
    <div class="marca">
      <svg class="ring" viewBox="0 0 100 100" role="img" aria-label="Dohyo reglamentario de 770 mm con banda blanca de 25 mm">
        <circle cx="50" cy="50" r="48" fill="var(--regla-fuerte)"></circle>
        <circle cx="50" cy="50" r="44.9" fill="var(--tinta)"></circle>
        <rect x="41.5" y="43.6" width="17" height="1.6" fill="var(--fondo)"></rect>
        <rect x="41.5" y="54.8" width="17" height="1.6" fill="var(--fondo)"></rect>
      </svg>
      <div>
        <p class="rotulo" style="margin:0">Bitácora de algoritmos · Webots · GPU</p>
        <h1>Gelatina<br>Nuclear</h1>
        <p class="sub">Mini-sumo · 10 × 10 cm · 495 g · control en C portable</p>
      </div>
    </div>
    <div class="mando">
      <div class="botonera">
        <a class="tecla" href="#aprendizaje">Aprendizaje</a>
        <a class="tecla" href="#tareas">Tareas</a>
        <button class="tecla" id="tema" type="button">Tema</button>
      </div>
      <div class="marcadores" id="marcadores"></div>
    </div>
  </header>

  <section class="curva">
    <header>
      <h2>Curva de aprendizaje</h2>
      <p class="nota" id="curva-nota"></p>
    </header>
    <div class="leyenda" id="curva-leyenda"></div>
    <div id="curva-lienzo"></div>
    <div class="juez" id="juez"></div>
  </section>

  <div class="disposicion">
    <nav class="historia" id="historia" aria-label="Versiones"></nav>
    <section class="expediente" id="expediente"></section>
  </div>

  <section class="seccion" id="aprendizaje"></section>
  <section class="seccion" id="tareas"></section>

  <footer class="pie">
    <p>Cada entrada la genera <code>tools/gnver.py</code> al registrar una versión.
    El guardián <code>python3 tools/gnver.py check</code> falla si hay código de control
    modificado sin versionar, que es lo que mantiene esta bitácora completa. La sección de
    aprendizaje sale de <code>ml/data/</code> y el tablero, de <code>Tareas/tareas.json</code>.</p>
  </footer>
</div>

<script type="application/json" id="datos">/*__DATOS__*/</script>
<script>
(function(){
"use strict";
const D = JSON.parse(document.getElementById("datos").textContent);
const V = D.versions || [];
const ML = D.ml || {};
const TAREAS = D.tareas || [];

/* ---- tema ------------------------------------------------------------ */
const raiz = document.documentElement;
document.getElementById("tema").addEventListener("click", function(){
  const oscuroAhora = raiz.getAttribute("data-theme") === "dark" ||
    (!raiz.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
  raiz.setAttribute("data-theme", oscuroAhora ? "light" : "dark");
});

/* ---- utilidades ------------------------------------------------------ */
const esc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const pct = (x, d) => (x == null) ? "—" : (x*100).toFixed(d || 0).replace(".", ",") + " %";
const num = (x, d) => (x == null) ? "—" : Number(x).toFixed(d == null ? 2 : d).replace(".", ",");
const miles = n => Number(n || 0).toLocaleString("es-ES");
const claseTipo = k => ({"new-behavior":"nuevo"})[k] || k;
const fecha = s => { try { return new Date(s).toLocaleDateString("es-ES",
  {day:"2-digit",month:"short",year:"numeric"}); } catch(e){ return s; } };
const COL_ES = {frente:"frente", lado:"lado", espalda:"espaldas"};

function conMetricas(){ return V.filter(v => (v.metrics||{}).rounds > 0); }
/* combate a 3 rondas con el reglamento: Webots si esta medido, si no el banco en C */
function reglamento(v){
  if (v.metrics_webots && v.metrics_webots.match_win_rate != null) return {x: v.metrics_webots.match_win_rate, fuente: "Webots"};
  if (v.metrics_reglamento && v.metrics_reglamento.match_win_rate != null) return {x: v.metrics_reglamento.match_win_rate, fuente: "banco en C"};
  return null;
}

/* ---- marcadores de cabecera ------------------------------------------ */
(function marcadores(){
  const ult = V[V.length-1];
  const m = conMetricas();
  const wr = m.length ? m[m.length-1].metrics.win_rate : null;
  const r = ult ? reglamento(ult) : null;
  const previa = V.length > 1 ? V[V.length-2] : null;
  let delta = "—", color = "var(--tinta-suave)", fuenteDelta = "";
  if (r && previa) {
    const rp = previa.metrics_webots && r.fuente === "Webots" ? {x: previa.metrics_webots.match_win_rate} : reglamento(previa);
    if (rp) {
      const d = (r.x - rp.x) * 100;
      delta = (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(0) + " pp";
      color = d > 0 ? "var(--mejora)" : (d < 0 ? "var(--regresion)" : "var(--neutro)");
      fuenteDelta = "frente a " + previa.version;
    }
  }
  const filas = [
    ["Versiones", V.length, "var(--tinta)", ""],
    ["Win rate · banco", wr == null ? "—" : pct(wr), "var(--tinta)", "modo de siempre"],
    ["Combate · reglamento", r ? pct(r.x) : "—", "var(--azul-vivo)", r ? r.fuente : ""],
    ["Respecto a la previa", delta, color, fuenteDelta]
  ];
  document.getElementById("marcadores").innerHTML = filas.map(f =>
    '<div class="marcador"><span class="rotulo">'+esc(f[0])+'</span>'+
    '<span class="cifra" style="color:'+f[2]+'">'+esc(f[1])+'</span>'+
    (f[3] ? '<span class="fuente">'+esc(f[3])+'</span>' : '')+'</div>').join("");
})();

/* ---- grafica de lineas generica (una sola escala 0-100 %) -------------- */
function grafica(o){
  /* o: {etiquetas:[...], series:[{nombre, token, valores:[...|null]}], alto, etiquetaX} */
  const W = 960, H = o.alto || 240, ml = 50, mr = 96, mt = 16, mb = 34;
  const iw = W - ml - mr, ih = H - mt - mb, n = o.etiquetas.length;
  const px = i => n === 1 ? ml + iw/2 : ml + (i/(n-1))*iw;
  const py = w => mt + ih - w*ih;
  let g = "";
  [0,0.25,0.5,0.75,1].forEach(t => {
    const y = py(t).toFixed(1);
    g += '<line x1="'+ml+'" y1="'+y+'" x2="'+(ml+iw)+'" y2="'+y+'" stroke="'+(t===0?"var(--regla-fuerte)":"var(--regla)")+'" stroke-width="1"></line>'+
         '<text x="'+(ml-9)+'" y="'+(+y+4)+'" text-anchor="end">'+(t*100)+' %</text>';
  });
  const paso = Math.max(1, Math.ceil(n / 10));
  o.etiquetas.forEach((e, i) => {
    if (i % paso === 0 || i === n-1)
      g += '<text class="'+(o.etiquetaX ? "" : "ver")+'" x="'+px(i).toFixed(1)+'" y="'+(H-mb+18)+'" text-anchor="middle">'+esc(e)+'</text>';
  });
  const finales = [];
  o.series.forEach(s => {
    const pts = s.valores.map((v,i) => v == null ? null : [px(i), py(v), v, i]).filter(Boolean);
    if (!pts.length) return;
    if (pts.length > 1)
      g += '<path d="'+pts.map((p,k) => (k?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join(" ")+
           '" fill="none" stroke="var('+s.token+')" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>';
    if (o.puntos !== false) pts.forEach(p => {
      g += '<g><circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="4.5" fill="var('+s.token+')" stroke="var(--placa)" stroke-width="2"></circle>'+
           '<circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="12" fill="transparent"><title>'+
           esc(o.etiquetas[p[3]]+" · "+s.nombre+": "+pct(p[2], 1))+'</title></circle></g>';
    });
    const u = pts[pts.length-1];
    if (o.puntos === false)
      g += '<circle cx="'+u[0].toFixed(1)+'" cy="'+u[1].toFixed(1)+'" r="4.5" fill="var('+s.token+')" stroke="var(--placa)" stroke-width="2"></circle>';
    finales.push(u);
  });
  const chocan = finales.length === 2 && Math.abs(finales[0][1] - finales[1][1]) < 16;
  if (!chocan) finales.forEach(u => {
    g += '<text class="valor" x="'+(u[0]+12).toFixed(1)+'" y="'+(u[1]+4.5).toFixed(1)+'">'+pct(u[2])+'</text>';
  });
  return '<svg class="lienzo" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(o.titulo || "")+'"><g>'+g+'</g></svg>';
}

function leyenda(series){
  return series.map(s => '<span><i class="'+s.clase+'"></i>'+esc(s.nombre)+'</span>').join("");
}

/* ---- curva de aprendizaje de la bitacora ------------------------------- */
(function pintarCurva(){
  const vs = V.filter(v => (v.metrics||{}).rounds > 0 || v.metrics_reglamento);
  const nota = document.getElementById("curva-nota");
  if (!vs.length) {
    document.getElementById("curva-lienzo").innerHTML = '<p class="vacio">Todavía no hay combates registrados.</p>';
    return;
  }
  nota.textContent = "Las dos medidas salen del banco nativo en C, 60 asaltos por rival. El win rate usa la diagonal a 36 cm de siempre; " +
    "el combate a tres rondas usa las colocaciones del reglamento (frente, lado y espaldas a 5 cm).";
  const series = [
    {nombre: "Win rate · diagonal de siempre", token: "--serie-1", clase: "s1", valores: vs.map(v => (v.metrics||{}).rounds ? v.metrics.win_rate : null)},
    {nombre: "Combate ganado · reglamento", token: "--serie-2", clase: "s2", valores: vs.map(v => v.metrics_reglamento ? v.metrics_reglamento.match_win_rate : null)}
  ];
  document.getElementById("curva-leyenda").innerHTML = leyenda(series);
  document.getElementById("curva-lienzo").innerHTML = grafica({etiquetas: vs.map(v => v.version), series, titulo: "Win rate y combate ganado por versión"});

  const w = V.filter(v => v.metrics_webots);
  if (!w.length) return;
  const fila = v => {
    const m = v.metrics_webots, b = v.metrics_webots_banco;
    return '<tr><td class="num">'+esc(v.version)+'</td><td class="gordo">'+pct(m.match_win_rate)+'</td>'+
      '<td class="num">'+m.wins+' · '+m.losses+' · '+m.draws+'</td><td class="num'+(m.self_outs ? " cero" : "")+'">'+m.self_outs+'</td>'+
      '<td class="num">'+(m.opponents||[]).map(o => esc(o.name)+" "+pct(o.match ? o.match.win : null)).join(" · ")+'</td>'+
      '<td class="num">'+(b ? b.wins+' · '+b.losses+' · '+b.draws : "—")+'</td></tr>';
  };
  document.getElementById("juez").innerHTML =
    '<p class="rotulo" style="margin:0 0 8px">El juez final · Webots con las colocaciones del reglamento, 30 asaltos por rival</p>'+
    '<div class="tabla-envoltorio"><table><thead><tr><th>Versión</th><th>Combate ganado</th><th class="num">V · D · E</th>'+
    '<th class="num">Auto-salidas</th><th>Por rival</th><th class="num">Diagonal · V · D · E</th></tr></thead><tbody>'+
    w.map(fila).join("")+'</tbody></table></div>';
})();

/* ---- carril de versiones --------------------------------------------- */
function pintarHistoria(sel){
  const h = document.getElementById("historia");
  h.innerHTML = '<p class="rotulo">Historial · más reciente arriba</p>' +
    V.slice().reverse().map(v => {
      const mt = v.metrics || {}, r = reglamento(v);
      const wr = mt.rounds ? pct(mt.win_rate) : "sin medir";
      return '<button class="hito" type="button" data-v="'+esc(v.version)+'" '+
        'aria-current="'+(v.version===sel)+'">'+
        '<span class="fila"><span class="ver">'+esc(v.version)+'</span>'+
        '<span class="chip '+esc(claseTipo(v.kind))+'">'+esc(v.kind)+'</span></span>'+
        '<span class="tit">'+esc(v.title)+'</span>'+
        '<span class="tit dato" style="color:var(--tinta-suave)">it '+v.iteration+' · '+esc(wr)+
        (r ? ' · combate '+pct(r.x)+(r.fuente === "Webots" ? " Webots" : "") : '')+'</span>'+
        '</button>';
    }).join("");
  h.querySelectorAll(".hito").forEach(b =>
    b.addEventListener("click", () => mostrar(b.dataset.v)));
}

/* ---- diff ------------------------------------------------------------ */
function pintarDiff(txt){
  if (!txt || !txt.trim()) return '<p class="vacio">Sin cambios de código en esta entrada.</p>';
  const lineas = txt.split("\n").map(l => {
    let c = "l";
    if (l.startsWith("+++") || l.startsWith("---")) c += " arch";
    else if (l.startsWith("@@")) c += " trozo";
    else if (l.startsWith("+")) c += " mas";
    else if (l.startsWith("-")) c += " menos";
    return '<span class="'+c+'">'+esc(l || " ")+'</span>';
  }).join("");
  return '<pre class="diff">'+lineas+'</pre>';
}

/* ---- tabla del reglamento: rival x colocacion + combate ---------------- */
function tablaReglamento(m, titulo, explica){
  const ops = (m.opponents || []).filter(o => o.placements);
  if (!ops.length) return "";
  const celda = p => {
    if (!p || !p.rounds) return '<td class="num">—</td>';
    const w = p.wins / p.rounds;
    return '<td class="num'+(w === 0 ? " cero" : "")+'">'+p.wins+'/'+p.rounds+'</td>';
  };
  return '<div class="bloque"><h3>'+esc(titulo)+'</h3>'+(explica ? '<p class="explica">'+explica+'</p>' : '')+
    '<div class="tabla-envoltorio"><table><thead><tr><th>Rival</th><th class="num">Frente</th><th class="num">Lado</th><th class="num">Espaldas</th>'+
    '<th class="num">Gana el combate</th><th class="num">Pierde</th></tr></thead><tbody>'+
    ops.map(o => {
      const pl = {}; o.placements.forEach(p => pl[p.name] = p);
      return '<tr><td class="num">'+esc(o.name)+'</td>'+celda(pl.frente)+celda(pl.lado)+celda(pl.espalda)+
        '<td class="num">'+pct(o.match.win, 1)+'</td><td class="num">'+pct(o.match.loss, 1)+'</td></tr>';
    }).join("")+'</tbody></table></div>'+
    '<p class="vacio" style="margin-top:10px">'+m.wins+' V · '+m.losses+' D · '+m.draws+' E · auto-salidas '+m.self_outs+
    (m.match_win_rate != null ? ' · combate ganado de media '+pct(m.match_win_rate, 1) : '')+'</p></div>';
}

/* ---- expediente de una versión --------------------------------------- */
function mostrar(ver){
  const v = V.find(x => x.version === ver) || V[V.length-1];
  if (!v) {
    document.getElementById("expediente").innerHTML =
      '<div class="bloque"><p class="vacio">La bitácora está vacía. '+
      'Crea la primera versión con <code>python3 tools/gnver.py new</code>.</p></div>';
    return;
  }
  const mt = v.metrics || {}, ds = v.diff_stat || {added:0,removed:0,files:0,touched:[]};
  const tocados = new Set(ds.touched || []);
  let H = "";

  H += '<div class="titular"><div class="linea">'+
       '<span class="num">'+esc(v.version)+'</span>'+
       '<span class="chip '+esc(claseTipo(v.kind))+'">'+esc(v.kind)+'</span>'+
       '<span class="chip v-'+esc(v.verdict||"pendiente")+'">'+esc(v.verdict||"pendiente")+'</span>'+
       '</div><h2>'+esc(v.title)+'</h2>'+
       '<p class="meta dato">Iteración '+v.iteration+' · '+esc(fecha(v.created_at))+
       ' · '+esc(v.author)+(v.parent?' · deriva de '+esc(v.parent):' · sin antecesora')+'</p></div>';

  const campos = [
    ["Qué cambió", v.summary, true],
    ["Por qué", v.rationale, true],
    ["Hipótesis", v.hypothesis, false],
    ["Efecto esperado", v.expected_effect, false],
    ["Riesgos asumidos", v.risks, false],
    ["Nota para el robot real", v.notes_real_robot, false]
  ].filter(c => c[1]);
  H += '<div class="bloque"><h3>Razonamiento</h3><div class="razonamiento">' +
    campos.map(c => '<div class="campo'+(c[2]?' ancho':'')+'">'+
      '<span class="rotulo">'+esc(c[0])+'</span><p>'+esc(c[1])+'</p></div>').join("") +
    '</div></div>';

  if ((v.params_changed||[]).length) {
    H += '<div class="bloque"><h3>Parámetros tocados</h3><div class="tabla-envoltorio"><table>'+
      '<thead><tr><th>Parámetro</th><th>Antes</th><th></th><th>Después</th><th>Motivo</th></tr></thead><tbody>'+
      v.params_changed.map(p => '<tr><td class="num">'+esc(p.name)+'</td>'+
        '<td class="num de">'+esc(p.from)+'</td><td class="flecha">→</td>'+
        '<td class="num a">'+esc(p.to)+'</td><td>'+esc(p.reason||"")+'</td></tr>').join("")+
      '</tbody></table></div></div>';
  }

  H += '<div class="bloque"><h3>Resultados en el ring · banco nativo, diagonal de siempre</h3>';
  if (mt.rounds) {
    const ops = Array.isArray(mt.opponents) ? mt.opponents : [];
    H += '<div class="marcadores" style="margin-bottom:'+(ops.length?"18px":"0")+'">'+
      [["Asaltos",mt.rounds,"var(--tinta)"],
       ["Victorias",mt.wins,"var(--mejora)"],
       ["Derrotas",mt.losses,"var(--regresion)"],
       ["Empates",mt.draws,"var(--tinta-media)"],
       ["Win rate",pct(mt.win_rate),"var(--azul-vivo)"],
       ["Auto-salidas",mt.self_outs!=null?mt.self_outs:"—","var(--regresion)"],
       ["Victoria media",mt.avg_win_time_s?num(mt.avg_win_time_s)+" s":"—","var(--tinta)"]
      ].map(f => '<div class="marcador"><span class="rotulo">'+esc(f[0])+'</span>'+
        '<span class="cifra" style="color:'+f[2]+'">'+esc(f[1])+'</span></div>').join("")+'</div>';
    if (ops.length) {
      H += '<span class="rotulo">Desglose por rival</span><div class="rivales" style="margin-top:10px">'+
        ops.map(o => {
          const w = Math.max(0, Math.min(1, o.win_rate||0));
          const col = w >= 0.6 ? "var(--mejora)" : (w >= 0.35 ? "var(--neutro)" : "var(--regresion)");
          return '<div class="rival"><span class="nom">'+esc(o.name)+'</span>'+
            '<span class="barra"><span style="width:'+(w*100).toFixed(1)+'%;background:'+col+'"></span></span>'+
            '<span class="cifra">'+pct(o.win_rate)+' · '+o.wins+'/'+o.rounds+'</span></div>';
        }).join("")+'</div>';
    }
  } else {
    H += '<p class="vacio">Sin combates registrados todavía en esta versión.</p>';
  }
  H += '</div>';

  if (v.metrics_reglamento)
    H += tablaReglamento(v.metrics_reglamento, "Con el reglamento · banco nativo en C",
      "Victorias por colocación sobre 20 asaltos cada una, y probabilidad de ganar el combate a tres rondas. El mirror es la propia versión contra sí misma.");
  if (v.metrics_webots)
    H += tablaReglamento(v.metrics_webots, "Con el reglamento · Webots",
      "Robot de 495 g, 10 asaltos por colocación. v0.3.0 es la versión congelada, compilada desde su instantánea.");

  H += '<div class="bloque"><div class="diff-cab"><h3 style="margin:0">Cambio de código</h3>'+
       '<span class="recuento"><span class="mas">+'+ds.added+'</span> / '+
       '<span class="menos">−'+ds.removed+'</span> en '+ds.files+' fichero(s)</span></div>'+
       pintarDiff(v.diff)+'</div>';

  H += '<div class="bloque"><h3>Estado del árbol de control</h3><div class="ficheros">'+
    (v.files||[]).map(f => '<div class="fichero">'+
      '<span class="ruta'+(tocados.has(f.path)?" tocado":"")+'">'+esc(f.path)+'</span>'+
      '<span class="der">'+f.lines+' líneas · '+esc(String(f.sha256).slice(0,10))+'</span></div>').join("")+
    '</div></div>';

  document.getElementById("expediente").innerHTML = H;
  pintarHistoria(v.version);
}

/* ---- aprendizaje en GPU -------------------------------------------------- */
function barrasDireccion(ps){
  const W = 560, fila = 26, H = ps.length*fila + 8, ml = 158, c = 330, medio = 150;
  const max = Math.max.apply(null, ps.map(p => p.importancia).concat([1e-9]));
  let g = '<line x1="'+c+'" x2="'+c+'" y1="0" y2="'+H+'" stroke="var(--regla-fuerte)" stroke-width="1"></line>';
  ps.forEach((p, k) => {
    const y = k*fila + 6, h = 14, w = Math.max(2, p.importancia/max*medio), sube = p.gradiente > 0, r = Math.min(4, w/2);
    const d = sube
      ? 'M'+c+','+y+' h'+(w-r)+' a'+r+','+r+' 0 0 1 '+r+','+r+' v'+(h-2*r)+' a'+r+','+r+' 0 0 1 '+(-r)+','+r+' h'+(-(w-r))+' z'
      : 'M'+c+','+y+' h'+(-(w-r))+' a'+r+','+r+' 0 0 0 '+(-r)+','+r+' v'+(h-2*r)+' a'+r+','+r+' 0 0 0 '+r+','+r+' h'+(w-r)+' z';
    g += '<g><text x="'+(ml-10)+'" y="'+(y+11)+'" text-anchor="end">'+esc(p.nombre)+'</text>'+
         '<path d="'+d+'" fill="var('+(sube ? "--serie-1" : "--serie-2")+')"></path>'+
         '<text x="'+(c+medio+16)+'" y="'+(y+11)+'">'+(sube ? "sube" : "baja")+'</text>'+
         '<title>'+esc(p.nombre+": conviene "+(sube ? "subirlo" : "bajarlo")+" · importancia "+num(p.importancia, 3))+'</title></g>';
  });
  return '<svg class="lienzo" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Sentido e importancia de cada parámetro">'+g+'</svg>';
}

(function aprendizaje(){
  const el = document.getElementById("aprendizaje");
  const corr = ML.corridas || [], liga = ML.liga, val = ML.validacion, rec = ML.recompensa, pol = ML.politicas || [];
  if (!corr.length && !liga) { el.hidden = true; return; }
  const ult = corr[corr.length-1];
  let H = '<header class="seccion-cab"><p class="rotulo" style="margin:0">Aprendizaje por refuerzo con retroalimentación humana · RTX 5070</p>'+
    '<h2>Aprendizaje en GPU</h2>'+
    '<p class="entradilla">Un simulador del dohyo escrito en PyTorch juega cientos de miles de asaltos a la vez en la GPU. '+
    'Una estrategia evolutiva (CMA-ES) prueba variantes de <code>params.h</code> contra el banco de rivales; tus votos entre '+
    'repeticiones entrenan un modelo de recompensa que pesa en la siguiente vuelta. Lo que sale de aquí son candidatos: '+
    'solo pasan a la bitácora después de medirse en el banco en C y en Webots.</p></header>';

  H += '<ol class="ciclo">'+
    '<li><b>Simular</b><span>La población entera se juega en una pasada de la GPU.</span><code>python -m ml entrenar</code></li>'+
    '<li><b>Votar</b><span>El mismo asalto jugado por dos algoritmos; eliges el mejor.</span><code>python -m ml servidor</code></li>'+
    '<li><b>Recompensa</b><span>Cinco redes aprenden de tus votos qué conducta prefieres.</span><code>python -m ml recompensa</code></li>'+
    '<li><b>Liga</b><span>Todos contra todos y la dirección hacia la que mejorar.</span><code>python -m ml liga</code></li></ol>';

  const marc = [
    ["Asaltos simulados", miles((ult ? corr.reduce((s,c) => s + c.generaciones*c.asaltos_por_generacion, 0) : 0)), "en la RTX 5070"],
    ["GPU contra el banco en C", val ? (val.ok ? val.casos+" / "+val.casos : "falla") : "—", val ? "|z| máximo "+num(val.z_max, 1) : "sin validar"],
    ["Tus votos", ML.votos || 0, (ML.pares||{}).pendientes ? (ML.pares.pendientes+" comparaciones esperan") : "sin comparaciones pendientes"],
    ["Peso de tu opinión", rec ? "λ = "+num(rec.lambda_sugerida) : "λ = 0", rec ? "según "+rec.n_datos+" votos" : "crece con los votos"]
  ];
  H += '<div class="marcadores">'+marc.map(f => '<div class="marcador"><span class="rotulo">'+esc(f[0])+'</span>'+
    '<span class="cifra">'+esc(f[1])+'</span><span class="fuente">'+esc(f[2])+'</span></div>').join("")+'</div>';

  H += '<div class="rejilla">';
  if (ult) {
    const s = [
      {nombre: "Mejor candidato de la generación", token: "--serie-1", clase: "s1", valores: ult.log.map(f => f[1])},
      {nombre: "Media de la población", token: "--serie-2", clase: "s2", valores: ult.log.map(f => f[2])}
    ];
    H += '<div class="bloque ancho"><div class="bloque-cab"><h3>Entrenamiento '+esc(ult.id)+'</h3>'+
      '<span class="rotulo">'+ult.generaciones+' generaciones × '+ult.poblacion+' candidatos · '+miles(ult.asaltos_por_generacion)+' asaltos por generación · '+Math.round(ult.segundos)+' s</span></div>'+
      '<p class="explica">Probabilidad de ganar el combate a tres rondas, media sobre el banco de rivales, en modo robusto. '+
      'El campeón, '+esc(ult.candidato)+', gana el '+pct(ult.campeon_combate, 1)+' frente al '+pct(ult.base_combate, 1)+' de '+esc(ult.desde)+
      '. La población satura cerca del 100 %: el banco de rivales se queda corto, y por eso el campeón entra en la liga para la vuelta siguiente.</p>'+
      '<div class="leyenda">'+leyenda(s)+'</div>'+
      grafica({etiquetas: ult.log.map(f => f[0]), series: s, alto: 220, puntos: false, etiquetaX: true, titulo: "Combate ganado por generación"})+
      '<details class="tabla"><summary>Ver como tabla</summary><div class="tabla-envoltorio"><table><thead><tr><th class="num">Gen</th><th class="num">Mejor</th><th class="num">Media</th></tr></thead><tbody>'+
      ult.log.filter((f,i) => i % 5 === 0 || i === ult.log.length-1).map(f => '<tr><td class="num">'+f[0]+'</td><td class="num">'+pct(f[1],1)+'</td><td class="num">'+pct(f[2],1)+'</td></tr>').join("")+
      '</tbody></table></div></details></div>';
  }
  if (liga) {
    const alg = liga.algoritmos || [], emax = Math.max.apply(null, alg.map(a => a.elo)), emin = Math.min.apply(null, alg.map(a => a.elo));
    H += '<div class="bloque"><h3>Liga · todos contra todos</h3>'+
      '<p class="explica">Cada algoritmo contra todos los demás en las tres colocaciones ('+liga.rondas+' asaltos por colocación, modo robusto). Rating de Bradley-Terry en escala Elo.</p>'+
      '<div class="tabla-envoltorio"><table><thead><tr><th>Algoritmo</th><th class="num">Elo</th><th class="num">Gana el combate</th></tr></thead><tbody>'+
      alg.map(a => '<tr><td class="num">'+esc(a.id)+(liga.campeones.indexOf(a.id) >= 0 ? ' <span class="chip v-mejora">campeón</span>' : '')+
        '<span class="elo-barra"><span style="width:'+(10 + 90*(a.elo - emin)/Math.max(1, emax - emin)).toFixed(1)+'%"></span></span></td>'+
        '<td class="num">'+Math.round(a.elo)+'</td><td class="num">'+pct(a.gana_combate_medio, 1)+'</td></tr>').join("")+
      '</tbody></table></div></div>';
    if (liga.direccion && liga.direccion.parametros.length) {
      H += '<div class="bloque"><h3>Hacia dónde se inclina la GPU</h3>'+
        '<p class="explica">Una red entrenada con las '+miles(liga.direccion.muestras)+' variantes probadas predice la aptitud de cualquier juego de parámetros (explica el '+
        pct(Math.max(0, liga.direccion.r2))+' de la varianza fuera de muestra). Su gradiente en el mejor algoritmo dice qué conviene subir o bajar; la longitud, cuánto importa.</p>'+
        '<div class="leyenda"><span><i class="s1"></i>subir</span><span><i class="s2"></i>bajar</span></div>'+
        barrasDireccion(liga.direccion.parametros)+'</div>';
    }
  }
  H += '<div class="bloque"><h3>Tu voto</h3>';
  if (rec && rec.rasgos) {
    const top = rec.rasgos.slice().sort((a,b) => Math.abs(b.pendiente) - Math.abs(a.pendiente)).slice(0,5);
    H += '<p class="explica">'+rec.n_datos+' votos. El modelo acierta el '+(rec.precision_validacion_cruzada == null ? "— (pocos votos)" : pct(rec.precision_validacion_cruzada))+
      ' de los votos que no vio, y pesa λ = '+num(rec.lambda_sugerida)+' en el entrenamiento. Lo que más premian tus votos:</p><table><tbody>'+
      top.map(r => '<tr><td>'+esc(r.nombre)+'</td><td class="num">'+(r.pendiente > 0 ? "más" : "menos")+'</td><td class="num">'+num(r.pendiente, 3)+'</td></tr>').join("")+'</tbody></table>';
  } else {
    H += '<p class="explica">Todavía no hay votos reales, así que el entrenamiento solo ha usado la aptitud simulada (λ = 0). '+
      'Hay '+((ML.pares||{}).pendientes || 0)+' comparaciones esperando: el campeón contra la versión de la que partió, en el mismo asalto. '+
      'Con seis votos el modelo empieza a pesar; con sesenta, pesa del todo.</p>'+
      '<pre class="orden">cd Mini-Sumo\nml/.venv/bin/python -m ml servidor     # http://localhost:8765</pre>';
  }
  H += '</div>';
  H += '<div class="bloque"><h3>Política neuronal · PPO</h3>';
  if (pol.length) {
    const p = pol[pol.length-1];
    H += '<p class="explica">Una red de 21 entradas y dos salidas conduce las ruedas sin estados escritos a mano. Se entrenó con PPO durante '+
      miles(p.pasos)+' pasos de 8 ms. Todavía es un experimento: no ha pasado por Webots.</p><table><tbody>'+
      p.rivales.map(r => '<tr><td class="num">'+esc(r.nombre)+'</td><td class="num">'+pct(r.gana, 1)+'</td></tr>').join("")+
      '<tr><td><b>Gana el combate de media</b></td><td class="num"><b>'+pct(p.combate_gana, 1)+'</b></td></tr></tbody></table>'+
      (p.c ? '<p class="vacio" style="margin-top:10px">Exportada a C99: '+miles(p.c.pesos)+' pesos, '+num(p.c.pesos*4/1024, 1)+' KB; el C da lo mismo que PyTorch con un error máximo de '+Number(p.c.error_max).toExponential(1)+'.</p>' : '');
  } else {
    H += '<p class="explica">La red de 21 entradas y dos salidas se está entrenando con PPO en la GPU. Aparecerá aquí con su evaluación en cuanto termine.</p>';
  }
  H += '</div></div>';
  el.innerHTML = H;
})();

/* ---- tareas ------------------------------------------------------------ */
(function tareas(){
  const el = document.getElementById("tareas");
  if (!TAREAS.length) { el.hidden = true; return; }
  const n = e => TAREAS.filter(t => t.estado === e).length;
  const nombreEstado = {en_curso: "en curso", pendiente: "pendiente", hecha: "hecha", bloqueada: "bloqueada", descartada: "descartada"};
  const raiz = TAREAS.filter(t => !t.padre);
  const fila = (t, hija) => '<div class="tarea'+(hija ? " hija" : "")+'"><span class="id">'+esc(t.id)+'</span>'+
    '<span class="txt">'+esc(t.texto)+'<small>'+esc(t.estado === "hecha" ? (t.evidencia || t.criterio) : (t.criterio || ""))+'</small></span>'+
    '<span class="chip e-'+esc(t.estado)+'">'+esc(nombreEstado[t.estado] || t.estado)+' · '+esc(t.responsable)+'</span></div>';
  const cuenta = (k, uno, varios) => k + " " + (k === 1 ? uno : varios);
  el.innerHTML = '<header class="seccion-cab"><p class="rotulo" style="margin:0">Tareas/tareas.txt · lista 13-09-26 V1</p><h2>Tareas</h2>'+
    '<p class="entradilla">'+cuenta(n("hecha"), "hecha", "hechas")+', '+n("en_curso")+' en curso y '+cuenta(n("pendiente"), "pendiente", "pendientes")+
    '. Una tarea solo se cierra con evidencia; la pequeña línea bajo cada una es su criterio o, si ya está hecha, la prueba.</p></header>'+
    '<div class="bloque">'+raiz.map(t => fila(t, false) + TAREAS.filter(h => h.padre === t.id).map(h => fila(h, true)).join("")).join("")+'</div>';
})();

mostrar(V.length ? V[V.length-1].version : null);
})();
</script>
"""


def main():
    data = collect()
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(HTML.replace("/*__DATOS__*/", payload), encoding="utf-8")
    n = len(data["versions"])
    print(f"[sitio] site/index.html regenerado con {n} version(es)")


if __name__ == "__main__":
    main()
