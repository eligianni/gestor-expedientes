/* Gestor de expedientes de pago — interfaz sin framework.
 * Toda llamada a la API pasa por api(). Los datos se insertan con textContent, nunca con innerHTML. */
"use strict";

const MENSAJE_CONFLICTO = "Otra persona guardó cambios en este registro. Recargá para ver la última versión.";

const estado = {
  pantalla: "pantalla-inicio",
  efector: "HBI",
  recargar: null, // función que vuelve a pedir lo que hay en pantalla (botón Recargar ante un 409)
};

// --- Utilidades de DOM ------------------------------------------------------

function el(etiqueta, atributos, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "texto") nodo.textContent = valor;
    else if (clave === "clase") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else nodo.setAttribute(clave, valor === true ? "" : valor);
  }
  for (const hijo of hijos) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

function vaciar(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.filter((h) => h !== null && h !== undefined && h !== false));
}

function cargando(nodo) {
  vaciar(nodo, el("p", { texto: "Cargando…" }));
}

function tabla(encabezados, filas, clasesColumnas) {
  const thead = el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", texto: t }))));
  const tbody = el("tbody", {}, ...filas.map((fila) => el("tr", {},
    ...fila.map((valor, i) => el("td", { clase: (clasesColumnas && clasesColumnas[i]) || null, texto: valor ?? "" })))));
  return el("div", { clase: "tabla-desplazable" }, el("table", {}, thead, tbody));
}

function formatoFechaHora(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

// --- Avisos -----------------------------------------------------------------

function mostrarAviso(texto, tipo, accion) {
  const avisos = document.getElementById("avisos");
  const mensaje = el("div", { clase: "mensaje mensaje-" + (tipo || "error"), role: tipo === "error" ? "alert" : null },
    el("p", { texto }));
  if (accion) mensaje.append(el("button", { type: "button", texto: accion.texto, onclick: accion.alHacerClic }));
  mensaje.append(el("button", { type: "button", clase: "secundario", texto: "Cerrar", "aria-label": "Cerrar mensaje",
    onclick: () => mensaje.remove() }));
  avisos.append(mensaje);
  return mensaje;
}

function limpiarAvisos() {
  vaciar(document.getElementById("avisos"));
}

// --- API --------------------------------------------------------------------

/** Llama a la API. Devuelve `datos` o null si hubo error (el error ya se mostró en #avisos). */
async function api(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: {} };
  if (cuerpo instanceof FormData) {
    opciones.body = cuerpo;
  } else if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json; charset=utf-8";
    opciones.body = JSON.stringify(cuerpo);
  }
  let respuesta;
  let datos;
  try {
    respuesta = await fetch(ruta, opciones);
    datos = await respuesta.json();
  } catch (error) {
    mostrarAviso("No se pudo comunicar con el programa. ¿Sigue abierto?", "error");
    return null;
  }
  if (respuesta.status === 409) {
    const mensaje = (datos && datos.error && datos.error.mensaje) || MENSAJE_CONFLICTO;
    mostrarAviso(mensaje, "error", {
      texto: "Recargar",
      alHacerClic: () => { limpiarAvisos(); if (estado.recargar) estado.recargar(); },
    });
    return null;
  }
  if (!datos || datos.ok === false) {
    const mensaje = (datos && datos.error && datos.error.mensaje) || ("Error " + respuesta.status);
    mostrarAviso(mensaje, "error");
    return null;
  }
  return datos.ok === true ? datos.datos : datos;
}

// --- Navegación -------------------------------------------------------------

const AL_MOSTRAR = {
  "pantalla-inicio": cargarInicio,
  "pantalla-oc": cargarOC,
  "pantalla-expedientes": cargarExpedientes,
  "pantalla-importar": cargarImportar,
};

function mostrarPantalla(id, enfocar) {
  if (!document.getElementById(id)) id = "pantalla-inicio";
  estado.pantalla = id;
  estado.recargar = AL_MOSTRAR[id] || null;
  for (const seccion of document.querySelectorAll("main > section")) {
    seccion.hidden = seccion.id !== id;
  }
  for (const boton of document.querySelectorAll(".menu button[data-pantalla]")) {
    if (boton.dataset.pantalla === id) boton.setAttribute("aria-current", "page");
    else boton.removeAttribute("aria-current");
  }
  limpiarAvisos();
  if (history.replaceState) history.replaceState(null, "", "#" + id);
  if (AL_MOSTRAR[id]) AL_MOSTRAR[id]();
  if (enfocar) {
    const titulo = document.querySelector("#" + id + " h1");
    if (titulo) { titulo.setAttribute("tabindex", "-1"); titulo.focus(); }
  }
}

function iniciarNavegacion() {
  for (const boton of document.querySelectorAll(".menu button[data-pantalla]")) {
    boton.addEventListener("click", () => mostrarPantalla(boton.dataset.pantalla, true));
  }
  const inicial = (location.hash || "").slice(1);
  mostrarPantalla(inicial.startsWith("pantalla-") ? inicial : "pantalla-inicio", false);
}

function iniciarEfector() {
  const selector = document.getElementById("selector-efector");
  try {
    const guardado = localStorage.getItem("gestor.efector");
    if (guardado && ["HBI", "CASPH", "Ambos"].includes(guardado)) estado.efector = guardado;
  } catch (error) { /* sin localStorage: queda HBI */ }
  selector.value = estado.efector;
  selector.addEventListener("change", () => {
    estado.efector = selector.value;
    try { localStorage.setItem("gestor.efector", estado.efector); } catch (error) { /* nada */ }
    if (estado.recargar) estado.recargar();
  });
}

// --- Inicio -----------------------------------------------------------------

async function cargarInicio() {
  const contenedor = document.getElementById("inicio-estado");
  cargando(contenedor);
  const salud = await api("GET", "/api/salud"); // única ruta sin sobre: api() la devuelve tal cual
  if (!salud) { vaciar(contenedor); return; }
  if (salud.db !== "ok") {
    vaciar(contenedor, el("div", { clase: "mensaje mensaje-error", role: "alert" },
      el("p", { texto: "No se pudo abrir la base de datos. Revisá la ubicación en Configuración." })));
    return;
  }
  const base = await api("GET", "/api/base/estado");
  if (!base) { vaciar(contenedor); return; }
  const partes = [];
  if (base.integridad !== "ok") {
    partes.push(el("div", { clase: "mensaje mensaje-error", role: "alert" },
      el("p", { texto: "La base de datos tiene un problema de integridad." }),
      el("button", { type: "button", texto: "Restaurar la última copia", onclick: restaurarUltimaCopia })));
  }
  partes.push(el("p", { texto: "Usuario: " + salud.usuario }));
  partes.push(el("p", { texto: base.ultimo_backup
    ? "Última copia de seguridad: " + base.ultimo_backup
    : "Todavía no hay copias de seguridad." }));
  vaciar(contenedor, ...partes);
}

async function restaurarUltimaCopia() {
  if (!window.confirm("¿Restaurar la última copia de seguridad? Se pierden los cambios posteriores a esa copia.")) return;
  const datos = await api("POST", "/api/base/restaurar", {});
  if (datos) {
    mostrarAviso("Se restauró la copia " + datos.restaurado + ".", "exito");
    cargarInicio();
  }
}

// --- Importar ---------------------------------------------------------------

const ETIQUETAS_DESCARTE = {
  sin_oc: "Sin N° de OC (vacías o subtotales)",
  partida: "Partida excluida (honorarios)",
  centro: "Centro de otro efector",
  exclusion_manual: "Exclusión manual (SAP u OC)",
};

const importar = { vistaPrevia: null, archivo: null, efector: null };

function formularioImportacion() {
  const archivo = document.getElementById("importar-archivo").files[0];
  const efector = document.getElementById("importar-efector").value;
  if (!archivo) {
    mostrarAviso("Elegí el archivo z_compras2 (.xlsx) a importar.", "error");
    return null;
  }
  const datos = new FormData();
  datos.append("efector", efector);
  datos.append("archivo", archivo, archivo.name);
  return { datos, archivo, efector };
}

