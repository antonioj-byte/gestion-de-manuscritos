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
const NIVELES = ["Muy fácil", "Bastante fácil", "Normal", "Algo difícil", "Muy difícil"];
const ORDENES = {
  legibilidad: (m) => m.metricas?.global.legibilidad,
  dialogo: (m) => m.metricas?.global.dialogo,
  nota: (m) => m.lectura?.media,
};

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
  lectura: new Set(),
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
  // Nivel de legibilidad como campo plano, para filtrar por él como por el género.
  for (const m of manuscritos) m.lectura_nivel = m.metricas?.global.legibilidad_detalle?.nivel || "";
  pintar();
  const pendiente = manuscritos.some((m) => m.proceso === "analizando" || m.lectura_proceso === "leyendo");
  if (pendiente && !sondeo) sondeo = setInterval(cargar, 1500);
  if (!pendiente && sondeo) { clearInterval(sondeo); sondeo = null; }
}

// --- Filtrado ----------------------------------------------------------------------------

const listos = () => manuscritos.filter((m) => m.proceso === "listo");

function pasa(m, omitir) {
  for (const campo of ["origen", "estado", "genero", "idioma"]) {
    if (campo !== omitir && filtro[campo].size && !filtro[campo].has(m[campo])) return false;
  }
  if (omitir !== "lectura_nivel" && filtro.lectura.size && !filtro.lectura.has(m.lectura_nivel)) return false;
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
  else if (filtro.orden in ORDENES) {
    // Los que no tienen el dato van al final, sin mezclarse con los que sí.
    const v = ORDENES[filtro.orden];
    r.sort((a, b) => (v(b) ?? -Infinity) - (v(a) ?? -Infinity));
  }
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
  return !!(filtro.q || filtro.origen.size || filtro.estado.size || filtro.genero.size || filtro.idioma.size || filtro.lectura.size ||
    filtro.inc.temas.size || filtro.inc.tags.size || filtro.exc.temas.size || filtro.exc.tags.size);
}

