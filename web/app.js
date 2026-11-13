"use strict";

const ESTADOS = {
  recibido: "Recibido",
  en_lectura: "En lectura",
  preseleccionado: "Preseleccionado",
  descartado: "Descartado",
  contratado: "Contratado",
};
const ORIGENES = { no_solicitado: "No solicitado", solicitado: "Solicitado" };
const TOPE_CHIPS = 14;

let manuscritos = [];
let config = { ia: false };
let abierto = null; // id del manuscrito abierto en la ficha
let sondeo = null;
const verTodos = { temas: false, tags: false };

const filtro = {
  q: "",
  orden: "recientes",
  modo: "todas", // «todas» o «cualquiera» de los temas y tags marcados
  origen: new Set(),
  estado: new Set(),
  genero: new Set(),
  idioma: new Set(),
  inc: { temas: new Set(), tags: new Set() },
  exc: { temas: new Set(), tags: new Set() },
};

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (n) => Number(n || 0).toLocaleString("es-ES");
const sinTildes = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

async function api(ruta, opciones) {
  const r = await fetch(ruta, opciones);
  if (!r.ok) {
    let detalle = `Error ${r.status}`;
    try { detalle = (await r.json()).detail || detalle; } catch {}
    throw new Error(detalle);
  }
  return r.json();
}

async function cargar() {
  manuscritos = await api("/api/manuscritos");
  pintar();
  const pendiente = manuscritos.some((m) => m.proceso === "analizando");
  if (pendiente && !sondeo) sondeo = setInterval(cargar, 1500);
  if (!pendiente && sondeo) { clearInterval(sondeo); sondeo = null; }
}

// --- Filtrado ----------------------------------------------------------------------------

const listos = () => manuscritos.filter((m) => m.proceso === "listo");

function pasa(m, omitir) {
  for (const campo of ["origen", "estado", "genero", "idioma"]) {
    if (campo !== omitir && filtro[campo].size && !filtro[campo].has(m[campo])) return false;
  }
  for (const campo of ["temas", "tags"]) {
    for (const e of filtro.exc[campo]) if (m[campo].includes(e)) return false;
  }
  if (omitir !== "etiquetas") {
    const pedidas = [
      ...[...filtro.inc.temas].map((e) => m.temas.includes(e)),
      ...[...filtro.inc.tags].map((e) => m.tags.includes(e)),
    ];
    if (pedidas.length) {
      const ok = filtro.modo === "todas" ? pedidas.every(Boolean) : pedidas.some(Boolean);
      if (!ok) return false;
    }
  }
  if (filtro.q) {
    const pajar = sinTildes([m.titulo, m.autor, m.logline, m.sumario, m.genero, m.subgenero, m.ambientacion, m.notas, ...m.temas, ...m.tags].join(" "));
    if (!sinTildes(filtro.q).split(/\s+/).filter(Boolean).every((p) => pajar.includes(p))) return false;
  }
  return true;
}

function resultados() {
  const r = listos().filter((m) => pasa(m));
  if (filtro.orden === "titulo") r.sort((a, b) => a.titulo.localeCompare(b.titulo, "es"));
  else if (filtro.orden === "palabras") r.sort((a, b) => b.palabras - a.palabras);
  return r;
}

function recuento(lista, campo) {
  const c = new Map();
  for (const m of lista) {
    for (const v of Array.isArray(m[campo]) ? m[campo] : [m[campo]]) {
      if (v) c.set(v, (c.get(v) || 0) + 1);
    }
  }
  return c;
}

function hayFiltros() {
  return !!(filtro.q || filtro.origen.size || filtro.estado.size || filtro.genero.size || filtro.idioma.size ||
    filtro.inc.temas.size || filtro.inc.tags.size || filtro.exc.temas.size || filtro.exc.tags.size);
}

function limpiar() {
  filtro.q = "";
  $("buscar").value = "";
  for (const c of ["origen", "estado", "genero", "idioma"]) filtro[c].clear();
  for (const c of ["temas", "tags"]) { filtro.inc[c].clear(); filtro.exc[c].clear(); }
  pintar();
}