function pintarInforme(informe, confirmado) {
  const contenedor = document.getElementById("importar-resultado");
  const partes = [el("h2", { texto: confirmado ? "Importación realizada" : "Vista previa" })];
  const filas = [["Filas del reporte", informe.filas]];
  for (const [motivo, etiqueta] of Object.entries(ETIQUETAS_DESCARTE)) {
    filas.push(["Descartadas: " + etiqueta, informe.descartes[motivo]]);
  }
  filas.push(
    ["Quedan", informe.quedan],
    ["OC distintas", informe.oc_distintas],
    ["Posiciones repetidas en el reporte", informe.duplicados],
    [confirmado ? "Renglones nuevos" : "Renglones nuevos (a crear)", informe.altas],
    [confirmado ? "Renglones actualizados" : "Renglones que cambian", informe.actualizadas],
    ["Renglones sin cambios", informe.sin_cambios],
  );
  partes.push(tabla(["Concepto", "Cantidad"], filas, [null, "numero"]));

  if (informe.avisos.length) {
    partes.push(el("h3", { texto: "Avisos" }));
    partes.push(el("ul", { clase: "lista-avisos" }, ...informe.avisos.map((a) => el("li", { texto: a }))));
  }
  if (informe.errores.length) {
    partes.push(el("h3", { texto: "Filas con errores (no se importan)" }));
    partes.push(tabla(["Fila", "OC", "Problema"], informe.errores.map((e) => [e.fila, e.oc, e.mensaje]), ["numero"]));
  }
  if (informe.cambios.length) {
    partes.push(el("h3", { texto: "Cambios contra lo que ya estaba cargado" }));
    partes.push(tabla(["OC", "Posición", "Campo", "Antes", "Después"],
      informe.cambios.map((c) => [c.oc, c.pos ?? "", c.campo, c.antes ?? "", c.despues ?? ""])));
  }
  vaciar(contenedor, el("div", { clase: "panel" }, ...partes));
}

async function vistaPreviaImportacion(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const formulario = formularioImportacion();
  if (!formulario) return;
  const botonConfirmar = document.getElementById("importar-confirmar");
  botonConfirmar.disabled = true;
  const contenedor = document.getElementById("importar-resultado");
  cargando(contenedor);
  const informe = await api("POST", "/api/importar/vista-previa", formulario.datos);
  if (!informe) { vaciar(contenedor); return; }
  importar.vistaPrevia = informe;
  importar.archivo = formulario.archivo;
  importar.efector = formulario.efector;
  pintarInforme(informe, false);
  botonConfirmar.disabled = false;
}

async function confirmarImportacion() {
  limpiarAvisos();
  const formulario = formularioImportacion();
  if (!formulario) return;
  if (formulario.archivo !== importar.archivo || formulario.efector !== importar.efector) {
    mostrarAviso("Cambiaste el archivo o el efector: volvé a hacer la vista previa antes de confirmar.", "aviso");
    document.getElementById("importar-confirmar").disabled = true;
    return;
  }
  const botonConfirmar = document.getElementById("importar-confirmar");
  botonConfirmar.disabled = true;
  const informe = await api("POST", "/api/importar/confirmar", formulario.datos);
  if (!informe) { botonConfirmar.disabled = false; return; }
  pintarInforme(informe, true);
  mostrarAviso("Importación realizada: " + informe.altas + " renglones nuevos y " + informe.actualizadas + " actualizados.", "exito");
  importar.vistaPrevia = null;
  cargarHistorial();
}

async function revisarCentros() {
  const efector = document.getElementById("importar-efector").value;
  const bloque = document.getElementById("importar-centros");
  if (efector !== "CASPH") { bloque.hidden = true; return; }
  const datos = await api("GET", "/api/parametros");
  if (!datos) return;
  const centros = (((datos.parametros.efectores || {}).CASPH || {}).centros) || [];
  bloque.hidden = centros.length > 0;
}

async function guardarCentros() {
  limpiarAvisos();
  const texto = document.getElementById("importar-centros-valor").value;
  const centros = texto.split(",").map((c) => c.trim()).filter((c) => c);
  if (!centros.length || centros.some((c) => !/^\d+$/.test(c))) {
    mostrarAviso("Escribí los centros SAP como números separados por coma (por ejemplo 2100, 2101).", "error");
    return;
  }
  const datos = await api("GET", "/api/parametros");
  if (!datos) return;
  const efectores = JSON.parse(JSON.stringify(datos.parametros.efectores));
  efectores.CASPH.centros = centros;
  const guardado = await api("PUT", "/api/parametros",
    { clave: "efectores", valor: efectores, version: datos.versiones.efectores });
  if (guardado) {
    mostrarAviso("Centros de CASPH guardados.", "exito");
    revisarCentros();
  }
}

async function cargarHistorial() {
  const contenedor = document.getElementById("importar-historial");
  cargando(contenedor);
  const lista = await api("GET", "/api/importaciones");
  if (!lista) { vaciar(contenedor); return; }
  if (!lista.length) {
    vaciar(contenedor, el("p", { clase: "texto-suave", texto: "Todavía no se importó ningún reporte." }));
    return;
  }
  vaciar(contenedor, tabla(["Fecha", "Archivo", "Efector", "Usuario"],
    lista.map((i) => [formatoFechaHora(i.fecha), i.archivo, i.efector, i.usuario])));
}

function cargarImportar() {
  const selectorEfector = document.getElementById("importar-efector");
  if (estado.efector === "HBI" || estado.efector === "CASPH") selectorEfector.value = estado.efector;
  revisarCentros();
  cargarHistorial();
}

function iniciarImportar() {
  document.getElementById("form-importar").addEventListener("submit", vistaPreviaImportacion);
  document.getElementById("importar-confirmar").addEventListener("click", confirmarImportacion);
  document.getElementById("importar-efector").addEventListener("change", () => {
    document.getElementById("importar-confirmar").disabled = true;
    revisarCentros();
  });
  document.getElementById("importar-archivo").addEventListener("change", () => {
    document.getElementById("importar-confirmar").disabled = true;
  });
  document.getElementById("importar-centros-guardar").addEventListener("click", guardarCentros);
}

// --- Montos (sin float: todo en centavos enteros) ---------------------------

function formatoPesos(centavos) {
  if (centavos === null || centavos === undefined || centavos === "") return "";
  const negativo = centavos < 0;
  const absoluto = Math.abs(Math.trunc(centavos));
  const pesos = Math.floor(absoluto / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const resto = String(absoluto % 100).padStart(2, "0");
  return (negativo ? "-" : "") + pesos + "," + resto;
}

/** "1.224.990,50" o "1224990.50" → 122499050; "" → null; inválido → NaN. */
function pesosACentavos(texto) {
  let t = String(texto ?? "").trim().replace(/\$|\s/g, "");
  if (!t) return null;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(t);
  if (!m) return NaN;
  return Number(m[1]) * 100 + Number((m[2] || "0").padEnd(2, "0"));
}

function campoFormulario(id, etiqueta, control, ayuda) {
  control.id = id;
  const partes = [el("label", { for: id, texto: etiqueta }), control];
  if (ayuda) {
    control.setAttribute("aria-describedby", id + "-ayuda");
    partes.push(el("p", { id: id + "-ayuda", clase: "texto-suave", texto: ayuda }));
  }
  return el("div", { clase: "campo" }, ...partes);
}

function entrada(valor, atributos) {
  const nodo = el("input", Object.assign({ type: "text" }, atributos || {}));
  nodo.value = valor ?? "";
  return nodo;
}

function selector(valor, opciones) {
  const nodo = el("select", {}, ...opciones.map(([v, t]) => el("option", { value: v, texto: t })));
  nodo.value = valor ?? opciones[0][0];
  return nodo;
}

function casilla(id, etiqueta, marcada) {
  const control = el("input", { type: "checkbox", id });
  control.checked = !!marcada;
  return el("div", { clase: "campo campo-casilla" }, control, el("label", { for: id, texto: etiqueta }));
}

// --- Órdenes de compra -------------------------------------------------------

const ocEstado = { ficha: null };

function contenedorOC() {
  const seccion = document.getElementById("pantalla-oc");
  let raiz = document.getElementById("oc-raiz");
  if (!raiz) {
    for (const p of seccion.querySelectorAll(":scope > p")) p.remove();
    const buscar = entrada("", { id: "oc-buscar", type: "search", placeholder: "N° de OC, SAP, proveedor u objeto" });
    const filtros = el("form", { clase: "panel formulario", id: "oc-filtros", onsubmit: (e) => { e.preventDefault(); listarOC(); } },
      el("div", { clase: "campo" }, el("label", { for: "oc-buscar", texto: "Buscar" }), buscar),
      casilla("oc-excluidas", "Mostrar también las OC excluidas", false),
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Buscar" }),
        el("button", { type: "button", clase: "secundario", texto: "Nueva OC manual", onclick: mostrarAltaOC })));
    raiz = el("div", { id: "oc-raiz" }, filtros, el("div", { id: "oc-detalle" }), el("div", { id: "oc-lista" }));
    seccion.append(raiz);
  }
  return raiz;
}

