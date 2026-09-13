const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ver = id => `v${String(id).padStart(4,'0')}`;
const date = value => new Date(value).toLocaleString('es-MX',{dateStyle:'medium',timeStyle:'short'});
const PUBLIC = document.documentElement.dataset.mode === 'public';
const asset = name => PUBLIC ? './'+name : '/'+name;
let state, draft, original, activeFile = 'controller.py', toastTimer;
async function api(path, data) {
  if (PUBLIC) {
    if (data !== undefined) throw new Error('La publicación es de consulta. Registra los cambios en el laboratorio local.');
    if (path.startsWith('/api/diff?')) {
      const query = new URLSearchParams(path.split('?')[1]);
      const [before, after] = await Promise.all(['from','to'].map(key => api('/api/versions/'+query.get(key))));
      return Object.fromEntries(Object.keys(before.files).map(name => [name, lineDiff(before.files[name], after.files[name], `v${before.id}/${name}`, `v${after.id}/${name}`)]));
    }
    path = path === '/api/state' ? './public-data/state.json' : './public-data/versions/'+path.split('/').pop()+'.json';
  }
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'No se pudo completar la solicitud.');
  return value;
}
function lineDiff(before, after, from, to) {
  if (before === after) return '';
  const a = before.match(/[^\n]*\n|[^\n]+$/g) || [], b = after.match(/[^\n]*\n|[^\n]+$/g) || [];
  const lines = [`--- ${from}\n`, `+++ ${to}\n`];
  const emit = (prefix, line) => lines.push(prefix+line+(line.endsWith('\n') ? '' : '\n\\ No newline at end of file\n'));
  if ((a.length+1)*(b.length+1) <= 2_000_000) {
    const width = b.length+1, grid = new Uint32Array((a.length+1)*width);
    for (let i=a.length-1;i>=0;i--) for (let j=b.length-1;j>=0;j--) grid[i*width+j] = a[i]===b[j] ? 1+grid[(i+1)*width+j+1] : Math.max(grid[(i+1)*width+j],grid[i*width+j+1]);
    let i=0,j=0;
    while (i<a.length || j<b.length) {
      if(i<a.length && j<b.length && a[i]===b[j]) {emit(' ',a[i++]);j++;}
      else if(j<b.length && (i===a.length || grid[i*width+j+1]>grid[(i+1)*width+j])) emit('+',b[j++]);
      else emit('-',a[i++]);
    }
  } else {
    // Bound memory for large files; retain the exact changes as one wider hunk.
    let start=0,end=0;
    while(start<a.length && start<b.length && a[start]===b[start]) start++;
    while(end<a.length-start && end<b.length-start && a[a.length-1-end]===b[b.length-1-end]) end++;
    a.slice(0,start).forEach(l=>emit(' ',l));
    a.slice(start,a.length-end).forEach(l=>emit('-',l));
    b.slice(start,b.length-end).forEach(l=>emit('+',l));
    if(end) a.slice(a.length-end).forEach(l=>emit(' ',l));
  }
  return lines.join('');
}
function toast(message, error=false) {
  const el = $('#toast'); el.textContent = message; el.className = error ? 'error' : ''; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, 6500);
}
const heading = (title, description, actions='') => `<div class="eyebrow"><span class="status-dot"></span> PROYECTO / MINI-SUMO 001</div><div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div><div class="actions">${actions}</div></div>`;
const exportButton = `<a class="button" href="${PUBLIC ? './mini-sumo-historial.zip' : '/api/export'}" download="mini-sumo-historial.zip">↓ Exportar historial</a>`;
const robotPanel = () => `<section class="panel"><div class="panel-head"><div><h2>Conoce a tu robot</h2><p>MS–001 / Plataforma mini-sumo</p></div><span class="pill neutral">DISEÑO INICIAL</span></div><div class="robot-stage"><span class="stage-label">VISTA CONCEPTUAL · ISOMÉTRICA</span><img src="${asset('robot.svg')}" alt="Diagrama conceptual del mini-sumo con dos ruedas, cuña frontal y sensores; base de 96 por 96 milímetros."><span class="stage-corner">X / Y / Z &nbsp; · &nbsp; UNIDADES: mm</span></div><div class="robot-meta"><div><small>DIMENSIONES</small><span>96 × 96 mm</span></div><div><small>MASA SIMULADA</small><span>460 / 500 g</span></div><div><small>TRACCIÓN</small><span>Diferencial · 2WD</span></div></div></section>`;