// Un clic incluye, otro excluye, otro quita.
function ciclar(campo, valor) {
  if (filtro.inc[campo].has(valor)) { filtro.inc[campo].delete(valor); filtro.exc[campo].add(valor); }
  else if (filtro.exc[campo].has(valor)) filtro.exc[campo].delete(valor);
  else filtro.inc[campo].add(valor);
  pintar();
}

// --- Pintado -----------------------------------------------------------------------------

function pintar() {
  pintarTarjetas();
  pintarFiltros();
  pintarActivos();
  pintarLista();
  if (abierto !== null) pintarFicha();
}

function pintarTarjetas() {
  const l = listos();
  const cuenta = (f) => l.filter(f).length;
  const tantos = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
  const tarjetas = [
    ["Manuscritos", l.length, `${num(l.reduce((s, m) => s + m.palabras, 0))} palabras en total`, ""],
    ["No solicitados", cuenta((m) => m.origen === "no_solicitado"), tantos(cuenta((m) => m.origen === "solicitado"), "solicitado", "solicitados"), "origen:no_solicitado"],
    ["Por leer", cuenta((m) => m.estado === "recibido"), `${cuenta((m) => m.estado === "en_lectura")} en lectura`, "estado:recibido"],
    ["Preseleccionados", cuenta((m) => m.estado === "preseleccionado"), tantos(cuenta((m) => m.estado === "contratado"), "contratado", "contratados"), "estado:preseleccionado"],
  ];
  $("tarjetas").innerHTML = tarjetas
    .map(([rotulo, cifra, nota, atajo]) =>
      `<button class="tarjeta" type="button" data-atajo="${atajo}"><div class="rotulo">${rotulo}</div><div class="cifra">${cifra}</div><div class="nota">${esc(nota)}</div></button>`)
    .join("");
}

function grupoCasillas(titulo, campo, nombres) {
  const base = recuento(listos().filter((m) => pasa(m, campo)), campo);
  const valores = nombres ? Object.keys(nombres) : [...recuento(listos(), campo).keys()].sort((a, b) => a.localeCompare(b, "es"));
  if (!valores.length) return "";
  return `<div class="filtro"><h3>${titulo}</h3>${valores
    .map((v) => {
      const n = base.get(v) || 0;
      return `<label class="opcion ${n ? "" : "cero"}"><input type="checkbox" data-campo="${campo}" value="${esc(v)}" ${filtro[campo].has(v) ? "checked" : ""}>${esc(nombres ? nombres[v] : v)}<span class="n">${n}</span></label>`;
    })
    .join("")}</div>`;
}

function grupoChips(titulo, campo) {
  // En modo «cualquiera», marcar un tag no debe esconder los demás.
  const base = recuento(listos().filter((m) => pasa(m, filtro.modo === "cualquiera" ? "etiquetas" : undefined)), campo);
  const marcados = [...filtro.inc[campo], ...filtro.exc[campo]];
  const resto = [...base.entries()].filter(([v]) => !marcados.includes(v)).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "es"));
  const visibles = verTodos[campo] ? resto : resto.slice(0, Math.max(TOPE_CHIPS - marcados.length, 4));
  const chip = (v, n, clase) =>
    `<button type="button" class="chip ${campo === "temas" ? "tema" : ""} ${clase}" data-chip="${campo}" data-valor="${esc(v)}" aria-pressed="${clase ? "true" : "false"}" title="${clase === "inc" ? "Incluido: clic para excluir" : clase === "exc" ? "Excluido: clic para quitar" : "Clic para incluir"}">${esc(v)}<span class="n">${n ?? ""}</span></button>`;
  const html = [
    ...[...filtro.inc[campo]].map((v) => chip(v, base.get(v) || 0, "inc")),
    ...[...filtro.exc[campo]].map((v) => chip(v, "", "exc")),
    ...visibles.map(([v, n]) => chip(v, n, "")),
  ].join("");
  if (!html) return "";
  const mas = resto.length > visibles.length || verTodos[campo]
    ? `<button type="button" class="ver-mas" data-mas="${campo}">${verTodos[campo] ? "Ver menos" : `Ver los ${resto.length + marcados.length}`}</button>`
    : "";
  return `<div class="filtro"><h3>${titulo}</h3><div class="chips">${html}</div>${mas}</div>`;
}