function cargarOC() {
  contenedorOC();
  if (ocEstado.ficha) {
    abrirFichaOC(ocEstado.ficha.oc.numero);
  } else {
    listarOC();
  }
}

async function listarOC() {
  contenedorOC();
  const lista = document.getElementById("oc-lista");
  cargando(lista);
  const parametros = new URLSearchParams();
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  const texto = document.getElementById("oc-buscar").value.trim();
  if (texto) parametros.set("q", texto);
  if (document.getElementById("oc-excluidas").checked) parametros.set("excluidas", "1");
  const ocs = await api("GET", "/api/oc?" + parametros.toString());
  if (!ocs) { vaciar(lista); return; }
  if (!ocs.length) {
    vaciar(lista, el("p", { clase: "texto-suave", texto: texto
      ? "No hay OC que coincidan con la búsqueda."
      : "Todavía no hay OC. Importá un z_compras2 desde la pantalla Importar." }));
    return;
  }
  const filas = ocs.map((oc) => {
    const marcas = [oc.tipo, oc.comodato ? "comodato" : "", oc.centralizada ? "centralizada" : "",
      oc.excluida ? "EXCLUIDA" : "", oc.origen === "MANUAL" ? "manual" : ""].filter(Boolean).join(" · ");
    return el("tr", {},
      el("td", {}, el("button", { type: "button", clase: "secundario", texto: oc.numero,
        "aria-label": "Ver la OC " + oc.numero, onclick: () => abrirFichaOC(oc.numero) })),
      el("td", { texto: oc.efector }),
      el("td", { texto: oc.razon_social + " (SAP " + oc.sap + ")" }),
      el("td", { texto: oc.objeto || "—" }),
      el("td", { texto: marcas }),
      el("td", { texto: (oc.vig_desde || "") + (oc.vig_hasta ? " a " + oc.vig_hasta : " (sin fin)") }),
      el("td", { clase: "numero", texto: oc.renglones }),
      el("td", { clase: "numero", texto: formatoPesos(oc.importe_centavos) }));
  });
  const encabezados = ["OC", "Efector", "Proveedor", "Objeto", "Tipo", "Vigencia", "Renglones", "Importe $"];
  vaciar(lista,
    el("p", { clase: "texto-suave", texto: ocs.length + (ocs.length === 1 ? " OC" : " OC") }),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filas))));
}

async function abrirFichaOC(numero) {
  contenedorOC();
  const detalle = document.getElementById("oc-detalle");
  cargando(detalle);
  const ficha = await api("GET", "/api/oc/" + encodeURIComponent(numero));
  if (!ficha) { vaciar(detalle); return; }
  ocEstado.ficha = ficha;
  pintarFichaOC(ficha);
  const titulo = document.getElementById("oc-ficha-titulo");
  if (titulo) titulo.focus();
}

function cerrarFichaOC() {
  ocEstado.ficha = null;
  vaciar(document.getElementById("oc-detalle"));
  listarOC();
}

const CAMPOS_OC_FORM = [
  ["objeto", "Objeto (como va en la autorización)", "texto"],
  ["objeto_articulo", "Artículo del objeto", "articulo"],
  ["concepto_corto", "Concepto corto (Texto SAP)", "texto"],
  ["dia_inicio_periodo", "Día de inicio del período (1 = mes calendario)", "dia"],
  ["tipo", "Tipo", "tipo"],
  ["comodato", "Tiene equipo en comodato", "casilla"],
  ["centralizada", "Es centralizada", "casilla"],
  ["ca", "CA (licitación-año)", "texto"],
  ["expediente_contratacion", "Expediente de contratación (GDE)", "gde"],
  ["gde_pdf_oc", "N° GDE del PDF de la OC", "gde"],
  ["leyenda_cv", "Leyenda del CV", "texto"],
  ["vig_desde", "Vigencia desde", "fecha"],
  ["vig_hasta", "Vigencia hasta", "fecha"],
  ["prorroga", "Prórroga hasta", "fecha"],
  ["excluida", "Excluir esta OC (no aparece en las listas)", "casilla"],
  ["motivo_exclusion", "Motivo de la exclusión", "texto"],
];

function controlCampoOC(campo, tipo, valor) {
  const id = "oc-campo-" + campo;
  if (tipo === "casilla") return casilla(id, null, valor);
  let control;
  if (tipo === "articulo") control = selector(valor, [["al", "al"], ["a la", "a la"], ["a los", "a los"], ["a las", "a las"]]);
  else if (tipo === "tipo") control = selector(valor, [["SERVICIO", "Servicio"], ["BIEN", "Bien"], ["PROVISION", "Provisión"]]);
  else if (tipo === "dia") control = entrada(valor, { type: "number", min: "1", max: "28", inputmode: "numeric" });
  else if (tipo === "fecha") control = entrada(valor, { type: "date" });
  else control = entrada(valor, tipo === "gde" ? { clase: "mono" } : {});
  control.id = id;
  return control;
}

function valorCampoOC(campo, tipo) {
  const control = document.getElementById("oc-campo-" + campo);
  if (tipo === "casilla") return control.checked ? 1 : 0;
  if (tipo === "dia") return control.value === "" ? null : Number(control.value);
  if (tipo === "fecha") return control.value || null;
  return control.value;
}

function pintarFichaOC(ficha) {
  const { oc, proveedor, renglones, expedientes } = ficha;
  const manuales = new Set(oc.campos_manuales || []);
  const campos = CAMPOS_OC_FORM.map(([campo, etiqueta, tipo]) => {
    const control = controlCampoOC(campo, tipo, oc[campo]);
    const texto = etiqueta + (manuales.has(campo) ? " (editado a mano)" : "");
    if (tipo === "casilla") {
      control.querySelector("label").textContent = texto;
      return control;
    }
    return el("div", { clase: "campo" }, el("label", { for: control.id, texto }), control);
  });
  const formulario = el("form", { clase: "formulario", onsubmit: guardarOC, novalidate: true },
    el("h3", { texto: "Datos que se cargan a mano" }),
    el("p", { clase: "texto-suave", texto: "Lo que edites acá queda marcado y la importación del z_compras2 no lo vuelve a pisar." }),
    ...campos,
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar cambios de la OC" })));

  const filasRenglones = renglones.map((r) => el("tr", {},
    el("td", { clase: "numero", texto: r.pos }),
    el("td", { texto: (r.codigo ? r.codigo + " · " : "") + r.descripcion }),
    el("td", { clase: "numero", texto: r.cantidad + (r.unidad ? " " + r.unidad : "") }),
    el("td", { clase: "numero", texto: formatoPesos(r.precio_centavos) }),
    el("td", { clase: "numero", texto: formatoPesos(r.importe_centavos) }),
    el("td", { texto: r.desglose_cantidad ? r.desglose_cantidad + " " + r.desglose_unidad + " × $ " + formatoPesos(r.desglose_precio_centavos)
      : (r.revisar_desglose ? "Revisar desglose" : "—") }),
    el("td", { clase: "numero", texto: r.sap_entregado + " / " + r.sap_por_entregar + (r.exceso_sap ? " (exceso)" : "") }),
    el("td", { clase: "numero", texto: r.consumo_previo }),
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Editar",
      "aria-label": "Editar el renglón " + r.pos, onclick: () => editarRenglon(r) }))));
  const encabezadosRenglones = ["Pos.", "Descripción", "Cantidad", "Precio $", "Importe $", "Desglose",
    "Entregado / por entregar (SAP)", "Consumo previo", ""];

  const partes = [
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "Volver a la lista", onclick: cerrarFichaOC })),
    el("h2", { id: "oc-ficha-titulo", tabindex: "-1", texto: "OC " + oc.numero + " — " + (proveedor ? proveedor.razon_social : "") }),
    el("p", { texto: "Efector " + oc.efector + " · SAP " + oc.sap + " · " + (oc.origen === "MANUAL" ? "cargada a mano" : "importada de SAP")
      + (oc.fecha_oc ? " · fecha OC " + oc.fecha_oc : "") + (oc.cerrada_sap ? " · cerrada en SAP" : "") }),
    formulario,
    el("h3", { texto: "Renglones" }),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...encabezadosRenglones.map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filasRenglones))),
    el("div", { id: "oc-renglon-edicion" }),
  ];
  if (oc.origen === "MANUAL") {
    partes.push(el("button", { type: "button", clase: "secundario", texto: "Agregar renglón", onclick: () => editarRenglon(null) }));
  }
  partes.push(el("h3", { texto: "Expedientes de esta OC" }));
  partes.push(expedientes.length
    ? tabla(["N°", "Tipo", "Período", "Estado", "Factura"], expedientes.map((x) => [x.id, x.tipo, x.periodo || "", x.estado, x.factura]))
    : el("p", { clase: "texto-suave", texto: "Todavía no hay expedientes para esta OC." }));
  vaciar(document.getElementById("oc-detalle"), el("div", { clase: "panel" }, ...partes));
}