function overview() {
  const latest = state.versions[0];
  return heading('Pequeño robot. Grandes iteraciones.', 'Tu laboratorio para diseñar, simular y evolucionar un mini-sumo.', exportButton + '<a class="button primary" href="#editor">+ Nueva versión</a>') +
  `<div class="stats"><div class="stat"><div class="stat-label">Versiones registradas<span>⑂</span></div><div class="stat-value">${String(state.versions.length).padStart(2,'0')}</div><div class="stat-foot accent">● Historial persistente</div></div><div class="stat"><div class="stat-label">Iteraciones documentadas<span>↻</span></div><div class="stat-value">${String(state.iterations.length).padStart(2,'0')}</div><div class="stat-foot">Cada observación cuenta</div></div><div class="stat"><div class="stat-label">Huella máxima<span>⌗</span></div><div class="stat-value">10 × 10 <small>cm</small></div><div class="stat-foot">96 × 96 mm en el modelo</div></div><div class="stat"><div class="stat-label">Límite de masa<span>⚖</span></div><div class="stat-value">500 <small>g</small></div><div class="stat-foot">40 g de margen en simulación</div></div></div>
  <div class="grid-main">${robotPanel()}<section class="panel"><div class="panel-head"><div><h2>Un paso a la vez</h2><p>La ruta del laboratorio al dohyo</p></div><span class="tag">FASE 01</span></div><div class="roadmap"><div class="step done"><span class="step-number">✓</span><span class="phase">LISTO</span><h3>Preparar el laboratorio</h3><p>Web, versiones y bitácora del proyecto.</p></div><div class="step ${state.validation?.passed && !state.validation.stale ? 'done' : 'current'}"><span class="step-number">${state.validation?.passed && !state.validation.stale ? '✓' : '02'}</span><h3>Construir en Webots</h3><p>Robot, sensores y escenario de simulación.</p></div><div class="step"><span class="step-number">03</span><h3>Desarrollar los algoritmos</h3><p>Un cambio, una versión. Sin perder el recorrido.</p></div><div class="step"><span class="step-number">04</span><h3>Simular, aprender, repetir</h3><p>Contrastar hipótesis antes del robot físico.</p></div></div><div class="panel-note">↗ &nbsp; Objetivo: sacar al rival del ring respetando los límites de tamaño y masa.</div></section></div>
  <div class="section-head"><h2>Última versión</h2><a class="text-link" href="#versions">Ver historial completo ↗</a></div><section class="panel"><a class="version-row" href="#versions/${latest.id}"><span class="version-symbol">⑂</span><div class="version-info"><h3>${esc(latest.title)} <span class="pill">${ver(latest.id)}</span></h3><p>${esc(latest.notes || 'Sin notas adicionales.')}</p></div><span class="hash">${latest.hash.slice(0,8)}</span><span class="version-time">${date(latest.created)}</span><span>↗</span></a></section>
  <div class="banner"><span class="banner-icon">⌘</span><div><strong>Todo empieza con una buena base.</strong><p>${state.combat_version ? 'Combate listo: tu MS-001 es el verde. El rival es rojo.' : 'El editor está listo. Los algoritmos de combate se desarrollarán en la siguiente etapa.'}</p></div><a class="text-link" href="#editor">Explorar estructura →</a></div>`;
}