function pintarFiltros() {
  if (!listos().length) { $("filtros").hidden = true; return; }
  $("filtros").hidden = false;
  const modo = `<div class="filtro"><h3>Temas y tags <span class="modo" role="group" aria-label="Cómo combinar los temas y tags marcados">
      <button type="button" data-modo="todas" class="${filtro.modo === "todas" ? "on" : ""}">Todos</button>
      <button type="button" data-modo="cualquiera" class="${filtro.modo === "cualquiera" ? "on" : ""}">Alguno</button></span></h3>
      <p class="ayuda">Un clic incluye, el segundo excluye y el tercero quita.</p></div>`;
  $("filtros").innerHTML =
    grupoCasillas("Origen", "origen", ORIGENES) +
    grupoCasillas("Estado", "estado", ESTADOS) +
    grupoCasillas("Género", "genero") +
    modo + grupoChips("Temas", "temas") + grupoChips("Tags", "tags") +
    grupoCasillas("Idioma", "idioma");
}

function pintarActivos() {
  const total = listos().length;
  const n = resultados().length;
  if (!total) { $("activos").innerHTML = ""; return; }
  const chips = [];
  const quitar = (tipo, campo, valor, texto, clase = "") =>
    chips.push(`<span class="chip ${clase}">${esc(texto)}<button type="button" class="x" data-quitar="${tipo}" data-campo="${campo}" data-valor="${esc(valor)}" aria-label="Quitar filtro ${esc(texto)}">×</button></span>`);
  for (const v of filtro.origen) quitar("set", "origen", v, ORIGENES[v]);
  for (const v of filtro.estado) quitar("set", "estado", v, ESTADOS[v]);
  for (const v of filtro.genero) quitar("set", "genero", v, v);
  for (const v of filtro.idioma) quitar("set", "idioma", v, v);
  for (const c of ["temas", "tags"]) {
    for (const v of filtro.inc[c]) quitar("inc", c, v, v, "inc");
    for (const v of filtro.exc[c]) quitar("exc", c, v, `sin ${v}`, "exc");
  }
  $("activos").innerHTML =
    `<span>${n === total ? "" : `${n} de `}${total} ${total === 1 ? "manuscrito" : "manuscritos"}</span>` +
    chips.join("") + (hayFiltros() ? `<button type="button" class="limpiar" id="limpiar">Limpiar filtros</button>` : "");
}

function metaLinea(m) {
  return [m.genero, m.subgenero, m.palabras ? `${num(m.palabras)} palabras` : "", m.idioma].filter(Boolean).map(esc).join(" · ");
}

