/* app.js -- laboratorio de aprendizaje de Gelatina Nuclear.
   Sin dependencias ni compilacion. Una sola vista con rutas por hash; los
   datos salen de ml/servidor.py. La politica de seguridad del servidor
   prohibe estilos y scripts en linea: los colores van por clases CSS o por
   atributos SVG, y las posiciones por el.style desde aqui. */
"use strict";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pct = (x, d = 0) => x == null ? "—" : (x * 100).toFixed(d).replace(".", ",") + " %";
const num = (x, d = 2) => x == null ? "—" : Number(x).toFixed(d).replace(".", ",");
const compacto = n => n >= 1e6 ? (n / 1e6).toFixed(1).replace(".", ",") + " M" : n >= 1e3 ? Math.round(n / 1e3) + " k" : String(n);
const fecha = s => { try { return new Date(s).toLocaleString("es-MX", {dateStyle: "medium", timeStyle: "short"}); } catch (e) { return s; } };

const ESTADOS = ["WAIT", "OPENING", "SEARCH", "TRACK", "ATTACK", "EDGE_ESCAPE"];
const ESTADO_ES = {WAIT: "espera", OPENING: "apertura", SEARCH: "búsqueda", TRACK: "persecución", ATTACK: "ataque", EDGE_ESCAPE: "escape de borde"};
const RASGO_ES = {
  resultado: "ganar el asalto", auto_salida: "salirse solo", expulsado: "ser expulsado",
  t_fin: "duración del asalto", t_primer_contacto: "tardar en tocar al rival",
  frac_contacto: "tiempo en contacto", empuje: "empuje hacia fuera", frac_riesgo_borde: "tiempo cerca del borde",
  velocidad: "velocidad", frac_giro_sitio: "girar en el sitio", brusquedad: "brusquedad de motores",
  bordes_por_s: "encuentros con el borde", ventaja_final: "rival más cerca del borde al final",
  agresividad: "avanzar hacia el rival",
};
const COLOCACION_ES = {frente: "frente a frente", lado: "de lado", espalda: "de espaldas", banco: "diagonal del banco"};

let S = null;            // /api/estado
let reproductor = null;  // repeticion en curso
let teclas = null;       // atajos de la pagina actual
let toastT;

async function api(path, data) {
  const r = await fetch(path, data === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const v = await r.json();
  if (!r.ok) throw new Error(v.error || "No se pudo completar la solicitud.");
  return v;
}

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = error ? "error" : "";
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; }, 5200);
}

const tip = {
  mostrar(html, x, y) {
    const t = $("#tip");
    t.innerHTML = html;
    t.hidden = false;
    const r = t.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    t.style.left = left + "px";
    t.style.top = top + "px";
  },
  ocultar() { $("#tip").hidden = true; },
};

/* ======================================================================== */
/*  Rutas                                                                    */
/* ======================================================================== */

const PAGINAS = {
  resumen: ["Resumen", pResumen], votar: ["Votar", pVotar], versiones: ["Versiones", pVersiones],
  entrenamiento: ["Entrenamiento", pEntrenamiento], direccion: ["Dirección", pDireccion],
  liga: ["Liga", pLiga], tareas: ["Tareas", pTareas],
};

async function ruta() {
  const [id, arg] = (location.hash.slice(1) || "resumen").split("/");
  const pag = PAGINAS[id] ? id : "resumen";
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("active", a.dataset.page === pag));
  $("#titulo-pagina").textContent = PAGINAS[pag][0];
  pararReproduccion();
  teclas = null;
  tip.ocultar();
  try {
    S = await api("/api/estado");
    $("#connection").textContent = "Laboratorio conectado";
    $("#nav-pendientes").textContent = S.pares.pendientes;
    await PAGINAS[pag][1]($("#content"), arg ? decodeURIComponent(arg) : null);
  } catch (e) {
    $("#connection").textContent = "Sin conexión";
    $("#content").innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}
window.addEventListener("hashchange", ruta);
document.addEventListener("DOMContentLoaded", ruta);
document.addEventListener("keydown", e => {
  if (!teclas || e.target.matches("textarea, input, select") || e.ctrlKey || e.metaKey || e.altKey) return;
  const f = teclas[e.key.toLowerCase()] || teclas[e.code];
  if (f) { e.preventDefault(); f(); }
});

/* ---- piezas comunes ------------------------------------------------------ */

function cabecera(eyebrow, titulo, texto, acciones = "") {
  return `<div class="eyebrow"><span class="status-dot"></span>${esc(eyebrow)}</div>
    <div class="page-heading"><div><h1>${esc(titulo)}</h1><p>${texto}</p></div><div class="actions">${acciones}</div></div>`;
}

function stat(etiqueta, valor, unidad, icono, pie, acento = false) {
  return `<div class="stat"><div class="stat-label">${esc(etiqueta)}<span>${icono}</span></div>
    <div class="stat-value">${esc(valor)}${unidad ? `<small> ${esc(unidad)}</small>` : ""}</div>
    <div class="stat-foot${acento ? " accent" : ""}">${esc(pie)}</div></div>`;
}

function vacio(simbolo, titulo, texto, comando = "") {
  return `<div class="panel"><div class="empty"><div class="empty-symbol">${simbolo}</div><h2>${esc(titulo)}</h2>
    <p>${texto}</p>${comando ? `<pre class="command">${esc(comando)}</pre>` : ""}</div></div>`;
}