function limpiar() {
  filtro.q = "";
  $("buscar").value = "";
  for (const c of ["origen", "estado", "genero", "idioma", "lectura"]) filtro[c].clear();
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

function grupoCasillas(titulo, campo, nombres, clave = campo) {
  const base = recuento(listos().filter((m) => pasa(m, campo)), campo);
  const valores = nombres ? Object.keys(nombres) : [...recuento(listos(), campo).keys()].sort((a, b) => a.localeCompare(b, "es"));
  if (!valores.length) return "";
  return `<div class="filtro"><h3>${titulo}</h3>${valores
    .map((v) => {
      const n = base.get(v) || 0;
      return `<label class="opcion ${n ? "" : "cero"}"><input type="checkbox" data-campo="${clave}" value="${esc(v)}" ${filtro[clave].has(v) ? "checked" : ""}>${esc(nombres ? nombres[v] : v)}<span class="n">${n}</span></label>`;
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
    grupoCasillas("Idioma", "idioma") +
    (listos().some((m) => m.lectura_nivel)
      ? grupoCasillas("Legibilidad", "lectura_nivel", Object.fromEntries(NIVELES.map((n) => [n, n])), "lectura")
      : "");
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
  for (const v of filtro.lectura) quitar("set", "lectura", v, `Lectura: ${v.toLowerCase()}`);
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

const pct = (v) => `${Math.round(v * 100)} %`;
const dec = (v) => Number(v).toLocaleString("es-ES", { maximumFractionDigits: 1 });

function medidasLinea(m) {
  const g = m.metricas?.global;
  if (!g) return "";
  return [
    g.legibilidad != null ? `Legibilidad ${g.legibilidad} (${g.legibilidad_detalle.nivel.toLowerCase()})` : "",
    `${pct(g.dialogo)} de diálogo`,
    m.metricas.tramos_lentos ? `${m.metricas.tramos_lentos} ${m.metricas.tramos_lentos === 1 ? "capítulo lento" : "capítulos lentos"}` : "",
  ].filter(Boolean).join(" · ");
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
        <div class="item-cab"><div><h2>${esc(m.titulo)}</h2><div class="autor">${esc(m.autor || "Autor sin identificar")}</div><div class="meta">${metaLinea(m)}</div>${medidasLinea(m) ? `<div class="meta">${medidasLinea(m)}</div>` : ""}</div>
        <div class="pildoras">${m.lectura?.media != null ? `<span class="pildora nota" title="Media de la rúbrica de la lectura asistida">${dec(m.lectura.media)} / 10</span>` : ""}<span class="pildora ${m.origen === "solicitado" ? "solicitado" : "borde"}">${ORIGENES[m.origen]}</span><span class="pildora ${m.estado}">${ESTADOS[m.estado]}</span></div></div>
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
    ${seccionMetricas(m)}
    ${seccionLectura(m)}
    <section><h3>Notas del equipo</h3><label class="campo"><textarea data-editar="notas" placeholder="Impresiones de lectura, a quién se lo pasas, qué se contestó…" aria-label="Notas del equipo">${esc(m.notas)}</textarea></label></section>
    ${m.extracto ? `<section><h3>Arranque del texto</h3><p class="extracto">${esc(m.extracto)}</p></section>` : ""}
    <div class="ficha-pie">
      ${tieneArchivo ? `<a class="boton" href="/api/manuscritos/${m.id}/archivo">Descargar original</a><button type="button" class="boton" id="reanalizar">Volver a analizar</button>` : ""}
      <button type="button" class="boton" id="imprimir">Imprimir o guardar PDF</button>
      <button type="button" class="boton peligro" id="eliminar">Eliminar</button>
    </div>`;
}

// --- Métricas y lectura ------------------------------------------------------------------

const COMO = {
  legibilidad: (d) => d.indice === "Flesch"
    ? "Índice de Flesch: 206,835 − 84,6 × sílabas por palabra − 1,015 × palabras por frase, acotado de 0 a 100. Más alto es más fácil."
    : "Índice de Szigriszt-Pazos: 206,835 − 62,3 × sílabas por palabra − palabras por frase, acotado de 0 a 100 y leído con la escala INFLESZ. Más alto es más fácil.",
  frase: "Palabras del texto entre número de frases. Las frases se cortan en punto, interrogación, exclamación o puntos suspensivos.",
  dialogo: "Parte de las palabras que va en párrafos que empiezan con raya o entre comillas. Cuenta también los incisos del narrador dentro de la raya.",
  lexico: "MTLD: longitud media de los tramos que mantienen más de un 72 % de palabras distintas. No depende de lo largo que sea el texto. Más alto es más variado; en narrativa suele ir de 70 a 120.",
  variacion: "Desviación típica del largo de las frases dividida por su media. Cerca de 0, todas las frases miden lo mismo; por encima de 0,8, alterna frases muy cortas y muy largas.",
};

function ficha_dato(rotulo, valor, nota, como) {
  return `<div class="medida"><div class="rotulo">${rotulo}</div><div class="valor">${valor}</div><div class="nota">${esc(nota)}</div>
    <details><summary>Cómo se calcula</summary><p>${esc(como)}</p></details></div>`;
}

// Barras verticales de una sola serie, una por capítulo o fragmento.
function barras(filas, { valor, formato, alto = 96, marca, maximo }) {
  const ancho = 580, base = alto - 4, n = filas.length;
  const tope = maximo ?? Math.max(...filas.map(valor), 0.0001);
  const paso = ancho / n, grosor = Math.max(Math.min(paso - 2, 28), 2);
  const cuerpos = filas.map((f, i) => {
    const h = Math.max((valor(f) / tope) * (base - 14), 1);
    const x = i * paso + (paso - grosor) / 2, r = Math.min(4, grosor / 2, h);
    const forma = `M${x},${base} v${-(h - r)} q0,${-r} ${r},${-r} h${grosor - 2 * r} q${r},0 ${r},${r} v${h - r} z`;
    return `<g class="marca ${marca?.(f) ? "senal" : ""}" data-pista="${esc(`${f.titulo || `Fragmento ${i + 1}`}: ${formato(valor(f))}${marca?.(f) ? " · tramo lento" : ""}`)}">
      <rect x="${i * paso}" y="0" width="${paso}" height="${alto}" fill="transparent"/><path d="${forma}"/>
      ${marca?.(f) ? `<circle cx="${x + grosor / 2}" cy="${base - h - 7}" r="3"/>` : ""}</g>`;
  }).join("");
  return `<svg class="grafica" viewBox="0 0 ${ancho} ${alto}" role="img" aria-label="Gráfica de barras; los mismos datos están en la tabla de capítulos">
    <line x1="0" y1="${base}" x2="${ancho}" y2="${base}" class="eje"/>${cuerpos}</svg>`;
}

function seccionMetricas(m) {
  const mt = m.metricas;
  if (!mt) return "";
  const g = mt.global, d = g.legibilidad_detalle;
  const medidas = [
    d ? ficha_dato("Legibilidad", d.nota, `${d.nivel} · ${d.indice} ${dec(d.valor)}`, COMO.legibilidad(d))
      : ficha_dato("Legibilidad", "—", `Sin fórmula validada para ${m.idioma || "este idioma"}`, "Solo se calcula en español (Szigriszt-Pazos) y en inglés (Flesch).") ,
    ficha_dato("Frase media", dec(g.frase_media), "palabras por frase", COMO.frase),
    ficha_dato("Diálogo", pct(g.dialogo), "de las palabras", COMO.dialogo),
    ficha_dato("Variedad léxica", g.diversidad_lexica != null ? dec(g.diversidad_lexica) : "—", g.diversidad_lexica != null ? "MTLD" : "Texto demasiado corto", COMO.lexico),
    ficha_dato("Variación de frase", g.variacion_frase != null ? dec(g.variacion_frase) : "—", "coeficiente de variación", COMO.variacion),
  ].join("");
  let porCapitulo = `<p class="ayuda">No se han reconocido cabeceras de capítulo en el texto, así que no hay desglose.</p>`;
  if (mt.capitulos.length) {
    const lentos = mt.tramos_lentos;
    porCapitulo = `
      <h4>Largo de frase por capítulo <span>palabras por frase · capítulo mediano ${dec(g.frase_mediana_capitulos)}</span></h4>
      ${barras(mt.capitulos, { valor: (c) => c.frase_media, formato: (v) => `${dec(v)} palabras por frase`, marca: (c) => c.lento })}
      <p class="ayuda">${lentos
        ? `<span class="punto"></span> ${lentos === 1 ? "1 capítulo marcado como lento" : `${lentos} capítulos marcados como lentos`}: frases al menos un 25 % más largas que las del capítulo mediano y no más diálogo que él. Es una señal para mirarlo, no un defecto.`
        : "Ningún capítulo destaca por lento (frases un 25 % más largas que las del capítulo mediano y no más diálogo que él)."}</p>
      <h4>Diálogo por capítulo <span>% de las palabras · media ${pct(g.dialogo)}</span></h4>
      ${barras(mt.capitulos, { valor: (c) => c.dialogo, formato: pct, maximo: Math.max(...mt.capitulos.map((c) => c.dialogo), 0.25) })}
      <details class="tabla"><summary>Ver la tabla de los ${mt.capitulos.length} capítulos</summary>
        <table><thead><tr><th>Capítulo</th><th>Palabras</th><th>Frase media</th><th>Diálogo</th><th>Legibilidad</th><th></th></tr></thead><tbody>
        ${mt.capitulos.map((c) => `<tr><td>${esc(c.titulo)}</td><td>${num(c.palabras)}</td><td>${dec(c.frase_media)}</td><td>${pct(c.dialogo)}</td><td>${c.legibilidad ?? "—"}</td><td>${c.lento ? "lento" : ""}</td></tr>`).join("")}
        </tbody></table></details>`;
  }
  return `<section><h3>Métricas del texto</h3>
    <p class="ayuda">Cuentas hechas sobre el texto, sin IA: el mismo archivo da siempre los mismos números.</p>
    <div class="medidas">${medidas}</div>${porCapitulo}</section>`;
}

function seccionLectura(m) {
  if (m.fuente === "ejemplo" || m.proceso !== "listo") return "";
  const cab = `<h3>Lectura asistida</h3>`;
  if (m.lectura_proceso === "leyendo") {
    return `<section>${cab}<p class="estado-proceso"><span class="giro"></span>Leyendo el manuscrito por fragmentos y preparando el informe. Puede tardar unos minutos.</p></section>`;
  }
  const L = m.lectura;
  const boton = config.ia
    ? `<button type="button" class="boton" id="pedir-lectura">${L ? "Repetir la lectura" : "Preparar informe de lectura"}</button>`
    : `<p class="aviso-fuente">Hace falta la clave de Anthropic para la lectura asistida.</p>`;
  const fallo = m.lectura_proceso === "error" ? `<p class="aviso-fuente">La lectura falló: ${esc(m.lectura_error)}</p>` : "";
  if (!L) {
    return `<section>${cab}<p class="ayuda">Claude lee el manuscrito entero por fragmentos de unas 3.000 palabras y prepara una rúbrica justificada con citas, fortalezas y debilidades, un borrador de informe y una versión para el autor. Tiene coste de API (del orden de un dólar por novela).</p>${fallo}${boton}</section>`;
  }
  const rubrica = Object.entries(config.criterios).map(([clave, nombre]) => {
    const c = L.rubrica[clave];
    return `<div class="criterio"><div class="criterio-cab"><strong>${nombre}</strong><span>${c.nota ?? "No aplica"}${c.nota ? " / 10" : ""}</span></div>
      ${c.nota ? `<div class="regla"><i style="width:${c.nota * 10}%"></i></div>` : ""}
      <p>${esc(c.justificacion)}</p>${c.cita ? `<blockquote>${esc(c.cita)}</blockquote>` : ""}</div>`;
  }).join("");
  const lista = (v) => `<ul>${v.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  const arco = L.arco.length > 1 ? `
      <h4>Tensión a lo largo del texto <span>de 1 (reposo) a 5 (máxima) · por fragmento</span></h4>
      ${barras(L.arco.map((a, i) => ({ ...a, titulo: a.capitulos.join(", ") || `Fragmento ${i + 1}` })), { valor: (a) => a.tension, formato: (v) => `tensión ${v} de 5`, maximo: 5 })}
      <p class="ayuda">Es la apreciación del modelo en cada fragmento, no una medida del texto.</p>` : "";
  return `<section>${cab}${fallo}
    <p class="aviso-fuente neutro">Opinión de un modelo (${esc(L.modelo)}) a partir de ${L.fragmentos} ${L.fragmentos === 1 ? "fragmento" : "fragmentos"}. Sirve para ordenar la pila y preparar el informe; la decisión es del equipo. No usa datos de ventas.</p>
    <div class="veredicto"><div><div class="rotulo">Propuesta</div><div class="valor">${esc(config.recomendaciones[L.recomendacion])}</div></div>
      <div><div class="rotulo">Media de la rúbrica</div><div class="valor">${L.media != null ? dec(L.media) : "—"} <small>/ 10</small></div></div></div>
    <p class="sumario">${esc(L.motivo)}</p>
    <h4>Rúbrica</h4><div class="rubrica">${rubrica}</div>
    <div class="dos"><div><h4>Fortalezas</h4>${lista(L.fortalezas)}</div><div><h4>Debilidades</h4>${lista(L.debilidades)}</div></div>
    ${arco}
    <h4>Borrador de informe de lectura</h4><p class="texto-largo">${esc(L.informe)}</p>
    <h4>Versión para el autor <button type="button" class="ver-mas" id="copiar-autor">Copiar</button></h4><p class="texto-largo">${esc(L.para_el_autor)}</p>
    <p class="ayuda">${num(L.tokens_entrada)} tokens de entrada y ${num(L.tokens_salida)} de salida${L.coste_usd != null ? ` · unos ${dec(L.coste_usd)} $` : ""} · ${L.segundos} s</p>
    ${boton}</section>`;
}

// Pista flotante de las gráficas.
const pista = document.createElement("div");
pista.className = "pista";
pista.hidden = true;
document.body.append(pista);
document.addEventListener("mousemove", (e) => {
  const marca = e.target.closest?.("[data-pista]");
  pista.hidden = !marca;
  if (!marca) return;
  pista.textContent = marca.dataset.pista;
  pista.style.left = `${Math.min(e.clientX + 12, innerWidth - pista.offsetWidth - 8)}px`;
  pista.style.top = `${e.clientY - 34}px`;
});

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
  if (e.target.id === "imprimir") return window.print();
  if (e.target.id === "pedir-lectura") {
    e.target.disabled = true;
    try { await api(`/api/manuscritos/${m.id}/lectura`, { method: "POST" }); } catch (err) { alert(err.message); }
    return cargar();
  }
  if (e.target.id === "copiar-autor") {
    await navigator.clipboard.writeText(m.lectura.para_el_autor);
    e.target.textContent = "Copiado";
    return;
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