async function guardarOC(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const { oc } = ocEstado.ficha;
  const cambios = {};
  for (const [campo, , tipo] of CAMPOS_OC_FORM) {
    const valor = valorCampoOC(campo, tipo);
    const actual = oc[campo] ?? (tipo === "fecha" || tipo === "dia" ? null : "");
    if (valor !== actual) cambios[campo] = valor;
  }
  if (!Object.keys(cambios).length) {
    mostrarAviso("No hay cambios para guardar.", "aviso");
    return;
  }
  estado.recargar = () => abrirFichaOC(oc.numero);
  const ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero), { version: oc.version, cambios });
  if (!ficha) return;
  ocEstado.ficha = ficha;
  pintarFichaOC(ficha);
  mostrarAviso("Cambios de la OC " + oc.numero + " guardados.", "exito");
}

function editarRenglon(renglon) {
  const nuevo = renglon === null;
  const r = renglon || {};
  const contenedor = document.getElementById("oc-renglon-edicion");
  const campos = [];
  if (nuevo) {
    campos.push(
      campoFormulario("rg-descripcion", "Descripción", entrada("")),
      campoFormulario("rg-codigo", "Código (vacío si es un servicio)", entrada("")),
      campoFormulario("rg-cantidad", "Cantidad", entrada("1", { inputmode: "decimal" })),
      campoFormulario("rg-unidad", "Unidad", entrada("UN")),
      campoFormulario("rg-precio", "Precio unitario $", entrada("", { inputmode: "decimal" }), "Por ejemplo 1.224.990,00"));
  }
  campos.push(
    campoFormulario("rg-desglose-cantidad", "Desglose: cantidad (por ejemplo 9 meses)", entrada(r.desglose_cantidad, { inputmode: "decimal" })),
    campoFormulario("rg-desglose-unidad", "Desglose: unidad", entrada(r.desglose_unidad || (nuevo ? "" : ""))),
    campoFormulario("rg-desglose-precio", "Desglose: precio por unidad $", entrada(formatoPesos(r.desglose_precio_centavos), { inputmode: "decimal" })),
    campoFormulario("rg-consumo", "Consumo previo al gestor", entrada(r.consumo_previo ?? "0", { inputmode: "decimal" })),
    casilla("rg-correctivo", "Es un renglón de mantenimiento correctivo", r.es_correctivo));
  const formulario = el("form", { clase: "panel formulario", novalidate: true,
    onsubmit: (e) => { e.preventDefault(); guardarRenglon(renglon); } },
    el("h3", { id: "rg-titulo", tabindex: "-1", texto: nuevo ? "Nuevo renglón" : "Renglón " + r.pos + ": " + r.descripcion }),
    ...campos,
    el("div", { clase: "acciones" },
      el("button", { type: "submit", texto: nuevo ? "Agregar renglón" : "Guardar renglón" }),
      el("button", { type: "button", clase: "secundario", texto: "Cancelar", onclick: () => vaciar(contenedor) })));
  vaciar(contenedor, formulario);
  document.getElementById("rg-titulo").focus();
}

async function guardarRenglon(renglon) {
  limpiarAvisos();
  const { oc } = ocEstado.ficha;
  const valor = (id) => document.getElementById(id).value.trim();
  const precioDesglose = pesosACentavos(valor("rg-desglose-precio"));
  if (Number.isNaN(precioDesglose)) { mostrarAviso("El precio del desglose no es un importe válido.", "error"); return; }
  const datos = {
    desglose_cantidad: valor("rg-desglose-cantidad") || null,
    desglose_unidad: valor("rg-desglose-unidad") || null,
    desglose_precio_centavos: precioDesglose,
    consumo_previo: valor("rg-consumo") || "0",
    es_correctivo: document.getElementById("rg-correctivo").checked ? 1 : 0,
  };
  estado.recargar = () => abrirFichaOC(oc.numero);
  let ficha;
  if (renglon === null) {
    const precio = pesosACentavos(valor("rg-precio"));
    if (precio === null || Number.isNaN(precio)) { mostrarAviso("Escribí el precio unitario del renglón.", "error"); return; }
    if (datos.desglose_cantidad === null) { delete datos.desglose_cantidad; delete datos.desglose_unidad; delete datos.desglose_precio_centavos; }
    Object.assign(datos, { descripcion: valor("rg-descripcion"), codigo: valor("rg-codigo"), cantidad: valor("rg-cantidad"),
      unidad: valor("rg-unidad"), precio_centavos: precio });
    ficha = await api("POST", "/api/oc/" + encodeURIComponent(oc.numero) + "/renglones", datos);
  } else {
    const cambios = {};
    for (const [campo, nuevoValor] of Object.entries(datos)) {
      if ((renglon[campo] ?? null) !== nuevoValor) cambios[campo] = nuevoValor;
    }
    if (!Object.keys(cambios).length) { mostrarAviso("No hay cambios para guardar.", "aviso"); return; }
    ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero) + "/renglones/" + renglon.pos,
      { version: renglon.version, cambios });
  }
  if (!ficha) return;
  ocEstado.ficha = ficha;
  pintarFichaOC(ficha);
  mostrarAviso("Renglón guardado.", "exito");
}

function mostrarAltaOC() {
  limpiarAvisos();
  ocEstado.ficha = null;
  const detalle = document.getElementById("oc-detalle");
  const efector = estado.efector === "CASPH" ? "CASPH" : "HBI";
  const formulario = el("form", { clase: "panel formulario", novalidate: true, onsubmit: crearOC },
    el("h2", { id: "oc-alta-titulo", tabindex: "-1", texto: "Nueva OC cargada a mano" }),
    el("p", { clase: "texto-suave", texto: "Para OC que todavía no aparecen en el z_compras2. Todos los datos quedan como cargados a mano." }),
    campoFormulario("alta-numero", "N° de OC", entrada("", { inputmode: "numeric" })),
    campoFormulario("alta-efector", "Efector", selector(efector, [["HBI", "HBI"], ["CASPH", "CASPH"]])),
    campoFormulario("alta-sap", "N° SAP del proveedor", entrada("", { inputmode: "numeric" })),
    campoFormulario("alta-razon", "Razón social (si el proveedor es nuevo)", entrada("")),
    campoFormulario("alta-fecha", "Fecha de la OC", entrada("", { type: "date" })),
    campoFormulario("alta-desde", "Vigencia desde", entrada("", { type: "date" })),
    campoFormulario("alta-hasta", "Vigencia hasta", entrada("", { type: "date" })),
    campoFormulario("alta-ca", "CA (licitación-año, por ejemplo 195-2025)", entrada("")),
    campoFormulario("alta-expediente", "Expediente de contratación (GDE)", entrada("", { clase: "mono" })),
    campoFormulario("alta-objeto", "Objeto", entrada("")),
    campoFormulario("alta-articulo", "Artículo del objeto", selector("al", [["al", "al"], ["a la", "a la"], ["a los", "a los"], ["a las", "a las"]])),
    campoFormulario("alta-concepto", "Concepto corto (Texto SAP)", entrada("")),
    campoFormulario("alta-dia", "Día de inicio del período", entrada("1", { type: "number", min: "1", max: "28" })),
    el("h3", { texto: "Renglón 1" }),
    campoFormulario("alta-descripcion", "Descripción", entrada("")),
    campoFormulario("alta-cantidad", "Cantidad", entrada("1", { inputmode: "decimal" })),
    campoFormulario("alta-precio", "Precio unitario $", entrada("", { inputmode: "decimal" })),
    campoFormulario("alta-desglose-cantidad", "Desglose: cantidad (opcional, por ejemplo 9)", entrada("", { inputmode: "decimal" })),
    campoFormulario("alta-desglose-unidad", "Desglose: unidad", entrada("MES")),
    campoFormulario("alta-desglose-precio", "Desglose: precio por unidad $", entrada("", { inputmode: "decimal" })),
    el("div", { clase: "acciones" },
      el("button", { type: "submit", texto: "Crear OC" }),
      el("button", { type: "button", clase: "secundario", texto: "Cancelar", onclick: () => vaciar(detalle) })));
  vaciar(detalle, formulario);
  document.getElementById("oc-alta-titulo").focus();
}