function tablaDatos(cabeceras, filas) {
  return `<details class="tabla"><summary>Ver como tabla</summary><div class="table-wrap"><table>
    <thead><tr>${cabeceras.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${filas.map(f => `<tr>${f.map(c => `<td class="num">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div></details>`;
}

const PY = "ml/.venv/bin/python -m ml";

/* ======================================================================== */
/*  Resumen                                                                  */
/* ======================================================================== */

async function pResumen(el) {
  const asaltos = S.corridas.reduce((s, c) => s + (c.config.generaciones || 0) * (c.config.asaltos_por_generacion || 0), 0);
  const lam = S.recompensa ? S.recompensa.lambda_sugerida : 0;
  const ult = S.corridas.find(c => c.terminada);
  const ultVer = S.versiones[S.versiones.length - 1];
  el.innerHTML = cabecera("APRENDIZAJE POR REFUERZO · RETROALIMENTACIÓN HUMANA", "Tú votas, la GPU aprende.",
    "Cada entrenamiento prueba cientos de variantes del algoritmo a la vez en la RTX 5070. Tus votos entre repeticiones enseñan a un modelo de recompensa qué conducta prefieres, y ese modelo pesa en el entrenamiento siguiente.",
    `<a class="button primary" href="#votar">Votar comparaciones (${S.pares.pendientes})</a>`) +
    `<section class="stats">
      ${stat("Versiones en la bitácora", S.versiones.length, "", "⑂", ultVer ? "última: " + ultVer.version : "—")}
      ${stat("Candidatos entrenados", S.candidatos.length, "", "◎", S.candidatos.length ? "último: " + S.candidatos[S.candidatos.length - 1].id : "ninguno todavía")}
      ${stat("Tus votos", S.votos, "", "⇄", "peso humano λ = " + num(lam), true)}
      ${stat("Asaltos simulados", compacto(asaltos), "", "▦", "en " + S.corridas.length + " entrenamiento(s)")}
    </section>
    <div class="grid-main">
      <section class="panel"><div class="panel-head"><div><h2>Último entrenamiento</h2><p>${ult ? esc(ult.id) : "todavía no hay ninguno"}</p></div>
        ${ult ? `<a class="pill" href="#entrenamiento/${esc(ult.id)}">VER CURVA</a>` : ""}</div>
        <div id="ult-entreno">${ult ? '<div class="loading">Cargando…</div>' : `<div class="pad"><p>Lanza el primero con</p><pre class="command">${PY} entrenar</pre></div>`}</div>
      </section>
      <section class="panel"><div class="panel-head"><div><h2>El ciclo</h2><p>Una vuelta: simular, votar, reentrenar</p></div><span class="pill neutral">RLHF</span></div>
        <div class="roadmap">
          ${paso(1, S.corridas.length > 0, false, "Entrenar en la GPU", "CMA-ES prueba variantes de params.h contra el banco de rivales, con las colocaciones del reglamento.", "entrenar")}
          ${paso(2, S.votos > 0 && !S.pares.pendientes, S.pares.pendientes > 0, "Votar repeticiones", S.pares.pendientes ? `${S.pares.pendientes} comparaciones esperan tu voto.` : "El mismo asalto jugado por dos algoritmos: eliges el mejor.", "")}
          ${paso(3, !!S.recompensa, false, "Reentrenar la recompensa", "Un conjunto de redes aprende de tus votos qué rasgos prefieres.", "recompensa")}
          ${paso(4, false, false, "Siguiente vuelta", "El entrenamiento suma tu recompensa a la aptitud simulada.", "ciclo")}
        </div>
        <div class="panel-note">${S.validacion ? "↗ Simulador de GPU validado contra el banco nativo en C: mismas estadísticas en las 96 comparaciones." : "Simulador sin validar: ejecuta " + esc(PY) + " validar"}</div>
      </section>
    </div>`;
  if (ult) {
    const c = await api("/api/corrida/" + encodeURIComponent(ult.id));
    const r = c.resumen;
    $("#ult-entreno").innerHTML = `<div class="specs">
      <div class="spec-line"><span>Campeón</span><strong>${esc(r.candidato)} · desde ${esc(r.config.desde)}</strong></div>
      <div class="spec-line"><span>Combate ganado (media contra el banco)</span><strong>${pct(r.base.combate_gana, 1)} → ${pct(r.campeon.combate_gana, 1)}</strong></div>
      <div class="spec-line"><span>Auto-salidas por asalto</span><strong>${pct(r.base.auto_salidas, 1)} → ${pct(r.campeon.auto_salidas, 1)}</strong></div>
      <div class="spec-line"><span>Generaciones × candidatos</span><strong>${r.config.generaciones} × ${r.config.poblacion} · ${Math.round(r.segundos)} s</strong></div>
      <div class="spec-line"><span>Mayores cambios</span><strong>${r.cambios.slice(0, 4).map(ch => esc(ch.nombre)).join(", ") || "—"}</strong></div>
    </div>`;
  }
}

function paso(n, hecho, actual, titulo, texto, cmd) {
  return `<div class="step${hecho ? " done" : ""}${actual ? " current" : ""}"><span class="step-number">${hecho ? "✓" : "0" + n}</span>
    ${cmd ? `<span class="phase">${esc(cmd)}</span>` : ""}<h3>${esc(titulo)}</h3><p>${esc(texto)}</p></div>`;
}

/* ======================================================================== */
/*  Votar                                                                    */
/* ======================================================================== */

async function pVotar(el) {
  const pares = await api("/api/pares");
  el.innerHTML = cabecera("RETROALIMENTACIÓN HUMANA", "¿Cuál pelea mejor?",
    "El mismo asalto (mismo rival, misma colocación y mismo sorteo) jugado por dos algoritmos. El verde es el algoritmo que se juzga; el rojo, su rival. No sabrás cuál es cuál hasta votar.") +
    `<div id="zona-voto"></div>`;
  const zona = $("#zona-voto");
  if (!pares.length) {
    zona.innerHTML = vacio("⇄", "No hay comparaciones pendientes", "Genera más al terminar un entrenamiento: el campeón contra la versión de la que partió.", `${PY} pares c-001 v0.3.0`);
    return;
  }
  let idx = 0;
  const elegidas = new Set();

  async function siguiente() {
    pararReproduccion();
    if (idx >= pares.length) {
      zona.innerHTML = vacio("✓", "Has votado todas las comparaciones", "Reentrena el modelo de recompensa para que tus votos cuenten en el próximo entrenamiento.", `${PY} recompensa\n${PY} ciclo`);
      teclas = null;
      return;
    }
    const par = pares[idx];
    const [A, B] = await Promise.all([api("/api/clip/" + par.a), api("/api/clip/" + par.b)]);
    elegidas.clear();
    zona.innerHTML = `
      <div class="toolbar"><span class="pill neutral">${esc(par.id)}</span>
        <span class="muted-s">rival <b>${esc(par.rival)}</b> · colocación <b>${esc(COLOCACION_ES[par.colocacion] || par.colocacion)}</b></span>
        <span class="progreso">${idx + 1} de ${pares.length}</span></div>
      <div class="ab">
        ${panelClip("A")}${panelClip("B")}
      </div>
      <div class="controles">
        <button id="play" type="button">Pausa<kbd>espacio</kbd></button>
        <button id="reinicio" type="button" class="compact">Desde el inicio<kbd>R</kbd></button>
        <select id="vel" aria-label="Velocidad"><option value="0.25">0,25×</option><option value="0.5">0,5×</option><option value="1" selected>1×</option><option value="2">2×</option></select>
        <input id="barra" type="range" min="0" max="1000" value="0" aria-label="Tiempo de la repetición">
        <span id="reloj" class="progreso">0,00 s</span>
      </div>
      <section class="panel voto-panel">
        <div class="votos">
          <button type="button" class="primary" data-voto="a">A es mejor<kbd>A</kbd></button>
          <button type="button" data-voto="igual">Igual de buenos<kbd>I</kbd></button>
          <button type="button" class="primary" data-voto="b">B es mejor<kbd>B</kbd></button>
          <button type="button" data-voto="ninguno">Los dos mal<kbd>N</kbd></button>
        </div>
        <div class="chips" id="chips">${S.etiquetas.map(t => `<button type="button" aria-pressed="false" data-etq="${esc(t)}">${esc(t)}</button>`).join("")}</div>
        <label>Nota (opcional): qué te hizo decidir<textarea id="nota" maxlength="2000" placeholder="Por ejemplo: A se queda en el centro y espera; B va a por él aunque arriesga el borde."></textarea></label>
        <button type="button" id="saltar" class="compact">Saltar esta comparación</button>
      </section>`;

    const vistas = [new Vista($("#lienzo-A"), A, $("#pie-A")), new Vista($("#lienzo-B"), B, $("#pie-B"))];
    const barra = $("#barra"), reloj = $("#reloj"), play = $("#play");
    reproductor = crearReproductor(vistas, R => {
      barra.value = String(Math.round(R.t / R.dur * 1000));
      reloj.textContent = num(R.t) + " s";
      play.firstChild.textContent = R.jugando ? "Pausa" : "Reproducir";
    });
    const alternar = () => { const R = reproductor; if (R.t >= R.dur) R.t = 0; R.jugando = !R.jugando; };
    const reiniciar = () => { reproductor.t = 0; reproductor.jugando = true; };
    play.onclick = alternar;
    $("#reinicio").onclick = reiniciar;
    $("#vel").onchange = e => { reproductor.vel = Number(e.target.value); };
    barra.oninput = () => { reproductor.t = Number(barra.value) / 1000 * reproductor.dur; reproductor.jugando = false; };
    $("#chips").onclick = e => {
      const b = e.target.closest("button[data-etq]");
      if (!b) return;
      const on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(on));
      on ? elegidas.add(b.dataset.etq) : elegidas.delete(b.dataset.etq);
    };
    const votar = async pref => {
      try {
        await api("/api/voto", {par: par.id, preferencia: pref, etiquetas: [...elegidas], nota: $("#nota").value});
        toast(`Voto guardado. A era ${A.algoritmo}; B era ${B.algoritmo}.`);
        S.pares.pendientes = Math.max(0, S.pares.pendientes - 1);
        $("#nav-pendientes").textContent = S.pares.pendientes;
        idx++;
        siguiente();
      } catch (e) { toast(e.message, true); }
    };
    zona.querySelectorAll("[data-voto]").forEach(b => { b.onclick = () => votar(b.dataset.voto); });
    $("#saltar").onclick = () => { idx++; siguiente(); };
    teclas = {a: () => votar("a"), b: () => votar("b"), i: () => votar("igual"), n: () => votar("ninguno"),
      r: reiniciar, Space: alternar};
  }
  siguiente();
}

function panelClip(letra) {
  return `<section class="panel"><div class="clip-cab"><span class="clip-letra">${letra}</span>
    <span class="leyenda"><span><i class="punto" id="sw-${letra}-r"></i>algoritmo</span><span><i class="punto" id="sw-${letra}-f"></i>rival</span></span></div>
    <canvas class="dohyo" id="lienzo-${letra}" aria-label="Repetición ${letra}"></canvas>
    <div class="clip-pie" id="pie-${letra}">—</div></section>`;
}

/* ---- repeticion en el dohyo ---------------------------------------------- */

const COL = {robot: "#c7eb1f", rival: "#e62e38", dohyo: "#141819", banda: "#e9ece6", fondo: "#0f171a", pala: "#d7dade"};

class Vista {
  constructor(canvas, clip, pie) {
    this.c = canvas; this.clip = clip; this.pie = pie;
    this.ctx = canvas.getContext("2d");
    const fila = canvas.closest("section");
    fila.querySelectorAll("i.punto").forEach((i, k) => { i.style.background = k ? COL.rival : COL.robot; });
  }
  get dur() { return this.clip.frames.length * this.clip.dt; }
  dibuja(t) {
    const dpr = window.devicePixelRatio || 1;
    const W = Math.round(this.c.clientWidth * dpr);
    if (this.c.width !== W) { this.c.width = W; this.c.height = W; }
    const F = this.clip.frames, n = F.length;
    const i = Math.min(n - 1, Math.floor(t / this.clip.dt));
    dibujaDohyo(this.ctx, W, F, i, dpr);
    const f = F[i], fin = F.findIndex(x => x[9] === 1);
    if (fin >= 0 && i >= fin) {
      const r = this.clip.resultado, txt = r > 0 ? "Gana" : r < 0 ? "Pierde" : "Empate";
      this.pie.textContent = `${txt}: ${this.clip.razon} a los ${num(this.clip.t_fin)} s`;
    } else {
      this.pie.textContent = `t ${num(i * this.clip.dt)} s · ${ESTADO_ES[ESTADOS[f[8]]] || "—"} · motores ${num(f[6])} / ${num(f[7])}`;
    }
  }
}

function dibujaDohyo(ctx, W, F, i, dpr) {
  const e = W / 0.92, c = W / 2;
  const X = x => c + x * e, Y = y => c - y * e;
  ctx.fillStyle = COL.fondo; ctx.fillRect(0, 0, W, W);
  ctx.beginPath(); ctx.arc(c, c, 0.385 * e, 0, 2 * Math.PI); ctx.fillStyle = COL.banda; ctx.fill();
  ctx.beginPath(); ctx.arc(c, c, 0.360 * e, 0, 2 * Math.PI); ctx.fillStyle = COL.dohyo; ctx.fill();
  ctx.strokeStyle = "rgba(233,236,230,.13)"; ctx.lineWidth = dpr;
  ctx.beginPath(); ctx.moveTo(X(-0.36), c); ctx.lineTo(X(0.36), c); ctx.moveTo(c, Y(-0.36)); ctx.lineTo(c, Y(0.36)); ctx.stroke();

  const estela = (ix, iy, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2 * dpr; ctx.lineJoin = "round"; ctx.beginPath();
    for (let k = Math.max(0, i - 60); k <= i; k++) { const p = F[k]; k === Math.max(0, i - 60) ? ctx.moveTo(X(p[ix]), Y(p[iy])) : ctx.lineTo(X(p[ix]), Y(p[iy])); }
    ctx.stroke();
  };
  estela(3, 4, "rgba(230,46,56,.35)");
  estela(0, 1, "rgba(199,235,31,.35)");
  const f = F[i];
  robot(ctx, X(f[3]), Y(f[4]), f[5], COL.rival, e);
  robot(ctx, X(f[0]), Y(f[1]), f[2], COL.robot, e);
}

function robot(ctx, x, y, th, color, e) {
  const h = 0.05 * e;
  ctx.save(); ctx.translate(x, y); ctx.rotate(-th);
  ctx.fillStyle = color; ctx.fillRect(-h, -h, 2 * h, 2 * h);
  ctx.fillStyle = COL.pala; ctx.fillRect(h * 0.72, -h, h * 0.28, 2 * h);          // pala
  ctx.fillStyle = "rgba(0,0,0,.55)";
  ctx.beginPath(); ctx.moveTo(h * 0.45, 0); ctx.lineTo(-h * 0.35, -h * 0.42); ctx.lineTo(-h * 0.35, h * 0.42); ctx.closePath(); ctx.fill();
  ctx.restore();
}

function crearReproductor(vistas, alTic) {
  const R = {t: 0, vel: 1, jugando: true, raf: 0, dur: Math.max(...vistas.map(v => v.dur)), ultimo: null};
  const tic = ts => {
    if (R.ultimo != null && R.jugando) {
      R.t = Math.min(R.dur, R.t + (ts - R.ultimo) / 1000 * R.vel);
      if (R.t >= R.dur) R.jugando = false;
    }
    R.ultimo = ts;
    vistas.forEach(v => v.dibuja(R.t));
    alTic(R);
    R.raf = requestAnimationFrame(tic);
  };
  R.raf = requestAnimationFrame(tic);
  return R;
}

function pararReproduccion() {
  if (reproductor) { cancelAnimationFrame(reproductor.raf); reproductor = null; }
}

/* ======================================================================== */
/*  Versiones (los cambios de los algoritmos)                                */
/* ======================================================================== */

async function pVersiones(el, v) {
  if (v) return detalleVersion(el, v);
  const filas = S.versiones.slice().reverse().map(x => {
    const m = x.metrics || {};
    return `<tr data-v="${esc(x.version)}"><td class="num"><a href="#versiones/${esc(x.version)}">${esc(x.version)}</a></td>
      <td><span class="pill neutral">${esc(x.kind)}</span></td><td>${esc(x.title)}<small>${fecha(x.created_at)}</small></td>
      <td>${esc(x.verdict || "pendiente")}</td><td class="num">${m.rounds ? pct(m.win_rate, 1) : "—"}</td></tr>`;
  }).join("");
  const cands = S.candidatos.slice().reverse().map(c => `<tr><td class="num">${esc(c.id)}</td><td class="num">${esc(c.base)}</td>
      <td class="num">${esc(c.origen)}</td><td class="num">${pct(c.combate_gana, 1)}</td><td class="num">${num(c.aptitud, 3)}</td></tr>`).join("");
  el.innerHTML = cabecera("BITÁCORA DE ALGORITMOS", "Cambios de los algoritmos",
    "Cada versión registra qué cambió, por qué y qué dio en el ring. Los candidatos son propuestas del entrenamiento: pasan a versión cuando se exportan a params.h, se miden y se registran con gnver.") +
    `<section class="panel"><div class="panel-head"><div><h2>Versiones registradas</h2><p>versions/manifest.json · win rate en el banco nativo, modo de siempre</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>VERSIÓN</th><th>TIPO</th><th>TÍTULO</th><th>VEREDICTO</th><th>WIN RATE</th></tr></thead><tbody>${filas}</tbody></table></div></section>
    <div class="sub-head"><h2>Candidatos del entrenamiento</h2><p>combate ganado de media contra el banco de rivales, modo robusto</p></div>
    ${S.candidatos.length ? `<section class="panel"><div class="table-wrap"><table><thead><tr><th>CANDIDATO</th><th>DESDE</th><th>ENTRENAMIENTO</th><th>COMBATE GANADO</th><th>APTITUD</th></tr></thead><tbody>${cands}</tbody></table></div></section>`
      : vacio("◎", "Sin candidatos", "Aparecen al terminar un entrenamiento.", `${PY} entrenar`)}`;
}

async function detalleVersion(el, v) {
  const x = await api("/api/version/" + encodeURIComponent(v));
  const campos = [["Qué cambió", x.summary], ["Por qué", x.rationale], ["Hipótesis", x.hypothesis],
    ["Efecto esperado y medido", x.expected_effect], ["Riesgos", x.risks], ["Nota para el robot real", x.notes_real_robot]].filter(c => c[1]);
  const diff = (x.diff || "").split("\n").map(l => {
    const k = l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "remove" : "context";
    return `<span class="${k}">${esc(l) || " "}</span>`;
  }).join("");
  el.innerHTML = cabecera("VERSIÓN " + x.version + " · " + x.kind.toUpperCase(), x.title,
    `Iteración ${x.iteration} · ${fecha(x.created_at)} · ${esc(x.author)}${x.parent ? " · deriva de " + esc(x.parent) : ""}`,
    `<a class="button" href="#versiones">← Todas las versiones</a>`) +
    `<div class="stack">
      <section class="panel">${campos.map(c => `<div class="panel-head"><h3>${esc(c[0])}</h3></div><div class="detail-note">${esc(c[1])}</div>`).join("")}</section>
      ${(x.params_changed || []).length ? `<section class="panel"><div class="panel-head"><h2>Parámetros tocados</h2></div><div class="table-wrap"><table>
        <thead><tr><th>PARÁMETRO</th><th>ANTES</th><th>DESPUÉS</th><th>MOTIVO</th></tr></thead><tbody>
        ${x.params_changed.map(p => `<tr><td class="num">${esc(p.name)}</td><td class="num">${esc(p.from)}</td><td class="num">${esc(p.to)}</td><td>${esc(p.reason)}</td></tr>`).join("")}
        </tbody></table></div></section>` : ""}
      <section class="panel"><div class="panel-head"><div><h2>Cambio de código</h2><p>+${x.diff_stat.added} / −${x.diff_stat.removed} en ${x.diff_stat.files} fichero(s)</p></div></div>
        <pre class="diff">${diff || '<span class="context">Sin cambios de código.</span>'}</pre></section>
    </div>`;
}

/* ======================================================================== */
/*  Entrenamiento                                                            */
/* ======================================================================== */

async function pEntrenamiento(el, rid) {
  if (!S.corridas.length) {
    el.innerHTML = cabecera("ESTRATEGIA EVOLUTIVA EN LA GPU", "Entrenamientos", "Todavía no hay ninguno.") +
      vacio("◎", "Sin entrenamientos", "Cada generación juega la población entera en una sola pasada de la GPU.", `${PY} entrenar`);
    return;
  }
  rid = rid || S.corridas[0].id;
  const filas = S.corridas.map(c => `<tr><td class="num"><a href="#entrenamiento/${esc(c.id)}">${esc(c.id)}</a></td>
    <td class="num">${esc(c.config.desde)}</td><td class="num">${c.config.generaciones} × ${c.config.poblacion}</td>
    <td class="num">${num(c.config.lambda_humano)}</td>
    <td class="num">${c.terminada ? `${pct(c.base.combate_gana, 1)} → ${pct(c.campeon.combate_gana, 1)}` : "en curso"}</td>
    <td class="num">${c.terminada ? esc(c.campeon.candidato) : "—"}</td></tr>`).join("");
  el.innerHTML = cabecera("ESTRATEGIA EVOLUTIVA EN LA GPU", "Entrenamientos",
    "CMA-ES sobre los parámetros de la máquina de estados. Cada punto de la curva es una generación entera jugada en la RTX 5070 contra el banco de rivales, en las tres colocaciones del reglamento.") +
    `<section class="panel"><div class="table-wrap"><table><thead><tr><th>ENTRENAMIENTO</th><th>DESDE</th><th>GEN × POBLACIÓN</th><th>λ HUMANO</th><th>COMBATE GANADO</th><th>CAMPEÓN</th></tr></thead>
      <tbody>${filas}</tbody></table></div></section><div id="detalle-corrida" class="stack"><div class="loading">Cargando…</div></div>`;
  const c = await api("/api/corrida/" + encodeURIComponent(rid));
  const log = c.log;
  const det = $("#detalle-corrida");
  det.innerHTML = `<div class="sub-head"><h2>${esc(c.id)}</h2><p>${c.config.asaltos_por_generacion.toLocaleString("es-MX")} asaltos por generación · rivales: ${esc(c.config.rivales.join(", "))}</p></div>
    <section class="panel"><div class="panel-head"><div><h2>Combate ganado por generación</h2><p>Probabilidad de ganar el combate a tres rondas, media sobre el banco de rivales</p></div></div>
      <div class="pad"><div class="leyenda"><span><i class="sw-1"></i>mejor candidato de la generación</span><span><i class="sw-2"></i>media de la población</span></div>
      <div id="curva"></div></div>
      ${tablaDatos(["Generación", "Mejor", "Media", "σ"], log.map(f => [f.gen, pct(f.combate_gana_max, 1), pct(f.combate_gana_media, 1), num(f.sigma, 3)]))}
    </section>
    <div id="res-corrida"></div>`;
  graficaLineas($("#curva"), {
    xs: log.map(f => f.gen), etiqueta: "Combate ganado por generación",
    series: [{nombre: "mejor", clase: "sw-1", color: "var(--viz-1)", valores: log.map(f => f.combate_gana_max)},
             {nombre: "media", clase: "sw-2", color: "var(--viz-2)", valores: log.map(f => f.combate_gana_media)}],
    yMin: 0, yMax: 1, yFmt: v => Math.round(v * 100) + " %", xFmt: v => "gen " + v,
  });
  const r = c.resumen;
  if (!r) { $("#res-corrida").innerHTML = `<p class="muted-s">El entrenamiento sigue en curso.</p>`; return; }
  const porRival = r.campeon.rivales.map((f, k) => {
    const b = r.base.rivales[k];
    return `<tr><td class="num">${esc(f.nombre)}</td><td class="num">${pct(b.combate?.gana, 1)}</td><td class="num">${pct(f.combate?.gana, 1)}</td>
      <td class="num">${pct(b.colocaciones.espalda.gana)} → ${pct(f.colocaciones.espalda.gana)}</td></tr>`;
  }).join("");
  $("#res-corrida").innerHTML = `<div class="two-col">
    <section class="panel"><div class="panel-head"><div><h2>${esc(r.candidato)} contra ${esc(r.config.desde)}</h2><p>48 asaltos por rival y colocación, modo robusto</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>RIVAL</th><th>COMBATE ${esc(r.config.desde)}</th><th>COMBATE ${esc(r.candidato)}</th><th>DE ESPALDAS</th></tr></thead><tbody>${porRival}</tbody></table></div></section>
    <section class="panel"><div class="panel-head"><div><h2>Parámetros que cambió</h2><p>ordenados por el tamaño del cambio respecto a su rango</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>PARÁMETRO</th><th>ANTES</th><th>DESPUÉS</th></tr></thead><tbody>
      ${r.cambios.slice(0, 14).map(ch => `<tr><td class="num">${esc(ch.nombre)}</td><td class="num">${esc(fmtParam(ch.de))}</td><td class="num">${esc(fmtParam(ch.a))}</td></tr>`).join("")}
      </tbody></table></div></section></div>`;
}

const fmtParam = v => typeof v === "number" && !Number.isInteger(v) ? v.toFixed(2).replace(".", ",") : String(v);

/* ======================================================================== */
/*  Direccion                                                                */
/* ======================================================================== */

async function pDireccion(el) {
  const d = S.liga && S.liga.direccion, h = S.recompensa;
  el.innerHTML = cabecera("HACIA DÓNDE SE INCLINAN LAS MEJORES VERSIONES", "Dirección de mejora",
    "Dos brújulas. La de la GPU sale de un modelo sustituto entrenado con todas las variantes que probó el entrenamiento: dice qué parámetros suben la probabilidad de ganar. La tuya sale del modelo de recompensa: dice qué conductas premian tus votos.") +
    `<div class="stack">
      <section class="panel"><div class="panel-head"><div><h2>La GPU se inclina hacia…</h2>
        <p>${d ? `${d.muestras.toLocaleString("es-MX")} variantes probadas · el sustituto explica el ${Math.round(Math.max(0, d.r2) * 100)} % de la varianza fuera de muestra` : "sin datos"}</p></div>
        <span class="leyenda"><span><i class="punto sw-pos"></i>subir</span><span><i class="punto sw-neg"></i>bajar</span></span></div>
        ${d ? `<div class="pad" id="barras-gpu"></div>${tablaDatos(["Parámetro", "Sentido", "Importancia", "Ganancia por paso de 5 %"], d.parametros.map(p => [p.nombre, p.sentido, num(p.importancia, 3), num(p.ganancia_por_paso, 3)]))}`
            : `<div class="pad"><p>Ejecuta la liga después de entrenar:</p><pre class="command">${PY} liga</pre></div>`}
      </section>
      <section class="panel"><div class="panel-head"><div><h2>Lo que tú prefieres</h2>
        <p>${h ? `${h.n_datos} votos · acierto en votos que no vio ${h.precision_validacion_cruzada == null ? "sin medir (pocos votos)" : pct(h.precision_validacion_cruzada)} · peso en el entrenamiento λ = ${num(h.lambda_sugerida)}` : "todavía no hay votos"}</p></div>
        <span class="leyenda"><span><i class="punto sw-pos"></i>te gusta más</span><span><i class="punto sw-neg"></i>te gusta menos</span></span></div>
        ${h ? `<div class="pad" id="barras-humano"></div>${tablaDatos(["Rasgo", "Pendiente", "Peso lineal"], h.rasgos.map(r => [RASGO_ES[r.nombre] || r.nombre, num(r.pendiente, 3), num(r.peso_lineal, 3)]))}`
            : `<div class="pad"><p>Vota comparaciones y reentrena:</p><pre class="command">${PY} recompensa</pre></div>`}
      </section>
    </div>`;
  if (d) barrasDireccion($("#barras-gpu"), d.parametros.slice(0, 12));
  if (h) barrasDivergentes($("#barras-humano"), h.rasgos.map(r => ({nombre: RASGO_ES[r.nombre] || r.nombre, valor: r.pendiente}))
    .sort((a, b) => Math.abs(b.valor) - Math.abs(a.valor)));
}

/* ======================================================================== */
/*  Liga                                                                     */
/* ======================================================================== */

async function pLiga(el) {
  const L = S.liga;
  if (!L) {
    el.innerHTML = cabecera("TODOS CONTRA TODOS", "Liga", "Todavía no hay liga.") + vacio("♜", "Sin liga", "Enfrenta en la GPU a todas las versiones y candidatos.", `${PY} liga`);
    return;
  }
  const filas = L.algoritmos.map((a, k) => `<tr><td class="num">${k + 1}</td><td class="num">${esc(a.id)}</td><td>${esc(a.tipo)}</td>
    <td class="num">${Math.round(a.elo)}</td><td class="num">${a.elo_humano == null ? "—" : Math.round(a.elo_humano)}</td><td class="num">${pct(a.gana_combate_medio, 1)}</td></tr>`).join("");
  el.innerHTML = cabecera("TODOS CONTRA TODOS EN LA GPU", "Liga",
    `Cada algoritmo pelea contra todos los demás en las tres colocaciones del reglamento (${L.rondas} asaltos por colocación). El Elo sale de un modelo de Bradley-Terry; el Elo humano, solo de tus votos. Actualizada ${fecha(L.fecha)}.`) +
    `<div class="stack"><section class="panel"><div class="table-wrap"><table><thead><tr><th>#</th><th>ALGORITMO</th><th>TIPO</th><th>ELO</th><th>ELO HUMANO</th><th>GANA COMBATE</th></tr></thead><tbody>${filas}</tbody></table></div></section>
    <section class="panel"><div class="panel-head"><div><h2>Quién gana a quién</h2><p>Fila: el algoritmo al mando de Gelatina. Columna: su rival. Probabilidad de ganar el combate.</p></div>
      <span class="leyenda"><span><i class="punto sw-pos"></i>gana</span><span><i class="punto sw-neg"></i>pierde</span></span></div>
      <div class="pad" id="mapa"></div>
      ${tablaDatos(["Algoritmo", ...L.nombres], L.nombres.map((n, i) => [n, ...L.matriz_combate[i].map((v, j) => i === j ? "—" : pct(v))]))}
    </section></div>`;
  mapaCalor($("#mapa"), L.nombres, L.matriz_combate);
}

/* ======================================================================== */
/*  Tareas                                                                   */
/* ======================================================================== */

async function pTareas(el) {
  const T = S.tareas || [];
  const orden = [["en_curso", "En curso"], ["pendiente", "Pendientes"], ["bloqueada", "Bloqueadas"], ["hecha", "Hechas"], ["descartada", "Descartadas"]];
  const fila = t => `<div class="tarea"><span class="num${t.padre ? " sub" : ""}">${esc(t.id)}</span>
    <div${t.padre ? ' class="sub"' : ""}><h3>${esc(t.texto)}</h3>${t.criterio ? `<p>Criterio: ${esc(t.criterio)}</p>` : ""}
      ${t.evidencia.length ? `<p>Evidencia: ${esc(t.evidencia[t.evidencia.length - 1].texto)}</p>` : ""}</div>
    <span class="pill${t.estado === "hecha" ? "" : " neutral"}">${esc(t.responsable)} · ${esc(t.prioridad)}</span></div>`;
  el.innerHTML = cabecera("CLAUDE/TAREAS", "Tareas",
    "El tablero de Tareas/tareas.json. Las tareas nuevas se escriben en Tareas/tareas.txt y entran con python3 Tareas/tareas.py importar.") +
    `<div class="stack">${orden.map(([e, titulo]) => {
      const ts = T.filter(t => t.estado === e);
      return ts.length ? `<section class="panel"><div class="panel-head"><h2>${titulo}</h2><span class="pill neutral">${ts.length}</span></div>${ts.map(fila).join("")}</section>` : "";
    }).join("")}</div>`;
}

/* ======================================================================== */
/*  Graficas (SVG, con capa de hover y tabla gemela)                         */
/* ======================================================================== */

function coordSVG(svg, ev, W) {
  const r = svg.getBoundingClientRect();
  return {x: (ev.clientX - r.left) * W / r.width, y: (ev.clientY - r.top) * W / r.width};
}

function graficaLineas(cont, {series, xs, yMin, yMax, yFmt, xFmt, etiqueta}) {
  const W = 880, H = 290, ml = 50, mr = 128, mt = 14, mb = 34, iw = W - ml - mr, ih = H - mt - mb, n = xs.length;
  const px = i => ml + (n === 1 ? iw / 2 : i / (n - 1) * iw);
  const py = v => mt + ih - (v - yMin) / (yMax - yMin) * ih;
  let g = "";
  for (let k = 0; k <= 4; k++) {
    const v = yMin + k / 4 * (yMax - yMin), y = py(v).toFixed(1);
    g += `<line x1="${ml}" x2="${ml + iw}" y1="${y}" y2="${y}" stroke="${k ? "var(--grid)" : "var(--axis)"}" stroke-width="1"/>
          <text x="${ml - 8}" y="${+y + 4}" text-anchor="end">${esc(yFmt(v))}</text>`;
  }
  const pasoX = Math.max(1, Math.ceil(n / 8));
  for (let i = 0; i < n; i += pasoX) g += `<text x="${px(i).toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(xs[i])}</text>`;
  const finales = series.map(s => py(s.valores[n - 1]));
  const chocan = finales.length > 1 && Math.abs(finales[0] - finales[1]) < 16;
  series.forEach((s, k) => {
    const d = s.valores.map((v, i) => (i ? "L" : "M") + px(i).toFixed(1) + " " + py(v).toFixed(1)).join(" ");
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    g += `<circle cx="${px(n - 1).toFixed(1)}" cy="${finales[k].toFixed(1)}" r="4.5" fill="${s.color}" stroke="var(--panel)" stroke-width="2"/>`;
    if (!chocan) g += `<text class="suave" x="${px(n - 1) + 12}" y="${finales[k] + 4}">${esc(s.nombre)} ${esc(yFmt(s.valores[n - 1]))}</text>`;
  });
  g += `<line class="cruz" x1="0" x2="0" y1="${mt}" y2="${mt + ih}" stroke="var(--axis)" stroke-width="1" visibility="hidden"/>`;
  series.forEach((s, k) => { g += `<circle class="hp hp${k}" r="4.5" fill="${s.color}" stroke="var(--panel)" stroke-width="2" visibility="hidden"/>`; });
  g += `<rect class="caza" x="${ml}" y="${mt}" width="${iw}" height="${ih}" fill="transparent"/>`;
  cont.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(etiqueta)}">${g}</svg>`;
  const svg = cont.querySelector("svg"), cruz = svg.querySelector(".cruz");
  const caza = svg.querySelector(".caza");
  caza.addEventListener("mousemove", ev => {
    const {x} = coordSVG(svg, ev, W);
    const i = Math.max(0, Math.min(n - 1, Math.round((x - ml) / iw * (n - 1))));
    cruz.setAttribute("x1", px(i)); cruz.setAttribute("x2", px(i)); cruz.setAttribute("visibility", "visible");
    series.forEach((s, k) => { const c = svg.querySelector(".hp" + k); c.setAttribute("cx", px(i)); c.setAttribute("cy", py(s.valores[i])); c.setAttribute("visibility", "visible"); });
    tip.mostrar(`<b>${esc(xFmt(xs[i]))}</b>` + series.map(s => `<div class="fila"><i class="${s.clase}"></i>${esc(s.nombre)}: ${esc(yFmt(s.valores[i]))}</div>`).join(""), ev.clientX, ev.clientY);
  });
  caza.addEventListener("mouseleave", () => {
    cruz.setAttribute("visibility", "hidden");
    svg.querySelectorAll(".hp").forEach(c => c.setAttribute("visibility", "hidden"));
    tip.ocultar();
  });
}

