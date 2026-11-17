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

// --- Arranque ---------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  iniciarEfector();
  iniciarImportar();
  iniciarNavegacion();
});