function pintarLista() {
  // Los que aún se analizan o han fallado no tienen ficha que filtrar: se ven solo sin filtros.
  const enCurso = hayFiltros() ? [] : manuscritos.filter((m) => m.proceso !== "listo");
  const r = resultados();
  let html = enCurso
    .map((m) =>
      m.proceso === "analizando"
        ? `<div class="item analizando"><h2>${esc(m.titulo)}</h2><div class="meta">${esc(m.archivo)}</div><div class="estado-proceso"><span class="giro"></span>Leyendo el manuscrito y preparando la ficha…</div></div>`
        : `<button type="button" class="item" data-id="${m.id}"><h2>${esc(m.titulo)}</h2><div class="meta">${esc(m.archivo)}</div><div class="estado-proceso error">No se pudo analizar: ${esc(m.error)}</div></button>`)
    .join("");

  if (!manuscritos.length) {
    html = `<div class="vacio"><strong>Todavía no hay manuscritos</strong>Sube los primeros archivos o carga unas fichas de ejemplo para ver cómo funciona la bandeja.<br>
      <button class="boton primario" type="button" data-accion="subir">Subir manuscritos</button><button class="boton" type="button" data-accion="ejemplos">Cargar ejemplos</button></div>`;
  } else if (!r.length && listos().length) {
    html += `<div class="vacio"><strong>Ningún manuscrito cumple estos filtros</strong>Prueba a quitar alguno o a combinar los tags con «Alguno».<br><button class="boton" type="button" data-accion="limpiar">Limpiar filtros</button></div>`;
  }

  html += r
    .map((m) => {
      const etiquetas = [
        ...m.temas.map((t) => `<span class="chip tema ${filtro.inc.temas.has(t) ? "inc" : ""}">${esc(t)}</span>`),
        ...m.tags.slice(0, 7).map((t) => `<span class="chip ${filtro.inc.tags.has(t) ? "inc" : ""}">${esc(t)}</span>`),
        m.tags.length > 7 ? `<span class="chip">+${m.tags.length - 7}</span>` : "",
      ].join("");
      return `<button type="button" class="item" data-id="${m.id}">
        <div class="item-cab"><div><h2>${esc(m.titulo)}</h2><div class="autor">${esc(m.autor || "Autor sin identificar")}</div><div class="meta">${metaLinea(m)}</div></div>
        <div class="pildoras"><span class="pildora ${m.origen === "solicitado" ? "solicitado" : "borde"}">${ORIGENES[m.origen]}</span><span class="pildora ${m.estado}">${ESTADOS[m.estado]}</span></div></div>
        ${m.logline || m.sumario ? `<p class="logline">${esc(m.logline || m.sumario.slice(0, 220))}</p>` : ""}
        <div class="chips">${etiquetas}</div></button>`;
    })
    .join("");
  $("lista").innerHTML = html;
}

// --- Ficha -------------------------------------------------------------------------------

function editables(m, campo) {
  return `<div class="chips">${m[campo]
    .map((v) => `<span class="chip ${campo === "temas" ? "tema" : ""}">${esc(v)}<button type="button" class="x" data-borrar="${campo}" data-valor="${esc(v)}" aria-label="Quitar ${esc(v)}">×</button></span>`)
    .join("")}<input class="anadir" data-anadir="${campo}" placeholder="+ añadir" aria-label="Añadir a ${campo}" list="lista-${campo}"></div>
    <datalist id="lista-${campo}">${[...recuento(listos(), campo).keys()].filter((v) => !m[campo].includes(v)).sort().map((v) => `<option value="${esc(v)}">`).join("")}</datalist>`;
}