async function crearOC(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const valor = (id) => document.getElementById(id).value.trim();
  const precio = pesosACentavos(valor("alta-precio"));
  const precioDesglose = pesosACentavos(valor("alta-desglose-precio"));
  if (precio === null || Number.isNaN(precio)) { mostrarAviso("Escribí el precio unitario del renglón 1.", "error"); return; }
  if (Number.isNaN(precioDesglose)) { mostrarAviso("El precio del desglose no es un importe válido.", "error"); return; }
  const renglon = { pos: 1, descripcion: valor("alta-descripcion"), cantidad: valor("alta-cantidad") || "1", precio_centavos: precio };
  if (valor("alta-desglose-cantidad")) {
    Object.assign(renglon, { desglose_cantidad: valor("alta-desglose-cantidad"),
      desglose_unidad: valor("alta-desglose-unidad") || "MES", desglose_precio_centavos: precioDesglose });
  }
  const datos = {
    numero: valor("alta-numero"), efector: valor("alta-efector"), sap: valor("alta-sap"), razon_social: valor("alta-razon"),
    fecha_oc: valor("alta-fecha") || null, vig_desde: valor("alta-desde") || null, vig_hasta: valor("alta-hasta") || null,
    ca: valor("alta-ca"), expediente_contratacion: valor("alta-expediente"), objeto: valor("alta-objeto"),
    objeto_articulo: valor("alta-articulo"), concepto_corto: valor("alta-concepto"),
    dia_inicio_periodo: Number(valor("alta-dia") || "1"), renglones: [renglon],
  };
  const ficha = await api("POST", "/api/oc", datos);
  if (!ficha) return;
  ocEstado.ficha = ficha;
  pintarFichaOC(ficha);
  mostrarAviso("OC " + ficha.oc.numero + " creada.", "exito");
  listarOC();
}

// --- Expedientes: lista ------------------------------------------------------

const ESTADOS_TEXTO = {
  BORRADOR: "Borrador", CONTROLADO: "Controlado", EN_FIRMA: "En firma", FIRMADO: "Firmado", ENVIADO: "Enviado",
  CONTABILIZADO: "Contabilizado", CERRADO: "Cerrado", PENDIENTE: "Pendiente", ANULADO: "Anulado",
};
const TIPOS_EXPEDIENTE = [["COMUN", "Común"], ["CENTRALIZADA", "Centralizada"], ["CORRECTIVO", "Correctivo"], ["EVENTUAL", "Pago eventual"]];

const expEstado = { exp: null, ficha: null, paso: 1, sugerido: null, fuera: [], sii: null };

function cargarExpedientes() {
  if (expEstado.exp) {
    abrirExpediente(expEstado.exp.id, expEstado.paso);
  } else {
    mostrarLista();
  }
}

function mostrarLista() {
  expEstado.exp = null;
  expEstado.ficha = null;
  document.getElementById("asistente").hidden = true;
  document.getElementById("expedientes-lista-bloque").hidden = false;
  estado.recargar = cargarExpedientes;
  listarExpedientes();
}

async function listarExpedientes() {
  const lista = document.getElementById("expedientes-lista");
  cargando(lista);
  const parametros = new URLSearchParams();
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  for (const [clave, id] of [["estado", "filtro-estado"], ["periodo", "filtro-periodo"], ["sap", "filtro-sap"]]) {
    const valor = document.getElementById(id).value.trim();
    if (valor) parametros.set(clave, valor);
  }
  const expedientes = await api("GET", "/api/expedientes?" + parametros.toString());
  if (!expedientes) { vaciar(lista); return; }
  if (!expedientes.length) {
    vaciar(lista, el("p", { clase: "texto-suave", texto: "No hay expedientes con esos filtros." }));
    return;
  }
  const encabezados = ["N°", "Tipo", "OC", "Proveedor", "Período", "Factura", "Estado"];
  const filas = expedientes.map((x) => el("tr", {},
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: String(x.id),
      "aria-label": "Abrir el expediente " + x.id, onclick: () => abrirExpediente(x.id, 1) })),
    el("td", { texto: x.tipo }),
    el("td", { texto: x.oc || "—" }),
    el("td", { texto: (x.razon_social || "") + (x.sap ? " (SAP " + x.sap + ")" : "") }),
    el("td", { texto: x.periodo || "—" }),
    el("td", { texto: x.factura || "—" }),
    el("td", { texto: ESTADOS_TEXTO[x.estado] || x.estado })));
  vaciar(lista,
    el("p", { clase: "texto-suave", texto: expedientes.length + (expedientes.length === 1 ? " expediente" : " expedientes") }),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filas))));
}

// --- Expedientes: asistente ------------------------------------------------

function mostrarAsistente() {
  document.getElementById("expedientes-lista-bloque").hidden = true;
  document.getElementById("asistente").hidden = false;
}

function pintarEncabezadoAsistente() {
  const { exp, ficha } = expEstado;
  const titulo = document.getElementById("asistente-titulo");
  const resumen = document.getElementById("asistente-resumen");
  if (!exp) {
    titulo.textContent = "Nuevo expediente";
    resumen.textContent = "Elegí el tipo y la OC para empezar.";
    return;
  }
  titulo.textContent = "Expediente " + exp.id + " — " + (exp.razon_social || "sin proveedor");
  resumen.textContent = [
    exp.oc ? "OC " + exp.oc : "sin OC",
    "período " + (exp.periodo || "sin definir") + (exp.periodo_manual ? " (manual)" : ""),
    "estado " + (ESTADOS_TEXTO[exp.estado] || exp.estado),
    ficha && ficha.oc.comodato ? "OC con comodato" : "",
  ].filter(Boolean).join(" · ");
}

function mostrarPaso(paso) {
  if (!expEstado.exp && paso !== 1) paso = 1;
  expEstado.paso = paso;
  for (let n = 1; n <= 7; n++) document.getElementById("asistente-paso-" + n).hidden = n !== paso;
  for (const boton of document.querySelectorAll(".pasos button[data-paso]")) {
    const n = Number(boton.dataset.paso);
    if (n === paso) boton.setAttribute("aria-current", "step"); else boton.removeAttribute("aria-current");
    boton.disabled = !expEstado.exp && n !== 1;
  }
  const pintores = { 1: pintarPaso1, 2: pintarPaso2, 3: pintarPaso3, 4: pintarPaso4, 5: pintarPaso5 };
  if (pintores[paso]) pintores[paso]();
}

function nuevoExpediente() {
  limpiarAvisos();
  expEstado.exp = null;
  expEstado.ficha = null;
  expEstado.sugerido = null;
  expEstado.fuera = [];
  expEstado.sii = null;
  mostrarAsistente();
  pintarEncabezadoAsistente();
  mostrarPaso(1);
  document.getElementById("asistente-titulo").focus();
}