function barraDerecha(x0, y, w, h) {
  const r = Math.min(4, w / 2, h / 2);
  return `M${x0},${y} h${Math.max(0, w - r)} a${r},${r} 0 0 1 ${r},${r} v${h - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-Math.max(0, w - r)} z`;
}
function barraIzquierda(x0, y, w, h) {
  const r = Math.min(4, w / 2, h / 2);
  return `M${x0},${y} h${-Math.max(0, w - r)} a${r},${r} 0 0 0 ${-r},${r} v${h - 2 * r} a${r},${r} 0 0 0 ${r},${r} h${Math.max(0, w - r)} z`;
}

function barrasDireccion(cont, filas) {
  const W = 880, fila = 30, h = 14, ml = 200, mr = 150, iw = W - ml - mr, H = filas.length * fila + 6;
  const max = Math.max(...filas.map(f => f.importancia), 1e-9);
  let g = "";
  filas.forEach((f, k) => {
    const y = k * fila + 6, w = Math.max(2, f.importancia / max * iw), sube = f.gradiente > 0;
    g += `<g class="fila-barra" data-k="${k}"><rect x="0" y="${y - 6}" width="${W}" height="${fila}" fill="transparent"/>
      <text class="suave" x="${ml - 12}" y="${y + h - 2}" text-anchor="end">${esc(f.nombre)}</text>
      <path d="${barraDerecha(ml, y, w, h)}" fill="${sube ? "var(--pos)" : "var(--neg)"}"/>
      <text x="${ml + w + 8}" y="${y + h - 2}">${sube ? "subir" : "bajar"} · ${num(f.importancia, 2)}</text></g>`;
  });
  g += `<line x1="${ml}" x2="${ml}" y1="0" y2="${H}" stroke="var(--axis)" stroke-width="1"/>`;
  cont.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Importancia y sentido de cada parámetro">${g}</svg>`;
  cont.querySelectorAll(".fila-barra").forEach(el => {
    const f = filas[+el.dataset.k];
    el.addEventListener("mousemove", ev => tip.mostrar(`<b>${esc(f.nombre)}</b><div>conviene ${f.gradiente > 0 ? "subirlo" : "bajarlo"}</div>
      <div>importancia ${num(f.importancia, 3)}</div><div>ganancia estimada por un paso del 5 %: ${num(f.ganancia_por_paso, 3)}</div>`, ev.clientX, ev.clientY));
    el.addEventListener("mouseleave", tip.ocultar);
  });
}