function pintarFicha() {
  const m = manuscritos.find((x) => x.id === abierto);
  if (!m) return cerrarFicha();
  const selector = (campo, mapa) =>
    `<select data-editar="${campo}">${Object.entries(mapa).map(([v, t]) => `<option value="${v}" ${m[campo] === v ? "selected" : ""}>${t}</option>`).join("")}</select>`;
  const fuente = {
    local: `<p class="aviso-fuente">Ficha hecha con la extracción básica, sin IA: los tags salen de las palabras más repetidas y no hay sumario de verdad. Configura la clave de Anthropic y pulsa «Volver a analizar».</p>`,
    ejemplo: `<p class="aviso-fuente neutro">Ficha de ejemplo, inventada para enseñar la bandeja.</p>`,
    ia: "",
  }[m.fuente] ?? "";
  const dato = (t, v) => (v && v.length ? `<dt>${t}</dt><dd>${esc(Array.isArray(v) ? v.join(", ") : v)}</dd>` : "");
  const tieneArchivo = m.fuente !== "ejemplo";

  // No repintar encima de lo que se está escribiendo.
  const activo = document.activeElement;
  if ($("ficha").contains(activo) && ["TEXTAREA", "INPUT"].includes(activo.tagName) && $("ficha").dataset.id === String(m.id)) return;

  $("ficha").dataset.id = m.id;
  $("ficha").innerHTML = `
    <div class="ficha-cab"><div><h2>${esc(m.titulo)}</h2><p class="autor">${esc(m.autor || "Autor sin identificar")} · ${metaLinea(m)}</p></div>
      <button type="button" class="cerrar" id="cerrar-ficha" aria-label="Cerrar ficha">×</button></div>
    ${m.proceso === "error" ? `<p class="aviso-fuente">No se pudo analizar: ${esc(m.error)}</p>` : fuente}
    ${m.logline ? `<p class="logline">${esc(m.logline)}</p>` : ""}
    <div class="controles">
      <label class="campo">Estado ${selector("estado", ESTADOS)}</label>
      <label class="campo">Origen ${selector("origen", ORIGENES)}</label>
    </div>
    ${m.sumario ? `<section><h3>${m.fuente === "local" ? "Primeras frases" : "Sumario"}</h3><p class="sumario">${esc(m.sumario)}</p></section>` : ""}
    <section><h3>Temas</h3>${editables(m, "temas")}</section>
    <section><h3>Tags</h3>${editables(m, "tags")}</section>
    <section><h3>Ficha</h3><dl class="datos">
      ${dato("Género", [m.genero, m.subgenero].filter(Boolean).join(" · "))}${dato("Público", m.publico)}${dato("Ambientación", m.ambientacion)}
      ${dato("Tono", m.tono)}${dato("Comparables", m.comparables)}${dato("Idioma", m.idioma)}
      ${dato("Extensión", m.palabras ? `${num(m.palabras)} palabras (unas ${num(Math.round(m.palabras / 300))} páginas)` : "")}
      ${dato("Archivo", m.archivo)}${dato("Recibido", new Date(m.creado).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" }))}
    </dl></section>
    <section><h3>Notas del equipo</h3><label class="campo"><textarea data-editar="notas" placeholder="Impresiones de lectura, a quién se lo pasas, qué se contestó…" aria-label="Notas del equipo">${esc(m.notas)}</textarea></label></section>
    ${m.extracto ? `<section><h3>Arranque del texto</h3><p class="extracto">${esc(m.extracto)}</p></section>` : ""}
    <div class="ficha-pie">
      ${tieneArchivo ? `<a class="boton" href="/api/manuscritos/${m.id}/archivo">Descargar original</a><button type="button" class="boton" id="reanalizar">Volver a analizar</button>` : ""}
      <button type="button" class="boton peligro" id="eliminar">Eliminar</button>
    </div>`;
}

function abrirFicha(id) {
  abierto = id;
  $("ficha").hidden = false;
  $("velo").hidden = false;
  $("ficha").dataset.id = "";
  pintarFicha();
  $("ficha").scrollTop = 0;
}

function cerrarFicha() {
  abierto = null;
  $("ficha").hidden = true;
  $("velo").hidden = true;
}