async function abrirExpediente(id, paso) {
  mostrarAsistente();
  estado.recargar = () => abrirExpediente(id, expEstado.paso);
  const exp = await api("GET", "/api/expedientes/" + id);
  if (!exp) return;
  if (!expEstado.exp || expEstado.exp.id !== exp.id) {
    expEstado.sugerido = null;
    expEstado.fuera = [];
    expEstado.sii = null;
  }
  expEstado.exp = exp;
  expEstado.ficha = exp.oc ? await api("GET", "/api/oc/" + encodeURIComponent(exp.oc)) : null;
  pintarEncabezadoAsistente();
  mostrarPaso(paso || 1);
}

/** Guarda cambios del expediente con su versión; devuelve el expediente actualizado o null. */
async function guardarExpediente(cambios, mensaje) {
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, expEstado.paso);
  const actualizado = await api("PUT", "/api/expedientes/" + exp.id, { version: exp.version, cambios });
  if (!actualizado) return null;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  if (mensaje) mostrarAviso(mensaje, "exito");
  return actualizado;
}

// Paso 1: tipo, OC y período.

async function pintarPaso1() {
  const contenedor = document.getElementById("asistente-paso-1");
  const exp = expEstado.exp;
  if (!exp) {
    const parametros = new URLSearchParams();
    if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
    const ocs = (await api("GET", "/api/oc?" + parametros.toString())) || [];
    const opciones = el("datalist", { id: "lista-oc" },
      ...ocs.map((oc) => el("option", { value: oc.numero, texto: oc.numero + " — " + oc.razon_social + (oc.objeto ? " — " + oc.objeto : "") })));
    const formulario = el("form", { clase: "formulario", novalidate: true, onsubmit: crearExpediente },
      el("h3", { texto: "1. Tipo y OC" }),
      campoFormulario("nuevo-tipo", "Tipo de expediente", selector("COMUN", TIPOS_EXPEDIENTE)),
      campoFormulario("nuevo-oc", "N° de OC", entrada("", { list: "lista-oc", inputmode: "numeric", autocomplete: "off" }),
        "Escribí el número o elegilo de la lista."),
      opciones,
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Crear expediente" })));
    vaciar(contenedor, formulario);
    return;
  }
  const partes = [el("h3", { texto: "1. OC y período" })];
  const oc = expEstado.ficha ? expEstado.ficha.oc : null;
  partes.push(el("p", { texto: "Tipo " + exp.tipo + (oc ? " · OC " + oc.numero + " · " + (oc.objeto || "sin objeto cargado")
    + " · día de inicio del período " + oc.dia_inicio_periodo : "") }));
  partes.push(el("p", { texto: exp.periodo
    ? "Período: " + exp.periodo + " (del " + exp.periodo_desde + " al " + exp.periodo_hasta + ")"
      + (exp.periodo_manual ? " — corregido a mano" : " — sugerido por los remitos")
    : "Todavía no hay período: se sugiere solo al pegar los remitos (paso 2), o cargalo a mano." }));
  if (expEstado.sugerido && expEstado.sugerido.periodo !== exp.periodo) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" },
      el("p", { texto: "Según los remitos, el período sugerido es " + expEstado.sugerido.periodo + "." }),
      el("button", { type: "button", texto: "Usar " + expEstado.sugerido.periodo, onclick: async () => {
        limpiarAvisos();
        const s = expEstado.sugerido;
        if (await guardarExpediente({ periodo: s.periodo, periodo_desde: s.desde, periodo_hasta: s.hasta, periodo_manual: 0 },
          "Período " + s.periodo + " guardado.")) pintarPaso1();
      } })));
  }
  partes.push(el("form", { clase: "formulario", novalidate: true, onsubmit: corregirPeriodo },
    campoFormulario("exp-periodo", "Corregir el período (AAAA-MM)", entrada(exp.periodo || "", { inputmode: "numeric", clase: "entrada-corta" }),
      "Al corregirlo a mano queda fijo: pegar más remitos ya no lo cambia."),
    el("div", { clase: "acciones" },
      el("button", { type: "submit", texto: "Guardar período" }),
      el("button", { type: "button", clase: "secundario", texto: "Seguir al paso 2", onclick: () => mostrarPaso(2) }))));
  vaciar(contenedor, ...partes);
}

async function crearExpediente(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const datos = { tipo: document.getElementById("nuevo-tipo").value, oc: document.getElementById("nuevo-oc").value.trim() };
  const exp = await api("POST", "/api/expedientes", datos);
  if (!exp) return;
  mostrarAviso("Expediente " + exp.id + " creado.", "exito");
  await abrirExpediente(exp.id, 2);
}

async function corregirPeriodo(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const periodo = document.getElementById("exp-periodo").value.trim();
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(periodo)) {
    mostrarAviso("El período debe tener la forma AAAA-MM (por ejemplo 2026-08).", "error");
    return;
  }
  if (periodo === expEstado.exp.periodo) { mostrarAviso("No hay cambios para guardar.", "aviso"); return; }
  if (await guardarExpediente({ periodo }, "Período " + periodo + " guardado (corregido a mano).")) pintarPaso1();
}

// Paso 2: remitos.

function pintarPaso2() {
  const contenedor = document.getElementById("asistente-paso-2");
  const exp = expEstado.exp;
  const renglones = expEstado.ficha ? expEstado.ficha.renglones : [];
  const partes = [
    el("h3", { texto: "2. Remitos" }),
    el("form", { clase: "formulario", novalidate: true, onsubmit: pegarRemitos },
      el("div", { clase: "campo campo-ancho" },
        el("label", { for: "remitos-texto", texto: "Pegar remitos, uno por línea: numero;fecha[;fecha_firma]" }),
        el("textarea", { id: "remitos-texto", rows: "6", spellcheck: "false", "aria-describedby": "remitos-ayuda" }),
        el("p", { id: "remitos-ayuda", clase: "texto-suave", texto: "Por ejemplo 0001-00003354;25/08/2026 o 0001-00000002;28/08/2026;02/09/2026. Un número que ya está reemplaza al anterior." })),
      casilla("remitos-equipo", "Son remitos del equipo en comodato", false),
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Agregar remitos" }))),
  ];
  if (expEstado.fuera.length) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" },
      el("p", { texto: "Fuera del período: " + expEstado.fuera.join(", ") + ". Si el remito lo aclara, marcá «Aclara el período»." })));
  }
  const remitos = exp.datos.remitos;
  if (!remitos.length) {
    partes.push(el("p", { clase: "texto-suave", texto: "Todavía no hay remitos cargados." }));
    vaciar(contenedor, ...partes);
    return;
  }
  const formulario = el("form", { clase: "formulario", novalidate: true, onsubmit: guardarRemitos });
  remitos.forEach((remito, i) => {
    const bloque = el("fieldset", { clase: "panel" },
      el("legend", { texto: "Remito " + remito.numero + " — " + remito.fecha
        + (remito.fecha_firma ? " (firmado " + remito.fecha_firma + ")" : "")
        + (remito.es_equipo_comodato ? " — equipo en comodato" : "") }));
    if (!remito.es_equipo_comodato) {
      const items = new Map((remito.items || []).map((it) => [Number(it.pos), it]));
      const filas = renglones.map((r) => {
        const item = items.get(Number(r.pos)) || {};
        const idBase = "rem-" + i + "-" + r.pos;
        return el("tr", {},
          el("td", { clase: "numero", texto: r.pos }),
          el("td", { texto: (r.codigo ? r.codigo + " · " : "") + r.descripcion }),
          el("td", {}, entrada(item.cantidad || "", { id: idBase + "-cantidad", inputmode: "decimal", clase: "entrada-corta",
            "aria-label": "Cantidad del renglón " + r.pos + " en el remito " + remito.numero })),
          el("td", {}, entrada(item.codigo || "", { id: idBase + "-codigo", clase: "entrada-corta mono", placeholder: r.codigo || "",
            "aria-label": "Código del renglón " + r.pos + " como figura en el remito " + remito.numero })));
      });
      bloque.append(el("div", { clase: "tabla-desplazable" }, el("table", {},
        el("thead", {}, el("tr", {}, ...["Pos.", "Renglón de la OC", "Cantidad", "Código en el remito (vacío = igual)"]
          .map((t) => el("th", { scope: "col", texto: t })))),
        el("tbody", {}, ...filas))));
      bloque.append(casilla("rem-" + i + "-aclara", "Aclara el período (no se informa fuera de período)", remito.aclara_periodo));
    }
    bloque.append(el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario",
      texto: "Quitar este remito", onclick: () => quitarRemito(i) })));
    formulario.append(bloque);
  });
  formulario.append(el("div", { clase: "acciones" },
    el("button", { type: "submit", texto: "Guardar cantidades" }),
    el("button", { type: "button", clase: "secundario", texto: "Seguir al paso 3", onclick: () => mostrarPaso(3) })));
  partes.push(formulario);
  vaciar(contenedor, ...partes);
}