function versions() {
  return heading('Cada cambio tiene historia.', 'Copias completas e inmutables de los archivos del controlador.', exportButton + '<a class="button primary" href="#editor">+ Nueva versión</a>') +
  `<div class="toolbar"><input id="version-search" type="search" placeholder="Buscar por título, notas, versión o hash…" aria-label="Buscar versiones"><span class="muted">${state.versions.length} versiones</span></div><section class="panel table-wrap"><table><thead><tr><th>VERSIÓN</th><th>CAMBIO</th><th>FECHA</th><th>SHA-256</th><th></th></tr></thead><tbody id="version-rows">${versionRows(state.versions)}</tbody></table></section><div class="callout">Cada guardado con cambios conserva los dos archivos, sus notas y el hash de su versión anterior. Los borradores todavía sin guardar no son versiones.</div>`;
}
function versionRows(list) {
  return list.length ? list.map(v => `<tr><td><span class="pill">${ver(v.id)}</span></td><td>${esc(v.title)}<small>${esc(v.notes)}</small></td><td>${date(v.created)}</td><td class="hash">${v.hash.slice(0,12)}</td><td><a class="button compact" href="#versions/${v.id}">Ver cambios ↗</a></td></tr>`).join('') : '<tr><td colspan="5">No se encontraron versiones.</td></tr>';
}
async function detail(id) {
  const item = await api(`/api/versions/${id}`);
  return heading(`${ver(item.id)} · ${esc(item.title)}`, `Registrada el ${date(item.created)}`, '<a class="button" href="#versions">← Historial</a>') +
  `<section class="panel"><div class="panel-head"><h2>Comparación de archivos</h2><span class="pill neutral">SOLO LECTURA</span></div><div class="detail-note">${esc(item.notes || 'Sin notas adicionales.')}</div><div class="form-panel"><div class="toolbar"><label>Comparar desde<select id="compare-from">${state.versions.filter(v => v.id !== item.id).map(v => `<option value="${v.id}" ${v.id === item.id-1 ? 'selected' : ''}>${ver(v.id)} · ${esc(v.title)}</option>`).join('') || '<option value="">Sin otra versión</option>'}</select></label><label>Archivo<select id="compare-file"><option>controller.py</option><option>parameters.json</option></select></label><button id="show-snapshot">Ver archivo completo</button></div><p id="diff-description"></p></div><pre class="diff" id="diff-content"></pre></section><div class="callout">SHA-256: <code>${item.hash}</code><br>Origen: <code>${item.parent_hash || 'Versión inicial'}</code></div>`;
}
function editor() {
  if (PUBLIC) return heading('Algoritmos del laboratorio.', 'Consulta la última versión publicada. Los cambios se registran en el laboratorio local.', exportButton) + `<section class="panel"><div class="panel-head"><h2>${ver(draft.base)} · ${esc(state.versions[0].title)}</h2><span class="pill neutral">SOLO LECTURA</span></div><div class="editor-tabs">${Object.keys(draft.files).map(f=>`<button data-file="${f}" class="${f===activeFile?'active':''}">${f}</button>`).join('')}</div><textarea class="code-editor" readonly aria-label="Contenido del archivo" spellcheck="false">${esc(draft.files[activeFile])}</textarea></section><div class="callout">Esta es una copia pública del historial. Para registrar un cambio, abre el laboratorio local, guarda una nueva versión y vuelve a publicar. La simulación se ejecuta en Webots.</div>`;
  return heading('El próximo cambio empieza aquí.', 'Cada guardado con cambios crea una nueva versión. El código no se ejecuta desde la web.', '<a class="button" href="#versions">⑂ Ver historial</a>') +
  `<div class="editor-layout"><section class="panel"><div class="editor-tabs">${Object.keys(draft.files).map(f => `<button data-file="${f}" class="${f === activeFile ? 'active' : ''}">${f === 'controller.py' ? '⌘' : '{ }'} &nbsp; ${f}</button>`).join('')}</div><textarea class="code-editor" id="code-editor" aria-label="Contenido del archivo" spellcheck="false" autocapitalize="off">${esc(draft.files[activeFile])}</textarea><div class="editor-footer"><span id="file-type">${activeFile.endsWith('.py') ? 'Python' : 'JSON'} · UTF-8</span><span id="save-status"></span></div></section><form class="panel form-panel" id="save-form"><h2>Registrar cambio</h2><p>Origen: ${ver(draft.base)}. Conserva incluso los ajustes más pequeños.</p><label>Título del cambio<input id="change-title" required maxlength="120" placeholder="¿Qué cambió?" value="${esc(draft.title)}"></label><label>Motivo y contexto<textarea id="change-notes" maxlength="5000" placeholder="Explica por qué haces este cambio…">${esc(draft.notes)}</textarea></label><button class="primary" id="save-version" type="submit">⑂ Guardar nueva versión</button><p class="muted">Ctrl / ⌘ + S para guardar.<br>La copia registrada se conserva en el servidor local.</p></form></div><div class="callout">${state.combat_version ? 'El controlador incluye ambos combatientes y el árbitro. Tu robot es MS-001 (verde). Cada ajuste de estrategia o parámetros requiere una nueva versión antes de ejecutarse.' : 'La estructura inicial contiene comentarios y un archivo de parámetros vacío. Aún no incluye búsqueda, ataque, evasión ni aprendizaje automático.'}</div>`;
}
function simulation() {
  const report = state.validation;
  return heading('El dohyo, antes del mundo real.', state.combat_version ? 'Tu robot es MS-001, el VERDE. Combate contra el rival ROJO en Webots.' : 'Modelo físico inicial para Webots R2025a. Sin controlador de combate.') + `<div class="grid-main">${robotPanel()}<section class="panel"><div class="panel-head"><h2>Ficha del modelo</h2><span class="pill neutral">MS–001</span></div><div class="specs">${[['Huella del robot','96 × 96 mm'],['Masa total','460 g'],['Ruedas','2 × Ø 32 mm'],['Detección de rival','3 sensores de distancia'],['Detección de borde','4 sensores infrarrojos'],['Dohyo provisional','Ø 770 mm · borde 25 mm'],['Controlador',state.combat_version ? ver(state.combat_version) + ' · combate' : '&lt;none&gt;'],['Rival',state.combat_version ? 'ROJO · autónomo' : 'Segundo robot pasivo']].map(([a,b]) => `<div class="spec-line"><span>${a}</span><strong>${b}</strong></div>`).join('')}</div></section></div>${matchResults()}<div class="section-head"><h2>Validación del escenario</h2><span class="pill ${report?.passed && !report.stale ? '' : 'neutral'}">${report?.stale ? 'DESACTUALIZADO' : report?.passed ? 'VALIDADO' : 'PENDIENTE'}</span></div><section class="panel form-panel">${report ? `<p>${report.stale ? 'El modelo cambió; vuelve a ejecutar el diagnóstico. ' : ''}Última comprobación: ${date(report.created)}. ${esc(report.summary)}</p><div class="specs">${report.checks.map(c => `<div class="spec-line"><span>${esc(c.name)}</span><strong>${c.passed ? '✓' : '✕'} ${esc(c.detail)}</strong></div>`).join('')}</div>` : '<p>Todavía no hay una validación registrada de Webots.</p>'}<h3>Abrir el proyecto local</h3><pre class="command">${state.combat_version ? 'python3 tools/fight.py' : 'webots --mode=pause simulation/worlds/mini_sumo.wbt'}</pre><p>Esta página documenta el modelo; la simulación 3D se ejecuta en Webots. El tamaño del dohyo y la fricción son supuestos iniciales que deben ajustarse al reglamento y a mediciones del robot real.</p></section>`;
}
function matchResults() {
  if (!state.combat_version) return '';
  const matches = state.matches || [];
  return `<div class="callout"><strong>TU ROBOT: MS-001 · VERDE</strong><br>Rival: ROJO. Inicio tras 3 segundos. El árbitro detiene el combate al tocar el suelo exterior o cumplir 60 segundos. La victoria se calcula en Webots.</div><div class="section-head"><h2>Combates registrados</h2><span class="pill">ALGORITMOS ${ver(state.combat_version)}</span></div><section class="panel">${matches.length ? matches.map(m => `<article class="iteration"><a class="text-link" href="#versions/${m.version_id}">${ver(m.version_id)} ↗</a> <span class="pill neutral">${m.mode === 'test' ? 'PRUEBA' : 'COMBATE'}</span><h3>${m.winner === 'player' ? 'Ganó tu robot verde' : m.winner === 'opponent' ? 'Ganó el rival rojo' : 'Empate'}</h3><p>${esc(m.reason)} · ${m.elapsed.toFixed(2)} s · ${date(m.created)}</p><p>${m.checks_passed ? `Contacto entre robots: ${m.contact_seconds.toFixed(2)} s. Desplazamiento y parada comprobados.` : 'Este registro no tiene todas las comprobaciones de diagnóstico aprobadas.'}</p></article>`).join('') : '<div class="empty"><p>El controlador está registrado. Los resultados aparecerán al terminar una pelea; recarga esta vista.</p></div>'}</section>`;
}
function iterations() {
  return heading('Una bitácora para aprender.', 'Relaciona cada hipótesis y observación con la versión exacta que estudiaste.') + `<div class="two-col"><section class="panel">${state.iterations.length ? state.iterations.map(i => `<article class="iteration"><span class="pill">ITERACIÓN ${String(i.id).padStart(2,'0')}</span> <a class="text-link" href="#versions/${i.version_id}">${ver(i.version_id)} ↗</a><h3>Hipótesis</h3><p>${esc(i.hypothesis)}</p><h3>Observación</h3><p>${esc(i.observation)}</p><p>${date(i.created)}</p></article>`).join('') : '<div class="empty"><div class="empty-symbol">↻</div><h2>Tu primera iteración está por venir.</h2><p>Documenta qué esperas que ocurra y qué observaste. Los resultados de combate aparecerán cuando comencemos a experimentar.</p><span class="pill neutral">SIN EXPERIMENTOS REGISTRADOS</span></div>'}</section><form class="panel form-panel" id="iteration-form"><h2>Registrar una observación</h2><p>La bitácora es manual. Un registro no equivale a una simulación ejecutada.</p><label>Versión estudiada<select id="iteration-version">${state.versions.map(v => `<option value="${v.id}">${ver(v.id)} · ${esc(v.title)}</option>`).join('')}</select></label><label>Hipótesis<textarea id="hypothesis" required maxlength="5000" placeholder="¿Qué quieres comprobar?"></textarea></label><label>Observación<textarea id="observation" required maxlength="5000" placeholder="¿Qué ocurrió y qué aprendiste?"></textarea></label><button class="primary" type="submit">+ Guardar observación</button></form></div>`;
}
function dirty() { return draft && original && JSON.stringify(draft.files) !== JSON.stringify(original); }
function updateDirty() { if ($('#save-status')) { $('#save-status').textContent = dirty() ? '● Cambios sin versionar' : '✓ Sin cambios pendientes'; $('#save-version').disabled = !dirty(); } }
async function render() {
  const route = location.hash.slice(1).split('/'); const page = route[0] || 'overview';
  document.querySelectorAll('nav a').forEach(a => {a.classList.toggle('active', a.dataset.page === page); if(a.dataset.page === page) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');});
  try {
    state = await api('/api/state'); $('#nav-count').textContent = state.versions.length; $('#connection').textContent = PUBLIC ? 'Historial publicado' : 'Historial conectado';
    if (page === 'editor' && !draft) {const latest = await api(`/api/versions/${state.versions[0].id}`); original = structuredClone(latest.files); draft = {base:latest.id,files:structuredClone(latest.files),title:'',notes:''};}
    $('#content').innerHTML = page === 'versions' && route[1] ? await detail(Number(route[1])) : ({overview,versions,editor,simulation,iterations}[page] || overview)();
    if (PUBLIC) {
      $('#iteration-form')?.remove();
      document.querySelectorAll('a[href="#editor"]').forEach(a=>{if(a.classList.contains('primary')) a.textContent='Ver algoritmos';});
      if(state.published_at) $('#content').insertAdjacentHTML('beforeend',`<p class="publication-note">Copia publicada el ${date(state.published_at)} · Los datos se actualizan con cada publicación.</p>`);
    }
    bind(page, route[1]);
  } catch (error) { $('#connection').textContent = 'Error de conexión'; $('#content').innerHTML = `<div class="error-box"><h2>No se pudo cargar la vista</h2><p>${esc(error.message)}</p><button id="retry">Reintentar</button></div>`; $('#retry').onclick = render; }
}
function bind(page, id) {
  if(page === 'versions' && !id) $('#version-search').oninput = e => {const q = e.target.value.toLowerCase(); $('#version-rows').innerHTML = versionRows(state.versions.filter(v => `${ver(v.id)} ${v.title} ${v.notes} ${v.hash}`.toLowerCase().includes(q)));};
  if(page === 'versions' && id) {
    let request = 0;
    const show = async(snapshot=false) => {const current = ++request; try {const file=$('#compare-file').value, from=$('#compare-from').value; let text; if(snapshot || !from) {text=(await api(`/api/versions/${id}`)).files[file];} else {text=(await api(`/api/diff?from=${from}&to=${id}`))[file];} if(current !== request) return; $('#diff-description').textContent = snapshot || !from ? `Archivo completo · ${ver(id)}` : `${ver(from)} → ${ver(id)} · líneas añadidas (+) y eliminadas (−)`; $('#diff-content').innerHTML = text ? text.split('\n').map(l => `<span class="${l.startsWith('+') ? 'add' : l.startsWith('-') ? 'remove' : 'context'}">${esc(l) || ' '}</span>`).join('') : 'Sin cambios en este archivo.';}catch(e){toast(e.message,true);}};
    $('#compare-from').onchange = () => show(); $('#compare-file').onchange = () => show(); $('#show-snapshot').onclick = () => show(true); show();
  }
  if(page === 'editor') {
    if (PUBLIC) {document.querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>{activeFile=b.dataset.file; $('#content').innerHTML=editor(); bind('editor');}); return;}
    updateDirty(); $('#code-editor').oninput = e => {draft.files[activeFile] = e.target.value; updateDirty();};
    $('#change-title').oninput = e => draft.title = e.target.value; $('#change-notes').oninput = e => draft.notes = e.target.value;
    document.querySelectorAll('[data-file]').forEach(b => b.onclick = () => {activeFile = b.dataset.file; $('#content').innerHTML = editor(); bind('editor');});
    $('#save-form').onsubmit = async e => {e.preventDefault(); const button=$('#save-version'); button.disabled=true; try {const saved = await api('/api/versions', draft); draft=null; original=null; toast(`${ver(saved.id)} guardada. Tu cambio ya forma parte del historial.`); location.hash=`versions/${saved.id}`;} catch(error){toast(error.message,true); updateDirty();}};
  }
  if(page === 'iterations' && !PUBLIC) $('#iteration-form').onsubmit = async e => {e.preventDefault(); const button=e.target.querySelector('button'); button.disabled=true; try {await api('/api/iterations',{version_id:Number($('#iteration-version').value),hypothesis:$('#hypothesis').value,observation:$('#observation').value}); toast('Observación registrada.'); await render();}catch(error){toast(error.message,true); button.disabled=false;}};
}
window.addEventListener('hashchange', render);
window.addEventListener('beforeunload', e => {if(dirty()){e.preventDefault(); e.returnValue='';}});
window.addEventListener('keydown', e => {if((e.ctrlKey || e.metaKey) && e.key === 's' && $('#save-form')) {e.preventDefault(); if(dirty()) $('#save-form').requestSubmit();}});
render();