async function guardar(id, cambios) {
  const m = await api(`/api/manuscritos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cambios),
  });
  manuscritos = manuscritos.map((x) => (x.id === id ? m : x));
  pintar();
}

// --- Subida ------------------------------------------------------------------------------

async function subir(archivos) {
  if (!archivos.length) return;
  const datos = new FormData();
  for (const a of archivos) datos.append("archivos", a);
  datos.append("origen", document.querySelector('input[name="origen"]:checked').value);
  $("subir-error").hidden = true;
  try {
    await api("/api/manuscritos", { method: "POST", body: datos });
    $("dlg-subir").close();
    await cargar();
  } catch (e) {
    $("subir-error").textContent = e.message;
    $("subir-error").hidden = false;
  }
  $("archivos").value = "";
}

async function cargarEjemplos() {
  await api("/api/ejemplos", { method: "POST" });
  await cargar();
}

// --- Eventos -----------------------------------------------------------------------------

$("btn-subir").onclick = () => $("dlg-subir").showModal();
$("btn-ejemplos").onclick = cargarEjemplos;
$("buscar").oninput = (e) => { filtro.q = e.target.value.trim(); pintarFiltros(); pintarActivos(); pintarLista(); };
$("orden").onchange = (e) => { filtro.orden = e.target.value; pintarLista(); };
$("velo").onclick = cerrarFicha;
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && abierto !== null && !$("dlg-subir").open) cerrarFicha(); });

$("tarjetas").onclick = (e) => {
  const t = e.target.closest("[data-atajo]");
  if (!t) return;
  limpiar();
  if (t.dataset.atajo) {
    const [campo, valor] = t.dataset.atajo.split(":");
    filtro[campo].add(valor);
    pintar();
  }
};

$("filtros").onchange = (e) => {
  const c = e.target.dataset.campo;
  if (!c) return;
  e.target.checked ? filtro[c].add(e.target.value) : filtro[c].delete(e.target.value);
  pintar();
};
$("filtros").onclick = (e) => {
  const chip = e.target.closest("[data-chip]");
  if (chip) return ciclar(chip.dataset.chip, chip.dataset.valor);
  const modo = e.target.closest("[data-modo]");
  if (modo) { filtro.modo = modo.dataset.modo; return pintar(); }
  const mas = e.target.closest("[data-mas]");
  if (mas) { verTodos[mas.dataset.mas] = !verTodos[mas.dataset.mas]; pintarFiltros(); }
};

$("activos").onclick = (e) => {
  if (e.target.id === "limpiar") return limpiar();
  const x = e.target.closest("[data-quitar]");
  if (!x) return;
  const { quitar, campo, valor } = x.dataset;
  (quitar === "set" ? filtro[campo] : filtro[quitar][campo]).delete(valor);
  pintar();
};

$("lista").onclick = (e) => {
  const accion = e.target.closest("[data-accion]")?.dataset.accion;
  if (accion === "subir") return $("dlg-subir").showModal();
  if (accion === "ejemplos") return cargarEjemplos();
  if (accion === "limpiar") return limpiar();
  const item = e.target.closest("[data-id]");
  if (item) abrirFicha(Number(item.dataset.id));
};

$("ficha").onclick = async (e) => {
  const m = manuscritos.find((x) => x.id === abierto);
  if (!m) return;
  if (e.target.id === "cerrar-ficha") return cerrarFicha();
  const borrar = e.target.closest("[data-borrar]");
  if (borrar) {
    const campo = borrar.dataset.borrar;
    return guardar(m.id, { [campo]: m[campo].filter((v) => v !== borrar.dataset.valor) });
  }
  if (e.target.id === "reanalizar") {
    await api(`/api/manuscritos/${m.id}/analizar`, { method: "POST" });
    cerrarFicha();
    return cargar();
  }
  if (e.target.id === "eliminar") {
    if (!confirm(`¿Eliminar «${m.titulo}» y su archivo? No se puede deshacer.`)) return;
    await api(`/api/manuscritos/${m.id}`, { method: "DELETE" });
    cerrarFicha();
    return cargar();
  }
};
$("ficha").onchange = (e) => {
  const campo = e.target.dataset.editar;
  if (campo && abierto !== null) { e.target.blur(); guardar(abierto, { [campo]: e.target.value }); }
};
$("ficha").onkeydown = (e) => {
  const campo = e.target.dataset?.anadir;
  if (!campo || e.key !== "Enter") return;
  e.preventDefault();
  const m = manuscritos.find((x) => x.id === abierto);
  const valor = e.target.value.trim();
  if (!m || !valor) return;
  e.target.blur();
  guardar(m.id, { [campo]: [...m[campo], valor] });
};

const zona = $("zona");
$("archivos").onchange = (e) => subir([...e.target.files]);
for (const ev of ["dragenter", "dragover"]) zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("sobre"); });
for (const ev of ["dragleave", "drop"]) zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("sobre"); });
zona.addEventListener("drop", (e) => subir([...e.dataTransfer.files]));

(async function iniciar() {
  config = await api("/api/config");
  const aviso = $("aviso-ia");
  aviso.textContent = config.ia
    ? `Análisis con IA activo (${config.modelo}).`
    : "Sin clave de Anthropic: las subidas se analizan con una extracción básica, sin IA.";
  aviso.classList.toggle("aviso", !config.ia);
  await cargar();
})();