async function pegarRemitos(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const texto = document.getElementById("remitos-texto").value;
  if (!texto.trim()) { mostrarAviso("Pegá al menos un remito.", "error"); return; }
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, 2);
  const datos = await api("POST", "/api/expedientes/" + exp.id + "/remitos/pegar", {
    version: exp.version, texto, es_equipo_comodato: document.getElementById("remitos-equipo").checked,
  });
  if (!datos) return;
  expEstado.sugerido = datos.periodo_sugerido;
  expEstado.fuera = datos.fuera_de_periodo || [];
  delete datos.periodo_sugerido;
  delete datos.fuera_de_periodo;
  expEstado.exp = datos;
  pintarEncabezadoAsistente();
  pintarPaso2();
  mostrarAviso("Remitos agregados." + (datos.periodo_manual ? "" : (datos.periodo ? " Período sugerido: " + datos.periodo + "." : "")), "exito");
}

function remitosDelFormulario() {
  const renglones = expEstado.ficha ? expEstado.ficha.renglones : [];
  return expEstado.exp.datos.remitos.map((remito, i) => {
    if (remito.es_equipo_comodato) return remito;
    const items = [];
    for (const r of renglones) {
      const cantidad = document.getElementById("rem-" + i + "-" + r.pos + "-cantidad").value.trim().replace(",", ".");
      const codigo = document.getElementById("rem-" + i + "-" + r.pos + "-codigo").value.trim();
      if (cantidad) items.push({ pos: r.pos, cantidad, codigo });
    }
    return Object.assign({}, remito, { items, aclara_periodo: document.getElementById("rem-" + i + "-aclara").checked });
  });
}

async function guardarRemitos(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const remitos = remitosDelFormulario();
  const invalida = remitos.flatMap((r) => r.items || []).find((it) => !/^\d+(\.\d+)?$/.test(it.cantidad));
  if (invalida) { mostrarAviso("La cantidad del renglón " + invalida.pos + " no es un número válido.", "error"); return; }
  if (await guardarExpediente({ datos: { remitos } }, "Cantidades guardadas.")) pintarPaso2();
}

async function quitarRemito(indice) {
  limpiarAvisos();
  const remito = expEstado.exp.datos.remitos[indice];
  if (!window.confirm("¿Quitar el remito " + remito.numero + " del expediente?")) return;
  const remitos = expEstado.exp.datos.remitos.filter((_, i) => i !== indice);
  if (await guardarExpediente({ datos: { remitos } }, "Remito " + remito.numero + " quitado.")) pintarPaso2();
}

// Paso 3: factura y SII.

const CAMPOS_FACTURA = [
  ["numero", "N° de factura (tal cual figura, por ejemplo 0003B00031812)", "texto"],
  ["fecha", "Fecha de emisión", "fecha"],
  ["centavos", "Importe total $", "pesos"],
  ["cae", "CAE", "texto"],
  ["vto_cae", "Vencimiento del CAE", "fecha"],
  ["destinatario", "Destinatario", "texto"],
  ["domicilio", "Domicilio del destinatario", "texto"],
  ["periodo_desde", "Período de la factura: desde (si lo indica)", "fecha"],
  ["periodo_hasta", "Período de la factura: hasta (si lo indica)", "fecha"],
];

const ETIQUETAS_SII = [
  ["cae", "CAE"], ["fecha_emision", "Fecha de emisión"], ["periodo", "Período"], ["monto_centavos", "Monto"],
  ["tipo_comprobante", "Tipo de comprobante"], ["nro_comprobante", "N° de comprobante"], ["razon_social", "Razón social"],
  ["cuit", "CUIT"], ["sap", "N° SAP"], ["area", "Área"], ["tipo_servicio", "Tipo de servicio"], ["concepto", "Concepto"],
  ["orden_compra", "Orden de compra"], ["cod_tramite", "Código de trámite"],
];

function controlFactura(campo, tipo, valor) {
  const atributos = { id: "fac-" + campo };
  if (tipo === "fecha") atributos.type = "date";
  if (tipo === "pesos") atributos.inputmode = "decimal";
  if (campo === "numero" || campo === "cae") atributos.clase = "mono";
  return entrada(tipo === "pesos" ? formatoPesos(valor) : valor, atributos);
}

function pintarSii(sii) {
  const bloque = document.getElementById("sii-resultado");
  if (!sii || !Object.keys(sii).length) {
    vaciar(bloque, el("p", { clase: "texto-suave", texto: "Todavía no se cargó el texto del SII." }));
    return;
  }
  const filas = ETIQUETAS_SII.map(([clave, etiqueta]) => [etiqueta,
    clave === "monto_centavos" ? (sii[clave] === null || sii[clave] === undefined ? "" : "$ " + formatoPesos(sii[clave])) : (sii[clave] ?? "")]);
  const partes = [tabla(["Dato del SII", "Valor"], filas)];
  if (sii.faltantes && sii.faltantes.length) {
    partes.unshift(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: "No se encontró en el texto: " + sii.faltantes.join(", ") + "." })));
  }
  vaciar(bloque, ...partes);
}

async function pintarPaso3() {
  const contenedor = document.getElementById("asistente-paso-3");
  const factura = expEstado.exp.datos.factura || {};
  let destino = { nombre: "INSSJP", domicilio: "PERU 169", localidad: "CABA" };
  const parametros = await api("GET", "/api/parametros");
  if (parametros && parametros.parametros.destinatario_factura) destino = parametros.parametros.destinatario_factura;
  const valores = Object.assign({ destinatario: destino.nombre, domicilio: destino.domicilio + " " + destino.localidad }, factura);
  const campos = CAMPOS_FACTURA.map(([campo, etiqueta, tipo]) =>
    campoFormulario("fac-" + campo, etiqueta, controlFactura(campo, tipo, valores[campo])));
  expEstado.sii = null;
  vaciar(contenedor,
    el("h3", { texto: "3. Factura y SII" }),
    el("form", { clase: "formulario", novalidate: true, onsubmit: guardarFactura },
      ...campos,
      el("div", { clase: "campo campo-ancho" },
        el("label", { for: "sii-texto", texto: "Pegar texto de SII" }),
        el("textarea", { id: "sii-texto", rows: "8", spellcheck: "false", "aria-describedby": "sii-ayuda" }),
        el("p", { id: "sii-ayuda", clase: "texto-suave", texto: "Copiá todo el texto de la factura cargada en el SII y pegalo acá; los datos se completan solos." })),
      el("div", { clase: "acciones" },
        el("button", { type: "button", clase: "secundario", texto: "Analizar texto del SII", onclick: analizarSii })),
      el("div", { id: "sii-resultado" }),
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Guardar factura y SII" }),
        el("button", { type: "button", clase: "secundario", texto: "Seguir al paso 4", onclick: () => mostrarPaso(4) }))));
  pintarSii(expEstado.exp.datos.sii);
}

async function analizarSii() {
  limpiarAvisos();
  const texto = document.getElementById("sii-texto").value;
  if (!texto.trim()) { mostrarAviso("Pegá el texto de la factura cargada en el SII.", "error"); return; }
  const sii = await api("POST", "/api/comprobantes/analizar", { texto });
  if (!sii) return;
  expEstado.sii = sii;
  pintarSii(sii);
  const completar = (campo, valor) => {
    const control = document.getElementById("fac-" + campo);
    if (control && !control.value && valor !== null && valor !== undefined) control.value = valor;
  };
  completar("cae", sii.cae);
  completar("fecha", sii.fecha_emision);
  completar("centavos", sii.monto_centavos === null ? null : formatoPesos(sii.monto_centavos));
  mostrarAviso("Texto del SII analizado. Revisá los datos y guardá.", "exito");
}