function barrasDivergentes(cont, filas) {
  const W = 880, fila = 30, h = 14, ml = 250, mr = 70, iw = W - ml - mr, H = filas.length * fila + 6, c = ml + iw / 2;
  const max = Math.max(...filas.map(f => Math.abs(f.valor)), 1e-9);
  let g = `<line x1="${c}" x2="${c}" y1="0" y2="${H}" stroke="var(--axis)" stroke-width="1"/>`;
  filas.forEach((f, k) => {
    const y = k * fila + 6, w = Math.max(2, Math.abs(f.valor) / max * (iw / 2 - 40)), pos = f.valor >= 0;
    g += `<g class="fila-barra" data-k="${k}"><rect x="0" y="${y - 6}" width="${W}" height="${fila}" fill="transparent"/>
      <text class="suave" x="${ml - 12}" y="${y + h - 2}" text-anchor="end">${esc(f.nombre)}</text>
      <path d="${pos ? barraDerecha(c, y, w, h) : barraIzquierda(c, y, w, h)}" fill="${pos ? "var(--pos)" : "var(--neg)"}"/>
      <text x="${pos ? c + w + 8 : c - w - 8}" y="${y + h - 2}" text-anchor="${pos ? "start" : "end"}">${f.valor > 0 ? "+" : ""}${num(f.valor, 2)}</text></g>`;
  });
  cont.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Qué rasgos premian tus votos">${g}</svg>`;
  cont.querySelectorAll(".fila-barra").forEach(el => {
    const f = filas[+el.dataset.k];
    el.addEventListener("mousemove", ev => tip.mostrar(`<b>${esc(f.nombre)}</b><div>${f.valor >= 0 ? "más de esto sube" : "más de esto baja"} la recompensa</div><div>pendiente ${num(f.valor, 3)} por desviación típica</div>`, ev.clientX, ev.clientY));
    el.addEventListener("mouseleave", tip.ocultar);
  });
}

const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const mezcla = (a, b, t) => { const A = hex(a), B = hex(b); return A.map((v, i) => Math.round(v + (B[i] - v) * t)); };

function mapaCalor(cont, nombres, M) {
  const n = nombres.length, celda = Math.min(72, Math.floor(700 / Math.max(n, 1))), ml = 86, mt = 30, W = ml + n * celda + 4, H = mt + n * celda + 4;
  let g = "";
  nombres.forEach((nm, j) => { g += `<text x="${ml + j * celda + celda / 2}" y="${mt - 10}" text-anchor="middle">${esc(nm)}</text>`; });
  for (let i = 0; i < n; i++) {
    g += `<text class="suave" x="${ml - 10}" y="${mt + i * celda + celda / 2 + 4}" text-anchor="end">${esc(nombres[i])}</text>`;
    for (let j = 0; j < n; j++) {
      const x = ml + j * celda + 1, y = mt + i * celda + 1, s = celda - 2;
      if (i === j) { g += `<rect x="${x}" y="${y}" width="${s}" height="${s}" rx="3" fill="#161f22"/>`; continue; }
      const v = M[i][j], t = Math.max(-1, Math.min(1, (v - 0.5) * 2));
      const rgb = t >= 0 ? mezcla("#383835", "#3987e5", t) : mezcla("#383835", "#e66767", -t);
      const lum = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
      g += `<g class="celda" data-i="${i}" data-j="${j}"><rect x="${x}" y="${y}" width="${s}" height="${s}" rx="3" fill="rgb(${rgb.join(",")})"/>
        ${s >= 40 ? `<text x="${x + s / 2}" y="${y + s / 2 + 4}" text-anchor="middle" fill="${lum > 0.55 ? "#0b0b0b" : "#ffffff"}">${Math.round(v * 100)}</text>` : ""}</g>`;
    }
  }
  cont.innerHTML = `<div class="table-wrap"><svg viewBox="0 0 ${W} ${H}" class="chart mapa" width="${W}" role="img" aria-label="Probabilidad de ganar el combate, todos contra todos">${g}</svg></div>`;
  cont.querySelectorAll(".celda").forEach(el => {
    const i = +el.dataset.i, j = +el.dataset.j;
    el.addEventListener("mousemove", ev => tip.mostrar(`<b>${esc(nombres[i])}</b> contra ${esc(nombres[j])}<div>gana el ${pct(M[i][j])} de los combates</div>`, ev.clientX, ev.clientY));
    el.addEventListener("mouseleave", tip.ocultar);
  });
}