async function guardarFactura(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const factura = Object.assign({}, expEstado.exp.datos.factura || {});
  for (const [campo, , tipo] of CAMPOS_FACTURA) {
    const valor = document.getElementById("fac-" + campo).value.trim();
    if (tipo === "pesos") {
      const centavos = pesosACentavos(valor);
      if (Number.isNaN(centavos)) { mostrarAviso("El importe de la factura no es un importe válido.", "error"); return; }
      factura[campo] = centavos;
    } else {
      factura[campo] = valor || null;
    }
  }
  const datos = { factura };
  if (expEstado.sii) datos.sii = expEstado.sii;
  if (await guardarExpediente({ datos }, "Factura" + (expEstado.sii ? " y SII guardados." : " guardada."))) {
    expEstado.sii = null;
    pintarPaso3();
  }
}

// Paso 4: controles.

const NIVELES_TEXTO = { error: "Error", salvable: "Salvable", aviso: "Aviso", verificar: "Verificar" };

async function pintarPaso4() {
  const contenedor = document.getElementById("asistente-paso-4");
  cargando(contenedor);
  const informe = await api("GET", "/api/expedientes/" + expEstado.exp.id + "/controles");
  if (!informe) { vaciar(contenedor); return; }
  pintarControles(informe);
}

function pintarControles(informe) {
  const contenedor = document.getElementById("asistente-paso-4");
  const r = informe.resumen;
  const partes = [
    el("h3", { texto: "4. Controles" }),
    el("ul", { clase: "resumen-controles", "aria-label": "Resumen de controles" },
      el("li", { texto: "Errores: " + r.error }),
      el("li", { texto: "Salvables: " + r.salvable + " (con nota: " + r.salvable_con_nota + ")" }),
      el("li", { texto: "Avisos: " + r.aviso }),
      el("li", { texto: "Para verificar: " + r.verificar })),
  ];
  if (!informe.resultados.length) {
    partes.push(el("p", { clase: "nota-guardada", texto: "Sin observaciones: el expediente pasa todos los controles." }));
  }
  informe.resultados.forEach((resultado, i) => {
    const bloque = el("div", { clase: "resultado nivel-" + resultado.nivel },
      el("p", {}, el("span", { clase: "nivel", texto: NIVELES_TEXTO[resultado.nivel] || resultado.nivel }), resultado.mensaje));
    if (resultado.nivel === "salvable") {
      const id = "nota-" + i;
      const area = el("textarea", { id, rows: "4" });
      area.value = resultado.nota_guardada ? resultado.nota_guardada.texto : (resultado.nota_sugerida || "");
      bloque.append(
        el("div", { clase: "campo campo-ancho" }, el("label", { for: id, texto: "Nota aclaratoria (editable)" }), area),
        resultado.nota_guardada
          ? el("p", { clase: "nota-guardada", texto: "Nota guardada por " + resultado.nota_guardada.usuario + "." })
          : el("p", { clase: "texto-suave", texto: "Falta guardar la nota para poder pasar a CONTROLADO." }),
        el("div", { clase: "acciones" }, el("button", { type: "button", texto: "Guardar nota",
          onclick: () => guardarNota(resultado, area.value) })));
    }
    partes.push(bloque);
  });
  partes.push(el("div", { clase: "acciones" },
    el("button", { type: "button", clase: "secundario", texto: "Volver a controlar", onclick: pintarPaso4 })));
  vaciar(contenedor, ...partes);
}

async function guardarNota(resultado, texto) {
  limpiarAvisos();
  if (!texto.trim()) { mostrarAviso("Escribí el texto de la nota aclaratoria.", "error"); return; }
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, 4);
  const datos = await api("POST", "/api/expedientes/" + exp.id + "/notas", {
    version: exp.version, codigo: resultado.codigo, referencia: resultado.referencia, texto,
  });
  if (!datos) return;
  expEstado.exp = datos.expediente;
  pintarEncabezadoAsistente();
  pintarControles(datos);
  mostrarAviso("Nota aclaratoria guardada.", "exito");
}

// Copiar al portapapeles.

function escaparHtml(texto) {
  return String(texto).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function copiarTexto(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    mostrarAviso("Texto copiado.", "exito");
  } catch (error) {
    mostrarAviso("No se pudo copiar. Seleccioná el texto y copialo a mano.", "error");
  }
}

/** Copia como HTML justificado (un <p> por párrafo) y también como texto plano, para pegar en GDE. */
async function copiarConFormato(texto) {
  const html = texto.split("\n").map((p) => '<p style="text-align: justify">' + escaparHtml(p) + "</p>").join("");
  try {
    await navigator.clipboard.write([new ClipboardItem({
      "text/html": new Blob([html], { type: "text/html" }),
      "text/plain": new Blob([texto], { type: "text/plain" }),
    })]);
    mostrarAviso("Texto copiado con formato.", "exito");
  } catch (error) {
    await copiarTexto(texto);
  }
}

function bloqueTexto(titulo, texto, conFormato) {
  return el("div", { clase: "panel" },
    el("h4", { texto: titulo }),
    el("p", { clase: "texto-generado", texto }),
    el("div", { clase: "acciones" },
      conFormato ? el("button", { type: "button", texto: "Copiar con formato", "aria-label": "Copiar con formato: " + titulo,
        onclick: () => copiarConFormato(texto) }) : null,
      el("button", { type: "button", clase: conFormato ? "secundario" : null, texto: "Copiar", "aria-label": "Copiar: " + titulo,
        onclick: () => copiarTexto(texto) })));
}

// Paso 5: textos generados.

async function pintarPaso5() {
  const contenedor = document.getElementById("asistente-paso-5");
  cargando(contenedor);
  const textos = await api("GET", "/api/expedientes/" + expEstado.exp.id + "/textos");
  if (!textos) {
    vaciar(contenedor, el("h3", { texto: "5. Textos" }),
      el("p", { clase: "texto-suave", texto: "Completá los datos que faltan (ver el mensaje de arriba) para generar los textos." }));
    return;
  }
  const partes = [el("h3", { texto: "5. Textos" }), bloqueTexto("Carátula", textos.caratula, false)];
  if (textos.autorizacion) {
    partes.push(bloqueTexto("Referencia de la autorización", textos.autorizacion.referencia, false));
    partes.push(bloqueTexto("Autorización de pago", textos.autorizacion.cuerpo, true));
  } else if (textos.autorizacion_error) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: "Autorización: " + textos.autorizacion_error })));
  }
  if (textos.constancia_comodato) {
    partes.push(bloqueTexto("Referencia de la constancia de comodato", textos.constancia_comodato.referencia, false));
    partes.push(bloqueTexto("Constancia de recepción de comodato", textos.constancia_comodato.cuerpo, true));
  } else if (textos.constancia_comodato_error) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: "Constancia de comodato: " + textos.constancia_comodato_error })));
  }
  partes.push(el("h4", { texto: "Referencias GDE y nombres de archivo" }));
  partes.push(el("div", { clase: "tabla-desplazable" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Referencia", "Archivo", ""].map((t) => el("th", { scope: "col", texto: t })))),
    el("tbody", {}, ...textos.referencias.map((r) => el("tr", {},
      el("td", { texto: r.referencia }),
      el("td", { clase: "mono", texto: r.archivo }),
      el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Copiar",
        "aria-label": "Copiar la referencia " + r.referencia, onclick: () => copiarTexto(r.referencia) }))))))));
  vaciar(contenedor, ...partes);
}

function iniciarExpedientes() {
  document.getElementById("expedientes-filtros").addEventListener("submit", (e) => { e.preventDefault(); listarExpedientes(); });
  document.getElementById("expediente-nuevo").addEventListener("click", nuevoExpediente);
  document.getElementById("asistente-volver").addEventListener("click", () => { limpiarAvisos(); mostrarLista(); });
  for (const boton of document.querySelectorAll(".pasos button[data-paso]")) {
    boton.addEventListener("click", () => { limpiarAvisos(); mostrarPaso(Number(boton.dataset.paso)); });
  }
}

// --- Arranque ---------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  iniciarEfector();
  iniciarImportar();
  iniciarExpedientes();
  iniciarNavegacion();
});
