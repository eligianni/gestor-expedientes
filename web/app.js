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

// Columnas de texto largo: van alineadas a la izquierda; todo lo demás, centrado.
const RE_COLUMNA_TEXTO = /proveedor|objeto|descripci|detalle|motivo|referencia|observaci|concepto|aviso|archivo|nombre|problema|raz[oó]n social/i;

function claseColumna(titulo, extra) {
  return [RE_COLUMNA_TEXTO.test(titulo || "") ? "izq" : "", extra || ""].filter(Boolean).join(" ") || null;
}

function tabla(encabezados, filas, clasesColumnas) {
  const thead = el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", clase: claseColumna(t), texto: t }))));
  const tbody = el("tbody", {}, ...filas.map((fila) => el("tr", {},
    ...fila.map((valor, i) => el("td", { clase: claseColumna(encabezados[i], clasesColumnas && clasesColumnas[i]), texto: valor ?? "" })))));
  return el("div", { clase: "tabla-desplazable" }, el("table", {}, thead, tbody));
}

/** Botones Excel, CSV e Imprimir de un exporte (enlaces de descarga; Imprimir abre la vista en otra pestaña). */
function botonesExporte(nombre, parametros, descripcion) {
  const consulta = new URLSearchParams(Object.entries(parametros || {}).filter(([, v]) => v !== "" && v !== null && v !== undefined));
  const ruta = (formato) => "/api/exportes/" + nombre + "." + formato + (consulta.toString() ? "?" + consulta.toString() : "");
  const sufijo = descripcion ? " " + descripcion : "";
  return el("div", { clase: "acciones exportes", role: "group", "aria-label": "Exportar" + sufijo },
    el("a", { clase: "boton secundario", href: ruta("xlsx"), download: "", "aria-label": "Excel" + sufijo, texto: "Excel" }),
    el("a", { clase: "boton secundario", href: ruta("csv"), download: "", "aria-label": "CSV" + sufijo, texto: "CSV" }),
    el("a", { clase: "boton secundario", href: ruta("html"), target: "_blank", rel: "noopener", "aria-label": "Imprimir" + sufijo,
      texto: "Imprimir" }));
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
/** El programa abierto es anterior a la última actualización (git pull): hay que cerrarlo y volver a abrirlo. */
const TEXTO_PROGRAMA_VIEJO = "El programa abierto es una versión anterior a la actualización: lo que guardes puede fallar. "
  + "Cerrá la ventana negra del programa (todas, si hay más de una), volvé a abrirlo con «python app.py» y usá la pestaña que se abre.";

function avisarProgramaViejo() {
  if (document.getElementById("aviso-programa-viejo")) return;
  document.body.prepend(el("div", { id: "aviso-programa-viejo", clase: "mensaje mensaje-error aviso-fijo", role: "alert" },
    el("p", { texto: TEXTO_PROGRAMA_VIEJO })));
}

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
  const rutaDesconocida = respuesta.status === 404 && datos && datos.error && /^Ruta no encontrada/.test(datos.error.mensaje || "");
  if (respuesta.headers.get("X-Gestor-Desactualizado") === "1" || rutaDesconocida) avisarProgramaViejo();
  if (rutaDesconocida) { mostrarAviso(TEXTO_PROGRAMA_VIEJO, "error"); return null; }
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
  "pantalla-calendario": cargarCalendario,
  "pantalla-oc": cargarOC,
  "pantalla-expedientes": cargarExpedientes,
  "pantalla-entregas": cargarEntregas,
  "pantalla-importar": cargarImportar,
  "pantalla-configuracion": cargarConfiguracion,
  "pantalla-centralizadas": cargarCentralizadas,
  "pantalla-ayuda": cargarAyuda,
  "pantalla-tablas": cargarTablas,
};

function mostrarPantalla(id, enfocar) {
  if (!document.getElementById(id)) id = "pantalla-inicio";
  if (id !== "pantalla-tablas") document.body.classList.remove("vista-amplia");
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

// Urgencia: ícono y palabra, además del color.
const URGENCIAS = { 1: ["▲", "Urgente"], 2: ["■", "Atención"], 3: ["●", "Para mirar"] };

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
  const [base, alertas] = [await api("GET", "/api/base/estado"), await api("GET", "/api/inicio/alertas")];
  if (!base || !alertas) { vaciar(contenedor); return; }
  const partes = [];
  const errorBase = alertas.find((a) => a.tipo === "base_con_errores");
  if (errorBase) {
    partes.push(el("div", { clase: "mensaje mensaje-error", role: "alert" },
      el("p", { texto: errorBase.mensaje }),
      el("button", { type: "button", texto: "Restaurar última copia", onclick: restaurarUltimaCopia })));
  }
  const resto = alertas.filter((a) => a.tipo !== "base_con_errores");
  partes.push(el("h2", { texto: "Alertas" }));
  if (!resto.length) {
    partes.push(el("p", { clase: "texto-suave", texto: "No hay alertas: todo al día." }));
  } else {
    const cuenta = [1, 2, 3].map((u) => [u, resto.filter((a) => a.urgencia === u).length]).filter(([, n]) => n);
    partes.push(el("p", { clase: "texto-suave", texto: cuenta.map(([u, n]) => n + " " + URGENCIAS[u][1].toLowerCase()).join(" · ") }));
    partes.push(el("ul", { clase: "lista-alertas" }, ...resto.map(itemAlerta)));
  }
  partes.push(el("p", { clase: "texto-suave", texto: "Usuario: " + salud.usuario + " · " + (base.ultimo_backup
    ? "Última copia de seguridad: " + base.ultimo_backup
    : "Todavía no hay copias de seguridad.") }));
  vaciar(contenedor, ...partes);
}

function itemAlerta(alerta) {
  const [icono, palabra] = URGENCIAS[alerta.urgencia] || ["●", "Para mirar"];
  const acciones = [];
  if (alerta.expediente_id) {
    acciones.push(el("button", { type: "button", clase: "secundario", texto: "Abrir expediente " + alerta.expediente_id,
      onclick: () => { expEstado.exp = { id: alerta.expediente_id }; expEstado.paso = 7; mostrarPantalla("pantalla-expedientes", true); } }));
  } else if (alerta.oc) {
    acciones.push(el("button", { type: "button", clase: "secundario", texto: "Ver OC " + alerta.oc,
      onclick: () => { ocEstado.ficha = { oc: { numero: alerta.oc } }; mostrarPantalla("pantalla-oc", true); } }));
  }
  return el("li", { clase: "alerta urgencia-" + alerta.urgencia },
    el("span", { clase: "urgencia" }, el("span", { "aria-hidden": "true", texto: icono + " " }), palabra),
    el("span", { clase: "alerta-mensaje", texto: alerta.mensaje }),
    ...acciones);
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
  cargarHistorial();
}

function iniciarImportar() {
  document.getElementById("form-importar").addEventListener("submit", vistaPreviaImportacion);
  document.getElementById("importar-confirmar").addEventListener("click", confirmarImportacion);
  document.getElementById("importar-efector").addEventListener("change", () => {
    document.getElementById("importar-confirmar").disabled = true;
  });
  document.getElementById("importar-archivo").addEventListener("change", () => {
    document.getElementById("importar-confirmar").disabled = true;
  });
  document.getElementById("form-migracion").addEventListener("submit", (e) => { e.preventDefault(); enviarMigracion(false); });
  document.getElementById("migracion-confirmar").addEventListener("click", () => enviarMigracion(true));
  for (const id of ["migracion-numeracion", "migracion-remitos"]) {
    document.getElementById(id).addEventListener("change", () => { document.getElementById("migracion-confirmar").disabled = true; });
  }
}

// --- Migración del seguimiento en Excel (NUMERACIÓN + solapa de remitos) ------------------------------------

function formularioMigracion() {
  const numeracion = document.getElementById("migracion-numeracion").files[0];
  const remitos = document.getElementById("migracion-remitos").files[0];
  if (!numeracion || !remitos) {
    mostrarAviso("Elegí los dos archivos: la NUMERACIÓN y el seguimiento de remitos.", "error");
    return null;
  }
  const datos = new FormData();
  datos.append("numeracion", numeracion, numeracion.name);
  datos.append("remitos", remitos, remitos.name);
  return datos;
}

async function enviarMigracion(confirmar) {
  limpiarAvisos();
  const datos = formularioMigracion();
  if (!datos) return;
  if (confirmar && !confirm("¿Crear los expedientes de la vista previa? Se puede repetir: lo ya migrado no se duplica.")) return;
  const destino = document.getElementById("migracion-resultado");
  cargando(destino);
  const informe = await api("POST", "/api/importar/seguimiento/" + (confirmar ? "confirmar" : "vista-previa"), datos);
  if (!informe) { vaciar(destino); return; }
  pintarMigracion(informe, confirmar);
  document.getElementById("migracion-confirmar").disabled = confirmar || !informe.resumen.expedientes;
  if (confirmar) {
    mostrarAviso("Migración hecha: " + informe.resumen.creados + " expedientes creados.", "exito");
    cargarHistorial();
  }
}

function pintarMigracion(informe, confirmado) {
  const r = informe.resumen;
  const estados = Object.entries(r.por_estado).map(([e, n]) => (ESTADOS_TEXTO[e] || e) + ": " + n).join(" · ");
  const partes = [
    el("h3", { texto: confirmado ? "Migración realizada" : "Vista previa de la migración" }),
    tabla(["Concepto", "Cantidad"], [
      [confirmado ? "Expedientes creados" : "Expedientes a crear", confirmado ? r.creados : r.expedientes],
      ["Por estado", estados || "—"],
      ["Ya estaban en el gestor (no se duplican)", r.ya_existentes],
      ["Remitos", r.remitos],
      ["Con cantidades por renglón deducidas", r.con_cantidades],
      ["Entregas nuevas", r.entregas_nuevas],
      ["Filas que no se importan", r.no_importados],
    ], [null, "numero"]),
  ];
  if (informe.hojas_ignoradas.length) {
    partes.push(el("p", { clase: "texto-suave", texto: "Hojas que no se leen: " + informe.hojas_ignoradas.join(", ") + "." }));
  }
  if (informe.no_importados.length) {
    partes.push(el("h4", { texto: "No se importan" }),
      tabla(["Origen", "Fila", "Detalle", "Motivo"], informe.no_importados.map((x) => [x.origen, x.fila, x.detalle, x.motivo])));
  }
  const filas = informe.expedientes.map((p) => [
    p.origen, p.entrega ?? "—", p.oc || "—", p.razon_social, p.periodo, p.factura || "—",
    p.centavos !== null && p.centavos !== undefined ? formatoPesos(p.centavos) : "—",
    p.ya_existe ? "Ya existe (N° " + p.ya_existe + ")" : (ESTADOS_TEXTO[p.estado] || p.estado),
    p.remitos.join(" / ") || "—",
    p.items.map((i) => "Rgl. " + i.pos + ": " + i.cantidad).join(", ") || "—",
    p.avisos.join(" "),
  ]);
  partes.push(el("h4", { texto: "Expedientes" }),
    tabla(["Origen", "Entrega", "OC", "Proveedor", "Período", "Factura", "Importe $", "Estado", "Remitos", "Cantidades", "Avisos"],
      filas, [null, "numero", null, null, null, null, "numero"]));
  vaciar(document.getElementById("migracion-resultado"), el("div", { clase: "panel" }, ...partes));
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

// --- Objeto con su artículo (chiquito, a la izquierda: «al servicio de…») -------------------------------------

const OPCIONES_ARTICULO = [["al", "al"], ["a la", "a la"], ["a los", "a los"], ["a las", "a las"]];

/** Campo «Objeto» con el selector de artículo a la izquierda, en el orden en que se lee en la autorización. */
function campoObjeto(idArticulo, idObjeto, articulo, objeto, etiqueta, ayuda) {
  const sel = selector(articulo || "al", OPCIONES_ARTICULO);
  sel.id = idArticulo;
  sel.className = "selector-articulo";
  sel.setAttribute("aria-label", "Artículo del objeto (sale solo según el objeto)");
  sel.title = "Artículo: «a la» si dice adquisición o provisión, «al» si dice servicio.";
  const texto = entrada(objeto || "", { id: idObjeto, clase: "entrada-objeto" });
  const partes = [el("label", { for: idObjeto, texto: etiqueta }), el("div", { clase: "objeto-con-articulo" }, sel, texto)];
  if (ayuda) partes.push(ayuda);
  return el("div", { clase: "campo campo-ancho" }, ...partes);
}

/** Ícono de PDF (SVG armado con el DOM, sin innerHTML). */
function iconoPdf() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [k, v] of [["viewBox", "0 0 24 24"], ["width", "18"], ["height", "18"], ["aria-hidden", "true"], ["focusable", "false"]]) svg.setAttribute(k, v);
  const hoja = document.createElementNS(ns, "path");
  hoja.setAttribute("d", "M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm7 1.5V8h4.5");
  hoja.setAttribute("fill", "none"); hoja.setAttribute("stroke", "currentColor"); hoja.setAttribute("stroke-width", "1.8");
  hoja.setAttribute("stroke-linejoin", "round");
  const texto = document.createElementNS(ns, "text");
  texto.setAttribute("x", "12"); texto.setAttribute("y", "17.5"); texto.setAttribute("text-anchor", "middle");
  texto.setAttribute("font-size", "6.5"); texto.setAttribute("font-weight", "700"); texto.setAttribute("fill", "currentColor");
  texto.textContent = "PDF";
  svg.append(hoja, texto);
  return svg;
}

// --- Órdenes de compra -------------------------------------------------------

const ocEstado = { ficha: null };

function contenedorOC() {
  const seccion = document.getElementById("pantalla-oc");
  let raiz = document.getElementById("oc-raiz");
  if (!raiz) {
    for (const p of seccion.querySelectorAll(":scope > p")) p.remove();
    const buscar = entrada("", { id: "oc-buscar", type: "search", placeholder: "N° de OC, SAP, proveedor u objeto" });
    const filtros = el("form", { clase: "panel formulario", id: "oc-filtros", onsubmit: (e) => { e.preventDefault(); cerrarFichaOC(); } },
      el("div", { clase: "campo" }, el("label", { for: "oc-buscar", texto: "Buscar" }), buscar),
      casilla("oc-excluidas", "Mostrar también las OC excluidas", false),
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Buscar" }),
        el("button", { type: "button", id: "oc-nueva", "aria-label": "Nueva OC desde su PDF",
          title: "Elegí uno o varios PDF de OC", onclick: () => document.getElementById("oc-nueva-archivo").click() }, iconoPdf(), "Nueva OC"),
        el("button", { type: "button", clase: "enlace", texto: "Sin PDF (escaneada): cargar a mano", onclick: mostrarAltaOC })),
      el("input", { type: "file", id: "oc-nueva-archivo", accept: "application/pdf,.pdf", multiple: true, hidden: true,
        "aria-label": "PDF de las OC nuevas (podés elegir varios)",
        onchange: (e) => { const archivos = Array.from(e.target.files); e.target.value = ""; if (archivos.length) procesarPdfsOC(archivos); } }));
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
  lista.hidden = Boolean(ocEstado.ficha);  // con la ficha abierta, la lista queda oculta
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
  const filas = ocs.map((oc) => el("tr", {},
    el("td", {}, el("div", { clase: "oc-con-lapiz" },
      el("button", { type: "button", clase: "secundario boton-celda", texto: oc.numero,
        "aria-label": "Ver la OC " + oc.numero, onclick: () => abrirFichaOC(oc.numero) }),
      botonLapiz("Editar los datos de la OC " + oc.numero, () => abrirDialogoEditarOC(oc.numero)))),
    el("td", { texto: (oc.efectores && oc.efectores.length ? oc.efectores : [oc.efector]).join(" · ") }),
    el("td", { clase: "izq", texto: oc.razon_social + " (SAP " + oc.sap + ")" }),
    el("td", { clase: "izq", texto: oc.objeto || "—" }),
    el("td", { texto: TIPOS_OC_TEXTO[oc.tipo] || oc.tipo }),
    el("td", {}, observacionesOC(oc)),
    el("td", { clase: "sin-corte", texto: vigenciaCorta(oc) }),
    el("td", { clase: "numero", texto: oc.renglones }),
    el("td", { clase: "numero sin-corte", texto: formatoPesos(oc.importe_centavos) })));
  const encabezados = [["OC"], ["Efector"], ["Proveedor", "izq"], ["Objeto", "izq"], ["Tipo"], ["Observaciones"], ["Vigencia"],
    ["Renglones"], ["Importe $"]];
  vaciar(lista,
    botonesExporte("seguimiento-oc", { efector: estado.efector === "Ambos" ? "" : estado.efector, q: texto }, "del seguimiento de OC"),
    el("p", { clase: "texto-suave", texto: ocs.length + (ocs.length === 1 ? " OC" : " OC") }),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-lista" },
      el("thead", {}, el("tr", {}, ...encabezados.map(([t, c]) => el("th", { scope: "col", clase: c || null, texto: t })))),
      el("tbody", {}, ...filas))));
}

const TIPOS_OC_TEXTO = { SERVICIO: "Servicio", BIEN: "Bien", PROVISION: "Provisión" };

/** "01/03/26 – 28/02/27" en un solo renglón; los bienes no tienen vigencia. */
function vigenciaCorta(oc) {
  if (oc.tipo === "BIEN") return "—";
  const corta = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(2, 4) : "");
  if (!oc.vig_desde && !oc.vig_hasta) return "—";
  return corta(oc.vig_desde) + " – " + (oc.vig_hasta ? corta(oc.vig_hasta) : "sin fin");
}

/** Lo obligatorio que le falta a la OC para crear expedientes o validaciones (PDF y, salvo centralizadas, concepto corto). */
function faltantesOC(oc) {
  // Las centralizadas no llevan textos SAP (el pago lo hace Nivel Central): solo hace falta el PDF.
  return [!oc.pdf_cargado && "el PDF de la OC",
    !oc.centralizada && !(oc.concepto_corto || "").trim() && "el concepto corto (Texto SAP)"].filter(Boolean);
}

/** Etiquetas de color (con su palabra) para lo que hay que tener en cuenta de la OC. */
function observacionesOC(oc) {
  const etiquetas = [];
  const etiqueta = (texto, tono, titulo) => etiquetas.push(el("span", { clase: "pastilla pastilla-" + tono, texto, title: titulo || null }));
  const faltan = faltantesOC(oc);
  if (faltan.length && !oc.excluida) etiqueta("Acciones pendientes", "pendiente", "Falta cargar " + faltan.join(" y "));
  if (oc.centralizada) etiqueta("Centralizada", "violeta", "Compra de Nivel Central");
  if (oc.comodato) etiqueta("Comodato", "info", "Tiene equipo en comodato");
  if (oc.renglones_otro_centro) {
    etiqueta(oc.renglones_otro_centro === oc.renglones ? "Otro centro" : "Otro centro " + oc.renglones_otro_centro + "/" + oc.renglones,
      "aviso", "Renglones de otro centro: se reciben y a veces no llevan factura");
  }
  if (oc.origen === "MANUAL") etiqueta("Manual", "neutra", "Cargada a mano o desde su PDF");
  if (oc.cerrada_sap) etiqueta("Cerrada en SAP", "neutra");
  if (oc.excluida) etiqueta("Excluida", "error");
  return etiquetas.length ? el("div", { clase: "etiquetas" }, ...etiquetas) : "—";
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
  document.getElementById("oc-lista").hidden = false;
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
  ["leyenda_cv", "Leyenda del CV (solo centralizadas: va en «Observaciones» del certificado de validación)", "texto"],
  ["vig_desde", "Vigencia desde", "fecha"],
  ["vig_hasta", "Vigencia hasta", "fecha"],
  ["excluida", "Excluir esta OC (no aparece en las listas)", "casilla"],
  ["motivo_exclusion", "Motivo de la exclusión", "texto"],
];

const CAMPOS_PERIODO_OC = ["dia_inicio_periodo", "vig_desde", "vig_hasta", "prorroga"];

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

/** Pastilla para un renglón de otro centro: se recibe, pero casi nunca lleva factura del efector. */
function marcaOtroCentro(r) {
  if (r.central) {
    return el("span", { clase: "pastilla pastilla-violeta marca-otro-centro", texto: "Centralizada · centro " + r.centro,
      title: "Renglón de Nivel Central (centro " + r.centro + ")." });
  }
  if (!r.otro_centro) return null;
  return el("span", { clase: "pastilla pastilla-aviso marca-otro-centro", texto: "Otro centro " + r.centro,
    title: "Renglón del centro " + r.centro + ": a veces se recibe sin factura del efector." });
}

function pintarFichaOC(ficha) {
  const { oc, proveedor, renglones, expedientes } = ficha;
  const ocCompleta = Object.assign({}, oc, { pdf_cargado: Boolean(ficha.pdf_oc), renglones_otro_centro: 0 });
  const faltan = faltantesOC(ocCompleta);

  const filasRenglones = renglones.map((r) => el("tr", { clase: r.otro_centro ? "fila-otro-centro" : null },
    el("td", { clase: "numero", texto: r.pos }),
    el("td", { clase: "izq" }, (r.codigo ? r.codigo + " · " : "") + r.descripcion, r.otro_centro || r.central ? " " : null, marcaOtroCentro(r)),
    el("td", { clase: "numero", texto: r.cantidad + (r.unidad ? " " + r.unidad : "") }),
    el("td", { clase: "numero", texto: formatoPesos(r.precio_centavos) }),
    el("td", { clase: "numero", texto: formatoPesos(r.importe_centavos) }),
    el("td", { texto: r.desglose_cantidad ? r.desglose_cantidad + " " + r.desglose_unidad + " × $ " + formatoPesos(r.desglose_precio_centavos)
      : (r.revisar_desglose ? "Revisar desglose" : "—") }),
    el("td", { clase: "numero", texto: r.sap_entregado + " / " + r.sap_por_entregar + (r.exceso_sap ? " (exceso)" : "") }),
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Editar",
      "aria-label": "Editar el renglón " + r.pos, onclick: () => editarRenglon(r) }))));
  // Cada renglón con subrenglones (1-10, 1-20…) los muestra debajo: son los que van en el certificado.
  const filasConSub = [];
  renglones.forEach((r, k) => {
    filasConSub.push(filasRenglones[k]);
    for (const sub of r.subrenglones || []) {
      filasConSub.push(el("tr", { clase: "fila-subrenglon" },
        el("td", { clase: "numero sin-corte", texto: r.pos + "-" + sub.pos }),
        el("td", { clase: "izq", texto: sub.descripcion || "" }),
        el("td", { clase: "numero", texto: textoCantidad(sub.cantidad) + (sub.unidad ? " " + sub.unidad : "") }),
        el("td", { clase: "numero", texto: sub.precio_centavos ? formatoPesos(sub.precio_centavos) : "" }),
        el("td", {}), el("td", {}), el("td", {}), el("td", {}), oc.centralizada ? el("td", {}) : null));
    }
  });
  const encabezadosRenglones = ["Pos.", "Descripción", "Cantidad", "Precio $", "Importe $", "Desglose",
    "Entregado / por entregar (SAP)", ""];
  if (oc.centralizada) {
    // Reparto por efector: cuánto de cada renglón valida HBI y cuánto CASPH (se carga en «Editar» del renglón).
    encabezadosRenglones.splice(7, 0, "HBI / CASPH");
    renglones.forEach((r, k) => {
      const reparto = r.por_efector || {};
      const texto = Object.keys(reparto).length
        ? ["HBI", "CASPH"].filter((e) => reparto[e] !== undefined).map((e) => e + " " + textoCantidad(reparto[e])).join(" · ")
        : "Sin repartir";
      filasRenglones[k].insertBefore(el("td", { clase: "sin-corte" + (Object.keys(reparto).length ? "" : " texto-suave"), texto }),
        filasRenglones[k].lastElementChild);
    });
  }

  const central = Boolean(oc.centralizada);
  const efectores = oc.efectores && oc.efectores.length ? oc.efectores : [oc.efector];
  const titulo = faltan.length ? "Primero cargá " + faltan.join(" y ") + "." : null;
  // Centralizada: no se crea un expediente de pago sino una validación por efector (HBI y CASPH por separado).
  const nuevoExp = central
    ? el("div", { clase: "acciones" }, ...efectores.map((ef) => el("button", { type: "button", disabled: faltan.length > 0,
      texto: "Nueva validación" + (efectores.length > 1 ? " " + ef : ""), title: titulo || "Validar un período de " + ef,
      onclick: () => nuevaValidacionCentralizada(oc.numero, ef) })))
    : el("button", { type: "button", texto: "Nuevo expediente", disabled: faltan.length > 0,
      title: titulo || "Crear un expediente de pago para esta OC", onclick: () => nuevoExpedienteDesdeOC(oc) });
  const etiquetas = observacionesOC(ocCompleta);
  const cabecera = el("div", { clase: "cabecera-oc" },
    el("div", { clase: "cabecera-oc-texto" },
      el("p", { clase: "sobretitulo", texto: "Orden de compra · " + efectores.join(" y ") + " · " + (TIPOS_OC_TEXTO[oc.tipo] || oc.tipo)
        + (central ? " · centralizada" : "") }),
      el("h2", { id: "oc-ficha-titulo", clase: "titulo-oc", tabindex: "-1", texto: "OC " + oc.numero }),
      el("p", { clase: "subtitulo-oc", texto: (proveedor ? proveedor.razon_social : "Proveedor sin cargar") + " · SAP " + oc.sap }),
      typeof etiquetas === "string" ? null : el("div", { clase: "etiquetas etiquetas-izq" }, ...etiquetas.childNodes)),
    el("div", { clase: "acciones cabecera-oc-acciones" },
      nuevoExp,
      el("button", { type: "button", clase: "secundario", onclick: () => abrirDialogoEditarOC(oc.numero) },
        iconoLapiz(), "Editar datos y PDF")));
  const pendiente = faltan.length
    ? el("div", { clase: "mensaje mensaje-pendiente" },
      el("p", { texto: "Para " + (central ? "validar" : "crear expedientes") + " falta cargar " + faltan.join(" y ") + "." }),
      el("button", { type: "button", texto: "Completar ahora", onclick: () => abrirDialogoEditarOC(oc.numero) }))
    : null;

  const consumo = el("div", { id: "oc-consumo" });
  const editables = expedientes.filter((x) => x.estado !== "ANULADO" && !x.consumo_remitos);
  const partes = [
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "Volver a la lista", onclick: cerrarFichaOC })),
    cabecera,
    pendiente,
    resumenDatosOC(oc, ficha.pdf_oc),
    el("h3", { texto: "Renglones" }),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...encabezadosRenglones.map((t) => el("th", { scope: "col", clase: claseColumna(t), texto: t })))),
      el("tbody", {}, ...filasConSub))),
    el("div", { id: "oc-renglon-edicion" }),
  ];
  if (oc.origen === "MANUAL") {
    partes.push(el("div", { clase: "acciones" },
      el("button", { type: "button", clase: "secundario", texto: "Agregar renglón", onclick: () => editarRenglon(null) })));
  }
  // Consumo: en una centralizada que validan los dos efectores, una tabla por efector (cada uno con su cantidad).
  const porEfector = central && efectores.length > 1;
  const consumos = porEfector ? efectores.map((ef) => [ef, el("div", { id: "oc-consumo-" + ef })]) : [[null, consumo]];
  partes.push(
    el("h3", { texto: "Consumo de la OC" }),
    el("div", { clase: "acciones" },
      el("button", { type: "button", clase: "secundario", texto: "Cargar consumo a mano", disabled: !editables.length,
        title: editables.length ? "Para los meses facturados que no tienen remitos cargados"
          : "Todos los expedientes ya tienen el consumo de sus remitos",
        onclick: () => abrirDialogoConsumoManual(ficha) }),
      porEfector ? null : botonesExporte("consumo-oc", { oc: oc.numero }, "del consumo de la OC " + oc.numero)));
  for (const [ef, destino] of consumos) {
    if (ef) partes.push(el("h4", { texto: "Consumo " + ef }), botonesExporte("consumo-oc", { oc: oc.numero, efector: ef },
      "del consumo de " + ef + " de la OC " + oc.numero));
    partes.push(destino);
  }
  partes.push(el("h3", { texto: central ? "Validaciones de esta OC" : "Expedientes de esta OC" }));
  const origenConsumo = (x) => (x.consumo_remitos ? "De los remitos"
    : (Object.keys(x.consumo_manual || {}).length ? "Cargado a mano" : "Sin consumo"));
  partes.push(expedientes.length
    ? tablaExpedientesOC(expedientes, origenConsumo, central)
    : el("p", { clase: "texto-suave", texto: central ? "Todavía no hay validaciones de esta OC." : "Todavía no hay expedientes para esta OC." }));
  vaciar(document.getElementById("oc-detalle"), el("div", { clase: "panel" }, ...partes));
  document.getElementById("oc-lista").hidden = true;
  for (const [ef, destino] of consumos) pintarConsumoOC(oc.numero, destino, ef);
}

// Estados en los que el expediente ya está terminado: se puede ver, no tramitar.
const ESTADOS_TERMINADOS = new Set(["COMPLETO", "ENVIADO", "CONTABILIZADO", "CERRADO", "FINALIZADO", "ANULADO"]);

/** «Expedientes de esta OC»: cada fila abre el expediente («Tramitar» si sigue en curso, «Visualizar» si terminó). */
function tablaExpedientesOC(expedientes, origenConsumo, central) {
  const encabezados = central ? ["N°", "Efector", "Período", "Estado", "N° de nota", "Consumo", ""]
    : ["N°", "Tipo", "Período", "Estado", "Factura", "Importe $", "Consumo", ""];
  const filas = expedientes.map((x) => {
    const terminado = ESTADOS_TERMINADOS.has(x.estado);
    // En curso, se abre en el primer paso que le falta: remitos, factura o controles.
    const sinConsumo = !x.consumo_remitos && !Object.keys(x.consumo_manual || {}).length;
    // El expediente común se abre en el paso que le corresponde según su estado (pasoSegunEstado).
    const paso = !central && x.tipo === "COMUN" ? null
      : terminado ? 1 : (sinConsumo ? 2 : (central ? (x.numero_cv ? 4 : 3) : (!x.factura ? 3 : 4)));
    const abrir = () => abrirExpedienteDesdeOC(x.id, paso);
    const boton = el("button", { type: "button", clase: terminado ? "secundario" : null, texto: terminado ? "Visualizar" : "Tramitar",
      "aria-label": (terminado ? "Visualizar" : "Tramitar") + " el expediente " + x.id,
      onclick: (e) => { e.stopPropagation(); abrir(); } });
    const estadoTexto = central ? (ESTADOS_CENTRALIZADA_TEXTO[x.estado] || x.estado) : (ESTADOS_TEXTO[x.estado] || x.estado);
    const celdas = central
      ? [el("td", { texto: x.efector || "" }), el("td", { texto: x.periodo || "" }),
        el("td", {}, el("span", { clase: "pastilla pastilla-" + (TONO_ESTADO[x.estado] || "neutra"), texto: estadoTexto })),
        el("td", { clase: "mono", texto: x.numero_nota || "—" })]
      : [el("td", { texto: x.tipo }), el("td", { texto: x.periodo || "" }),
        el("td", {}, el("span", { clase: "pastilla pastilla-" + (TONO_ESTADO[x.estado] || "neutra"), texto: estadoTexto })),
        el("td", { clase: "mono", texto: x.factura || "" }),
        el("td", { clase: "numero", texto: x.importe_centavos === null || x.importe_centavos === undefined ? "—" : formatoPesos(x.importe_centavos) })];
    return el("tr", { clase: "fila-clic", title: (terminado ? "Ver" : "Seguir tramitando") + " el expediente " + x.id, onclick: abrir },
      el("td", { clase: "numero", texto: String(x.id) }),
      ...celdas,
      el("td", { texto: origenConsumo(x) }),
      el("td", {}, boton));
  });
  return el("div", { clase: "tabla-desplazable" }, el("table", {},
    el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", texto: t })))),
    el("tbody", {}, ...filas)));
}

/** Abre el expediente en la pantalla Expedientes, en el paso indicado. */
function abrirExpedienteDesdeOC(id, paso) {
  limpiarAvisos();
  Object.assign(expEstado, { exp: { id }, ficha: null, paso, sugerido: null, fuera: [], sii: null });
  mostrarPantalla("pantalla-expedientes", false);
}

/** "2026-09" → "09/2026"; las columnas especiales tienen su nombre. */
function textoPeriodo(periodo) {
  if (periodo === "unica") return "Consumido";
  if (/^\d{4}-\d{2}$/.test(periodo)) return periodo.slice(5, 7) + "/" + periodo.slice(0, 4);
  return periodo === "sin_periodo" ? "Sin período" : periodo;
}

/** Tabla de consumo: renglón × período, con total, saldo y % consumido. */
async function pintarConsumoOC(numero, destino, efector) {
  cargando(destino);
  const consumo = await api("GET", "/api/oc/" + encodeURIComponent(numero) + "/consumo" + (efector ? "?efector=" + efector : ""));
  if (!consumo) { vaciar(destino); return; }
  const { periodos, filas } = consumo.grilla;
  const porPos = Object.fromEntries(consumo.renglones.map((r) => [r.pos, r]));
  if (!filas.length) { vaciar(destino, el("p", { clase: "texto-suave", texto: "La OC no tiene renglones." })); return; }
  const encabezados = ["Rgl.", "Descripción", "Cantidad OC", ...periodos.map(textoPeriodo), "Total consumido", "Saldo", "%"];
  const cuerpo = filas.map((f) => {
    const r = porPos[f.pos] || {};
    const total = Number(r.validado || 0);
    return el("tr", { clase: f.agotado ? "fila-agotada" : (f.por_agotarse ? "fila-por-agotarse" : null) },
      el("td", { clase: "numero", texto: f.pos }),
      el("td", { clase: "izq", texto: f.descripcion }),
      el("td", { clase: "numero sin-corte", texto: textoCantidad(f.cantidad_oc) + (f.unidad ? " " + f.unidad : "") }),
      ...periodos.map((p) => {
        const valor = f.celdas[p];
        return el("td", { clase: "numero" + (valor && valor !== "0" ? "" : " celda-vacia"), texto: valor && valor !== "0" ? textoCantidad(valor) : "·" });
      }),
      el("td", { clase: "numero", texto: textoCantidad(String(Math.round(total * 10000) / 10000)) }),
      el("td", { clase: "numero", texto: textoCantidad(f.saldo) }),
      el("td", { clase: "numero" }, el("span", { clase: "pastilla pastilla-" + (f.agotado ? "error" : (f.por_agotarse ? "aviso" : "neutra")),
        texto: (r.pct_consumido ?? 0) + " %" + (f.agotado ? " · agotado" : (f.por_agotarse ? " · por agotarse" : "")) })));
  });
  vaciar(destino, el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-consumo" },
    el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", clase: t === "Descripción" ? "izq" : null, texto: t })))),
    el("tbody", {}, ...cuerpo))),
  el("p", { clase: "nota-pie", texto: "Cada mes suma lo de los remitos de sus expedientes, o lo cargado a mano si el mes no tiene remitos. «·» = sin consumo." }));
}

/** Consumo de los meses ya facturados que no tienen remitos cargados (p. ej. los migrados del seguimiento). */
function abrirDialogoConsumoManual(ficha) {
  const { oc, renglones } = ficha;
  const editables = ficha.expedientes.filter((x) => x.estado !== "ANULADO" && !x.consumo_remitos);
  const anterior = document.getElementById("dialogo-consumo-oc");
  if (anterior) anterior.remove();
  const filas = editables.map((x) => el("tr", { "data-exp": String(x.id) },
    el("td", { clase: "sin-corte", texto: x.periodo ? textoPeriodo(x.periodo) : "Sin período" }),
    el("td", { texto: String(x.id) }),
    el("td", { clase: "sin-corte", texto: x.factura || "—" }),
    ...renglones.map((r) => el("td", {}, entrada(textoCantidad((x.consumo_manual || {})[String(r.pos)]), {
      inputmode: "decimal", clase: "entrada-chica", "data-pos": String(r.pos),
      "aria-label": "Consumo del renglón " + r.pos + " en el expediente " + x.id + (x.periodo ? " (" + x.periodo + ")" : "") })))));
  const guardar = el("button", { type: "button", texto: "Guardar consumo" });
  const dialogo = el("dialog", { id: "dialogo-consumo-oc", clase: "dialogo", "aria-labelledby": "consumo-manual-titulo" },
    el("div", { clase: "dialogo-encabezado" },
      el("h2", { id: "consumo-manual-titulo", texto: "Cargar consumo a mano — OC " + oc.numero }),
      el("p", { clase: "texto-suave", texto: "Para los meses que ya tienen factura pero no remitos cargados. Lo que pongas cuenta como "
        + "consumido en ese período; vacío = sin consumo. Si después se cargan los remitos, manda lo de los remitos." })),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-renglones-dialogo" },
      el("thead", {}, el("tr", {},
        el("th", { scope: "col", texto: "Período" }), el("th", { scope: "col", texto: "Exp." }), el("th", { scope: "col", texto: "Factura" }),
        ...renglones.map((r) => el("th", { scope: "col", title: r.descripcion },
          "Rgl. " + r.pos, el("span", { clase: "th-detalle", texto: (r.desglose_cantidad ? r.desglose_unidad : r.unidad) || "" }))))),
      el("tbody", {}, ...filas))),
    el("div", { clase: "acciones dialogo-acciones" }, guardar,
      el("button", { type: "button", clase: "secundario", texto: "Cerrar", onclick: () => dialogo.close() })));
  guardar.addEventListener("click", async () => {
    guardar.disabled = true;
    let guardados = 0;
    for (const fila of dialogo.querySelectorAll("tbody tr")) {
      const x = editables.find((e) => String(e.id) === fila.dataset.exp);
      const cantidades = {};
      let cambio = false;
      for (const input of fila.querySelectorAll("input")) {
        const valor = input.value.trim();
        if (valor) cantidades[input.dataset.pos] = valor;
        if (valor !== textoCantidad((x.consumo_manual || {})[input.dataset.pos])) cambio = true;
      }
      if (!cambio) continue;
      const exp = await api("PUT", "/api/expedientes/" + x.id + "/consumo-manual", { version: x.version, cantidades });
      if (!exp) {
        avisoEnDialogo(dialogo, "Expediente " + x.id + ": " + ultimoError());
        guardar.disabled = false;
        return;
      }
      const nueva = (exp.datos && exp.datos.consumo_manual) || {};
      Object.assign(x, { version: exp.version, consumo_manual: nueva });
      guardados += 1;
    }
    dialogo.close();
    mostrarAviso(guardados ? "Consumo guardado en " + guardados + (guardados === 1 ? " expediente." : " expedientes.") : "No había cambios para guardar.",
      guardados ? "exito" : "aviso");
  });
  dialogo.addEventListener("close", () => { dialogo.remove(); abrirFichaOC(oc.numero); });
  document.body.append(dialogo);
  dialogo.showModal();
  const primero = dialogo.querySelector("tbody input");
  if (primero) primero.focus();
}

/** Crea el expediente de la OC (si tiene su PDF y el concepto corto) y abre el asistente. */
async function nuevoExpedienteDesdeOC(oc) {
  limpiarAvisos();
  const exp = await api("POST", "/api/expedientes", { tipo: oc.centralizada ? "CENTRALIZADA" : "COMUN", oc: oc.numero });
  if (!exp) return;
  Object.assign(expEstado, { exp, ficha: null, paso: 2, sugerido: null, fuera: [], sii: null });
  mostrarPantalla("pantalla-expedientes");
  mostrarAviso("Expediente " + exp.id + " creado para la OC " + oc.numero + ". Seguí con los remitos.", "exito");
}

// --- PDF de la OC ------------------------------------------------------------
// Antes de validar, cada OC se carga desde su PDF digital: objeto, cantidades, unidades y subrenglones (los servicios
// medidos en meses), que en el z_compras2 suelen venir mal. Se compara con lo cargado y se aplica solo lo marcado.

const CAMPOS_MONEDA_PDF = new Set(["precio_centavos", "importe_centavos", "desglose_precio_centavos"]);

function valorPdf(campo, valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (campo === "centralizada") return valor ? "Sí" : "No";
  if (CAMPOS_MONEDA_PDF.has(campo)) return "$ " + formatoPesos(valor);
  if (campo === "cantidad" || campo === "desglose_cantidad") return String(valor).replace(".", ",");
  return String(valor);
}

function textoCargaPdf(pdf) {
  return "Datos tomados del PDF el " + formatoFechaHora(pdf.fecha) + " por " + pdf.usuario
    + (pdf.archivo ? " (" + pdf.archivo + ")" : "") + ".";
}

/** Panel para subir el PDF de la OC; `alTerminar(ficha)` se llama después de aplicar los cambios. */
function seccionPdfOC(ficha, alTerminar, opciones = {}) {
  const { oc, pdf_oc: pdf } = ficha;
  const prefijo = "pdf-" + oc.numero;
  const archivo = el("input", { type: "file", accept: "application/pdf,.pdf" });
  const texto = el("textarea", { rows: "6", spellcheck: "false" });
  texto.id = prefijo + "-texto";
  const revision = el("div", { id: prefijo + "-revision", "aria-live": "polite" });
  const formulario = el("form", { clase: "formulario", novalidate: true,
    onsubmit: (e) => { e.preventDefault(); leerPdfOC(oc.numero, archivo, texto, revision, alTerminar); } },
    campoFormulario(prefijo + "-archivo", "PDF digital de la OC (el firmado en GDE)", archivo,
      "Se lee el texto del PDF; no sirve un escaneo."),
    el("details", {}, el("summary", { texto: "¿El PDF no se puede leer? Pegá su texto" }),
      el("div", { clase: "campo campo-ancho" }, el("label", { for: texto.id, texto: "Texto de la OC copiado del visor de PDF" }), texto)),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: pdf ? "Volver a leer el PDF" : "Leer y comparar" })));
  const estadoPdf = pdf
    ? el("p", { clase: "texto-suave", texto: "✓ " + textoCargaPdf(pdf) })
    : el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto:
      "Todavía no se cargó el PDF de esta OC. Subilo antes de validar: de ahí salen el objeto de la contratación, "
      + "las cantidades y los subrenglones." }));
  return el("section", { clase: "panel seccion-pdf-oc", "aria-labelledby": prefijo + "-titulo" },
    el("h3", { id: prefijo + "-titulo", texto: "PDF de la OC" + (opciones.obligatorio ? " *" : "") }), estadoPdf, formulario, revision);
}

async function leerPdfOC(numero, archivo, texto, destino, alTerminar) {
  limpiarAvisos();
  const ventana = destino.closest("dialog");
  const datos = new FormData();
  if (archivo.files[0]) datos.append("archivo", archivo.files[0], archivo.files[0].name);
  else if (texto.value.trim()) datos.append("texto", texto.value);
  else {
    if (ventana) avisoEnDialogo(ventana, "Elegí el PDF de la OC o pegá su texto.");
    else mostrarAviso("Elegí el PDF de la OC o pegá su texto.", "error");
    return;
  }
  cargando(destino);
  const comparacion = await api("POST", "/api/oc/" + encodeURIComponent(numero) + "/pdf", datos);
  vaciar(destino);
  if (!comparacion) { if (ventana) avisoEnDialogo(ventana, ultimoError()); return; }
  abrirColaPdf([{ tipo: "comparar", archivo: comparacion.archivo || "texto pegado", comparacion }], alTerminar);
}

function casillaTomar(id, etiqueta, marcada) {
  const control = el("input", { type: "checkbox", id, "aria-label": etiqueta });
  control.checked = !!marcada;
  return control;
}

function pintarRevisionPdf(destino, comparacion, alTerminar, opciones = {}) {
  const { oc, leido } = comparacion;
  const partes = [el("h4", { id: "pdf-revision-titulo", tabindex: "-1", texto: "Lo que dice el PDF de la OC " + oc.numero })];
  const resumen = [leido.razon_social && leido.razon_social + (leido.sap ? " (SAP " + leido.sap + ")" : ""),
    leido.procedimiento, leido.importe_total_centavos !== null && leido.importe_total_centavos !== undefined
      ? "importe total $ " + formatoPesos(leido.importe_total_centavos) : "",
    leido.prorroga ? "prórroga: " + leido.prorroga : ""].filter(Boolean).join(" · ");
  if (resumen) partes.push(el("p", { texto: resumen }));
  if (comparacion.avisos.length) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso", role: "status" },
      el("ul", { clase: "lista-avisos" }, ...comparacion.avisos.map((a) => el("li", { texto: a })))));
  }

  // Datos de la OC (el artículo va chiquito a la izquierda del objeto, no en una fila propia)
  const hayObjeto = comparacion.campos_oc.some((c) => c.campo === "objeto" && c.distinto);
  const filasOc = comparacion.campos_oc.filter((c) => !(c.campo === "objeto_articulo" && hayObjeto)).map((c) => {
    const id = "pdf-oc-" + c.campo;
    let valorNuevo = el("span", { texto: valorPdf(c.campo, c.pdf) });
    if (!c.distinto) {
      // igual en el gestor y en el PDF: solo se muestra
    } else if (c.campo === "objeto") {
      const editor = entrada(c.pdf, { id: id + "-valor", "aria-label": "Objeto a guardar", clase: "entrada-objeto" });
      const articulo = selector(leido.objeto_articulo || "al", OPCIONES_ARTICULO);
      articulo.id = "pdf-oc-objeto_articulo-valor";
      articulo.className = "selector-articulo";
      articulo.setAttribute("aria-label", "Artículo del objeto a guardar");
      valorNuevo = el("div", {}, el("div", { clase: "objeto-con-articulo" }, articulo, editor), leido.objeto_completo
        ? el("details", {}, el("summary", { texto: "Texto completo del PDF" }), el("p", { clase: "texto-suave", texto: leido.objeto_completo }))
        : null);
    } else if (c.campo === "objeto_articulo") {
      valorNuevo = selector(c.pdf, [["al", "al"], ["a la", "a la"], ["a los", "a los"], ["a las", "a las"]]);
      valorNuevo.id = id + "-valor";
      valorNuevo.setAttribute("aria-label", "Artículo del objeto a guardar");
    }
    const tomar = c.distinto
      ? casillaTomar(id, "Tomar del PDF: " + c.etiqueta, c.automatico || !c.manual || c.actual === "" || c.actual === null)
      : el("span", { clase: "texto-suave", texto: "Igual" });
    const nota = c.automatico ? " (automático)" : c.campo === "objeto" ? " (revisalo)" : c.manual ? " (editado a mano)" : "";
    return el("tr", {}, el("td", {}, tomar), el("th", { scope: "row", texto: c.etiqueta + nota }),
      el("td", { texto: valorPdf(c.campo, c.actual) }), el("td", {}, valorNuevo));
  });
  partes.push(el("h5", { texto: "Datos de la OC" }),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-revision" },
      el("thead", {}, el("tr", {}, ...["Tomar", "Dato", "En el gestor", "En el PDF"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filasOc))));

  // Renglones
  const filasRenglones = [];
  for (const r of comparacion.renglones) {
    const subrenglones = r.subrenglones.map((s) => "Subrenglón " + s.pos + ": " + valorPdf("cantidad", s.cantidad) + " " + s.unidad
      + (s.precio_centavos !== null ? " × $ " + formatoPesos(s.precio_centavos) : "")
      + (s.importe_centavos !== null ? " = $ " + formatoPesos(s.importe_centavos) : "")).join(" · ");
    const encabezado = el("th", { scope: "row", rowspan: String(Math.max(1, r.existe ? r.diferencias.length : 1)) },
      el("span", { texto: "Renglón " + r.pos }), el("br"), el("span", { clase: "texto-suave", texto: r.descripcion }),
      subrenglones ? el("p", { clase: "texto-suave subrenglones", texto: subrenglones }) : null);
    if (!r.existe) {
      const p = r.propuesta;
      filasRenglones.push(el("tr", {},
        el("td", {}, casillaTomar("pdf-r" + r.pos + "-nuevo", "Agregar el renglón " + r.pos + " del PDF", true)), encabezado,
        el("td", { texto: "Renglón nuevo" }), el("td", { texto: "No está en el gestor" }),
        el("td", { texto: p.cantidad + " " + p.unidad + " × $ " + formatoPesos(p.precio_centavos) + " = $ " + formatoPesos(p.importe_centavos)
          + (p.desglose_cantidad ? " (desglose " + p.desglose_cantidad + " " + p.desglose_unidad + " × $ " + formatoPesos(p.desglose_precio_centavos) + ")" : "") })));
      continue;
    }
    if (!r.diferencias.length) {
      filasRenglones.push(el("tr", {}, el("td", {}, el("span", { clase: "texto-suave", texto: "Igual" })), encabezado,
        el("td", { colspan: "3", texto: "Sin diferencias con el gestor." })));
      continue;
    }
    r.diferencias.forEach((d, i) => {
      const celdas = [el("td", {}, casillaTomar("pdf-r" + r.pos + "-" + d.campo, "Tomar del PDF: renglón " + r.pos + ", " + d.etiqueta, true))];
      if (i === 0) celdas.push(encabezado);
      celdas.push(el("td", { texto: d.etiqueta }), el("td", { texto: valorPdf(d.campo, d.actual) }), el("td", { texto: valorPdf(d.campo, d.pdf) }));
      filasRenglones.push(el("tr", {}, ...celdas));
    });
  }
  partes.push(el("h5", { texto: "Renglones" }),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-revision" },
      el("thead", {}, el("tr", {}, ...["Tomar", "Renglón", "Dato", "En el gestor", "En el PDF"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filasRenglones))));

  if (!opciones.sinBotones) {
    partes.push(el("div", { clase: "acciones" },
      el("button", { type: "button", texto: "Aplicar lo marcado", onclick: () => aplicarPdfOC(destino, comparacion, alTerminar) }),
      el("button", { type: "button", clase: "secundario", texto: "Descartar", onclick: () => vaciar(destino) })));
  }
  vaciar(destino, el("div", { clase: "revision-pdf" }, ...partes));
  document.getElementById("pdf-revision-titulo").focus();
}

function subrenglonPdf(s) {
  return { pos: s.pos, cantidad: String(s.cantidad), unidad: s.unidad || "", descripcion: s.descripcion || "",
    precio_centavos: s.precio_centavos ?? null };
}

async function aplicarPdfOC(destino, comparacion, alTerminar) {
  limpiarAvisos();
  const marcado = (id) => { const c = document.getElementById(id); return !!(c && c.checked); };
  const cambiosOc = {};
  const selArticulo = document.getElementById("pdf-oc-objeto_articulo-valor");
  const actualArticulo = (comparacion.campos_oc.find((c) => c.campo === "objeto_articulo") || {}).actual;
  if (selArticulo && marcado("pdf-oc-objeto") && selArticulo.value !== actualArticulo) cambiosOc.objeto_articulo = selArticulo.value;
  for (const c of comparacion.campos_oc) {
    if (c.campo === "objeto_articulo" && selArticulo) continue;
    if (!c.distinto || !marcado("pdf-oc-" + c.campo)) continue;
    const editor = document.getElementById("pdf-oc-" + c.campo + "-valor");
    cambiosOc[c.campo] = editor ? editor.value.trim() : c.pdf;
  }
  if ("objeto" in cambiosOc && !cambiosOc.objeto) { mostrarAviso("El objeto no puede quedar vacío.", "error"); errorAlaVentana(); return false; }
  const renglones = [];
  for (const r of comparacion.renglones) {
    if (!r.existe) {
      if (marcado("pdf-r" + r.pos + "-nuevo")) {
        const cambios = Object.fromEntries(Object.entries(r.propuesta).filter(([, v]) => v !== null && v !== ""));
        renglones.push({ pos: r.pos, version: null, cambios });
      }
      continue;
    }
    const cambios = {};
    for (const d of r.diferencias) if (marcado("pdf-r" + r.pos + "-" + d.campo)) cambios[d.campo] = d.pdf;
    if (Object.keys(cambios).length) renglones.push({ pos: r.pos, version: r.version, cambios });
  }
  estado.recargar = () => vaciar(destino);
  // Los subrenglones del PDF (1-10, 1-20…) se guardan siempre: son los que van en el certificado.
  const subrenglones = Object.fromEntries(comparacion.renglones.filter((r) => (r.subrenglones || []).length)
    .map((r) => [r.pos, r.subrenglones.map(subrenglonPdf)]));
  const ficha = await api("POST", "/api/oc/" + encodeURIComponent(comparacion.oc.numero) + "/pdf/aplicar", {
    version: comparacion.oc.version, archivo: comparacion.archivo || "", leido: comparacion.leido, oc: cambiosOc, renglones,
    subrenglones });
  if (!ficha) { errorAlaVentana(); return false; }
  const cantidad = Object.keys(cambiosOc).length + renglones.length;
  await alTerminar(ficha);
  if (colaPdf.dialogo) return true;
  mostrarAviso(cantidad
    ? "Datos del PDF aplicados a la OC " + ficha.oc.numero + "."
    : "Quedó registrado que la OC " + ficha.oc.numero + " coincide con su PDF.", "exito");
}

/** Ícono de lápiz (SVG, decorativo). */
function iconoLapiz() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [k, v] of [["viewBox", "0 0 24 24"], ["width", "16"], ["height", "16"], ["aria-hidden", "true"], ["focusable", "false"]]) svg.setAttribute(k, v);
  const trazo = document.createElementNS(ns, "path");
  trazo.setAttribute("d", "M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4");
  trazo.setAttribute("fill", "none"); trazo.setAttribute("stroke", "currentColor"); trazo.setAttribute("stroke-width", "1.8");
  trazo.setAttribute("stroke-linejoin", "round"); trazo.setAttribute("stroke-linecap", "round");
  svg.append(trazo);
  return svg;
}

/** Botón chiquito con un lápiz (44 px de alto igual, por accesibilidad). */
function botonLapiz(etiqueta, alHacerClic) {
  return el("button", { type: "button", clase: "secundario boton-lapiz", "aria-label": etiqueta, title: etiqueta, onclick: alHacerClic }, iconoLapiz());
}

/** Datos de la OC en modo lectura (lo demás —GDE del PDF, concepto corto, día de inicio— se ve al editar). */
function resumenDatosOC(oc, pdf) {
  const fecha = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "");
  const dato = (etiqueta, valor, clase) => el("div", { clase: "dato" + (clase ? " " + clase : "") },
    el("dt", { texto: etiqueta }), el("dd", { texto: valor === null || valor === undefined || valor === "" ? "—" : String(valor) }));
  const datos = [dato("Objeto", oc.objeto ? "Corresponde " + oc.objeto_articulo + " " + oc.objeto : "", "dato-ancho")];
  if (oc.tipo !== "BIEN") {
    datos.push(dato("Vigencia", oc.vig_desde || oc.vig_hasta
      ? (oc.vig_desde ? fecha(oc.vig_desde) : "") + (oc.vig_hasta ? " al " + fecha(oc.vig_hasta) : " (sin fin)") : ""));
  }
  datos.push(
    dato("Fecha de la OC", fecha(oc.fecha_oc)),
    dato("CA", oc.ca),
    dato("Expediente de contratación", oc.expediente_contratacion, "dato-mono"),
    dato("PDF de la OC", pdf ? "Cargado el " + formatoFechaHora(pdf.fecha) : "Falta cargarlo"),
    dato("Origen", oc.origen === "MANUAL" ? "Cargada a mano / desde su PDF" : "Importada de SAP" + (oc.cerrada_sap ? " (cerrada en SAP)" : "")));
  if (oc.centralizada) datos.push(dato("Leyenda del CV", oc.leyenda_cv, "dato-ancho"));
  if (oc.excluida) datos.push(dato("Excluida", oc.motivo_exclusion || "sí", "dato-ancho"));
  return el("dl", { clase: "datos-oc", "aria-label": "Datos de la OC " + oc.numero }, ...datos);
}

async function abrirDialogoEditarOC(numero) {
  limpiarAvisos();
  const ficha = await api("GET", "/api/oc/" + encodeURIComponent(numero));
  if (!ficha) return;
  const anterior = document.getElementById("dialogo-editar-oc");
  if (anterior) anterior.remove();
  let oc = ficha.oc;
  const manuales = new Set(oc.campos_manuales || []);
  const OBLIGATORIOS = new Set(["concepto_corto"]);
  const etiquetaDe = (campo, etiqueta) => etiqueta + (OBLIGATORIOS.has(campo) ? " *" : "") + (manuales.has(campo) ? " (editado a mano)" : "");
  const bloque = (campo) => {
    const [, etiqueta, tipo] = CAMPOS_OC_FORM.find(([c]) => c === campo);
    const control = controlCampoOC(campo, tipo, oc[campo]);
    if (tipo === "casilla") { control.querySelector("label").textContent = etiquetaDe(campo, etiqueta); return control; }
    return el("div", { clase: "campo", "data-campo": campo }, el("label", { for: control.id, texto: etiquetaDe(campo, etiqueta) }), control);
  };
  const periodo = el("div", { clase: "grilla-dialogo" }, bloque("vig_desde"), bloque("vig_hasta"), bloque("dia_inicio_periodo"));
  const leyenda = bloque("leyenda_cv");
  const exclusion = el("div", { clase: "grilla-dialogo" }, bloque("excluida"), bloque("motivo_exclusion"));
  const estadoGuardado = el("div", { id: "editar-oc-estado", "aria-live": "polite" });
  const encabezado = el("div", { clase: "dialogo-encabezado" },
    el("h2", { id: "editar-oc-titulo", texto: "Editar OC " + oc.numero + (ficha.proveedor ? " — " + ficha.proveedor.razon_social : "") }),
    el("p", { clase: "texto-suave", texto: "Lo que cambies queda marcado como cargado a mano: la importación del z_compras2 no lo pisa." }));
  const seccionPdf = seccionPdfOC(ficha, () => { dialogo.close(); abrirDialogoEditarOC(numero); }, { obligatorio: true });
  const formulario = el("form", { method: "dialog", clase: "formulario", novalidate: true,
    onsubmit: (e) => { e.preventDefault(); guardarDialogoOC(dialogo, () => oc, (nueva) => { oc = nueva; }); } },
    campoObjeto("oc-campo-objeto_articulo", "oc-campo-objeto", oc.objeto_articulo, oc.objeto, etiquetaDe("objeto", "Objeto (como va en la autorización)")),
    el("div", { clase: "grilla-dialogo" }, bloque("tipo"), bloque("concepto_corto"), bloque("comodato"), bloque("centralizada")),
    periodo,
    el("div", { clase: "grilla-dialogo" }, bloque("ca"), bloque("expediente_contratacion"), bloque("gde_pdf_oc")),
    leyenda,
    exclusion,
    el("div", { clase: "dialogo-acciones dialogo-pie" },
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Guardar cambios" }),
        el("button", { type: "button", clase: "secundario", texto: "Cerrar", onclick: () => dialogo.close() })),
      el("p", { clase: "nota-pie", texto: "Los campos señalados con (*) son obligatorios para crear expedientes de la OC. "
        + "Podés cerrar sin completarlos: la OC queda con «Acciones pendientes»." })));
  const dialogo = el("dialog", { id: "dialogo-editar-oc", clase: "dialogo dialogo-mediano", "aria-labelledby": "editar-oc-titulo" },
    encabezado, estadoGuardado, seccionPdf, formulario);
  const actualizarVisibles = () => {
    periodo.hidden = document.getElementById("oc-campo-tipo").value === "BIEN";
    leyenda.hidden = !document.getElementById("oc-campo-centralizada").checked;
  };
  dialogo.addEventListener("change", (e) => {
    if (["oc-campo-tipo", "oc-campo-centralizada"].includes(e.target.id)) actualizarVisibles();
    if (formulario.contains(e.target)) vaciar(estadoGuardado);
  });
  dialogo.addEventListener("close", () => {
    dialogo.remove();
    if (ocEstado.ficha && ocEstado.ficha.oc.numero === numero) abrirFichaOC(numero);
  });
  document.body.append(dialogo);
  actualizarVisibles();
  dialogo.showModal();
  document.getElementById("oc-campo-objeto").focus();
}

/** Guarda lo cambiado en la ventana y muestra la confirmación ahí mismo (la ventana queda abierta). */
async function guardarDialogoOC(dialogo, ocActual, alGuardar) {
  const oc = ocActual();
  const estadoGuardado = document.getElementById("editar-oc-estado");
  const cambios = {};
  for (const [campo, , tipo] of CAMPOS_OC_FORM) {
    const control = document.getElementById("oc-campo-" + campo);
    if (!control || control.closest("[hidden]")) continue;
    const valor = valorCampoOC(campo, tipo);
    const actual = oc[campo] ?? (tipo === "fecha" || tipo === "dia" ? null : "");
    if (valor !== actual) cambios[campo] = valor;
  }
  if (!Object.keys(cambios).length) {
    vaciar(estadoGuardado, el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: "No hay cambios para guardar." })));
    return;
  }
  limpiarAvisos();
  estado.recargar = () => { dialogo.close(); abrirDialogoEditarOC(oc.numero); };
  const ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero), { version: oc.version, cambios });
  if (!ficha) {
    const error = document.querySelector("#avisos .mensaje-error p");
    vaciar(estadoGuardado, el("div", { clase: "mensaje mensaje-error", role: "alert" },
      el("p", { texto: error ? error.textContent : "No se pudo guardar." })));
    return;
  }
  limpiarAvisos();
  alGuardar(ficha.oc);
  const nombres = Object.keys(cambios).map((c) => {
    const def = CAMPOS_OC_FORM.find(([k]) => k === c);
    return def ? def[1].replace(/ \(.*$/, "") : c;
  });
  vaciar(estadoGuardado, el("div", { clase: "mensaje mensaje-exito", role: "status" },
    el("p", { texto: "✓ Guardado: " + nombres.join(", ") + "." })));
  estadoGuardado.scrollIntoView({ block: "nearest" });
  if (document.getElementById("oc-lista")) listarOC();
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
    casilla("rg-correctivo", "Es un renglón de mantenimiento correctivo", r.es_correctivo));
  if (!nuevo && ocEstado.ficha && ocEstado.ficha.oc.centralizada) {
    const reparto = r.por_efector || {};
    campos.push(el("fieldset", { clase: "campo campo-ancho editor-subrenglones" },
      el("legend", { texto: "Cantidad de cada efector (OC centralizada)" }),
      el("p", { clase: "texto-suave", texto: "En la misma unidad que el consumo (" + (r.desglose_unidad || r.unidad || "unidades")
        + "). Si el renglón es de un solo efector, poné 0 en el otro. Vacío los dos = toda la cantidad para cada uno." }),
      el("div", { clase: "grilla-dialogo" },
        campoFormulario("rg-ef-HBI", "HBI", entrada(textoCantidad(reparto.HBI), { inputmode: "decimal" })),
        campoFormulario("rg-ef-CASPH", "CASPH", entrada(textoCantidad(reparto.CASPH), { inputmode: "decimal" })))));
  }
  if (!nuevo) campos.push(editorSubrenglones(r));
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

/** Subrenglones del renglón (1-10, 1-20…): descripción, cantidad y unidad, como van en el certificado. */
function editorSubrenglones(r) {
  const cuerpo = el("tbody", { id: "rg-subrenglones" });
  const fila = (s) => el("tr", {},
    el("td", {}, entrada(s.pos ?? "", { "data-campo": "pos", inputmode: "numeric", clase: "entrada-mini", "aria-label": "Subrenglón" })),
    el("td", {}, entrada(s.descripcion || "", { "data-campo": "descripcion", "aria-label": "Descripción del subrenglón" })),
    el("td", {}, entrada(textoCantidad(s.cantidad), { "data-campo": "cantidad", inputmode: "decimal", clase: "entrada-chica",
      "aria-label": "Cantidad del subrenglón" })),
    el("td", {}, entrada(s.unidad || "", { "data-campo": "unidad", clase: "entrada-mini", "aria-label": "Unidad del subrenglón" })),
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Quitar", onclick: (e) => e.target.closest("tr").remove() })));
  for (const s of r.subrenglones || []) cuerpo.append(fila(s));
  for (const [k, s] of (r.subrenglones || []).entries()) cuerpo.children[k].dataset.precio = s.precio_centavos ?? "";
  return el("fieldset", { clase: "campo campo-ancho editor-subrenglones" },
    el("legend", { texto: "Subrenglones (van así en el certificado de validación)" }),
    el("p", { clase: "texto-suave", texto: "Lo entregado se asigna en orden: primero se completa el primero y después el siguiente." }),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-renglones-dialogo" },
      el("thead", {}, el("tr", {}, ...["Sub.", "Descripción", "Cantidad", "Unidad", ""].map((t) => el("th", { scope: "col", texto: t })))),
      cuerpo)),
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "+ Subrenglón",
      onclick: () => { const n = cuerpo.children.length; cuerpo.append(fila({ pos: (n + 1) * 10, unidad: r.desglose_unidad || "" })); } })));
}

/** Subrenglones del editor, o null si hay un dato mal (ya avisado). */
function subrenglonesDelEditor() {
  const filas = document.querySelectorAll("#rg-subrenglones tr");
  const lista = [];
  for (const f of filas) {
    const v = (c) => f.querySelector('[data-campo="' + c + '"]').value.trim();
    if (!v("pos") && !v("cantidad") && !v("descripcion")) continue;
    if (!/^\d+$/.test(v("pos"))) { mostrarAviso("El número de subrenglón debe ser un número (por ejemplo 10).", "error"); return null; }
    if (!/^\d+([.,]\d+)?$/.test(v("cantidad"))) { mostrarAviso("Revisá la cantidad del subrenglón " + v("pos") + ".", "error"); return null; }
    const precio = f.dataset.precio;
    lista.push({ pos: Number(v("pos")), cantidad: v("cantidad").replace(",", "."), unidad: v("unidad").toUpperCase(),
      descripcion: v("descripcion"), precio_centavos: precio === undefined || precio === "" ? null : Number(precio) });
  }
  return lista.sort((a, b) => a.pos - b.pos);
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
    const subrenglones = subrenglonesDelEditor();
    if (subrenglones === null) return;
    const cambioSub = JSON.stringify(subrenglones) !== JSON.stringify((renglon.subrenglones || []).map(subrenglonPdf));
    const reparto = {};
    for (const ef of ["HBI", "CASPH"]) {
      const control = document.getElementById("rg-ef-" + ef);
      const texto = control ? control.value.trim().replace(",", ".") : "";
      if (texto && !/^\d+(\.\d+)?$/.test(texto)) { mostrarAviso("La cantidad de " + ef + " no es un número.", "error"); return; }
      if (texto) reparto[ef] = texto;
    }
    const anterior = renglon.por_efector || {};
    const cambioReparto = Boolean(document.getElementById("rg-ef-HBI"))
      && ["HBI", "CASPH"].some((ef) => (reparto[ef] ?? "") !== (anterior[ef] ?? ""));
    if (!Object.keys(cambios).length && !cambioSub && !cambioReparto) { mostrarAviso("No hay cambios para guardar.", "aviso"); return; }
    let version = renglon.version;
    if (Object.keys(cambios).length) {
      ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero) + "/renglones/" + renglon.pos, { version, cambios });
      if (!ficha) return;
      version = ficha.renglones.find((x) => x.pos === renglon.pos).version;
    }
    if (cambioSub) {
      ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero) + "/renglones/" + renglon.pos + "/subrenglones",
        { version, subrenglones });
      if (!ficha) return;
      version = ficha.renglones.find((x) => x.pos === renglon.pos).version;
    }
    if (cambioReparto) {
      ficha = await api("PUT", "/api/oc/" + encodeURIComponent(oc.numero) + "/renglones/" + renglon.pos + "/efectores",
        { version, por_efector: reparto });
    }
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
    campoObjeto("alta-articulo", "alta-objeto", "al", "", "Objeto"),
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

// --- Nueva OC desde su PDF: se lee el PDF y se confirman los datos en una ventana ------------------------------

// --- Revisión de PDF de OC en una ventana: una o varias, «Confirmar datos (2/5)» ---------------------------------
// Cada PDF es una OC nueva (se confirman sus datos y se crea) o una que ya está (se compara y se aplica lo marcado).

const colaPdf = { items: [], i: 0, dialogo: null, alTerminar: null };

/** Lee los PDF elegidos en «Nueva OC» y abre la ventana para revisarlos uno por uno. */
async function procesarPdfsOC(archivos) {
  limpiarAvisos();
  const items = archivos.map((f) => ({ tipo: "leyendo", archivo: f.name, file: f }));
  abrirColaPdf(items, null);
  for (let n = 0; n < items.length; n++) {
    const item = items[n];
    if (colaPdf.dialogo) pintarLeyendo(n + 1, items.length, item.archivo);
    const datos = new FormData();
    datos.append("archivo", item.file, item.file.name);
    const respuesta = await api("POST", "/api/oc/pdf", datos);
    if (!respuesta) { Object.assign(item, { tipo: "error", error: ultimoError() }); continue; }
    if (!respuesta.existe) { Object.assign(item, { tipo: "nueva", leido: respuesta.leido }); continue; }
    const otra = new FormData();
    otra.append("archivo", item.file, item.file.name);
    const comparacion = await api("POST", "/api/oc/" + encodeURIComponent(respuesta.leido.numero) + "/pdf", otra);
    if (comparacion) Object.assign(item, { tipo: "comparar", comparacion });
    else Object.assign(item, { tipo: "error", error: ultimoError() });
  }
  limpiarAvisos();
  if (colaPdf.dialogo) mostrarItemCola();
}

function ultimoError() {
  const aviso = document.querySelector("#avisos .mensaje-error p");
  const texto = aviso ? aviso.textContent : "No se pudo leer el PDF.";
  limpiarAvisos();
  return texto;
}

/** Copia el último error de la página a la ventana abierta (los avisos de atrás quedan tapados). */
function errorAlaVentana() {
  if (!colaPdf.dialogo) return;
  avisoEnDialogo(colaPdf.dialogo, ultimoError());
}

function abrirColaPdf(items, alTerminar) {
  if (colaPdf.dialogo) colaPdf.dialogo.close();
  const dialogo = el("dialog", { id: "dialogo-pdf-oc", clase: "dialogo", "aria-labelledby": "cola-titulo" });
  Object.assign(colaPdf, { items, i: 0, dialogo, alTerminar });
  dialogo.addEventListener("close", () => {
    dialogo.remove();
    if (colaPdf.dialogo === dialogo) colaPdf.dialogo = null;
    const hubo = items.some((x) => x.resultado === "creada" || x.resultado === "actualizada");
    if (hubo && !alTerminar && document.getElementById("oc-lista")) {
      const creadas = items.filter((x) => x.resultado === "creada");
      if (items.length === 1 && creadas.length === 1) abrirFichaOC(creadas[0].leido.numero);
      else if (ocEstado.ficha) abrirFichaOC(ocEstado.ficha.oc.numero); else listarOC();
    }
  });
  document.body.append(dialogo);
  dialogo.showModal();
  if (items.some((x) => x.tipo === "leyendo")) pintarLeyendo(1, items.length, items[0].archivo);
  else mostrarItemCola();
}

function encabezadoCola(titulo, detalle) {
  const total = colaPdf.items.length;
  return el("div", { clase: "dialogo-encabezado" },
    el("h2", { id: "cola-titulo", tabindex: "-1", texto: titulo }),
    detalle ? el("p", { clase: "texto-suave", texto: detalle }) : null,
    total > 1 ? el("div", { clase: "barra-progreso", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(total),
      "aria-valuenow": String(Math.min(colaPdf.i, total)) },
      el("span", { style: "width:" + Math.round(100 * Math.min(colaPdf.i, total) / total) + "%" })) : null);
}

function pintarLeyendo(n, total, archivo) {
  vaciar(colaPdf.dialogo, encabezadoCola("Leyendo los PDF (" + n + "/" + total + ")…", archivo), el("p", { texto: "Cargando…" }));
}

function siguienteDeCola(resultado) {
  const item = colaPdf.items[colaPdf.i];
  item.resultado = resultado;
  colaPdf.i += 1;
  if (colaPdf.items.length === 1 && colaPdf.dialogo) {
    colaPdf.dialogo.close();
    const numero = (item.leido && item.leido.numero) || (item.comparacion && item.comparacion.oc.numero) || "";
    if (resultado === "creada") mostrarAviso("Se creó la OC " + numero + " con los datos confirmados.", "exito");
    if (resultado === "actualizada") mostrarAviso("Se aplicó lo marcado del PDF a la OC " + numero + ".", "exito");
    return;
  }
  mostrarItemCola();
}

function mostrarItemCola() {
  const dialogo = colaPdf.dialogo;
  if (!dialogo) return;
  const { items, i } = colaPdf;
  if (i >= items.length) { pintarResumenCola(); return; }
  const item = items[i];
  const paso = items.length > 1 ? " (" + (i + 1) + "/" + items.length + ")" : "";
  const saltear = el("button", { type: "button", clase: "secundario", texto: items.length > 1 ? "Saltear" : "Cancelar",
    onclick: () => (items.length > 1 ? siguienteDeCola("salteada") : dialogo.close()) });
  const cancelarResto = items.length > 1 && i < items.length - 1
    ? el("button", { type: "button", clase: "enlace", texto: "Cancelar las que faltan", onclick: () => {
      for (let k = i; k < items.length; k++) items[k].resultado = items[k].resultado || "salteada";
      colaPdf.i = items.length; mostrarItemCola(); } })
    : null;
  if (item.tipo === "error") {
    vaciar(dialogo, encabezadoCola("No se pudo leer el PDF" + paso, item.archivo),
      el("div", { clase: "mensaje mensaje-error", role: "alert" }, el("p", { texto: item.error })),
      el("div", { clase: "acciones dialogo-acciones" },
        el("button", { type: "button", texto: items.length > 1 ? "Seguir" : "Cerrar",
          onclick: () => (items.length > 1 ? siguienteDeCola("error") : dialogo.close()) }), cancelarResto));
    document.getElementById("cola-titulo").focus();
    return;
  }
  if (item.tipo === "nueva") {
    const leido = item.leido;
    const crear = el("button", { type: "button", texto: items.length > 1 && i < items.length - 1 ? "Crear OC y seguir" : "Crear OC",
      onclick: async () => {
        crear.disabled = true;
        const ficha = await crearNuevaOC(dialogo, leido, item.archivo);
        crear.disabled = false;
        if (ficha) siguienteDeCola("creada");
      } });
    vaciar(dialogo, encabezadoCola("Confirmar datos" + paso + " — OC nueva " + (leido.numero || ""),
      item.archivo + ": revisá lo que se leyó del PDF y corregí lo que haga falta."),
      formularioNuevaOC(leido),
      el("div", { clase: "acciones dialogo-acciones" }, crear, saltear, cancelarResto));
    const objeto = document.getElementById("noc-objeto");
    if (objeto) objeto.focus();
    return;
  }
  // OC que ya está en el gestor: comparación con el PDF.
  const comparacion = item.comparacion;
  const cuerpo = el("div", {});
  const aplicar = el("button", { type: "button", texto: items.length > 1 && i < items.length - 1 ? "Aplicar y seguir" : "Aplicar lo marcado",
    onclick: async () => {
      aplicar.disabled = true;
      const ok = await aplicarPdfOC(cuerpo, comparacion, async (ficha) => {
        if (colaPdf.alTerminar) await colaPdf.alTerminar(ficha);
      });
      aplicar.disabled = false;
      if (ok) siguienteDeCola("actualizada");
    } });
  vaciar(dialogo, encabezadoCola("Confirmar datos" + paso + " — OC " + comparacion.oc.numero + " (ya está en el gestor)",
    item.archivo + ": tildá lo que querés tomar del PDF."), cuerpo,
    el("div", { clase: "acciones dialogo-acciones" }, aplicar, saltear, cancelarResto));
  pintarRevisionPdf(cuerpo, comparacion, null, { sinBotones: true });
}

function pintarResumenCola() {
  const dialogo = colaPdf.dialogo;
  const textos = { creada: "Creada", actualizada: "Actualizada", salteada: "Salteada", error: "No se pudo leer" };
  const tonos = { creada: "exito", actualizada: "info", salteada: "neutra", error: "error" };
  const cuenta = (r) => colaPdf.items.filter((x) => x.resultado === r).length;
  const filas = colaPdf.items.map((x) => el("tr", {},
    el("td", { clase: "izq", texto: x.archivo }),
    el("td", { texto: (x.leido && x.leido.numero) || (x.comparacion && x.comparacion.oc.numero) || "—" }),
    el("td", {}, el("span", { clase: "pastilla pastilla-" + (tonos[x.resultado] || "neutra"), texto: textos[x.resultado] || "Salteada" }))));
  vaciar(dialogo, encabezadoCola("Listo",
      [cuenta("creada") + " creadas", cuenta("actualizada") + " actualizadas", cuenta("salteada") + " salteadas",
        cuenta("error") ? cuenta("error") + " sin leer" : ""].filter(Boolean).join(" · ")),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { scope: "col", clase: "izq", texto: "Archivo" }), el("th", { scope: "col", texto: "OC" }),
        el("th", { scope: "col", texto: "Resultado" }))),
      el("tbody", {}, ...filas))),
    el("div", { clase: "acciones dialogo-acciones" }, el("button", { type: "button", texto: "Cerrar", onclick: () => dialogo.close() })));
  document.getElementById("cola-titulo").focus();
}

function textoCantidad(valor) {
  return valor === null || valor === undefined ? "" : String(valor).replace(".", ",");
}

/** Formulario de la OC nueva con lo leído del PDF (va dentro de la ventana de revisión). */
function formularioNuevaOC(leido) {
  const efectorPorDefecto = leido.efector || (estado.efector === "CASPH" ? "CASPH" : "HBI");
  const tipo = selector(leido.tipo || "SERVICIO", [["SERVICIO", "Servicio"], ["BIEN", "Bien"], ["PROVISION", "Provisión"]]);
  const campo = (id, etiqueta, control, ayuda) => campoFormulario("noc-" + id, etiqueta, control, ayuda);
  const periodo = el("div", { clase: "grilla-dialogo", id: "noc-periodo" },
    campo("desde", "Vigencia desde", entrada(leido.vig_desde || "", { type: "date" })),
    campo("hasta", "Vigencia hasta", entrada(leido.vig_hasta || "", { type: "date" })),
    campo("dia", "Día de inicio del período", entrada(String(leido.dia_inicio_periodo || 1), { type: "number", min: "1", max: "28" }),
      "Sale del día en que arranca la vigencia (1 = mes calendario)."));
  const mostrarPeriodo = () => { periodo.hidden = tipo.value === "BIEN"; };
  const centralizada = casilla("noc-centralizada", "Es centralizada (UOC: Nivel central)", leido.centralizada === 1);

  const filas = (leido.renglones || []).map((r) => {
    const d = r.desglose || {};
    const celda = (campoR, valor, atributos) => el("td", {}, entrada(valor ?? "", Object.assign({
      "data-campo": campoR, "aria-label": campoR.replace(/_/g, " ") + " del renglón " + r.pos }, atributos || {})));
    return el("tr", { "data-pos": String(r.pos) },
      el("td", { clase: "numero", texto: String(r.pos) }),
      celda("codigo", r.codigo, { clase: "entrada-chica" }),
      celda("descripcion", r.descripcion),
      celda("cantidad", textoCantidad(r.cantidad), { inputmode: "decimal", clase: "entrada-chica" }),
      celda("unidad", r.unidad, { clase: "entrada-mini" }),
      celda("precio", formatoPesos(r.precio_centavos), { inputmode: "decimal", clase: "entrada-plata" }),
      celda("importe", formatoPesos(r.importe_centavos), { inputmode: "decimal", clase: "entrada-plata" }),
      celda("desglose_cantidad", textoCantidad(d.cantidad), { inputmode: "decimal", clase: "entrada-chica" }),
      celda("desglose_unidad", d.unidad || "", { clase: "entrada-mini" }),
      celda("desglose_precio", d.precio_centavos ? formatoPesos(d.precio_centavos) : "", { inputmode: "decimal", clase: "entrada-plata" }));
  });

  const avisos = (leido.avisos || []).length
    ? el("div", { clase: "mensaje mensaje-aviso" }, el("ul", { clase: "lista-avisos" }, ...leido.avisos.map((a) => el("li", { texto: a }))))
    : null;
  const textoCompleto = leido.objeto_completo
    ? el("details", {}, el("summary", { texto: "Texto completo del objeto en el PDF" }), el("p", { clase: "texto-suave", texto: leido.objeto_completo }))
    : null;

  const formulario = el("form", { clase: "formulario", novalidate: true, onsubmit: (e) => e.preventDefault() },
    avisos,
    el("div", { clase: "grilla-dialogo" },
      campo("numero", "N° de OC", entrada(leido.numero || "", { inputmode: "numeric" })),
      campo("efector", "Efector", selector(efectorPorDefecto, [["HBI", "HBI"], ["CASPH", "CASPH"]])),
      campo("tipo", "Tipo", tipo),
      campo("fecha", "Fecha de la OC", entrada(leido.fecha_oc || "", { type: "date" }))),
    el("div", { clase: "grilla-dialogo" },
      campo("sap", "N° SAP del proveedor", entrada(leido.sap || "", { inputmode: "numeric" })),
      campo("razon", "Razón social", entrada(leido.razon_social || ""))),
    campoObjeto("noc-articulo", "noc-objeto", leido.objeto_articulo, leido.objeto, "Objeto de la contratación (revisalo)", textoCompleto),
    periodo,
    el("div", { clase: "grilla-dialogo" },
      campo("ca", "CA (licitación-año)", entrada(leido.ca || "")),
      campo("expediente", "Expediente de contratación (GDE)", entrada(leido.expediente_contratacion || "", { clase: "mono" })),
      campo("gde", "N° GDE del PDF de la OC", entrada(leido.gde_pdf_oc || "", { clase: "mono" }))),
    el("div", { clase: "grilla-dialogo" },
      campo("concepto", "Concepto corto (Texto SAP)", entrada(""), "Opcional: lo podés completar después."),
      centralizada),
    el("h3", { texto: "Renglones" }),
    el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-renglones-dialogo" },
      el("thead", {}, el("tr", {}, ...["Rgl.", "Código", "Descripción", "Cantidad", "Unidad", "Precio $", "Importe $",
        "Desglose: cant.", "Unidad", "Precio $"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filas))),
  );
  formulario.addEventListener("change", (e) => { if (e.target === tipo) mostrarPeriodo(); });
  setTimeout(mostrarPeriodo, 0);
  return formulario;
}

/** Crea la OC con lo confirmado en la ventana; devuelve la ficha o null (el error queda en la ventana). */
async function crearNuevaOC(dialogo, leido, archivo) {
  const valor = (id) => document.getElementById("noc-" + id).value.trim();
  const renglones = [];
  for (const fila of dialogo.querySelectorAll("tbody tr")) {
    const v = (campoR) => fila.querySelector('[data-campo="' + campoR + '"]').value.trim();
    const pos = Number(fila.dataset.pos);
    const precio = pesosACentavos(v("precio"));
    const importe = pesosACentavos(v("importe"));
    if (precio === null || Number.isNaN(precio)) { avisoEnDialogo(dialogo, "Revisá el precio del renglón " + pos + "."); return null; }
    if (Number.isNaN(importe)) { avisoEnDialogo(dialogo, "Revisá el importe del renglón " + pos + "."); return null; }
    const renglon = { pos, codigo: v("codigo"), descripcion: v("descripcion"), cantidad: v("cantidad") || "1", unidad: v("unidad"),
      precio_centavos: precio };
    if (importe !== null) renglon.importe_centavos = importe;
    if (v("desglose_cantidad")) {
      const precioDesglose = pesosACentavos(v("desglose_precio"));
      if (precioDesglose === null || Number.isNaN(precioDesglose)) { avisoEnDialogo(dialogo, "Revisá el precio del desglose del renglón " + pos + "."); return null; }
      Object.assign(renglon, { desglose_cantidad: v("desglose_cantidad"), desglose_unidad: v("desglose_unidad") || "MES",
        desglose_precio_centavos: precioDesglose });
    }
    renglones.push(renglon);
  }
  const tipo = valor("tipo");
  const datos = {
    numero: valor("numero"), efector: valor("efector"), sap: valor("sap"), razon_social: valor("razon"),
    fecha_oc: valor("fecha") || null, tipo, ca: valor("ca"), expediente_contratacion: valor("expediente"),
    gde_pdf_oc: valor("gde"), objeto: valor("objeto"), objeto_articulo: document.getElementById("noc-articulo").value,
    concepto_corto: valor("concepto"), centralizada: document.getElementById("noc-centralizada").checked ? 1 : 0, renglones,
  };
  if (tipo !== "BIEN") {
    Object.assign(datos, { vig_desde: valor("desde") || null, vig_hasta: valor("hasta") || null,
      dia_inicio_periodo: Number(valor("dia") || "1") });
  }
  if (!datos.objeto) { avisoEnDialogo(dialogo, "Falta el objeto de la contratación."); return null; }
  const cabecera = Object.fromEntries(Object.entries(leido).filter(([k]) => k !== "renglones" && k !== "avisos"));
  const subrenglones = Object.fromEntries((leido.renglones || []).filter((r) => (r.subrenglones || []).length)
    .map((r) => [r.pos, r.subrenglones.map(subrenglonPdf)]));
  const ficha = await api("POST", "/api/oc/desde-pdf", { oc: datos, archivo: archivo || "", leido: cabecera, subrenglones });
  if (!ficha) { errorAlaVentana(); return null; }
  limpiarAvisos();
  return ficha;
}

/** Mensaje de error dentro de la ventana (los avisos de la página quedan tapados por el fondo del diálogo). */
function avisoEnDialogo(dialogo, texto) {
  let caja = dialogo.querySelector(".dialogo-error");
  if (!caja) {
    caja = el("div", { clase: "mensaje mensaje-error dialogo-error", role: "alert" }, el("p"));
    dialogo.querySelector(".dialogo-encabezado").after(caja);
  }
  caja.querySelector("p").textContent = texto;
  caja.scrollIntoView({ block: "nearest" });
}

// --- Expedientes: lista ------------------------------------------------------

const ESTADOS_TEXTO = {
  BORRADOR: "Borrador", CONTROLADO: "Controlado", EN_FIRMA: "En firma", FIRMADO: "Firmado", COMPLETO: "Completo", ENVIADO: "Enviado",
  CONTABILIZADO: "Contabilizado", CERRADO: "Cerrado", PENDIENTE: "Pendiente", ANULADO: "Anulado",
  RECIBIDO_MANTENIMIENTO: "Recibido de Mantenimiento", INFORME_ECONOMICO: "Informe económico", DEVUELTO: "Devuelto",
  PARA_FACTURAR: "Para facturar", ARMADO: "Armado", EN_DTO_ECONOMICO_CONTABLE: "En Dto. Económico Contable",
  FINALIZADO: "Finalizado",
};
const TONO_ESTADO = {
  BORRADOR: "", CONTROLADO: "info", EN_FIRMA: "violeta", FIRMADO: "violeta", COMPLETO: "exito", ENVIADO: "info", CONTABILIZADO: "exito",
  CERRADO: "exito", FINALIZADO: "exito", PENDIENTE: "aviso", ANULADO: "error", DEVUELTO: "aviso",
  RECIBIDO_MANTENIMIENTO: "info", INFORME_ECONOMICO: "info", PARA_FACTURAR: "info", ARMADO: "info",
  EN_DTO_ECONOMICO_CONTABLE: "violeta",
};

/** Estado del expediente como pastilla: la palabra siempre está; el color solo acompaña. */
function pastillaEstado(estadoExp) {
  const tono = TONO_ESTADO[estadoExp];
  return el("span", { clase: "pastilla" + (tono ? " pastilla-" + tono : ""), texto: ESTADOS_TEXTO[estadoExp] || estadoExp });
}

// Las centralizadas no son expedientes de pago: se validan desde «Centralizadas» o la ficha de la OC.
const TIPOS_EXPEDIENTE = [["COMUN", "Común"], ["CORRECTIVO", "Correctivo"], ["EVENTUAL", "Pago eventual"]];

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
  listarPendientes();
  pintarServiciosCasph();
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
    el("td", {}, el("button", { type: "button", clase: "secundario boton-celda", texto: String(x.id),
      "aria-label": "Abrir el expediente " + x.id, onclick: () => abrirExpediente(x.id, null) })),
    el("td", { texto: (TIPOS_EXPEDIENTE.find(([v]) => v === x.tipo) || [null, x.tipo])[1] }),
    el("td", { texto: x.oc || "—" }),
    el("td", { clase: "izq", texto: (x.razon_social || "") + (x.sap ? " (SAP " + x.sap + ")" : "") }),
    el("td", { texto: x.periodo || "—" }),
    el("td", { texto: x.factura || "—" }),
    el("td", {}, pastillaEstado(x.estado))));
  vaciar(lista,
    el("p", { clase: "texto-suave", texto: expedientes.length + (expedientes.length === 1 ? " expediente" : " expedientes") }),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...encabezados.map((t) => el("th", { scope: "col", clase: claseColumna(t), texto: t })))),
      el("tbody", {}, ...filas))));
}

// --- Expedientes: asistente ------------------------------------------------

/** Anular (no se borra nada): queda en estado Anulado con su motivo y deja de contar para consumo y duplicados. */
function abrirDialogoAnular() {
  const exp = expEstado.exp;
  if (!exp) return;
  const anterior = document.getElementById("dialogo-anular");
  if (anterior) anterior.remove();
  const motivo = el("textarea", { id: "anular-motivo", rows: "3" });
  const confirmar = el("button", { type: "button", clase: "boton-peligro-lleno", texto: "Anular expediente " + exp.id });
  const dialogo = el("dialog", { id: "dialogo-anular", clase: "dialogo dialogo-mediano", "aria-labelledby": "anular-titulo" },
    el("div", { clase: "dialogo-encabezado" },
      el("h2", { id: "anular-titulo", texto: "Anular el expediente " + exp.id }),
      el("p", { clase: "texto-suave", texto: "No se borra: queda en estado «Anulado» con el motivo, deja de contar para el consumo "
        + "de la OC y para los controles de factura repetida, y se puede consultar igual." })),
    el("div", { clase: "campo campo-ancho" },
      el("label", { for: "anular-motivo", texto: "Motivo (obligatorio)" }), motivo,
      el("p", { clase: "texto-suave", texto: "Por ejemplo: «Duplicado del expediente 118»." })),
    el("div", { clase: "acciones dialogo-acciones" }, confirmar,
      el("button", { type: "button", clase: "secundario", texto: "Cancelar", onclick: () => dialogo.close() })));
  confirmar.addEventListener("click", async () => {
    const texto = motivo.value.trim();
    if (!texto) { avisoEnDialogo(dialogo, "Escribí el motivo de la anulación."); motivo.focus(); return; }
    confirmar.disabled = true;
    estado.recargar = () => { dialogo.close(); abrirExpediente(exp.id, expEstado.paso); };
    const anulado = await api("POST", "/api/expedientes/" + exp.id + "/anular", { version: exp.version, motivo: texto });
    confirmar.disabled = false;
    if (!anulado) { avisoEnDialogo(dialogo, ultimoError()); return; }
    dialogo.close();
    mostrarLista();
    mostrarAviso("Expediente " + exp.id + " anulado: " + texto, "exito");
  });
  dialogo.addEventListener("close", () => dialogo.remove());
  document.body.append(dialogo);
  dialogo.showModal();
  motivo.focus();
}

function mostrarAsistente() {
  document.getElementById("expedientes-lista-bloque").hidden = true;
  document.getElementById("asistente").hidden = false;
}

function pintarEncabezadoAsistente() {
  const { exp, ficha } = expEstado;
  const titulo = document.getElementById("asistente-titulo");
  const resumen = document.getElementById("asistente-resumen");
  if (!exp) {
    document.getElementById("asistente-anular").hidden = true;
    titulo.textContent = "Nuevo expediente";
    resumen.textContent = "Elegí el tipo y la OC para empezar.";
    return;
  }
  titulo.textContent = (exp.tipo === "CENTRALIZADA" ? "Validación " : "Expediente ") + exp.id + " — " + (exp.razon_social || "sin proveedor");
  document.getElementById("asistente-anular").hidden = exp.estado === "ANULADO";
  resumen.textContent = [
    exp.oc ? "OC " + exp.oc : "sin OC",
    "período " + (exp.periodo || "sin definir") + (exp.periodo_manual ? " (manual)" : ""),
    "estado " + (exp.tipo === "CENTRALIZADA" ? (ESTADOS_CENTRALIZADA_TEXTO[exp.estado] || exp.estado)
      : (ESTADOS_TEXTO[exp.estado] || exp.estado)) + (exp.tipo === "CENTRALIZADA" ? " · validación centralizada de " + exp.efector : ""),
    ficha && ficha.oc.comodato ? "OC con comodato" : "",
  ].filter(Boolean).join(" · ");
}

// Validación centralizada: 4 pasos propios (no hay factura, SII ni autorización: eso lo hace Nivel Central).
const PASOS_CENTRALIZADA = { 1: "1. OC y período", 2: "2. Remitos y certificado", 3: "3. CV firmado", 4: "4. Nota a Central" };
const ESTADOS_CENTRALIZADA_TEXTO = { BORRADOR: "En curso", CONTROLADO: "En curso", EN_FIRMA: "En curso", FIRMADO: "CV firmado",
  ENVIADO: "Validado", ANULADO: "Anulada" };

function esCentralizada() {
  return Boolean(expEstado.exp && expEstado.exp.tipo === "CENTRALIZADA");
}

// Pasos del asistente: [contenedor, título]. El expediente común sigue el orden real del trámite; los demás tipos,
// el asistente clásico. Los contenedores 8 a 14 son los pasos nuevos del trámite (los 4 a 7 quedan para los clásicos).
const PASOS_TRAMITE = [
  [1, "1. OC y período"], [2, "2. Remitos"], [8, "3. Certificado de validación"], [9, "4. Ingreso en SAP"],
  [3, "5. Factura y SII"], [10, "6. Caratulación"], [11, "7. Carga en GDE"], [12, "8. Factura en SAP"],
  [13, "9. Autorización de pago"], [14, "10. Cierre"],
];
const PASOS_CLASICOS = [[1, "1. OC y período"], [2, "2. Remitos"], [3, "3. Factura y SII"], [4, "4. Controles"],
  [5, "5. Textos"], [6, "6. Documentos"], [7, "7. Estado"]];
// Pasos del asistente clásico que en el trámite viven en otro lado (controles → caratulación, GDE, estado → cierre).
const PASO_CLASICO_EN_TRAMITE = { 4: 10, 5: 10, 6: 11, 7: 14 };

function esTramite() {
  return Boolean(expEstado.exp && expEstado.exp.tipo === "COMUN");
}

function pasosDelAsistente() {
  if (esCentralizada()) return Object.entries(PASOS_CENTRALIZADA).map(([n, t]) => [Number(n), t]);
  return esTramite() ? PASOS_TRAMITE : PASOS_CLASICOS;
}

function tituloPaso(n, porDefecto) {
  const paso = pasosDelAsistente().find(([m]) => m === n);
  return paso ? paso[1] : porDefecto;
}

/** Botón para seguir al paso que viene en el orden del asistente. */
function botonSiguiente(clase) {
  const pasos = pasosDelAsistente();
  const i = pasos.findIndex(([n]) => n === expEstado.paso);
  const siguiente = i >= 0 ? pasos[i + 1] : null;
  if (!siguiente) return null;
  return el("button", { type: "button", clase: clase === undefined ? "secundario" : clase, texto: "Seguir: " + siguiente[1],
    onclick: () => { limpiarAvisos(); mostrarPaso(siguiente[0]); } });
}

/** Paso en el que conviene abrir un expediente común según lo que ya tiene hecho. */
function pasoSegunEstado(exp) {
  if (!exp || exp.tipo !== "COMUN") return 1;
  const tramite = exp.datos.tramite || {};
  const gde = exp.datos.gde || {};
  if (exp.estado === "BORRADOR") {
    if (!(exp.datos.remitos || []).length) return 2;
    if (!gde.cv) return 8;
    if (!tramite.ingreso_sap) return 9;
    if (!(exp.datos.factura || {}).numero) return 3;
    return 10;
  }
  if (exp.estado === "CONTROLADO") return tramite.factura_sap ? 13 : (gde.factura ? 12 : 11);
  if (exp.estado === "EN_FIRMA") return 13;
  return 14;
}

function mostrarPaso(paso) {
  if (!expEstado.exp && paso !== 1) paso = 1;
  const pasos = pasosDelAsistente();
  if (esTramite() && PASO_CLASICO_EN_TRAMITE[paso]) paso = PASO_CLASICO_EN_TRAMITE[paso];
  if (!pasos.some(([n]) => n === paso)) paso = 1;
  expEstado.paso = paso;
  for (let n = 1; n <= 14; n++) document.getElementById("asistente-paso-" + n).hidden = n !== paso;
  vaciar(document.getElementById("asistente-pasos"), ...pasos.map(([n, texto]) => el("li", {},
    el("button", { type: "button", texto, disabled: !expEstado.exp && n !== 1,
      "aria-current": n === paso ? "step" : null,
      onclick: () => { limpiarAvisos(); mostrarPaso(n); } }))));
  const pintores = esCentralizada()
    ? { 1: pintarPaso1, 2: pintarPaso2, 3: pintarPasoCvFirmado, 4: pintarPasoNotaCentral }
    : { 1: pintarPaso1, 2: pintarPaso2, 3: pintarPaso3, 4: pintarPaso4, 5: pintarPaso5, 6: pintarPaso6, 7: pintarPaso7,
      8: pintarPasoCertificado, 9: pintarPasoIngresoSap, 10: pintarPasoCaratulacion, 11: pintarPasoGde,
      12: pintarPasoFacturaSap, 13: pintarPasoAutorizacion, 14: pintarPasoCierre };
  if (pintores[paso]) pintores[paso]();
}

/** Paso 3 de una validación centralizada: el N° de IF del certificado de validación firmado. */
function pintarPasoCvFirmado() {
  const contenedor = document.getElementById("asistente-paso-3");
  const central = expEstado.exp.datos.centralizada || {};
  const campo = entradaGde("central-cv", "N° de IF del certificado de validación firmado", central.numero_cv);
  vaciar(contenedor,
    el("h3", { texto: "3. Certificado de validación firmado" }),
    el("p", { clase: "texto-suave", texto: "Bajá el certificado, hacelo firmar en GDE y cargá acá su número de IF." }),
    el("div", { clase: "acciones" }, botonCertificado("secundario")),
    el("form", { clase: "formulario", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (await guardarCentral({ numero_cv: document.getElementById("central-cv").value.trim() }, "N° de IF guardado.")) mostrarPaso(3);
    } },
      campo,
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Guardar N° de IF" }),
        el("button", { type: "button", clase: "secundario", texto: "Seguir al paso 4", onclick: () => mostrarPaso(4) }))));
}

/** Paso 4: la Nota a Central (para copiar), su número y la fecha de envío. Con eso queda «Validado». */
async function pintarPasoNotaCentral() {
  const contenedor = document.getElementById("asistente-paso-4");
  const central = expEstado.exp.datos.centralizada || {};
  cargando(contenedor);
  const nota = await api("GET", "/api/expedientes/" + expEstado.exp.id + "/nota-central");
  const partes = [el("h3", { texto: "4. Nota a Central" })];
  if (nota) {
    partes.push(bloqueTexto("Referencia de la nota", nota.referencia, false), bloqueTexto("Nota a Central", nota.cuerpo, true));
  } else {
    partes.push(el("p", { clase: "texto-suave", texto: "Completá los datos que faltan (ver el mensaje de arriba) para generar la nota." }));
  }
  partes.push(el("form", { clase: "formulario panel", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    const numero = document.getElementById("central-nota").value.trim();
    const fecha = document.getElementById("central-envio").value;
    if (await guardarCentral({ numero_nota: numero, fecha_envio: fecha || null },
      numero && fecha ? "Nota enviada: la validación quedó «Validada»." : "Datos de la nota guardados.")) mostrarPaso(4);
  } },
    el("h4", { texto: "Envío" }),
    entradaGde("central-nota", "N° de la nota (GDE)", central.numero_nota),
    campoFormulario("central-envio", "Fecha de envío", entrada(central.fecha_envio || "", { type: "date" }),
      "Con el número y la fecha de envío, la validación queda «Validada»."),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar y dar por validado" }))));
  vaciar(contenedor, ...partes);
}

/** Guarda los datos de la validación centralizada (IF del CV, nota, fecha de envío) conservando los demás. */
async function guardarCentral(cambios, mensaje) {
  limpiarAvisos();
  const exp = expEstado.exp;
  const central = Object.assign({ numero_cv: "", numero_nota: "", fecha_envio: null }, exp.datos.centralizada || {}, cambios);
  estado.recargar = () => abrirExpediente(exp.id, expEstado.paso);
  const actualizado = await api("PUT", "/api/expedientes/" + exp.id + "/centralizada", {
    version: exp.version, centralizada: { numero_cv: central.numero_cv || "", numero_nota: central.numero_nota || "",
      fecha_envio: central.fecha_envio || null } });
  if (!actualizado) return null;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  mostrarAviso(mensaje, "exito");
  return actualizado;
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
  mostrarPaso(paso || pasoSegunEstado(exp));
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
      campoFormulario("nuevo-sap", "Proveedor SAP (solo pago eventual sin OC)", entrada("", { inputmode: "numeric", autocomplete: "off", clase: "entrada-corta" })),
      campoFormulario("nuevo-efector", "Efector (solo pago eventual sin OC)", selector(estado.efector === "CASPH" ? "CASPH" : "HBI", [["HBI", "HBI"], ["CASPH", "CASPH"]])),
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Crear expediente" })));
    vaciar(contenedor, formulario);
    return;
  }
  const partes = [el("h3", { texto: tituloPaso(1, "1. OC y período") })];
  const oc = expEstado.ficha ? expEstado.ficha.oc : null;
  partes.push(el("p", { texto: "Tipo " + exp.tipo + (oc ? " · OC " + oc.numero + " · " + (oc.objeto || "sin objeto cargado")
    + " · día de inicio del período " + oc.dia_inicio_periodo : "") }));
  if (expEstado.ficha) {
    partes.push(expEstado.ficha.pdf_oc
      ? el("p", { clase: "texto-suave", texto: "✓ PDF de la OC: " + textoCargaPdf(expEstado.ficha.pdf_oc) })
      : seccionPdfOC(expEstado.ficha, async (ficha) => { expEstado.ficha = ficha; pintarEncabezadoAsistente(); await pintarPaso1(); }));
  }
  partes.push(el("p", { texto: exp.periodo
    ? "Período: " + exp.periodo + " (del " + exp.periodo_desde + " al " + exp.periodo_hasta + ")"
      + (exp.periodo_manual ? " — corregido a mano" : " — sugerido por los remitos")
    : "Todavía no hay período: se sugiere con la fecha de los remitos (paso 2), y ahí lo confirmás o lo cambiás." }));
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
      botonSiguiente())));
  vaciar(contenedor, ...partes);
}

async function crearExpediente(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const datos = { tipo: document.getElementById("nuevo-tipo").value, oc: document.getElementById("nuevo-oc").value.trim() };
  if (datos.tipo === "EVENTUAL" && !datos.oc) {
    datos.sap = document.getElementById("nuevo-sap").value.trim();
    datos.efector = document.getElementById("nuevo-efector").value;
  }
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
  const remitos = exp.datos.remitos;
  const nuevos = el("div", { id: "remitos-nuevos" }, tarjetaRemitoNuevo());
  const agregar = el("button", { type: "button", id: "remito-otro", clase: "secundario", texto: "+ Otro remito",
    onclick: () => { nuevos.append(tarjetaRemitoNuevo()); actualizarFilasRemito(); nuevos.lastElementChild.querySelector("input").focus(); } });
  const partes = [
    el("h3", { texto: tituloPaso(2, "2. Remitos") }),
    el("form", { clase: "formulario", id: "remitos-form", novalidate: true, onsubmit: pegarRemitos },
      el("p", { clase: "texto-suave", texto: "Cargá cada remito con sus fechas y, ahí mismo, cuánto se entregó de cada renglón "
        + "de la OC (vacío = nada). Hasta " + MAX_REMITOS + " remitos por expediente." }),
      nuevos,
      el("div", { clase: "acciones" }, agregar, el("button", { type: "submit", texto: "Guardar remitos" }),
        el("span", { id: "remitos-cupo", clase: "texto-suave", "data-cargados": String(remitos.length) })),
      el("p", { clase: "nota-pie", texto: "Si cargás un número que ya está, se actualizan sus fechas (y sus cantidades, si las cargaste)." })),
  ];
  if (!remitos.length) {
    partes.push(el("p", { clase: "texto-suave", texto: "Todavía no hay remitos cargados." }));
  } else {
    partes.push(panelPeriodo(exp), el("h3", { texto: "Remitos cargados (" + remitos.length + ")" }), tablaRemitosCargados(remitos),
      el("div", { clase: "acciones" },
        el("button", { type: "button", clase: "secundario", texto: "Ver y editar remitos", onclick: () => abrirDialogoRemitos(0) }),
        esTramite() ? null : botonCertificado("secundario"),
        botonSiguiente()));
  }
  vaciar(contenedor, ...partes);
  actualizarFilasRemito();
}

/** Texto corto de las cantidades de un remito: «R1: 2000 · R2: 650». */
function resumenCantidades(remito) {
  if (remito.es_equipo_comodato) return "Equipo en comodato";
  const items = (remito.items || []).filter((it) => String(it.cantidad ?? "").trim() !== "");
  return items.length ? items.map((it) => "R" + it.pos + ": " + it.cantidad).join(" · ") : "Sin cantidades";
}

function tablaRemitosCargados(remitos) {
  return el("div", { clase: "tabla-desplazable" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["#", "N° de remito", "Fecha", "Firma", "Cantidades", ""]
      .map((t) => el("th", { scope: "col", texto: t })))),
    el("tbody", {}, ...remitos.map((r, i) => el("tr", { clase: "fila-clic", onclick: () => abrirDialogoRemitos(i) },
      el("td", { clase: "numero", texto: String(i + 1) }),
      el("td", { clase: "mono", texto: r.numero }),
      el("td", {}, r.fecha ? fechaCorta(r.fecha) : el("span", { clase: "pastilla pastilla-aviso", texto: "Falta la fecha" })),
      el("td", { texto: r.fecha_firma ? fechaCorta(r.fecha_firma) : "—" }),
      el("td", { texto: resumenCantidades(r) }),
      el("td", {}, botonLapiz("Ver y editar el remito " + r.numero, (e) => { e.stopPropagation(); abrirDialogoRemitos(i); })))))));
}

/** Tabla de los renglones de la OC con la cantidad de un remito: con entradas (editable) o en texto. */
function tablaCantidadesRemito(items, editable, etiquetaRemito) {
  const renglones = expEstado.ficha ? expEstado.ficha.renglones : [];
  if (!renglones.length) return el("p", { clase: "texto-suave", texto: "La OC no tiene renglones cargados." });
  const porPos = new Map((items || []).map((it) => [Number(it.pos), it]));
  return el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-cantidades" },
    el("thead", {}, el("tr", {}, ...["Pos.", "Renglón de la OC", "Cantidad"]
      .map((t) => el("th", { scope: "col", clase: t === "Renglón de la OC" ? "izq" : null, texto: t })))),
    el("tbody", {}, ...renglones.map((r) => {
      const actual = (porPos.get(Number(r.pos)) || {}).cantidad ?? "";
      return el("tr", {},
        el("td", { clase: "numero", texto: r.pos }),
        el("td", { clase: "izq" }, (r.codigo ? r.codigo + " · " : "") + r.descripcion, r.otro_centro || r.central ? " " : null, marcaOtroCentro(r)),
        el("td", {}, editable
          ? entrada(String(actual), { "data-pos": String(r.pos), inputmode: "decimal", clase: "entrada-corta",
            "aria-label": "Cantidad del renglón " + r.pos + " en " + etiquetaRemito })
          : el("span", { clase: "numero", texto: actual === "" ? "—" : String(actual) })));
    }))));
}

let contadorRemitoNuevo = 0;

/** Tarjeta para cargar un remito nuevo: número, fechas, comodato y, debajo, las cantidades de cada renglón. */
function tarjetaRemitoNuevo() {
  const n = ++contadorRemitoNuevo;
  const id = (campo) => "rn-" + n + "-" + campo;
  const comodato = el("input", { type: "checkbox", id: id("comodato"), "data-campo": "es_equipo_comodato" });
  const cantidades = el("div", { clase: "cantidades-remito" },
    el("p", { clase: "etiqueta-cantidades", texto: "Cantidades entregadas" }), tablaCantidadesRemito([], true, "el remito nuevo"));
  comodato.addEventListener("change", () => { cantidades.hidden = comodato.checked; });
  return el("fieldset", { clase: "panel remito-nuevo" },
    el("legend", { clase: "orden-remito" }),
    el("div", { clase: "grilla-remito" },
      campoFormulario(id("numero"), "N° de remito", entrada("", { "data-campo": "numero", clase: "mono", placeholder: "0001-00003354", autocomplete: "off" })),
      campoFormulario(id("fecha"), "Fecha del remito", entrada("", { "data-campo": "fecha", type: "date" })),
      campoFormulario(id("firma"), "Fecha de firma (si tiene)", entrada("", { "data-campo": "fecha_firma", type: "date" })),
      el("div", { clase: "campo campo-casilla" }, comodato, el("label", { for: id("comodato"), texto: "Equipo en comodato (sin cantidades)" }))),
    cantidades,
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario boton-quitar", texto: "Quitar",
      onclick: (e) => {
        const lista = e.target.closest("#remitos-nuevos");
        e.target.closest("fieldset").remove();
        if (!lista.children.length) lista.append(tarjetaRemitoNuevo());
        actualizarFilasRemito();
      } })));
}

/** Numera las tarjetas y respeta el máximo de remitos por expediente. */
function actualizarFilasRemito() {
  const lista = document.getElementById("remitos-nuevos");
  const cupo = document.getElementById("remitos-cupo");
  if (!lista || !cupo) return;
  const cargados = Number(cupo.dataset.cargados || 0);
  [...lista.children].forEach((tarjeta, i) => {
    tarjeta.querySelector(".orden-remito").textContent = "Remito " + (cargados + i + 1);
    tarjeta.querySelector(".boton-quitar").setAttribute("aria-label", "Quitar el remito " + (cargados + i + 1));
  });
  const boton = document.getElementById("remito-otro");
  if (boton) boton.disabled = cargados + lista.children.length >= MAX_REMITOS;
  cupo.textContent = cargados + " cargados · " + Math.max(0, MAX_REMITOS - cargados) + " disponibles";
}

const RE_CANTIDAD = /^\d+([.,]\d+)?$/;

/** Cantidades de las entradas [data-pos] de un contenedor: [{pos, cantidad}] sin las vacías; null si alguna no es válida. */
function cantidadesDe(contenedor) {
  const items = [];
  for (const control of contenedor.querySelectorAll("[data-pos]")) {
    const texto = control.value.trim();
    if (!texto) continue;
    if (!RE_CANTIDAD.test(texto)) { control.focus(); return null; }
    items.push({ pos: Number(control.dataset.pos), cantidad: texto.replace(",", ".") });
  }
  return items;
}

async function pegarRemitos(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const remitos = [];
  for (const tarjeta of document.querySelectorAll("#remitos-nuevos > fieldset")) {
    const valor = (campo) => tarjeta.querySelector('[data-campo="' + campo + '"]');
    const comodato = valor("es_equipo_comodato").checked;
    const items = comodato ? [] : cantidadesDe(tarjeta);
    const nombre = tarjeta.querySelector(".orden-remito").textContent;
    if (items === null) { mostrarAviso(nombre + ": hay una cantidad que no es un número.", "error"); return; }
    const remito = { numero: valor("numero").value.trim(), fecha: valor("fecha").value, fecha_firma: valor("fecha_firma").value,
      es_equipo_comodato: comodato, items };
    if (!remito.numero && !remito.fecha && !remito.fecha_firma && !items.length) continue;  // tarjeta vacía
    if (!remito.numero) { mostrarAviso("Falta el número del " + nombre.toLowerCase() + ".", "error"); valor("numero").focus(); return; }
    if (!remito.fecha) { mostrarAviso("Falta la fecha del remito " + remito.numero + ".", "error"); valor("fecha").focus(); return; }
    remitos.push(remito);
  }
  if (!remitos.length) { mostrarAviso("Cargá al menos un remito (número y fecha).", "error"); return; }
  const sinCantidades = remitos.filter((r) => !r.es_equipo_comodato && !r.items.length).map((r) => r.numero);
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, 2);
  const datos = await api("POST", "/api/expedientes/" + exp.id + "/remitos/pegar", { version: exp.version, remitos });
  if (!datos) return;
  expEstado.sugerido = datos.periodo_sugerido;
  expEstado.fuera = datos.fuera_de_periodo || [];
  delete datos.periodo_sugerido;
  delete datos.fuera_de_periodo;
  expEstado.exp = datos;
  pintarEncabezadoAsistente();
  pintarPaso2();
  mostrarAviso("Remitos guardados." + (datos.periodo_manual ? "" : (datos.periodo ? " Período sugerido: " + datos.periodo + "." : ""))
    + (sinCantidades.length ? " Sin cantidades: " + sinCantidades.join(", ") + " (las podés cargar con el lápiz)." : ""),
  sinCantidades.length ? "aviso" : "exito");
}

/** Ventana con los remitos cargados, uno por página: se ven en lectura y se editan con el lápiz; «Guardar» los guarda. */
function abrirDialogoRemitos(indice) {
  const anterior = document.getElementById("dialogo-remitos");
  if (anterior) anterior.remove();
  const vista = { pagina: indice || 0, editando: false };
  const cuerpo = el("div", { clase: "dialogo-cuerpo" });
  const subtitulo = el("p", { clase: "texto-suave" });
  const dialogo = el("dialog", { id: "dialogo-remitos", clase: "dialogo", "aria-labelledby": "remitos-titulo" },
    el("div", { clase: "dialogo-encabezado" }, el("h2", { id: "remitos-titulo", texto: "Remitos del expediente " + expEstado.exp.id }), subtitulo),
    cuerpo);
  const remitos = () => expEstado.exp.datos.remitos;

  const guardar = async (nuevos, mensaje) => {
    const exp = expEstado.exp;
    estado.recargar = () => { dialogo.close(); abrirExpediente(exp.id, 2); };
    const actualizado = await api("PUT", "/api/expedientes/" + exp.id, { version: exp.version, cambios: { datos: { remitos: nuevos } } });
    if (!actualizado) { avisoEnDialogo(dialogo, ultimoError()); return false; }
    expEstado.exp = actualizado;
    pintarEncabezadoAsistente();
    pintarPaso2();
    mostrarAviso(mensaje, "exito");
    return true;
  };

  const pintar = () => {
    const lista = remitos();
    if (!lista.length) { dialogo.close(); return; }
    vista.pagina = Math.min(vista.pagina, lista.length - 1);
    const i = vista.pagina;
    const r = lista[i];
    const error = dialogo.querySelector(".dialogo-error");
    if (error) error.remove();
    subtitulo.textContent = "Remito " + (i + 1) + " de " + lista.length + (vista.editando ? " · editando" : "");
    const paginas = el("div", { clase: "paginador" },
      el("button", { type: "button", clase: "secundario", texto: "‹ Anterior", disabled: vista.editando || i === 0,
        onclick: () => { vista.pagina -= 1; pintar(); } }),
      el("span", { clase: "texto-suave", texto: (i + 1) + " / " + lista.length }),
      el("button", { type: "button", clase: "secundario", texto: "Siguiente ›", disabled: vista.editando || i === lista.length - 1,
        onclick: () => { vista.pagina += 1; pintar(); } }));
    let contenido;
    let acciones;
    if (!vista.editando) {
      const dato = (etiqueta, valor) => el("div", { clase: "dato" }, el("dt", { texto: etiqueta }), el("dd", { texto: valor }));
      contenido = el("div", {},
        el("dl", { clase: "datos-oc datos-remito" },
          dato("N° de remito", r.numero),
          dato("Fecha del remito", r.fecha ? fechaCorta(r.fecha) : "Falta"),
          dato("Fecha de firma", r.fecha_firma ? fechaCorta(r.fecha_firma) : "—"),
          dato("Equipo en comodato", r.es_equipo_comodato ? "Sí" : "No"),
          dato("Aclara el período", r.aclara_periodo ? "Sí" : "No")),
        r.es_equipo_comodato ? el("p", { clase: "texto-suave", texto: "El remito del equipo en comodato no lleva cantidades." })
          : tablaCantidadesRemito(r.items, false, "el remito " + r.numero));
      acciones = el("div", { clase: "acciones dialogo-acciones" },
        el("button", { type: "button", clase: "boton-lapiz-texto", onclick: () => { vista.editando = true; pintar(); } },
          iconoLapiz(), " Editar"),
        el("button", { type: "button", clase: "secundario boton-peligro", texto: "Quitar este remito", onclick: async () => {
          if (!window.confirm("¿Quitar el remito " + r.numero + " del expediente?")) return;
          if (await guardar(remitos().filter((_, k) => k !== i), "Remito " + r.numero + " quitado.")) pintar();
        } }),
        el("button", { type: "button", clase: "secundario", texto: "Cerrar", onclick: () => dialogo.close() }));
    } else {
      const comodato = el("input", { type: "checkbox", id: "rm-comodato", checked: Boolean(r.es_equipo_comodato) });
      const aclara = el("input", { type: "checkbox", id: "rm-aclara", checked: Boolean(r.aclara_periodo) });
      const cantidades = el("div", { clase: "cantidades-remito", hidden: Boolean(r.es_equipo_comodato) },
        tablaCantidadesRemito(r.items, true, "el remito " + r.numero));
      comodato.addEventListener("change", () => { cantidades.hidden = comodato.checked; });
      contenido = el("div", {},
        el("div", { clase: "grilla-dialogo" },
          campoFormulario("rm-numero", "N° de remito", entrada(r.numero || "", { clase: "mono", autocomplete: "off" })),
          campoFormulario("rm-fecha", "Fecha del remito", entrada(r.fecha || "", { type: "date" })),
          campoFormulario("rm-firma", "Fecha de firma (si tiene)", entrada(r.fecha_firma || "", { type: "date" })),
          el("div", { clase: "campo campo-casilla" }, comodato, el("label", { for: "rm-comodato", texto: "Equipo en comodato" })),
          el("div", { clase: "campo campo-casilla" }, aclara, el("label", { for: "rm-aclara", texto: "Aclara el período" }))),
        cantidades);
      acciones = el("div", { clase: "acciones dialogo-acciones" },
        el("button", { type: "button", texto: "Guardar", onclick: async () => {
          const numero = document.getElementById("rm-numero").value.trim();
          if (!numero) { avisoEnDialogo(dialogo, "Falta el número del remito."); return; }
          if (remitos().some((x, k) => k !== i && x.numero === numero)) { avisoEnDialogo(dialogo, "El remito " + numero + " ya está cargado."); return; }
          const items = comodato.checked ? [] : cantidadesDe(cantidades);
          if (items === null) { avisoEnDialogo(dialogo, "Hay una cantidad que no es un número."); return; }
          const anteriores = new Map((r.items || []).map((it) => [Number(it.pos), it.codigo || ""]));
          const editado = Object.assign({}, r, {
            numero, fecha: document.getElementById("rm-fecha").value || null, fecha_firma: document.getElementById("rm-firma").value || null,
            es_equipo_comodato: comodato.checked, aclara_periodo: !comodato.checked && aclara.checked,
            items: items.map((it) => Object.assign(it, { codigo: anteriores.get(it.pos) || "" })),
          });
          const nuevos = remitos().map((x, k) => (k === i ? editado : x));
          if (await guardar(nuevos, "Remito " + numero + " guardado.")) { vista.editando = false; pintar(); }
        } }),
        el("button", { type: "button", clase: "secundario", texto: "Cancelar", onclick: () => { vista.editando = false; pintar(); } }));
    }
    vaciar(cuerpo, paginas, contenido, acciones);
  };
  dialogo.addEventListener("close", () => dialogo.remove());
  document.body.append(dialogo);
  pintar();
  dialogo.showModal();
}

const MAX_REMITOS = 20;
const MESES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
  "noviembre", "diciembre"];

function fechaCorta(iso) {
  return iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "";
}

/** Período del expediente: sugerido por la fecha de los remitos (bienes: el mes del remito; servicios: según la OC),
 * para confirmarlo o cambiarlo, y aviso de los remitos que no caen en él (ni por fecha ni por firma). */
function panelPeriodo(exp) {
  const partes = [];
  if (exp.periodo_desactualizado && !panelPeriodo.corrigiendo) {
    // Las fechas quedaron calculadas con una regla anterior: se vuelven a calcular con el mismo período.
    panelPeriodo.corrigiendo = true;
    guardarExpediente({ periodo: exp.periodo }, "Se corrigieron las fechas del período " + exp.periodo + ".")
      .then((ok) => { panelPeriodo.corrigiendo = false; if (ok) pintarPaso2(); });
  }
  if (!exp.periodo) {
    partes.push(el("p", { texto: "Todavía no hay período: se sugiere con la fecha de los remitos." }));
  } else {
    const [anio, mes] = exp.periodo.split("-").map(Number);
    partes.push(el("p", {},
      el("strong", { texto: "Período: " + MESES_NOMBRE[mes - 1] + " " + anio }),
      // Mes calendario (bienes, o servicios que van por mes): no hace falta mostrar las fechas.
      exp.periodo_mes_calendario ? " " : " (" + fechaCorta(exp.periodo_desde) + " al " + fechaCorta(exp.periodo_hasta) + ") ",
      el("span", { clase: "pastilla pastilla-" + (exp.periodo_manual ? "exito" : "aviso"),
        texto: exp.periodo_manual ? "Confirmado" : "Sugerido por los remitos" })));
  }
  const cambiar = entrada(exp.periodo || "", { id: "periodo-rapido", inputmode: "numeric", clase: "entrada-corta",
    placeholder: "AAAA-MM", "aria-label": "Período (AAAA-MM)" });
  partes.push(el("div", { clase: "acciones" },
    exp.periodo && !exp.periodo_manual ? el("button", { type: "button", texto: "Confirmar período", onclick: async () => {
      limpiarAvisos();
      if (await guardarExpediente({ periodo: exp.periodo }, "Período " + exp.periodo + " confirmado.")) pintarPaso2();
    } }) : null,
    cambiar,
    el("button", { type: "button", clase: "secundario", texto: "Cambiar período", onclick: async () => {
      limpiarAvisos();
      const periodo = cambiar.value.trim();
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(periodo)) { mostrarAviso("El período debe tener la forma AAAA-MM (por ejemplo 2026-09).", "error"); return; }
      if (await guardarExpediente({ periodo }, "Período " + periodo + " guardado.")) pintarPaso2();
    } })));
  const fuera = exp.remitos_fuera_de_periodo || [];
  if (fuera.length) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: (fuera.length === 1 ? "El remito " : "Los remitos ")
      + fuera.join(", ") + (fuera.length === 1 ? " no cae" : " no caen") + " en el período, ni por su fecha ni por la de firma. "
      + "Revisá el período o, si el remito lo aclara, marcá «Aclara el período»." })));
  }
  return el("section", { clase: "panel panel-periodo", "aria-label": "Período del expediente" }, ...partes);
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

// Una sola tabla para corroborar: cada dato con lo de la factura (editable), lo del SII y lo que debe ser.
// [clave, rótulo, campo de la factura (input) o función que lo lee, clave del SII, clave de lo esperado, tipo de comparación]
const FILAS_COMPROBANTES = [
  // El SII muestra el punto de venta con 4 dígitos aunque la factura tenga 5: se comparan los números, no los ceros.
  ["numero", "N° de comprobante", "numero", "nro_comprobante", null, "factura"],
  ["letra", "Letra / tipo de comprobante", (f) => letraFactura(f.numero), "tipo_comprobante", null, "letra"],
  ["fecha", "Fecha de emisión", "fecha", "fecha_emision", null, "texto"],
  ["centavos", "Importe total $", "centavos", "monto_centavos", null, "pesos"],
  ["cae", "CAE", "cae", "cae", null, "texto"],
  ["vto_cae", "Vencimiento del CAE", "vto_cae", null, null, "texto"],
  ["periodo", "Período (mes en que termina)", "periodo", "periodo", "periodo", "periodo"],
  ["oc", "Orden de compra", (f) => (f.menciona || {}).oc, "orden_compra", "oc", "sap"],
  ["cuit", "CUIT del proveedor", (f) => (expEstado.facturaPdf || {}).cuit_emisor, "cuit", "cuit", "digitos"],
  ["razon_social", "Razón social", null, "razon_social", "razon_social", "texto"],
  ["sap", "N° SAP del proveedor", null, "sap", "sap", "sap"],
  ["destinatario", "Destinatario", "destinatario", null, "destinatario", "texto"],
  ["domicilio", "Domicilio del destinatario", "domicilio", null, "domicilio", "domicilio"],
  ["area", "Área (SII)", null, "area", "area", "texto"],
  ["tipo_servicio", "Tipo de servicio (SII)", null, "tipo_servicio", "tipo_servicio", "texto"],
  ["concepto", "Concepto (SII)", null, "concepto", "concepto", "texto"],
  ["cod_tramite", "Código de trámite (SII)", null, "cod_tramite", null, "texto"],
];

function letraFactura(numero) {
  const m = /^\s*\d+\s*([A-Z])/i.exec(numero || "");
  return m ? m[1].toUpperCase() : "";
}

function controlFactura(campo, tipo, valor) {
  const atributos = { id: "fac-" + campo, "aria-label": (CAMPOS_FACTURA.find(([c]) => c === campo) || [, campo])[1] };
  if (tipo === "fecha") atributos.type = "date";
  if (tipo === "pesos") atributos.inputmode = "decimal";
  if (campo === "numero" || campo === "cae") atributos.clase = "mono";
  return entrada(tipo === "pesos" ? formatoPesos(valor) : valor, atributos);
}

/** Valor normalizado para comparar (null = no hay dato). */
function normalizarDato(valor, tipo) {
  if (valor === null || valor === undefined || valor === "") return null;
  const texto = String(valor).trim();
  if (!texto) return null;
  if (tipo === "factura") { const m = /^(\d+)\s*[A-Z]?\s*-?\s*(\d+)$/i.exec(texto); return m ? Number(m[1]) + "-" + Number(m[2]) : texto; }
  if (tipo === "letra") { const m = /([ABCM])\s*$/i.exec(texto); return m ? m[1].toUpperCase() : texto.toUpperCase(); }
  if (tipo === "digitos") return texto.replace(/\D/g, "");
  if (tipo === "sap") return texto.replace(/^0+/, "");
  if (tipo === "domicilio") return texto.toUpperCase().replace(/[ÚU]/g, "U").replace(/\s+/g, " ").slice(0, 8);
  // Texto: sin tildes, mayúsculas y sin signos («GRUPO EFIA S.R.L.» = «GRUPO EFIA SRL»).
  return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function textoDato(valor, tipo) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (tipo === "pesos") return "$ " + formatoPesos(valor);
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(valor))) return String(valor).split("-").reverse().join("/");
  return String(valor);
}

async function pintarPaso3() {
  const contenedor = document.getElementById("asistente-paso-3");
  const factura = expEstado.exp.datos.factura || {};
  let destino = { nombre: "INSSJP", domicilio: "PERU 169", localidad: "CABA" };
  const parametros = await api("GET", "/api/parametros");
  if (parametros && parametros.parametros.destinatario_factura) destino = parametros.parametros.destinatario_factura;
  const valores = Object.assign({ destinatario: destino.nombre, domicilio: destino.domicilio + " " + destino.localidad }, factura);
  expEstado.sii = null;
  expEstado.facturaPdf = null;
  expEstado.revision = null;
  const tiposFactura = Object.fromEntries(CAMPOS_FACTURA.map(([c, , t]) => [c, t]));
  const filas = FILAS_COMPROBANTES.map(([clave, rotulo, campoFactura, claveSii, claveEsperado]) => {
    let celdaFactura;
    if (clave === "periodo") {
      celdaFactura = el("td", { clase: "celda-periodo" },
        controlFactura("periodo_desde", "fecha", valores.periodo_desde), el("span", { clase: "texto-suave", texto: " al " }),
        controlFactura("periodo_hasta", "fecha", valores.periodo_hasta));
    } else if (typeof campoFactura === "string") {
      celdaFactura = el("td", {}, controlFactura(campoFactura, tiposFactura[campoFactura], valores[campoFactura]));
    } else {
      celdaFactura = el("td", { id: "cmp-fac-" + clave, clase: campoFactura ? null : "celda-no-aplica", texto: campoFactura ? "—" : "" });
    }
    return el("tr", { "data-clave": clave },
      el("th", { scope: "row", clase: "izq", texto: rotulo }),
      celdaFactura,
      el("td", { id: "cmp-sii-" + clave, clase: claveSii ? null : "celda-no-aplica", texto: claveSii ? "—" : "" }),
      el("td", { id: "cmp-esp-" + clave, clase: claveEsperado ? null : "celda-no-aplica", texto: claveEsperado ? "—" : "" }),
      el("td", { id: "cmp-est-" + clave }));
  });
  const archivoFactura = el("input", { type: "file", accept: "application/pdf,.pdf" });
  const archivoSii = el("input", { type: "file", accept: "application/pdf,.pdf" });
  const tablaDatos = el("table", { clase: "tabla-comprobantes" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col", clase: "izq", texto: "Dato" }), el("th", { scope: "col", texto: "Factura" }),
      el("th", { scope: "col", texto: "Carga en el SII" }), el("th", { scope: "col", texto: "Debe ser (expediente)" }),
      el("th", { scope: "col", texto: "" }))),
    el("tbody", {}, ...filas));
  tablaDatos.addEventListener("input", actualizarComparacion);
  vaciar(contenedor,
    el("h3", { texto: tituloPaso(3, "3. Factura y SII") }),
    el("section", { clase: "panel seccion-pdf-oc", "aria-labelledby": "comprobantes-pdf-titulo" },
      el("h4", { id: "comprobantes-pdf-titulo", texto: "Cargar desde los PDF" }),
      el("p", { clase: "texto-suave", texto: "Subí el PDF de la factura y el de su carga en el SII: se completan los datos y se controlan "
        + "enseguida contra el expediente. Podés subir uno solo; lo que no se encuentre lo completás a mano en la tabla." }),
      el("div", { clase: "grilla-dialogo" },
        campoFormulario("fac-pdf", "PDF de la factura", archivoFactura, "El PDF digital del proveedor (no un escaneo)."),
        campoFormulario("sii-pdf", "PDF de la carga en el SII", archivoSii, "La constancia «Factura de Proveedor» del SII.")),
      el("div", { clase: "acciones" },
        el("button", { type: "button", texto: "Leer y controlar", onclick: () => leerComprobantesPdf(archivoFactura, archivoSii) }),
        el("details", { clase: "pegar-sii" },
          el("summary", { texto: "¿El PDF del SII no se puede leer? Pegá su texto" }),
          el("div", { clase: "campo campo-ancho" },
            el("label", { for: "sii-texto", texto: "Texto de la factura cargada en el SII" }),
            el("textarea", { id: "sii-texto", rows: "6", spellcheck: "false" })),
          el("div", { clase: "acciones" },
            el("button", { type: "button", clase: "secundario", texto: "Analizar texto del SII", onclick: analizarSii }))))),
    el("form", { clase: "formulario", novalidate: true, onsubmit: guardarFactura },
      el("div", { clase: "encabezado-comprobantes" },
        el("h4", { texto: "Corroborar los datos" }),
        el("div", { id: "comprobantes-resumen", "aria-live": "polite" })),
      el("div", { id: "comprobantes-notas" }),
      el("div", { clase: "tabla-desplazable" }, tablaDatos),
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Guardar factura y SII" }),
        el("button", { type: "button", clase: "secundario", texto: "Volver a controlar", onclick: () => revisarComprobantes() }),
        botonSiguiente())));
  actualizarComparacion();
  const siiGuardado = expEstado.exp.datos.sii || {};
  if (factura.numero || Object.entries(siiGuardado).some(([k, v]) => k !== "faltantes" && v)) revisarComprobantes(true);
  else vaciar(document.getElementById("comprobantes-resumen"),
    el("span", { clase: "texto-suave", texto: "Subí los PDF o completá la factura para controlarla." }));
}

/** Completa las columnas SII / Debe ser y marca en cada fila si coincide. */
function actualizarComparacion() {
  const factura = facturaDelFormulario();
  const sii = expEstado.sii || expEstado.exp.datos.sii || {};
  const esperado = (expEstado.revision && expEstado.revision.esperado) || {};
  for (const [clave, , campoFactura, claveSii, claveEsperado, tipo] of FILAS_COMPROBANTES) {
    let valorFactura = null;
    // Período: el mes en que termina (así se carga en el SII cuando es un período específico).
    if (clave === "periodo") valorFactura = (factura.periodo_hasta || factura.periodo_desde || "").slice(0, 7) || null;
    else if (typeof campoFactura === "string") valorFactura = factura[campoFactura];
    else if (campoFactura) {
      valorFactura = campoFactura(factura);
      document.getElementById("cmp-fac-" + clave).textContent = textoDato(valorFactura, tipo);
    }
    const valorSii = claveSii ? sii[claveSii] : null;
    const valorEsperado = claveEsperado ? esperado[claveEsperado] : null;
    if (claveSii) document.getElementById("cmp-sii-" + clave).textContent = textoDato(valorSii, tipo === "pesos" ? "pesos" : "texto");
    if (claveEsperado) document.getElementById("cmp-esp-" + clave).textContent = textoDato(valorEsperado, "texto");
    const valores = [valorFactura, valorSii, valorEsperado].map((v) => normalizarDato(v, tipo === "pesos" ? "texto" : tipo)).filter((v) => v !== null);
    const estado = document.getElementById("cmp-est-" + clave);
    const fila = estado.closest("tr");
    fila.classList.remove("fila-distinta");
    if (valores.length < 2) {
      vaciar(estado, valores.length ? null : el("span", { clase: "pastilla pastilla-neutra", texto: "Sin dato" }));
    } else if (valores.every((v) => v === valores[0])) {
      vaciar(estado, el("span", { clase: "pastilla pastilla-exito", texto: "Coincide" }));
    } else {
      fila.classList.add("fila-distinta");
      vaciar(estado, el("span", { clase: "pastilla pastilla-error", texto: "No coincide" }));
    }
  }
}

/** Factura del formulario del paso 3 (centavos en int; NaN si el importe está mal escrito). */
function facturaDelFormulario() {
  const factura = Object.assign({}, expEstado.exp.datos.factura || {});
  for (const [campo, , tipo] of CAMPOS_FACTURA) {
    const control = document.getElementById("fac-" + campo);
    if (!control) continue;
    const valor = control.value.trim();
    factura[campo] = tipo === "pesos" ? pesosACentavos(valor) : (valor || null);
  }
  if (expEstado.facturaPdf && expEstado.facturaPdf.menciona) factura.menciona = expEstado.facturaPdf.menciona;
  return factura;
}

/** Lee los PDF elegidos (factura y/o SII), completa la tabla y controla enseguida. */
async function leerComprobantesPdf(archivoFactura, archivoSii) {
  limpiarAvisos();
  if (!archivoFactura.files[0] && !archivoSii.files[0]) { mostrarAviso("Elegí el PDF de la factura, el del SII o los dos.", "error"); return; }
  const notas = [];
  if (archivoFactura.files[0]) {
    const datos = new FormData();
    datos.append("archivo", archivoFactura.files[0], archivoFactura.files[0].name);
    const respuesta = await api("POST", "/api/comprobantes/factura-pdf", datos);
    if (!respuesta) return;
    const leido = respuesta.leido;
    expEstado.facturaPdf = leido;
    for (const [campo, , tipo] of CAMPOS_FACTURA) {
      const valor = leido[campo];
      if (valor === null || valor === undefined || valor === "") continue;
      document.getElementById("fac-" + campo).value = tipo === "pesos" ? formatoPesos(valor) : valor;
    }
    if (leido.faltantes.length) notas.push("No se encontró en la factura: " + leido.faltantes.join(", ") + ". Completalo a mano.");
    notas.push(...leido.avisos);
  }
  if (archivoSii.files[0]) {
    const datos = new FormData();
    datos.append("archivo", archivoSii.files[0], archivoSii.files[0].name);
    const respuesta = await api("POST", "/api/comprobantes/sii-pdf", datos);
    if (!respuesta) return;
    usarSii(respuesta.sii, notas);
  }
  await revisarComprobantes(false, notas);
}

/** Toma los datos del SII (del PDF o del texto pegado) y completa lo que falte de la factura. */
function usarSii(sii, notas) {
  expEstado.sii = sii;
  const completar = (campo, valor) => {
    const control = document.getElementById("fac-" + campo);
    if (control && !control.value && valor !== null && valor !== undefined) control.value = valor;
  };
  completar("cae", sii.cae);
  completar("fecha", sii.fecha_emision);
  completar("centavos", sii.monto_centavos === null ? null : formatoPesos(sii.monto_centavos));
  if (sii.faltantes && sii.faltantes.length) notas.push("No se encontró en el SII: " + sii.faltantes.join(", ") + ".");
}

/** Controla factura y SII contra el expediente (sin guardar) y deja el resumen: «3 errores · 1 para verificar». */
async function revisarComprobantes(silencioso, notas) {
  const factura = facturaDelFormulario();
  if (Number.isNaN(factura.centavos)) { mostrarAviso("El importe de la factura no es un importe válido.", "error"); return; }
  const sii = expEstado.sii || expEstado.exp.datos.sii || null;
  const revision = await api("POST", "/api/expedientes/" + expEstado.exp.id + "/comprobantes/revisar", {
    factura, sii, cuit_emisor: expEstado.facturaPdf ? expEstado.facturaPdf.cuit_emisor : null });
  if (!revision) return;
  expEstado.revision = revision;
  actualizarComparacion();
  vaciar(document.getElementById("comprobantes-notas"),
    ...(notas || []).map((nota) => el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: nota }))));
  const cuenta = (nivel) => revision.resultados.filter((r) => r.nivel === nivel).length;
  const resumen = document.getElementById("comprobantes-resumen");
  if (!revision.resultados.length) {
    vaciar(resumen, el("span", { clase: "pastilla pastilla-exito", texto: "Todo coincide con el expediente" }));
  } else {
    const partes = [];
    const enlace = (cantidad, singular, plural, tono) => el("button", { type: "button", clase: "enlace-resumen tono-" + tono,
      texto: cantidad + " " + (cantidad === 1 ? singular : plural), onclick: () => abrirDialogoRevision(revision) });
    if (cuenta("error")) partes.push(enlace(cuenta("error"), "error", "errores", "error"));
    if (cuenta("salvable")) partes.push(enlace(cuenta("salvable"), "salvable", "salvables", "violeta"));
    if (cuenta("aviso")) partes.push(enlace(cuenta("aviso"), "aviso", "avisos", "aviso"));
    if (cuenta("verificar")) partes.push(enlace(cuenta("verificar"), "para verificar", "para verificar", "info"));
    vaciar(resumen, ...partes.flatMap((p, i) => (i ? [el("span", { clase: "texto-suave", texto: " · " }), p] : [p])));
  }
  if (!silencioso) document.getElementById("comprobantes-resumen").scrollIntoView({ block: "nearest" });
}

/** Ventana con el detalle de lo que no coincide (errores primero). */
function abrirDialogoRevision(revision) {
  const anterior = document.getElementById("dialogo-revision");
  if (anterior) anterior.remove();
  const orden = { error: 0, salvable: 1, aviso: 2, verificar: 3 };
  const items = [...revision.resultados].sort((a, b) => (orden[a.nivel] ?? 9) - (orden[b.nivel] ?? 9)).map((r) =>
    el("div", { clase: "resultado nivel-" + r.nivel },
      el("p", {}, el("span", { clase: "nivel", texto: NIVELES_TEXTO[r.nivel] || r.nivel }),
        (r.ambito === "sii" ? "SII: " : "Factura: ") + r.mensaje)));
  const dialogo = el("dialog", { id: "dialogo-revision", clase: "dialogo dialogo-mediano", "aria-labelledby": "revision-titulo" },
    el("div", { clase: "dialogo-encabezado" },
      el("h2", { id: "revision-titulo", texto: "Control de la factura y el SII" }),
      el("p", { clase: "texto-suave", texto: revision.errores
        ? revision.errores + (revision.errores === 1 ? " error" : " errores") + " para corregir antes de seguir."
        : "Sin errores; revisá lo siguiente." })),
    ...items,
    el("div", { clase: "acciones dialogo-acciones" },
      el("button", { type: "button", texto: "Cerrar", onclick: () => dialogo.close() })));
  dialogo.addEventListener("close", () => dialogo.remove());
  document.body.append(dialogo);
  dialogo.showModal();
}

async function analizarSii() {
  limpiarAvisos();
  const texto = document.getElementById("sii-texto").value;
  if (!texto.trim()) { mostrarAviso("Pegá el texto de la factura cargada en el SII.", "error"); return; }
  const sii = await api("POST", "/api/comprobantes/analizar", { texto });
  if (!sii) return;
  const notas = [];
  usarSii(sii, notas);
  await revisarComprobantes(false, notas);
}

async function guardarFactura(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const factura = facturaDelFormulario();
  if (Number.isNaN(factura.centavos)) { mostrarAviso("El importe de la factura no es un importe válido.", "error"); return; }
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

function pintarControles(informe, contenedor, titulo) {
  contenedor = contenedor || document.getElementById("asistente-paso-4");
  const r = informe.resumen;
  const partes = [
    titulo === null ? null : el("h3", { texto: titulo || "4. Controles" }),
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
    el("button", { type: "button", clase: "secundario", texto: "Volver a controlar",
      onclick: () => (esTramite() ? mostrarPaso(expEstado.paso) : pintarPaso4()) })));
  vaciar(contenedor, ...partes);
}

async function guardarNota(resultado, texto) {
  limpiarAvisos();
  if (!texto.trim()) { mostrarAviso("Escribí el texto de la nota aclaratoria.", "error"); return; }
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, expEstado.paso);
  const datos = await api("POST", "/api/expedientes/" + exp.id + "/notas", {
    version: exp.version, codigo: resultado.codigo, referencia: resultado.referencia, texto,
  });
  if (!datos) return;
  expEstado.exp = datos.expediente;
  pintarEncabezadoAsistente();
  if (esTramite()) mostrarPaso(expEstado.paso); else pintarControles(datos);
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

/** Botón del certificado de validación: primero verifica (y avisa qué falta), después descarga el .docx. */
function botonCertificado(clase) {
  return el("button", { type: "button", clase: clase || null, texto: "Descargar certificado de validación (.docx)",
    onclick: async () => {
      limpiarAvisos();
      const base = "/api/expedientes/" + expEstado.exp.id;
      const listo = await api("GET", base + "/cv/verificar");
      if (!listo) return;
      const enlace = el("a", { href: base + "/cv.docx", download: "" });
      document.body.append(enlace);
      enlace.click();
      enlace.remove();
    } });
}

// Paso 5: textos generados.

async function pintarPaso5() {
  const contenedor = document.getElementById("asistente-paso-5");
  cargando(contenedor);
  const textos = await api("GET", "/api/expedientes/" + expEstado.exp.id + "/textos");
  const correctivo = expEstado.exp.tipo === "CORRECTIVO" ? seccionCorrectivo(textos)
    : expEstado.exp.tipo === "EVENTUAL" ? seccionEventual(textos) : null;
  if (!textos) {
    vaciar(contenedor, el("h3", { texto: "5. Textos" }), correctivo,
      el("div", { clase: "acciones" }, botonCertificado()),
      el("p", { clase: "texto-suave", texto: "Completá los datos que faltan (ver el mensaje de arriba) para generar los textos. "
        + "El certificado de validación no necesita la factura: sale con el período y las cantidades de los remitos." }));
    return;
  }
  const base = "/api/expedientes/" + expEstado.exp.id;
  const partes = [
    el("h3", { texto: "5. Documentos y textos" }),
    el("div", { clase: "acciones" },
      botonCertificado(),
      textos.autorizacion
        ? el("a", { clase: "boton secundario", href: base + "/autorizacion.docx", download: "", texto: "Descargar autorización (.docx)" })
        : null),
    correctivo,
    bloqueTexto("Carátula", textos.caratula, false),
  ];
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
  if (textos.sap) {
    const { ingreso, contabilizada, entrada } = textos.sap;
    partes.push(el("h4", { texto: "Textos para SAP" }));
    if (ingreso.aviso_largo) partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: ingreso.aviso_largo })));
    const fila = (etiqueta, valor) => el("tr", {},
      el("th", { scope: "row", texto: etiqueta }),
      el("td", { clase: "mono", texto: valor }),
      el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Copiar",
        "aria-label": "Copiar " + etiqueta, onclick: () => copiarTexto(valor) })));
    partes.push(el("div", { clase: "tabla-desplazable" }, el("table", {}, el("tbody", {},
      fila("Ingreso: fecha de documento", ingreso.fecha_documento),
      fila("Ingreso: importe", ingreso.importe),
      fila("Ingreso: Texto (" + ingreso.largo_texto + " caracteres)", ingreso.texto),
      fila("Ingreso: asignación", ingreso.asignacion),
      fila("Ingreso: TXT cabecera", ingreso.txt_cabecera),
      fila("Ingreso: clase", ingreso.clase),
      fila("Contabilizada: TXT cabecera", contabilizada.txt_cabecera),
      fila(entrada.transaccion + ": fecha de documento", entrada.fecha_documento),
      fila(entrada.transaccion + ": fecha de contabilización", entrada.fecha_contabilizacion),
      fila(entrada.transaccion + ": período", entrada.periodo),
      fila(entrada.transaccion + ": texto breve", entrada.texto_breve),
      ...entrada.renglones.map((r) => fila(entrada.transaccion + ": cantidad renglón " + r.pos, r.cantidad))))));
  } else if (textos.sap_error) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: "Textos SAP: " + textos.sap_error })));
  }
  partes.push(el("h4", { texto: "Referencias GDE y nombres de archivo" }));
  if (textos.referencias_error) partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: textos.referencias_error })));
  partes.push(el("div", { clase: "tabla-desplazable" }, el("table", {},
    el("thead", {}, el("tr", {}, ...["Referencia", "Archivo", ""].map((t) => el("th", { scope: "col", texto: t })))),
    el("tbody", {}, ...textos.referencias.map((r) => el("tr", {},
      el("td", { texto: r.referencia }),
      el("td", { clase: "mono", texto: r.archivo }),
      el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Copiar",
        "aria-label": "Copiar la referencia " + r.referencia, onclick: () => copiarTexto(r.referencia) }))))))));
  vaciar(contenedor, ...partes);
}

// Paso 6: números GDE.

const RE_GDE = /^(EX|IF|PV|RM|DOCFI|NO|ME|PROSA|IFGRA|ITFCO)-\d{4}-\d{6,9}-( -)?INSSJP-[A-Z0-9]+#INSSJP$/;
const CAMPOS_GDE = [
  ["expediente", "Expediente (EX)"], ["caratula", "Carátula"], ["factura", "Factura"], ["sii", "Carga en SII"],
  ["oc_pdf", "PDF de la OC (vacío = el de la OC)"], ["remito_equipo", "Remito del equipo en comodato"], ["cv", "Certificado de validación"],
  ["vale_hoja", "Vale / hoja de entrada"], ["autorizacion", "Autorización de pago"], ["constancia", "Constancia de comodato"],
  ["contabilizacion", "Constancia de contabilización"],
];

/** Igual que util.normalizar_gde: mayúsculas, % → #, "-   -" → "- -" y sin el resto de los espacios. */
function normalizarGde(texto) {
  return String(texto || "").toUpperCase().replace(/%/g, "#").replace(/-\s+-/g, "-\u0000-").replace(/\s+/g, "").replace(/\u0000/g, " ");
}

function entradaGde(id, etiqueta, valor) {
  const control = entrada(valor || "", { id, clase: "mono", autocomplete: "off", spellcheck: "false" });
  const ayuda = el("p", { id: id + "-estado", clase: "texto-suave", "aria-live": "polite" });
  control.setAttribute("aria-describedby", id + "-estado");
  const revisar = () => {
    const normalizado = normalizarGde(control.value);
    if (!control.value.trim()) { ayuda.textContent = ""; control.removeAttribute("aria-invalid"); return; }
    if (RE_GDE.test(normalizado)) {
      ayuda.textContent = "✓ Válido: " + normalizado;
      control.removeAttribute("aria-invalid");
    } else {
      ayuda.textContent = "✗ Formato no válido (por ejemplo IF-2026-90061259-INSSJP-GESP#INSSJP).";
      control.setAttribute("aria-invalid", "true");
    }
  };
  control.addEventListener("input", revisar);
  revisar();
  return el("div", { clase: "campo campo-ancho" }, el("label", { for: id, texto: etiqueta }), control, ayuda);
}

function pintarPaso6() {
  const contenedor = document.getElementById("asistente-paso-6");
  const exp = expEstado.exp;
  const gde = exp.datos.gde || {};
  const remitos = exp.datos.remitos.filter((r) => !r.es_equipo_comodato);
  const campos = CAMPOS_GDE.map(([clave, etiqueta]) => entradaGde("gde-" + clave, etiqueta, gde[clave]));
  const orden = campoFormulario("gde-orden", "Orden del remito del equipo en el expediente",
    entrada(gde.orden_remito_equipo ?? "", { type: "number", min: "1", inputmode: "numeric", clase: "entrada-corta" }));
  const remitosGde = remitos.map((r, i) => entradaGde("gde-remito-" + i, "Remito " + r.numero, (gde.remitos || {})[r.numero]));
  vaciar(contenedor,
    el("h3", { texto: "6. Números de GDE" }),
    el("form", { clase: "formulario", novalidate: true, onsubmit: guardarGde },
      ...campos.slice(0, 5),
      remitosGde.length ? el("h4", { texto: "Remitos" }) : null,
      ...remitosGde,
      ...campos.slice(5),
      orden,
      el("div", { clase: "acciones" },
        el("button", { type: "submit", texto: "Guardar números GDE" }),
        botonSiguiente())));
}

async function guardarGde(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const exp = expEstado.exp;
  const gde = {};
  for (const [clave] of CAMPOS_GDE) gde[clave] = document.getElementById("gde-" + clave).value.trim();
  gde.remitos = {};
  exp.datos.remitos.filter((r) => !r.es_equipo_comodato).forEach((r, i) => {
    const valor = document.getElementById("gde-remito-" + i).value.trim();
    if (valor) gde.remitos[r.numero] = valor;
  });
  gde.orden_remito_equipo = document.getElementById("gde-orden").value.trim() || null;
  estado.recargar = () => abrirExpediente(exp.id, 6);
  const actualizado = await api("PUT", "/api/expedientes/" + exp.id + "/gde", { version: exp.version, gde });
  if (!actualizado) return;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  pintarPaso6();
  mostrarAviso("Números GDE guardados.", "exito");
}

// Paso 5, solo CORRECTIVO: presupuestos, informe económico (con Copiar) e informe mensual.

function filaPresupuesto(p, indice) {
  return el("div", { clase: "fila-presupuesto filtros" },
    campoFormulario("pres-prov-" + indice, "Proveedor del presupuesto " + (indice + 1), entrada(p.proveedor || "", { autocomplete: "off" })),
    campoFormulario("pres-monto-" + indice, "Importe $", entrada(p.centavos != null ? formatoPesos(p.centavos) : "",
      { inputmode: "decimal", clase: "entrada-corta" })));
}

function seccionCorrectivo(textos) {
  const exp = expEstado.exp;
  const c = exp.datos.correctivo || {};
  const presupuestos = (c.presupuestos && c.presupuestos.length ? c.presupuestos : [{}, {}]).slice();
  const lista = el("div", { id: "correctivo-presupuestos" }, ...presupuestos.map(filaPresupuesto));
  const formulario = el("form", { clase: "formulario panel", novalidate: true, onsubmit: guardarCorrectivo },
    el("h4", { texto: "Mantenimiento correctivo" }),
    campoFormulario("corr-procedimiento", "Procedimiento", entrada(c.procedimiento || "", { autocomplete: "off", placeholder: "CAM 12/2026" })),
    campoFormulario("corr-objeto", "Objeto del correctivo", entrada(c.objeto_correctivo || "", { autocomplete: "off" })),
    lista,
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "Agregar presupuesto", onclick: () => {
      lista.append(filaPresupuesto({}, lista.childElementCount));
    } })),
    campoFormulario("corr-informes", "Informes (números GDE, uno por línea)",
      Object.assign(el("textarea", { rows: "3" }), { value: (c.informes || []).join("\n") })),
    campoFormulario("corr-monto", "Monto a convalidar $", entrada(c.monto_convalidado != null ? formatoPesos(c.monto_convalidado) : "",
      { inputmode: "decimal", clase: "entrada-corta" })),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar correctivo" })));
  const partes = [formulario];
  if (textos && textos.correctivo && textos.correctivo.porcentaje_convalidado !== null) {
    partes.push(el("p", { texto: "Convalidado: " + textos.correctivo.porcentaje_convalidado + " % del renglón de correctivo ($ "
      + formatoPesos(textos.correctivo.importe_renglon) + ")." }));
  }
  if (textos && textos.referencia_correctivo) partes.push(bloqueTexto("Referencia del correctivo", textos.referencia_correctivo, false));
  if (textos && textos.informe_economico) partes.push(bloqueTexto("Informe económico", textos.informe_economico, true));
  for (const clave of ["referencia_correctivo_error", "informe_economico_error"]) {
    if (textos && textos[clave]) partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: textos[clave] })));
  }
  const mes = entrada(exp.periodo || "", { inputmode: "numeric", clase: "entrada-corta", placeholder: "AAAA-MM" });
  const resultado = el("div", { id: "correctivo-mensual" });
  partes.push(el("form", { clase: "formulario panel", novalidate: true, onsubmit: (e) => { e.preventDefault(); informeMensualCorrectivos(mes.value.trim(), resultado); } },
    el("h4", { texto: "Informe mensual de correctivos" }),
    campoFormulario("corr-mes", "Mes (AAAA-MM)", mes),
    el("div", { clase: "acciones" }, el("button", { type: "submit", clase: "secundario", texto: "Ver informe del mes" })),
    resultado));
  return el("div", { clase: "seccion-correctivo" }, ...partes);
}

async function guardarCorrectivo(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const exp = expEstado.exp;
  const presupuestos = [];
  const filas = document.querySelectorAll("#correctivo-presupuestos .fila-presupuesto");
  for (let i = 0; i < filas.length; i++) {
    const proveedor = document.getElementById("pres-prov-" + i).value.trim();
    const texto = document.getElementById("pres-monto-" + i).value;
    const centavos = pesosACentavos(texto);
    if (!proveedor && centavos === null) continue;
    if (centavos === null || Number.isNaN(centavos)) { mostrarAviso("El importe del presupuesto " + (i + 1) + " no es válido.", "error"); return; }
    presupuestos.push({ proveedor, centavos });
  }
  const monto = pesosACentavos(document.getElementById("corr-monto").value);
  if (Number.isNaN(monto)) { mostrarAviso("El monto a convalidar no es válido.", "error"); return; }
  const correctivo = {
    procedimiento: document.getElementById("corr-procedimiento").value.trim(),
    objeto_correctivo: document.getElementById("corr-objeto").value.trim(),
    presupuestos,
    informes: document.getElementById("corr-informes").value.split(/\n/).map((l) => l.trim()).filter(Boolean),
    monto_convalidado: monto,
  };
  estado.recargar = () => abrirExpediente(exp.id, 5);
  const actualizado = await api("PUT", "/api/expedientes/" + exp.id + "/correctivo", { version: exp.version, correctivo });
  if (!actualizado) return;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  await pintarPaso5();
  mostrarAviso("Correctivo guardado.", "exito");
}

async function informeMensualCorrectivos(mes, destino) {
  limpiarAvisos();
  const filas = await api("GET", "/api/correctivos/informe-mensual?mes=" + encodeURIComponent(mes));
  if (!filas) { vaciar(destino); return; }
  if (!filas.length) { vaciar(destino, el("p", { clase: "texto-suave", texto: "No hay correctivos con período " + mes + "." })); return; }
  const lineas = filas.map((f) => [f.expediente || "N° " + f.id, f.oc, f.procedimiento, f.adjudicatario, f.detalle,
    f.monto != null ? "$ " + formatoPesos(f.monto) : ""]);
  const encabezados = ["Expediente", "OC", "Procedimiento", "Adjudicatario", "Detalle", "Monto"];
  const comoTexto = [encabezados.join("\t"), ...lineas.map((l) => l.join("\t"))].join("\n");
  vaciar(destino, tabla(encabezados, lineas),
    el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "Copiar tabla",
      onclick: () => copiarTexto(comoTexto) })));
}

// Paso 5, solo EVENTUAL: campos de la solicitud de pago eventual y sus 8 párrafos (Copiar por párrafo).

const CAMPOS_EVENTUAL = [
  ["tipo_factura", "Tipo de factura (B o C)"],
  ["establecimiento", "Establecimiento / hospital (para la referencia)"],
  ["establecimiento_detallado", "Nombre del establecimiento detallado"],
  ["tipo_servicio", "Tipo de servicio (ej.: mantenimiento preventivo de los ascensores)"],
  ["docfi", "N° de documento financiero (DOCFI)"],
  ["orden_docfi", "Orden del DOCFI"],
  ["remito", "N° de remito (vacío = el primero cargado)"],
  ["documento_remito", "N° GDE del remito"],
  ["orden_remito", "Orden del remito"],
  ["providencia_informe", "N° de providencia del informe técnico"],
  ["orden_informe", "Orden del informe técnico"],
  ["cargo_responsable", "Cargo del responsable técnico"],
  ["responsable", "Nombre y apellido del responsable"],
  ["cuit", "CUIT del proveedor (vacío = el del padrón)"],
  ["orden_compra", "N° de OC (vacío = la del expediente)"],
  ["vencimiento_oc", "Vencimiento de la OC (AAAA-MM-DD; vacío = fin de vigencia)"],
  ["expediente_anterior", "Expediente anterior (de la OC)"],
  ["providencia_prorroga", "N° de providencia de prórroga"],
  ["orden_prorroga", "Orden de la prórroga"],
  ["gerencia", "Gerencia competente"],
  ["nota_autorizacion", "N° de nota de autorización"],
  ["orden_autorizacion", "Orden de la nota de autorización"],
];

function seccionEventual(textos) {
  const exp = expEstado.exp;
  const guardado = exp.datos.eventual || {};
  const formulario = el("form", { clase: "formulario panel", novalidate: true, onsubmit: guardarEventual },
    el("h4", { texto: "Solicitud de pago eventual" }),
    el("p", { clase: "texto-suave", texto: "La factura, el importe, el período y el expediente GDE salen de los pasos 1, 3 y 6." }),
    el("div", { clase: "filtros" }, ...CAMPOS_EVENTUAL.map(([clave, etiqueta]) =>
      campoFormulario("ev-" + clave, etiqueta, entrada(guardado[clave] || "", { autocomplete: "off" })))),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar solicitud" })));
  const partes = [formulario];
  const solicitud = textos && textos.solicitud_pago_eventual;
  if (solicitud) {
    partes.push(bloqueTexto("Referencia de la solicitud", solicitud.referencia, false));
    solicitud.parrafos.forEach((parrafo, i) => partes.push(bloqueTexto("Párrafo " + (i + 1), parrafo, false)));
    partes.push(el("div", { clase: "acciones" }, el("button", { type: "button", clase: "secundario", texto: "Copiar los 8 párrafos",
      onclick: () => copiarTexto(solicitud.parrafos.join("\n\n")) })));
  } else if (textos && textos.solicitud_pago_eventual_error) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto: textos.solicitud_pago_eventual_error })));
  }
  return el("div", { clase: "seccion-eventual" }, ...partes);
}

async function guardarEventual(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const exp = expEstado.exp;
  const eventual = {};
  for (const [clave] of CAMPOS_EVENTUAL) eventual[clave] = document.getElementById("ev-" + clave).value.trim();
  if (eventual.vencimiento_oc && !/^\d{4}-\d{2}-\d{2}$/.test(eventual.vencimiento_oc)) {
    mostrarAviso("El vencimiento de la OC debe tener la forma AAAA-MM-DD.", "error");
    return;
  }
  estado.recargar = () => abrirExpediente(exp.id, 5);
  const actualizado = await api("PUT", "/api/expedientes/" + exp.id + "/eventual", { version: exp.version, eventual });
  if (!actualizado) return;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  await pintarPaso5();
  mostrarAviso("Solicitud de pago eventual guardada.", "exito");
}

// --- Trámite del expediente común (orden real) ----------------------------------------------

/** Textos del trámite (no fallan si falta algo: cada parte trae su motivo en <clave>_error). */
function textosTramite() {
  return api("GET", "/api/expedientes/" + expEstado.exp.id + "/tramite");
}

/** Guarda un paso del trámite (con la versión) y vuelve a pintar el paso actual. */
async function tramitar(accion, valores, mensaje) {
  limpiarAvisos();
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, expEstado.paso);
  const actualizado = await api("POST", "/api/expedientes/" + exp.id + "/tramite",
    Object.assign({ version: exp.version, accion }, valores || {}));
  if (!actualizado) return null;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  mostrarPaso(expEstado.paso);
  mostrarAviso(mensaje, "exito");
  return actualizado;
}

function filaCopiar(etiqueta, valor) {
  return el("tr", {},
    el("th", { scope: "row", texto: etiqueta }),
    el("td", { clase: "mono", texto: valor }),
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: "Copiar",
      "aria-label": "Copiar " + etiqueta, onclick: () => copiarTexto(valor) })));
}

function tablaCopiar(filas) {
  return el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tabla-copiar" }, el("tbody", {}, ...filas)));
}

function avisoFalta(texto) {
  return el("div", { clase: "mensaje mensaje-aviso" }, el("p", { texto }));
}


/** Pastilla de un documento que se firma en GDE: sin enviar, en firma (con fecha) o firmado (con su número). */
function estadoFirma(numero, enFirma) {
  if (numero) return el("p", {}, el("span", { clase: "pastilla pastilla-exito", texto: "Firmado" }), " " + numero);
  if (enFirma) return el("p", {}, el("span", { clase: "pastilla pastilla-violeta", texto: "En proceso de firma" }),
    " desde el " + fechaCorta(enFirma));
  return el("p", {}, el("span", { clase: "pastilla pastilla-neutra", texto: "Sin enviar a firma" }));
}

/** Marca «hecho» de un paso (ingreso en SAP, factura en SAP): botón para marcarlo o, si ya está, la fecha y deshacer. */
function marcaHecho(accion, fecha, textoHacer, textoHecho) {
  if (fecha) {
    return el("div", { clase: "acciones" },
      el("span", { clase: "pastilla pastilla-exito", texto: textoHecho + " el " + fechaCorta(fecha) }),
      el("button", { type: "button", clase: "secundario", texto: "Desmarcar",
        onclick: () => tramitar(accion, { hecho: false }, "Marca quitada.") }), botonSiguiente());
  }
  return el("div", { clase: "acciones" }, el("button", { type: "button", texto: textoHacer,
    onclick: () => tramitar(accion, { hecho: true }, textoHecho + ".") }), botonSiguiente());
}

// 3. Certificado de validación: descarga, referencia, «en firma» y N° GDE del firmado (tarda ~1 día en firmarse).
async function pintarPasoCertificado() {
  const contenedor = document.getElementById("asistente-paso-8");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const exp = expEstado.exp;
  const tramite = exp.datos.tramite || {};
  const gde = exp.datos.gde || {};
  vaciar(contenedor,
    el("h3", { texto: tituloPaso(8) }),
    el("p", { clase: "texto-suave", texto: "Sale con el período y las cantidades de los remitos: no necesita la factura." }),
    el("div", { clase: "acciones" }, botonCertificado()),
    textos.referencia_cv ? bloqueTexto("Referencia GDE del certificado", textos.referencia_cv, false)
      : avisoFalta("Referencia: " + textos.referencia_cv_error),
    el("h4", { texto: "Firma" }),
    estadoFirma(gde.cv, tramite.cv_en_firma),
    gde.cv ? null : el("div", { clase: "acciones" }, tramite.cv_en_firma
      ? el("button", { type: "button", clase: "secundario", texto: "Quitar «en proceso de firma»",
        onclick: () => tramitar("cv_en_firma", { hecho: false }, "Marca quitada.") })
      : el("button", { type: "button", texto: "Marcar en proceso de firma",
        onclick: () => tramitar("cv_en_firma", { hecho: true }, "Certificado en proceso de firma.") })),
    el("form", { clase: "formulario", novalidate: true, onsubmit: (e) => {
      e.preventDefault();
      tramitar("cv_firmado", { gde: document.getElementById("tr-cv").value.trim() }, "N° GDE del certificado guardado.");
    } },
      entradaGde("tr-cv", "N° GDE del certificado firmado", gde.cv),
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar N° del certificado firmado" }), botonSiguiente())));
}

// 4. Ingreso en SAP del bien (vale de entrada, un bloque por remito) o del servicio (hoja de entrada).
async function pintarPasoIngresoSap() {
  const contenedor = document.getElementById("asistente-paso-9");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const tramite = expEstado.exp.datos.tramite || {};
  const e = textos.entrada_sap;
  const partes = [el("h3", { texto: tituloPaso(9) })];
  if (!e) {
    partes.push(avisoFalta(textos.entrada_sap_error));
  } else if (e.tipo === "BIEN") {
    partes.push(el("p", { clase: "texto-suave", texto: "Ingreso de material (vale de entrada): un ingreso por remito." }),
      tablaCopiar([filaCopiar("OC", e.oc), filaCopiar("Fecha de documento", e.fecha_documento)]));
    for (const r of e.remitos) {
      partes.push(el("h4", { texto: "Remito " + r.numero }), tablaCopiar([
        filaCopiar("N° de remito (nota de entrega)", r.numero),
        filaCopiar("Fecha de entrega (del remito)", r.fecha),
        ...r.renglones.map((x) => filaCopiar("Cantidad renglón " + x.pos, x.cantidad))]),
      r.renglones.length ? null : avisoFalta("Este remito no tiene cantidades cargadas (paso 2)."));
    }
  } else {
    partes.push(el("p", { clase: "texto-suave", texto: "Hoja de entrada de servicios: período validado, no el de toda la OC." }),
      tablaCopiar([
        filaCopiar("OC", e.oc),
        filaCopiar("Texto breve", e.texto_breve),
        filaCopiar("Fecha desde", e.desde),
        filaCopiar("Fecha hasta", e.hasta),
        filaCopiar("Centro (lugar de servicio)", e.centro),
        ...e.renglones.map((x) => filaCopiar("Cantidad renglón " + x.pos, x.cantidad))]));
  }
  partes.push(marcaHecho("ingreso_sap", tramite.ingreso_sap, "Marcar como ingresado en SAP", "Ingresado en SAP"));
  vaciar(contenedor, ...partes);
}

// 6. Caratulación: controles en orden, datos para caratular, motivo y N° de expediente (EX).
async function pintarPasoCaratulacion() {
  const contenedor = document.getElementById("asistente-paso-10");
  cargando(contenedor);
  const [textos, informe] = [await textosTramite(), await api("GET", "/api/expedientes/" + expEstado.exp.id + "/controles")];
  if (!textos || !informe) { vaciar(contenedor); return; }
  const exp = expEstado.exp;
  const gde = exp.datos.gde || {};
  const r = informe.resumen;
  const bloquea = r.error > 0 || r.salvable > r.salvable_con_nota;
  const controlesDiv = el("div", {});
  pintarControles(informe, controlesDiv, null);
  const c = textos.caratulacion;
  const partes = [el("h3", { texto: tituloPaso(10) })];
  if (bloquea) {
    partes.push(el("div", { clase: "mensaje mensaje-error" }, el("p", { texto: "Todavía no se puede caratular: hay " + r.error
      + " errores y " + (r.salvable - r.salvable_con_nota) + " salvables sin nota. Resolvelos abajo." })), controlesDiv);
  } else {
    partes.push(el("div", { clase: "mensaje mensaje-exito" }, el("p", { texto: "Controles en orden"
      + (r.aviso || r.verificar ? " (" + r.aviso + " avisos y " + r.verificar + " para verificar)" : "") + ": ya se puede caratular." })),
    el("details", { clase: "detalle-controles" }, el("summary", { texto: "Ver los controles" }), controlesDiv));
  }
  partes.push(el("h4", { texto: "Datos para caratular" }), tablaCopiar([
    filaCopiar("Código de trámite", c.codigo_tramite),
    filaCopiar("Mail", c.mail),
    filaCopiar("N°", c.numero),
    filaCopiar("Oficina", c.oficina),
    textos.caratula ? filaCopiar("Motivo", textos.caratula) : null]));
  if (!textos.caratula) partes.push(avisoFalta("Motivo: " + textos.caratula_error));
  partes.push(el("form", { clase: "formulario panel", novalidate: true, onsubmit: (e) => {
    e.preventDefault();
    tramitar("caratular", { expediente: document.getElementById("tr-ex").value.trim() }, "N° de expediente guardado.");
  } },
    entradaGde("tr-ex", "N° de expediente (EX)", gde.expediente),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar N° de expediente" }), botonSiguiente())));
  vaciar(contenedor, ...partes);
}

// Documentos de la carga en GDE (la autorización y la constancia de contabilización van en sus propios pasos).
const GDE_DE_REFERENCIA = { factura: "factura", sii: "sii", remito_equipo: "remito_equipo", vale_hoja: "vale_hoja" };

function tarjetaGde(titulo, referencia, campo) {
  return el("div", { clase: "tarjeta-gde" },
    el("h4", { texto: titulo }),
    referencia ? el("div", { clase: "referencia-gde" }, el("span", { clase: "mono", texto: referencia }),
      el("button", { type: "button", clase: "secundario", texto: "Copiar", "aria-label": "Copiar la referencia " + referencia,
        onclick: () => copiarTexto(referencia) })) : null,
    campo);
}

// 7. Carga en GDE: cada documento con su referencia (Copiar) y su N° GDE al lado; se guarda todo junto.
async function pintarPasoGde() {
  const contenedor = document.getElementById("asistente-paso-11");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const exp = expEstado.exp;
  const gde = exp.datos.gde || {};
  const referencias = Object.fromEntries((textos.referencias || []).map((x) => [x.clave, x.referencia]));
  const remitos = exp.datos.remitos.filter((x) => !x.es_equipo_comodato);
  const tarjetas = [
    tarjetaGde("Carátula", null, entradaGde("gde-caratula", "N° GDE de la carátula", gde.caratula)),
    tarjetaGde("Factura", referencias.factura, entradaGde("gde-factura", "N° GDE", gde.factura)),
    tarjetaGde("Carga en SII", referencias.sii, entradaGde("gde-sii", "N° GDE", gde.sii)),
    tarjetaGde("PDF de la OC", null, entradaGde("gde-oc_pdf", "N° GDE (vacío = el de la OC)", gde.oc_pdf)),
    tarjetaGde(remitos.length > 1 ? "Remitos" : "Remito", referencias.remitos,
      el("div", {}, ...remitos.map((x, i) => entradaGde("gde-remito-" + i, "N° GDE del remito " + x.numero, (gde.remitos || {})[x.numero])))),
  ];
  if (referencias.remito_equipo) {
    tarjetas.push(tarjetaGde("Remito del equipo en comodato", referencias.remito_equipo,
      el("div", {}, entradaGde("gde-remito_equipo", "N° GDE", gde.remito_equipo),
        campoFormulario("gde-orden", "Orden del remito del equipo en el expediente",
          entrada(gde.orden_remito_equipo ?? "", { type: "number", min: "1", inputmode: "numeric", clase: "entrada-corta" })))));
  }
  tarjetas.push(tarjetaGde("Certificado de validación", referencias.cv,
    el("p", { clase: "texto-suave", texto: gde.cv ? "N° GDE: " + gde.cv + " (cargado en el paso 3)." : "Falta el N° GDE del certificado firmado (paso 3)." })));
  tarjetas.push(tarjetaGde(referencias.vale_hoja && referencias.vale_hoja.includes("VALE") ? "Vale de entrada" : "Hoja de entrada",
    referencias.vale_hoja, entradaGde("gde-vale_hoja", "N° GDE", gde.vale_hoja)));
  if (textos.constancia_comodato) {
    tarjetas.push(tarjetaGde("Constancia de recepción de comodato", textos.constancia_comodato.referencia,
      el("div", {}, bloqueTexto("Constancia de recepción de comodato", textos.constancia_comodato.cuerpo, true),
        entradaGde("gde-constancia", "N° GDE", gde.constancia))));
  }
  const guardar = (e) => {
    e.preventDefault();
    const nuevo = {};
    for (const clave of ["caratula", "factura", "sii", "oc_pdf", "remito_equipo", "vale_hoja", "constancia"]) {
      const campo = document.getElementById("gde-" + clave);
      if (campo) nuevo[clave] = campo.value.trim();
    }
    nuevo.remitos = {};
    remitos.forEach((x, i) => {
      const valor = document.getElementById("gde-remito-" + i).value.trim();
      if (valor) nuevo.remitos[x.numero] = valor;
    });
    const orden = document.getElementById("gde-orden");
    if (orden) nuevo.orden_remito_equipo = orden.value.trim() || null;
    tramitar("gde", { gde: nuevo }, "Números GDE guardados.");
  };
  vaciar(contenedor,
    el("h3", { texto: tituloPaso(11) }),
    el("p", { clase: "texto-suave", texto: "Copiá la referencia de cada documento al subirlo a GDE y anotá su número. "
      + "Se puede guardar a medias y seguir después." }),
    textos.referencias_error ? avisoFalta("Referencias: " + textos.referencias_error) : null,
    el("form", { clase: "formulario", novalidate: true, onsubmit: guardar }, ...tarjetas,
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar números GDE" }), botonSiguiente())));
}

// 8. Ingreso de la factura en SAP (sin transacción): con el N° de expediente y la fecha de la factura.
async function pintarPasoFacturaSap() {
  const contenedor = document.getElementById("asistente-paso-12");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const tramite = expEstado.exp.datos.tramite || {};
  const f = textos.factura_sap;
  const partes = [el("h3", { texto: tituloPaso(12) })];
  if (!f) {
    partes.push(avisoFalta(textos.factura_sap_error));
  } else {
    if (f.aviso_largo) partes.push(avisoFalta(f.aviso_largo));
    partes.push(tablaCopiar([
      filaCopiar("Expediente", f.expediente),
      filaCopiar("Fecha de documento", f.fecha_documento),
      filaCopiar("Fecha de contabilización", f.fecha_contabilizacion),
      filaCopiar("Importe", f.importe),
      filaCopiar("Texto (" + f.largo_texto + " caracteres)", f.texto),
      filaCopiar("Asignación", f.asignacion),
      filaCopiar("Txt. cabecera (al ingresar)", f.txt_cabecera_ingreso),
      filaCopiar("Txt. cabecera (después, en lugar de los ceros)", f.txt_cabecera),
      filaCopiar("Clase", f.clase),
      filaCopiar("Texto breve", f.texto_breve)]));
  }
  partes.push(marcaHecho("factura_sap", tramite.factura_sap, "Marcar factura ingresada en SAP", "Factura ingresada en SAP"));
  vaciar(contenedor, ...partes);
}

// 9. Autorización de pago: descarga, en firma (~1 día) y N° GDE de la firmada (queda FIRMADO).
async function pintarPasoAutorizacion() {
  const contenedor = document.getElementById("asistente-paso-13");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const exp = expEstado.exp;
  const gde = exp.datos.gde || {};
  const base = "/api/expedientes/" + exp.id;
  const partes = [el("h3", { texto: tituloPaso(13) })];
  if (!gde.expediente) partes.push(avisoFalta("Primero cargá el N° de expediente en la caratulación (paso 6)."));
  if (textos.autorizacion) {
    partes.push(el("div", { clase: "acciones" },
      el("a", { clase: "boton", href: base + "/autorizacion.docx", download: "", texto: "Descargar autorización (.docx)" })),
    bloqueTexto("Referencia de la autorización", textos.autorizacion.referencia, false),
    bloqueTexto("Autorización de pago", textos.autorizacion.cuerpo, true));
  } else {
    partes.push(avisoFalta("Autorización: " + textos.autorizacion_error));
  }
  const enFirma = exp.estado === "EN_FIRMA" ? (exp.datos.historial || []).slice().reverse()
    .find((h) => h.estado === "EN_FIRMA") : null;
  partes.push(el("h4", { texto: "Firma" }),
    estadoFirma(gde.autorizacion, enFirma ? enFirma.fecha.slice(0, 10) : null));
  if (exp.estado === "CONTROLADO") {
    partes.push(el("div", { clase: "acciones" }, el("button", { type: "button", texto: "Marcar en proceso de firma",
      onclick: () => tramitar("autorizacion_en_firma", {}, "Autorización en proceso de firma.") })));
  }
  partes.push(el("form", { clase: "formulario", novalidate: true, onsubmit: (e) => {
    e.preventDefault();
    tramitar("autorizacion_firmada", { gde: document.getElementById("tr-autorizacion").value.trim() },
      "Autorización firmada: el expediente quedó «Firmado».");
  } },
    entradaGde("tr-autorizacion", "N° GDE de la autorización firmada", gde.autorizacion),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar N° de la autorización firmada" }), botonSiguiente())));
  vaciar(contenedor, ...partes);
}

// 10. Cierre: constancia de contabilización al expediente y pase al buzón de Contable (queda COMPLETO).
async function pintarPasoCierre() {
  const contenedor = document.getElementById("asistente-paso-14");
  cargando(contenedor);
  const textos = await textosTramite();
  if (!textos) { vaciar(contenedor); return; }
  const exp = expEstado.exp;
  const gde = exp.datos.gde || {};
  const tramite = exp.datos.tramite || {};
  const constancia = (textos.referencias || []).find((x) => x.clave === "constancia");
  const partes = [el("h3", { texto: tituloPaso(14) }),
    el("p", {}, "Estado: ", el("span", { clase: "pastilla pastilla-" + (TONO_ESTADO[exp.estado] || "neutra"),
      texto: ESTADOS_TEXTO[exp.estado] || exp.estado }))];
  if (exp.estado === "COMPLETO" || tramite.pase && exp.estado !== "FIRMADO") {
    partes.push(el("div", { clase: "mensaje mensaje-exito" }, el("p", { texto: "Pase al buzón de Contable dado el "
      + fechaCorta(tramite.pase) + "." + (exp.estado === "COMPLETO" ? " Va en la próxima entrega (pantalla Entregas)." : "") })));
  }
  if (constancia) partes.push(bloqueTexto("Referencia de la constancia de contabilización", constancia.referencia, false));
  if (["FIRMADO", "COMPLETO"].includes(exp.estado)) {
    partes.push(el("form", { clase: "formulario panel", novalidate: true, onsubmit: (e) => {
      e.preventDefault();
      tramitar("pase", { gde: document.getElementById("tr-contabilizacion").value.trim() },
        "Pase dado: el expediente quedó «Completo».");
    } },
      entradaGde("tr-contabilizacion", "N° GDE de la constancia de contabilización", gde.contabilizacion),
      el("div", { clase: "acciones" }, el("button", { type: "submit",
        texto: exp.estado === "COMPLETO" ? "Guardar N° de la constancia" : "Guardar y dar el pase al buzón de Contable" }))));
  } else if (!["ENVIADO", "CONTABILIZADO", "CERRADO", "ANULADO"].includes(exp.estado)) {
    partes.push(avisoFalta("El pase se da con la autorización de pago firmada (paso 9)."));
  }
  partes.push(...partesEstado(exp, true));
  vaciar(contenedor, ...partes);
}

// Paso 7: estado.

const TRANSICIONES_COMUN = {
  BORRADOR: ["CONTROLADO"], CONTROLADO: ["EN_FIRMA", "BORRADOR"], EN_FIRMA: ["FIRMADO", "CONTROLADO"],
  FIRMADO: ["COMPLETO"], COMPLETO: ["FIRMADO"], ENVIADO: ["CONTABILIZADO"], CONTABILIZADO: ["CERRADO"],
};
const ESTADOS_FINALES = ["CERRADO", "ANULADO", "FINALIZADO"];

function pintarPaso7() {
  const exp = expEstado.exp;
  vaciar(document.getElementById("asistente-paso-7"), el("h3", { texto: "7. Estado" }),
    el("p", { texto: "Estado actual: " + (ESTADOS_TEXTO[exp.estado] || exp.estado) }), ...partesEstado(exp, false));
}

const ACCIONES_HISTORIAL = {
  CV_EN_FIRMA: "Certificado en firma", CV_FIRMADO: "Certificado firmado", INGRESO_SAP: "Ingreso en SAP",
  CARATULAR: "Caratulación (EX)", GDE: "Números GDE", FACTURA_SAP: "Factura en SAP",
  AUTORIZACION_EN_FIRMA: "Autorización en firma", AUTORIZACION_FIRMADA: "Autorización firmada",
  PASE: "Pase al buzón de Contable",
};

/** Pendiente / reanudar, cambios de estado (solo en el asistente clásico) e historial. */
function partesEstado(exp, tramite) {
  const partes = [];
  if (exp.estado === "PENDIENTE") {
    partes.push(el("div", { clase: "mensaje mensaje-aviso" },
      el("p", { texto: "Pendiente: " + exp.motivo_pendiente + " · seguimiento " + (exp.fecha_seguimiento || "") })),
      el("div", { clase: "acciones" }, el("button", { type: "button", texto: "Reanudar", onclick: reanudar })));
  } else if (!ESTADOS_FINALES.includes(exp.estado)) {
    // los destinos los da el servidor según el tipo (ENVIADO solo por entrega)
    const destinos = (exp.destinos || TRANSICIONES_COMUN[exp.estado] || []).filter((d) => d !== "ENVIADO");
    if (!tramite && exp.estado === "FIRMADO") {
      partes.push(el("p", { clase: "texto-suave", texto: "Para marcarlo como enviado, asignalo a una entrega." }));
    }
    // En el trámite el estado avanza solo con cada paso: no hay botones de «Pasar a…».
    if (!tramite) {
      partes.push(el("div", { clase: "acciones" }, ...destinos.map((destino) => el("button", { type: "button",
        clase: destino === "BORRADOR" || destino === "CONTROLADO" && exp.estado === "EN_FIRMA" ? "secundario" : null,
        texto: "Pasar a " + (ESTADOS_TEXTO[destino] || destino), onclick: () => cambiarEstado(destino) }))));
    }
    partes.push(el("form", { clase: "formulario panel", novalidate: true, onsubmit: marcarPendiente },
      el("h4", { texto: "Dejar pendiente" }),
      campoFormulario("pend-motivo", "Motivo", entrada("")),
      campoFormulario("pend-fecha", "Fecha de seguimiento", entrada("", { type: "date" })),
      el("div", { clase: "acciones" }, el("button", { type: "submit", clase: "secundario", texto: "Dejar pendiente" }))));
  }
  const historial = (exp.datos.historial || []).slice().reverse();
  partes.push(el("h4", { texto: "Historial" }));
  partes.push(tabla(["Fecha", "Usuario", "Acción", "Estado"],
    historial.map((h) => [formatoFechaHora(h.fecha), h.usuario, (ACCIONES_HISTORIAL[h.accion] || h.accion) + (h.motivo ? " (" + h.motivo + ")" : ""),
      (h.desde ? (ESTADOS_TEXTO[h.desde] || h.desde) + " → " : "") + (ESTADOS_TEXTO[h.estado] || h.estado)])));
  return partes;
}

async function enviarEstado(ruta, cuerpo, mensaje) {
  limpiarAvisos();
  const exp = expEstado.exp;
  estado.recargar = () => abrirExpediente(exp.id, expEstado.paso);
  const actualizado = await api("POST", "/api/expedientes/" + exp.id + ruta, Object.assign({ version: exp.version }, cuerpo));
  if (!actualizado) return;
  expEstado.exp = actualizado;
  pintarEncabezadoAsistente();
  mostrarPaso(expEstado.paso);
  mostrarAviso(mensaje, "exito");
}

function cambiarEstado(destino) {
  return enviarEstado("/estado", { estado: destino }, "Expediente en " + (ESTADOS_TEXTO[destino] || destino) + ".");
}

function marcarPendiente(evento) {
  evento.preventDefault();
  const motivo = document.getElementById("pend-motivo").value.trim();
  const fecha = document.getElementById("pend-fecha").value;
  if (!motivo || !fecha) { limpiarAvisos(); mostrarAviso("Indicá el motivo y la fecha de seguimiento.", "error"); return; }
  return enviarEstado("/estado", { estado: "PENDIENTE", motivo, fecha_seguimiento: fecha }, "Expediente pendiente.");
}

function reanudar() {
  return enviarEstado("/reanudar", {}, "Expediente reanudado.");
}

function iniciarExpedientes() {
  document.getElementById("expedientes-filtros").addEventListener("submit", (e) => { e.preventDefault(); listarExpedientes(); });
  document.getElementById("expediente-nuevo").addEventListener("click", nuevoExpediente);
  document.getElementById("asistente-volver").addEventListener("click", () => {
    limpiarAvisos();
    if (esCentralizada()) { mostrarLista(); mostrarPantalla("pantalla-centralizadas", true); return; }
    mostrarLista();
  });
  document.getElementById("asistente-anular").addEventListener("click", abrirDialogoAnular);
}

// --- Calendario ---------------------------------------------------------------

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

// Los siete estados de una celda (leyenda-calendario): clase de color + letra + nombre, para no depender solo del color.
const ESTADOS_CALENDARIO = [
  ["validado", "V", "validado", "firmado, enviado, contabilizado o cerrado"],
  ["en_curso", "C", "en curso", "borrador, controlado o en firma"],
  ["pendiente_motivo", "M", "pendiente con motivo", "expediente en espera"],
  ["pendiente_en_plazo", "P", "pendiente en plazo", "sin expediente, todavía dentro de los días de gracia"],
  ["atrasado", "A", "atrasado", "sin expediente y pasaron los días de gracia"],
  ["sin_iniciar", "·", "sin iniciar", "el período todavía no empezó"],
  ["fuera", "-", "fuera de vigencia", "la OC no cubre ese mes"],
];
const NOMBRE_ESTADO_CAL = Object.fromEntries(ESTADOS_CALENDARIO.map(([clave, , nombre]) => [clave, nombre]));
const MARCAS_CALENDARIO = [
  ["vence_pronto", "!", "OC por vencer", "borde naranja en la fila"],
  ["entrega_enviada", "●", "en entrega enviada", "el expediente salió en una entrega"],
  ["centralizada_enviada", "◆", "centralizada enviada", "la centralizada del período ya se envió"],
];

function pintarLeyendaCalendario() {
  const leyenda = document.getElementById("leyenda-calendario");
  if (leyenda.childElementCount) return;
  const item = (clase, letra, nombre, detalle) => el("li", {},
    el("span", { clase: "cal-muestra " + clase, "aria-hidden": "true", texto: letra }),
    el("span", { texto: letra + " — " + nombre + " (" + detalle + ")" }));
  vaciar(leyenda,
    el("h2", { clase: "titulo-chico", texto: "Referencias" }),
    el("ul", { clase: "lista-leyenda" },
      ...ESTADOS_CALENDARIO.map(([clave, letra, nombre, detalle]) => item("cal-" + clave, letra, nombre, detalle)),
      ...MARCAS_CALENDARIO.map(([clave, letra, nombre, detalle]) => item("cal-marca-" + clave, letra, nombre, detalle))));
}

function cargarCalendario() {
  const anio = document.getElementById("cal-anio");
  if (!anio.value) anio.value = String(new Date().getFullYear());
  pintarLeyendaCalendario();
  return pedirCalendario();
}

async function pedirCalendario() {
  const contenedor = document.getElementById("calendario-tabla");
  cargando(contenedor);
  const parametros = new URLSearchParams({ anio: document.getElementById("cal-anio").value.trim() });
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  const tipo = document.getElementById("cal-tipo").value;
  const sap = document.getElementById("cal-sap").value.trim();
  if (tipo) parametros.set("tipo", tipo);
  if (sap) parametros.set("sap", sap);
  const datos = await api("GET", "/api/calendario?" + parametros.toString());
  if (!datos) { vaciar(contenedor); return; }
  if (!datos.filas.length) {
    vaciar(contenedor, el("p", { clase: "texto-suave", texto: "No hay OC vigentes en " + datos.anio + " con esos filtros." }));
    return;
  }
  const encabezado = el("tr", {}, el("th", { scope: "col", texto: "OC / proveedor" }),
    ...MESES.map((mes) => el("th", { scope: "col", clase: "cal-mes", title: mes + " " + datos.anio, texto: mes.slice(0, 3) })));
  const filas = datos.filas.map((fila) => el("tr", { clase: fila.vence_pronto ? "cal-vence_pronto" : null },
    el("th", { scope: "row", clase: "cal-oc" },
      el("span", { clase: "numero", texto: fila.oc }),
      fila.vence_pronto ? el("span", { clase: "cal-aviso-vence", texto: " ! vence el " + fila.vig_hasta }) : null,
      el("br"),
      el("span", { clase: "texto-suave", texto: fila.razon_social + (fila.objeto ? " — " + fila.objeto : "") })),
    ...fila.celdas.map((celda, i) => celdaCalendario(fila, celda, i, datos.anio))));
  vaciar(contenedor,
    botonesExporte("calendario", { anio: datos.anio, efector: estado.efector === "Ambos" ? "" : estado.efector, tipo, sap },
      "del calendario " + datos.anio),
    el("div", { clase: "tabla-desplazable" },
      el("table", { clase: "calendario" }, el("thead", {}, encabezado), el("tbody", {}, ...filas))));
}

function celdaCalendario(fila, celda, indice, anio) {
  const marcas = (celda.entrega_enviada ? "●" : "") + (celda.centralizada_enviada ? "◆" : "");
  const etiqueta = MESES[indice] + " " + anio + ": " + NOMBRE_ESTADO_CAL[celda.estado]
    + (celda.entrega_enviada ? ", en entrega enviada" : "") + (celda.centralizada_enviada ? ", centralizada enviada" : "")
    + " — OC " + fila.oc;
  const td = el("td", { clase: "cal-celda cal-" + celda.estado, "aria-label": etiqueta, title: etiqueta },
    el("span", { "aria-hidden": "true", texto: celda.letra + (marcas ? " " + marcas : "") }));
  if (celda.estado === "fuera") return td;
  td.tabIndex = 0;
  td.setAttribute("role", "button");
  const abrir = () => abrirDesdeCalendario(fila, celda);
  td.addEventListener("click", abrir);
  td.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrir(); } });
  return td;
}

/** Clic o Enter en una celda: abre su expediente o crea uno nuevo con la OC y el período de la celda. */
async function abrirDesdeCalendario(fila, celda) {
  limpiarAvisos();
  let id = celda.expediente_id;
  if (!id) {
    estado.recargar = pedirCalendario;
    const exp = await api("POST", "/api/expedientes", {
      tipo: "COMUN", oc: fila.oc, periodo: celda.periodo, periodo_desde: celda.desde, periodo_hasta: celda.hasta, periodo_manual: 1,
    });
    if (!exp) return;
    id = exp.id;
  }
  expEstado.exp = { id };
  expEstado.paso = celda.expediente_id ? 7 : 2;
  mostrarPantalla("pantalla-expedientes", true);
  if (!celda.expediente_id) mostrarAviso("Expediente " + id + " creado para la OC " + fila.oc + ", período " + celda.periodo + ".", "exito");
}

function iniciarCalendario() {
  document.getElementById("calendario-filtros").addEventListener("submit", (e) => { e.preventDefault(); limpiarAvisos(); pedirCalendario(); });
}

// --- Entregas -----------------------------------------------------------------

const entEstado = { abierta: null };

function hoyIso() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

function descripcionExpediente(x) {
  return "N° " + x.id + " · OC " + (x.oc || "—") + " · " + (x.razon_social || "") + " · " + (x.periodo || "sin período")
    + (x.factura ? " · FC " + x.factura : "");
}

async function cargarEntregas() {
  const contenedor = document.getElementById("entregas-contenido");
  estado.recargar = cargarEntregas;
  cargando(contenedor);
  const parametros = new URLSearchParams();
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  const datos = await api("GET", "/api/entregas?" + parametros.toString());
  if (!datos) { vaciar(contenedor); return; }
  const efectorInicial = estado.efector === "Ambos" ? "HBI" : estado.efector;
  const alta = el("form", { clase: "panel formulario filtros", novalidate: true, onsubmit: crearEntrega },
    el("h2", { clase: "titulo-chico", texto: "Nueva entrega" }),
    campoFormulario("entrega-efector", "Efector", selector(efectorInicial, [["HBI", "HBI"], ["CASPH", "CASPH"]])),
    campoFormulario("entrega-nombre", "Nombre (opcional)", entrada("", { autocomplete: "off", placeholder: "Entrega N" })),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Crear entrega" })));
  const partes = [alta];
  partes.push(el("p", { clase: "texto-suave", texto: datos.firmados_sin_entrega.length
    ? (datos.firmados_sin_entrega.length === 1 ? "1 expediente firmado espera entrega."
      : datos.firmados_sin_entrega.length + " expedientes firmados esperan entrega.")
    : "No hay expedientes firmados sin entrega." }));
  if (!datos.entregas.length) {
    partes.push(el("p", { clase: "texto-suave", texto: "Todavía no hay entregas." }));
  } else {
    const filas = datos.entregas.map((e) => el("tr", { clase: "fila-clic", title: "Ver las facturas de la entrega", onclick: () => abrirEntrega(e.id) },
      el("td", {}, el("button", { type: "button", clase: "secundario", texto: e.efector + " " + e.numero,
        "aria-label": "Abrir la entrega " + e.efector + " " + e.numero, onclick: (ev) => { ev.stopPropagation(); abrirEntrega(e.id); } })),
      el("td", { texto: e.nombre }),
      el("td", { texto: e.estado === "ENVIADA" ? "Enviada" : "Abierta" }),
      el("td", { texto: e.fecha_envio || "—" }),
      el("td", { clase: "numero", texto: String(e.expedientes) })));
    partes.push(el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Entrega", "Nombre", "Estado", "Enviada el", "Expedientes"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filas))));
  }
  vaciar(contenedor, ...partes);
  if (entEstado.abierta) abrirEntrega(entEstado.abierta);
}

async function crearEntrega(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const entrega = await api("POST", "/api/entregas", {
    efector: document.getElementById("entrega-efector").value, nombre: document.getElementById("entrega-nombre").value.trim(),
  });
  if (!entrega) return;
  mostrarAviso("Entrega " + entrega.efector + " " + entrega.numero + " creada.", "exito");
  entEstado.abierta = entrega.id;
  cargarEntregas();
}

/** La entrega en una ventana: todas sus facturas (proveedor, OC, período, N° e importe) con el total. */
async function abrirEntrega(id) {
  entEstado.abierta = id;
  const entrega = await api("GET", "/api/entregas/" + id);
  if (!entrega) { entEstado.abierta = null; return; }
  const lista = await api("GET", "/api/entregas?efector=" + encodeURIComponent(entrega.efector));
  const candidatos = lista ? lista.firmados_sin_entrega : [];
  const abierta = entrega.estado === "ABIERTA";
  const anterior = document.getElementById("dialogo-entrega");
  if (anterior) { anterior.dataset.recargando = "1"; anterior.close(); }
  const dialogo = el("dialog", { id: "dialogo-entrega", clase: "dialogo", "aria-labelledby": "entrega-titulo" });
  const partes = [el("div", { clase: "dialogo-encabezado" },
    el("h2", { id: "entrega-titulo", texto: "Entrega " + entrega.efector + " " + entrega.numero + " — " + entrega.nombre }),
    el("p", { clase: "texto-suave", texto: (abierta ? "Abierta: todavía se pueden agregar o quitar expedientes." : "Enviada el " + entrega.fecha_envio + ".")
      + " " + entrega.expedientes.length + (entrega.expedientes.length === 1 ? " factura." : " facturas.") }))];
  if (entrega.expedientes.length) {
    const total = entrega.expedientes.reduce((t, x) => t + (x.importe_centavos || 0), 0);
    const filas = entrega.expedientes.map((x) => el("tr", { clase: "fila-clic", title: "Abrir el expediente " + x.id,
      onclick: () => { dialogo.close(); abrirExpedienteDesdeOC(x.id, 1); } },
      el("td", { clase: "numero", texto: String(x.id) }),
      el("td", { clase: "izq", texto: x.razon_social || "" }),
      el("td", { texto: x.oc || "—" }),
      el("td", { texto: x.periodo || "—" }),
      el("td", { clase: "mono sin-corte", texto: x.factura || "—" }),
      el("td", { clase: "numero sin-corte", texto: x.importe_centavos === null || x.importe_centavos === undefined ? "—" : formatoPesos(x.importe_centavos) }),
      el("td", {}, el("span", { clase: "pastilla pastilla-" + (TONO_ESTADO[x.estado] || "neutra"), texto: ESTADOS_TEXTO[x.estado] || x.estado })),
      el("td", {}, abierta ? el("button", { type: "button", clase: "secundario", texto: "Quitar",
        "aria-label": "Quitar el expediente " + x.id + " de la entrega",
        onclick: (ev) => { ev.stopPropagation(); cambiarEntrega(entrega, "/quitar", [x.id], "Expediente quitado."); } }) : null)));
    partes.push(el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["N°", "Proveedor", "OC", "Período", "Factura", "Importe $", "Estado", ""]
        .map((t) => el("th", { scope: "col", clase: t === "Proveedor" ? "izq" : null, texto: t })))),
      el("tbody", {}, ...filas),
      el("tfoot", {}, el("tr", {}, el("th", { scope: "row", clase: "izq", colspan: "5", texto: "Total" }),
        el("td", { clase: "numero sin-corte", texto: formatoPesos(total) }), el("td", {}), el("td", {}))))),
      el("div", { clase: "acciones" },
        el("a", { clase: "boton secundario", href: "/api/entregas/" + entrega.id + "/numeracion.csv", download: "",
          texto: "Descargar CSV NUMERACIÓN" })),
      botonesExporte("entrega", { id: entrega.id }, "de la entrega " + entrega.efector + " " + entrega.numero));
  } else {
    partes.push(el("p", { clase: "texto-suave", texto: "La entrega no tiene expedientes." }));
  }
  if (abierta && candidatos.length) {
    const casillas = candidatos.map((x) => el("div", { clase: "campo campo-casilla" },
      el("input", { type: "checkbox", id: "asignar-" + x.id, value: String(x.id) }),
      el("label", { for: "asignar-" + x.id, texto: descripcionExpediente(x) })));
    partes.push(el("form", { clase: "formulario", novalidate: true, onsubmit: (e) => {
      e.preventDefault();
      const ids = casillas.map((c) => c.querySelector("input")).filter((i) => i.checked).map((i) => Number(i.value));
      if (!ids.length) { avisoEnDialogo(dialogo, "Marcá al menos un expediente."); return; }
      cambiarEntrega(entrega, "/asignar", ids, ids.length === 1 ? "Expediente agregado." : ids.length + " expedientes agregados.");
    } },
    el("fieldset", {}, el("legend", { texto: "Expedientes firmados sin entrega (" + entrega.efector + ")" }), ...casillas),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Agregar a la entrega" }))));
  }
  if (abierta && entrega.expedientes.length) {
    partes.push(el("form", { clase: "formulario filtros", novalidate: true, onsubmit: (e) => { e.preventDefault(); enviarEntrega(entrega); } },
      campoFormulario("entrega-fecha", "Fecha de envío", entrada(hoyIso(), { type: "date" })),
      el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Marcar como enviada" }))));
  }
  partes.push(el("div", { clase: "acciones dialogo-acciones" },
    el("button", { type: "button", texto: "Cerrar", onclick: () => dialogo.close() })));
  vaciar(dialogo, ...partes);
  dialogo.addEventListener("close", () => {
    if (!dialogo.dataset.recargando) entEstado.abierta = null;
    dialogo.remove();
  });
  document.body.append(dialogo);
  dialogo.showModal();
}

async function cambiarEntrega(entrega, accion, ids, mensaje) {
  limpiarAvisos();
  estado.recargar = cargarEntregas;
  const actualizada = await api("POST", "/api/entregas/" + entrega.id + accion, { version: entrega.version, expedientes: ids });
  const ventana = document.getElementById("dialogo-entrega");
  if (!actualizada) { if (ventana) avisoEnDialogo(ventana, ultimoError()); return; }
  mostrarAviso(mensaje, "exito");
  await cargarEntregas();
}

async function enviarEntrega(entrega) {
  limpiarAvisos();
  const fecha = document.getElementById("entrega-fecha").value;
  if (!fecha) { avisoEnDialogo(document.getElementById("dialogo-entrega"), "Indicá la fecha de envío."); return; }
  if (!window.confirm("¿Marcar la entrega como enviada? Sus " + entrega.expedientes.length + " expedientes pasan a ENVIADO.")) return;
  estado.recargar = cargarEntregas;
  const enviada = await api("POST", "/api/entregas/" + entrega.id + "/enviar", { version: entrega.version, fecha });
  const ventana = document.getElementById("dialogo-entrega");
  if (!enviada) { if (ventana) avisoEnDialogo(ventana, ultimoError()); return; }
  mostrarAviso("Entrega " + enviada.efector + " " + enviada.numero + " enviada el " + enviada.fecha_envio + ".", "exito");
  await cargarEntregas();
}

// --- Pendientes (lista dentro de Expedientes) ----------------------------------

async function listarPendientes() {
  const contenedor = document.getElementById("expedientes-pendientes");
  if (!contenedor) return;
  const lista = await api("GET", "/api/pendientes");
  if (!lista) { vaciar(contenedor); return; }
  const visibles = lista.filter((p) => estado.efector === "Ambos" || p.efector === estado.efector);
  if (!visibles.length) { vaciar(contenedor); return; }
  const filas = visibles.map((p) => el("tr", { clase: p.dias_demora > 0 ? "fila-demorada" : null },
    el("td", {}, el("button", { type: "button", clase: "secundario", texto: String(p.id),
      "aria-label": "Abrir el expediente pendiente " + p.id, onclick: () => abrirExpediente(p.id, 7) })),
    el("td", { texto: p.proveedor }),
    el("td", { texto: p.oc || "—" }),
    el("td", { texto: p.periodo || "—" }),
    el("td", { texto: p.motivo }),
    el("td", { texto: p.fecha_seguimiento || "—" }),
    el("td", { clase: "numero", texto: p.dias_demora > 0 ? p.dias_demora + (p.dias_demora === 1 ? " día" : " días") : "en plazo" })));
  vaciar(contenedor, el("div", { clase: "panel" },
    el("h2", { clase: "titulo-chico", texto: "Pendientes (" + visibles.length + ")" }),
    botonesExporte("pendientes", {}, "de los pendientes"),
    el("div", { clase: "tabla-desplazable" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["N°", "Proveedor", "OC", "Período", "Motivo", "Seguimiento", "Demora"].map((t) => el("th", { scope: "col", texto: t })))),
      el("tbody", {}, ...filas)))));
}

// --- Configuración --------------------------------------------------------------

// Parámetros compartidos editables: clave de la tabla config, ruta dentro del valor y tipo de dato.
const CAMPOS_PARAMETROS = [
  { id: "par-gestor-hbi", etiqueta: "Centro gestor del HBI", clave: "efectores", ruta: ["HBI", "centros_gestores"], tipo: "lista",
    defecto: ["4500"], ayuda: "Al importar el z_compras2 entra todo lo imputado a este centro gestor, aunque el renglón tenga otro centro." },
  { id: "par-gestor-casph", etiqueta: "Centro gestor del CASPH", clave: "efectores", ruta: ["CASPH", "centros_gestores"], tipo: "lista",
    defecto: ["4900"], ayuda: "Al importar el z_compras2 entra todo lo imputado a este centro gestor, aunque el renglón tenga otro centro." },
  { id: "par-org-hbi", etiqueta: "Organización de compras propia del HBI", clave: "efectores", ruta: ["HBI", "org_compras"], tipo: "lista",
    defecto: ["1900"], ayuda: "Las OC de otra organización de compras se marcan como centralizadas." },
  { id: "par-org-casph", etiqueta: "Organización de compras propia del CASPH", clave: "efectores", ruta: ["CASPH", "org_compras"], tipo: "lista",
    defecto: ["1300"], ayuda: "Las OC de otra organización de compras se marcan como centralizadas." },
  { id: "par-centros-hbi", etiqueta: "Centros SAP del HBI (solo reportes sin la columna Centro gestor)", clave: "efectores", ruta: ["HBI", "centros"], tipo: "lista", ayuda: "Números separados por coma." },
  { id: "par-centros-casph", etiqueta: "Centros SAP del CASPH (solo reportes sin la columna Centro gestor)", clave: "efectores", ruta: ["CASPH", "centros"], tipo: "lista", ayuda: "Números separados por coma." },
  { id: "par-partidas", etiqueta: "Partidas excluidas", clave: "partidas_excluidas", ruta: [], tipo: "lista", ayuda: "Las OC con estas partidas no se importan." },
  { id: "par-excl-sap", etiqueta: "Proveedores excluidos (SAP)", clave: "exclusiones", ruta: ["sap"], tipo: "lista" },
  { id: "par-excl-oc", etiqueta: "OC excluidas", clave: "exclusiones", ruta: ["oc"], tipo: "lista" },
  { id: "par-gracia", etiqueta: "Días de gracia", clave: "dias_gracia", ruta: [], tipo: "entero", ayuda: "Días después del fin del período antes de marcarlo atrasado." },
  { id: "par-aviso-oc", etiqueta: "Aviso de OC por vencer (días)", clave: "dias_aviso_vencimiento_oc", ruta: [], tipo: "entero" },
  { id: "par-umbral", etiqueta: "Umbral de renglón por agotarse (%)", clave: "umbral_por_agotarse_pct", ruta: [], tipo: "entero" },
  { id: "par-limite-sap", etiqueta: "Límite del Texto SAP (caracteres)", clave: "limite_texto_sap", ruta: [], tipo: "entero" },
  { id: "par-email", etiqueta: "Email de la carátula", clave: "email_caratula", ruta: [], tipo: "texto" },
  { id: "par-car-codigo", etiqueta: "Caratulación: código de trámite", clave: "caratulacion", ruta: ["codigo_tramite"], tipo: "texto" },
  { id: "par-car-mail", etiqueta: "Caratulación: mail", clave: "caratulacion", ruta: ["mail"], tipo: "texto" },
  { id: "par-car-numero", etiqueta: "Caratulación: n°", clave: "caratulacion", ruta: ["numero"], tipo: "texto" },
  { id: "par-car-oficina", etiqueta: "Caratulación: oficina", clave: "caratulacion", ruta: ["oficina"], tipo: "texto" },
  { id: "par-email-eventual", etiqueta: "Email de la carátula (pago eventual)", clave: "pago_eventual", ruta: ["email_caratula"], tipo: "texto" },
];

function leerRuta(valor, ruta) {
  return ruta.reduce((actual, parte) => (actual && typeof actual === "object" ? actual[parte] : undefined), valor);
}

function escribirRuta(valor, ruta, nuevo) {
  if (!ruta.length) return nuevo;
  const copia = JSON.parse(JSON.stringify(valor ?? {}));
  let actual = copia;
  for (const parte of ruta.slice(0, -1)) {
    if (!actual[parte] || typeof actual[parte] !== "object") actual[parte] = {};
    actual = actual[parte];
  }
  actual[ruta[ruta.length - 1]] = nuevo;
  return copia;
}

function valorParaCampo(campo, valor) {
  if (campo.tipo === "lista") return (valor === undefined && campo.defecto ? campo.defecto : valor || []).join(", ");
  return valor === undefined || valor === null ? "" : String(valor);
}

function valorDelCampo(campo) {
  const texto = document.getElementById(campo.id).value.trim();
  if (campo.tipo === "lista") return { valor: texto.split(",").map((v) => v.trim()).filter((v) => v) };
  if (campo.tipo === "entero") {
    if (!/^\d+$/.test(texto)) return { error: campo.etiqueta + ": escribí un número entero." };
    return { valor: Number(texto) };
  }
  return { valor: texto };
}

const confEstado = { parametros: null, versiones: null };

async function cargarConfiguracion() {
  const contenedor = document.getElementById("configuracion-contenido");
  estado.recargar = cargarConfiguracion;
  cargando(contenedor);
  const [local, datos, base] = [await api("GET", "/api/config-local"), await api("GET", "/api/parametros"), await api("GET", "/api/base/estado")];
  if (!local || !datos || !base) { vaciar(contenedor); return; }
  confEstado.parametros = datos.parametros;
  confEstado.versiones = datos.versiones;
  const pc = el("form", { clase: "panel formulario", novalidate: true, onsubmit: guardarConfigLocal },
    el("h2", { clase: "titulo-chico", texto: "Esta PC" }),
    campoFormulario("conf-base", "Ubicación de la base de datos", entrada(local.guardada.base_datos || "", { autocomplete: "off" }),
      "Ruta del archivo .db (puede estar en una carpeta compartida). En uso ahora: " + local.en_uso.base_datos
      + ". El cambio rige al volver a abrir el programa."),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar ubicación" })),
    el("p", { clase: "texto-suave", texto: "Archivo de configuración: " + local.archivo }));
  const copia = el("div", { clase: "panel" },
    el("h2", { clase: "titulo-chico", texto: "Copias de seguridad y cierre" }),
    el("p", { id: "conf-ultimo-backup", texto: base.ultimo_backup ? "Última copia: " + base.ultimo_backup : "Todavía no hay copias de seguridad." }),
    el("p", { id: "conf-backup-diario", clase: "texto-suave", texto: base.ultimo_backup_diario
      ? "Copia diaria (una por día, en la carpeta «diarios»; se guardan 90 días): " + base.ultimo_backup_diario
      : "Todavía no hay copia diaria: se hace sola al abrir el programa y una vez por día mientras está abierto." }),
    el("div", { clase: "acciones" },
      el("button", { type: "button", texto: "Copia de seguridad ahora", onclick: copiaManual }),
      el("button", { type: "button", clase: "secundario", texto: "Cerrar programa", onclick: cerrarPrograma })));
  const parametros = el("form", { clase: "panel formulario", novalidate: true, onsubmit: guardarParametros },
    el("h2", { clase: "titulo-chico", texto: "Parámetros compartidos (valen para las dos PC)" }),
    ...CAMPOS_PARAMETROS.map((campo) => campoFormulario(campo.id, campo.etiqueta,
      entrada(valorParaCampo(campo, leerRuta(datos.parametros[campo.clave], campo.ruta)),
        Object.assign({ autocomplete: "off" }, campo.tipo === "entero" ? { inputmode: "numeric", clase: "entrada-corta" } : {})),
      campo.ayuda)),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Guardar parámetros" })));
  vaciar(contenedor, pc, copia, parametros);
}

async function guardarConfigLocal(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const resultado = await api("PUT", "/api/config-local", { base_datos: document.getElementById("conf-base").value.trim() });
  if (resultado) mostrarAviso(resultado.mensaje, "exito");
}

async function guardarParametros(evento) {
  evento.preventDefault();
  limpiarAvisos();
  const nuevos = {};
  for (const campo of CAMPOS_PARAMETROS) {
    const leido = valorDelCampo(campo);
    if (leido.error) { mostrarAviso(leido.error, "error"); document.getElementById(campo.id).focus(); return; }
    const base = campo.clave in nuevos ? nuevos[campo.clave] : confEstado.parametros[campo.clave];
    nuevos[campo.clave] = escribirRuta(base, campo.ruta, leido.valor);
  }
  const cambiados = Object.keys(nuevos).filter((clave) => JSON.stringify(nuevos[clave]) !== JSON.stringify(confEstado.parametros[clave]));
  if (!cambiados.length) { mostrarAviso("No hay cambios para guardar.", "aviso"); return; }
  for (const clave of cambiados) {
    if (!(clave in confEstado.versiones)) { mostrarAviso("El parámetro " + clave + " no existe en la base.", "error"); return; }
    const datos = await api("PUT", "/api/parametros", { clave, valor: nuevos[clave], version: confEstado.versiones[clave] });
    if (!datos) return;
    confEstado.parametros = datos.parametros;
    confEstado.versiones = datos.versiones;
  }
  mostrarAviso(cambiados.length === 1 ? "Parámetro guardado." : cambiados.length + " parámetros guardados.", "exito");
}

async function copiaManual() {
  limpiarAvisos();
  const datos = await api("POST", "/api/base/backup", {});
  if (!datos) return;
  document.getElementById("conf-ultimo-backup").textContent = "Última copia: " + datos.backup;
  mostrarAviso("Copia de seguridad creada: " + datos.backup + ".", "exito");
}

async function cerrarPrograma() {
  if (!window.confirm("¿Cerrar el programa? Para volver a usarlo, abrilo de nuevo con Iniciar.bat.")) return;
  limpiarAvisos();
  const datos = await api("POST", "/api/apagar", {});
  if (!datos) return;
  vaciar(document.querySelector("main"), el("section", {},
    el("h1", { texto: "Programa cerrado" }),
    el("p", { texto: "Ya podés cerrar esta pestaña. Para volver a usarlo, hacé doble clic en Iniciar.bat." })));
}

// --- Centralizadas: exportes ------------------------------------------------------

function pintarBotonesCentralizadas() {
  const periodo = document.getElementById("central-periodo").value.trim();
  vaciar(document.getElementById("centralizadas-botones"),
    botonesExporte("centralizadas", { periodo }, "de las centralizadas" + (periodo ? " de " + periodo : "")));
}

function iniciarCentralizadas() {
  const campo = document.getElementById("central-periodo");
  campo.addEventListener("input", pintarBotonesCentralizadas);
  document.getElementById("centralizadas-exporte").addEventListener("submit", (e) => e.preventDefault());
  pintarBotonesCentralizadas();
  document.getElementById("central-anio").value = String(new Date().getFullYear());
  document.getElementById("centralizadas-filtros").addEventListener("submit", (e) => { e.preventDefault(); cargarCentralizadas(); });
  document.getElementById("centralizadas-importar").addEventListener("submit", (e) => { e.preventDefault(); importarCentralizadas(false); });
  document.getElementById("central-importar-confirmar").addEventListener("click", () => importarCentralizadas(true));
}

// --- Centralizadas: tabla OC × período con CV, nota, fecha de envío y checklist ----------

const ESTADOS_TABLERO = {
  validado: ["V", "Validado", "exito"], cv_firmado: ["F", "CV firmado", "violeta"], en_curso: ["C", "En curso", "info"],
  pendiente: ["P", "Pendiente (en plazo)", "aviso"], atrasado: ["A", "Atrasado", "error"], sin_iniciar: ["·", "Todavía no empezó", "neutra"],
  fuera: ["-", "Fuera de la vigencia", "neutra"],
};

/** Tablero: una fila por OC centralizada y efector, un mes por columna con el estado de su validación. */
async function cargarCentralizadas() {
  const destino = document.getElementById("centralizadas-tabla");
  const anio = document.getElementById("central-anio").value.trim();
  if (!/^\d{4}$/.test(anio)) { mostrarAviso("El año debe tener 4 dígitos (por ejemplo 2026).", "error"); return; }
  cargando(destino);
  const parametros = new URLSearchParams({ anio });
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  const datos = await api("GET", "/api/centralizadas/tablero?" + parametros.toString());
  if (!datos) { vaciar(destino); return; }
  if (!datos.filas.length) {
    vaciar(destino, el("p", { clase: "texto-suave", texto: "No hay OC centralizadas con vigencia en " + datos.anio
      + ". Una OC es centralizada si lo dice su PDF («UOC: Nivel Central») o si la marcás al editarla." }));
    return;
  }
  const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  const filas = datos.filas.map((f) => el("tr", {},
    el("th", { scope: "row", clase: "izq" },
      el("button", { type: "button", clase: "enlace", texto: "OC " + f.oc, onclick: () => irAOC(f.oc) }),
      el("span", { clase: "texto-suave", texto: " · " + f.razon_social })),
    el("td", {}, el("span", { clase: "pastilla pastilla-neutra", texto: f.efector })),
    ...f.celdas.map((c) => {
      const [letra, texto, tono] = ESTADOS_TABLERO[c.estado] || ["?", c.estado, "neutra"];
      const etiqueta = texto + " — " + c.periodo + (c.numero_nota ? " · nota " + c.numero_nota : "");
      if (c.estado === "fuera") return el("td", { clase: "celda-tablero tono-" + tono, title: etiqueta, texto: letra });
      return el("td", { clase: "celda-tablero tono-" + tono },
        el("button", { type: "button", clase: "boton-celda", title: etiqueta, "aria-label": "OC " + f.oc + " " + f.efector + ", " + etiqueta
          + (c.expediente_id ? ": abrir la validación" : ": empezar la validación"),
          texto: letra, onclick: () => abrirValidacionCentralizada(f.oc, f.efector, c) }));
    })));
  vaciar(destino, el("div", { clase: "tabla-desplazable" }, el("table", { clase: "tablero-centralizadas" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col", clase: "izq", texto: "OC" }), el("th", { scope: "col", texto: "Efector" }),
        ...meses.map((m) => el("th", { scope: "col", texto: m })))),
      el("tbody", {}, ...filas))),
    el("ul", { clase: "leyenda-tablero", "aria-label": "Referencias" },
      ...Object.values(ESTADOS_TABLERO).map(([letra, texto, tono]) =>
        el("li", {}, el("span", { clase: "celda-tablero tono-" + tono, texto: letra }), " " + texto))),
    el("p", { clase: "nota-pie", texto: "Hacé clic en un mes para abrir su validación o empezarla." }));
}

/** Carga el seguimiento de centralizadas en Excel: primero «Ver qué se carga» y después «Cargar». */
async function importarCentralizadas(confirmar) {
  limpiarAvisos();
  const archivo = document.getElementById("central-archivo");
  if (!archivo.files[0]) { mostrarAviso("Elegí el seguimiento de centralizadas (.xlsx).", "error"); return; }
  const destino = document.getElementById("central-importar-resultado");
  cargando(destino);
  const datos = new FormData();
  datos.append("archivo", archivo.files[0], archivo.files[0].name);
  const informe = await api("POST", "/api/importar/centralizadas/" + (confirmar ? "confirmar" : "vista-previa"), datos);
  if (!informe) { vaciar(destino); return; }
  const r = informe.resumen;
  const partes = [el("div", { clase: "mensaje " + (confirmar ? "mensaje-exito" : "mensaje-aviso") }, el("p", { texto: confirmar
    ? "Listo: " + r.creados + " validaciones cargadas (" + r.ya_cargadas + " ya estaban)."
    : r.a_crear + " validaciones para cargar (" + r.validadas + " ya validadas, con nota), " + r.ya_cargadas + " ya cargadas"
      + (r.ocs_a_marcar ? "; " + r.ocs_a_marcar + " OC se marcan como centralizadas" : "") + "." }))];
  if (informe.sin_oc.length) {
    partes.push(el("div", { clase: "mensaje mensaje-aviso mensaje-columna" },
      el("p", { texto: informe.sin_oc.length + " OC del Excel no están en el gestor y sus filas no se cargan. Cargá su PDF "
        + "(Órdenes de compra → Nueva OC) y volvé a cargar el Excel: lo que ya esté no se repite." }),
      el("ul", {}, ...informe.sin_oc.map((x) => el("li", { texto: x.oc + " — " + x.razon_social + " (" + x.filas + " filas)" })))));
  }
  if (informe.avisos.length) {
    partes.push(el("details", {}, el("summary", { texto: informe.avisos.length + " avisos del Excel" }),
      el("ul", {}, ...informe.avisos.map((a) => el("li", { texto: a })))));
  }
  vaciar(destino, ...partes);
  if (confirmar) cargarCentralizadas();
}

function irAOC(numero) {
  ocEstado.ficha = { oc: { numero } };
  mostrarPantalla("pantalla-oc", true);
}

/** Abre la validación del mes; si no existe, la crea (OC + efector) y la abre en el paso de remitos. */
async function abrirValidacionCentralizada(oc, efector, celda) {
  limpiarAvisos();
  if (celda.expediente_id) {
    Object.assign(expEstado, { exp: { id: celda.expediente_id }, ficha: null, paso: 2, sugerido: null, fuera: [], sii: null });
    mostrarPantalla("pantalla-expedientes");
    return;
  }
  if (!window.confirm("¿Empezar la validación de " + celda.periodo + " de la OC " + oc + " para " + efector + "?")) return;
  await nuevaValidacionCentralizada(oc, efector, celda.periodo);
}

async function nuevaValidacionCentralizada(oc, efector, periodo) {
  const datos = { tipo: "CENTRALIZADA", oc, efector };
  if (periodo) datos.periodo = periodo;
  const exp = await api("POST", "/api/expedientes", datos);
  if (!exp) return;
  Object.assign(expEstado, { exp, ficha: null, paso: 2, sugerido: null, fuera: [], sii: null });
  mostrarPantalla("pantalla-expedientes");
  mostrarAviso("Validación " + exp.id + " de la OC " + oc + " (" + efector + ") creada. Cargá los remitos.", "exito");
}

// --- Ayuda: el instructivo tal cual ------------------------------------------------

async function cargarAyuda() {
  const destino = document.getElementById("ayuda-texto");
  const datos = await api("GET", "/api/ayuda");
  destino.textContent = datos ? datos.markdown : "No se pudo cargar el instructivo.";
}


// --- Tablas: vistas con columnas, orden, filtros y exportación a Excel ------------------------------------------
// El servidor manda todas las filas; el filtrado y el orden se hacen acá. Excel recibe exactamente lo que se ve.
// Las vistas (columnas, orden y filtros) se recuerdan en esta PC; también se pueden guardar con nombre.

const TABLAS_DISPONIBLES = [["expedientes", "Expedientes"], ["oc", "Órdenes de compra"], ["renglones", "Renglones de OC"],
  ["entregas", "Entregas"]];
const COLUMNAS_A_LA_IZQUIERDA = new Set(["razon_social", "objeto", "descripcion", "proveedores", "nombre", "observaciones",
  "motivo_pendiente", "motivo_anulacion", "remitos", "estados_expedientes"]);
const TABLA_FILAS_POR_TANDA = 300;
const tablaEstado = { nombre: "expedientes", datos: null, vista: null, mostrar: TABLA_FILAS_POR_TANDA };

function guardadoLocal(clave, valor) {
  try {
    if (valor === undefined) return JSON.parse(localStorage.getItem("gestor.tablas." + clave) || "null");
    localStorage.setItem("gestor.tablas." + clave, JSON.stringify(valor));
  } catch (error) { /* sin almacenamiento local: la vista no se recuerda */ }
  return null;
}

function vistaPredeterminada(columnas) {
  return { visibles: columnas.filter((c) => c.visible).map((c) => c.clave), orden: null, filtros: {}, buscar: "" };
}

function normalizarBusqueda(texto) {
  return String(texto ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

function fechaCorta(iso) {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? m[3] + "/" + m[2] + "/" + m[1] : String(iso);
}

function textoCelda(columna, valor) {
  if (valor === null || valor === undefined || valor === "") return "";
  if (columna.clave === "tipo" && tablaEstado.nombre === "expedientes") {
    return (TIPOS_EXPEDIENTE.find(([v]) => v === valor) || [null, valor])[1];
  }
  if (columna.clave === "tipo" && tablaEstado.nombre === "oc") return TIPOS_OC_TEXTO[valor] || valor;
  switch (columna.tipo) {
    case "moneda": return formatoPesos(valor);
    case "fecha": return fechaCorta(valor);
    case "fecha_hora": return formatoFechaHora(valor);
    case "si_no": return valor ? "Sí" : "No";
    case "cantidad": return String(valor).replace(".", ",");
    default: return String(valor);
  }
}

/** Valor comparable: números para montos y cantidades, ISO para fechas, texto normalizado para el resto. */
function valorOrden(columna, valor) {
  if (valor === null || valor === undefined || valor === "") return null;
  if (["moneda", "numero", "cantidad", "si_no"].includes(columna.tipo)) return Number(valor);
  if (columna.tipo === "fecha" || columna.tipo === "fecha_hora") return String(valor);
  return normalizarBusqueda(valor);
}

function valorDelFiltro(columna, texto) {
  const t = texto.trim();
  if (columna.tipo === "moneda") return pesosACentavos(t);
  if (["numero", "cantidad"].includes(columna.tipo)) return Number(t.replace(/\./g, "").replace(",", "."));
  if (columna.tipo === "fecha" || columna.tipo === "fecha_hora") {
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(t);
    return m ? m[3] + "-" + m[2].padStart(2, "0") + "-" + m[1].padStart(2, "0") : t;
  }
  return normalizarBusqueda(t);
}

/** Filtro de una columna: texto que contiene; en números y fechas también >, <, >=, <=, = y rangos "a..b". */
function cumpleFiltro(columna, valor, filtro) {
  if (filtro === undefined || filtro === null || String(filtro).trim() === "") return true;
  if (filtro === "(vacío)") return valor === null || valor === undefined || valor === "";
  if (columna.tipo === "si_no") return String(valor ? 1 : 0) === filtro;
  const comparable = ["moneda", "numero", "cantidad", "fecha", "fecha_hora"].includes(columna.tipo);
  if (comparable) {
    const actual = valorOrden(columna, valor);
    const rango = /^(.+?)\.\.(.+)$/.exec(filtro);
    const comparacion = /^(>=|<=|>|<|=)\s*(.+)$/.exec(filtro.trim());
    if (rango || comparacion) {
      if (actual === null) return false;
      const v = columna.tipo === "fecha_hora" ? String(actual).slice(0, 10) : actual;
      if (rango) {
        const desde = valorDelFiltro(columna, rango[1]);
        const hasta = valorDelFiltro(columna, rango[2]);
        return v >= desde && v <= hasta;
      }
      const objetivo = valorDelFiltro(columna, comparacion[2]);
      return { ">=": v >= objetivo, "<=": v <= objetivo, ">": v > objetivo, "<": v < objetivo, "=": v === objetivo }[comparacion[1]];
    }
  }
  if (filtro.startsWith("=")) return normalizarBusqueda(textoCelda(columna, valor)) === normalizarBusqueda(filtro.slice(1));
  return normalizarBusqueda(textoCelda(columna, valor)).includes(normalizarBusqueda(filtro));
}

function filasVisibles() {
  const { datos, vista } = tablaEstado;
  const columnas = new Map(datos.columnas.map((c) => [c.clave, c]));
  const visibles = vista.visibles.filter((c) => columnas.has(c)).map((c) => columnas.get(c));
  const buscar = normalizarBusqueda(vista.buscar);
  let filas = datos.filas.filter((fila) => {
    for (const [clave, filtro] of Object.entries(vista.filtros)) {
      if (columnas.has(clave) && !cumpleFiltro(columnas.get(clave), fila[clave], filtro)) return false;
    }
    if (buscar) return visibles.some((c) => normalizarBusqueda(textoCelda(c, fila[c.clave])).includes(buscar));
    return true;
  });
  if (vista.orden && columnas.has(vista.orden.clave)) {
    const columna = columnas.get(vista.orden.clave);
    const signo = vista.orden.asc ? 1 : -1;
    filas = filas.slice().sort((a, b) => {
      const x = valorOrden(columna, a[columna.clave]);
      const y = valorOrden(columna, b[columna.clave]);
      if (x === y) return 0;
      if (x === null) return 1;
      if (y === null) return -1;
      return (x < y ? -1 : 1) * signo;
    });
  }
  return { visibles, filas };
}

async function cargarTablas() {
  const raiz = document.getElementById("tablas-raiz");
  cargando(raiz);
  const parametros = new URLSearchParams();
  if (estado.efector !== "Ambos") parametros.set("efector", estado.efector);
  const datos = await api("GET", "/api/tablas/" + tablaEstado.nombre + "?" + parametros.toString());
  if (!datos) { vaciar(raiz); return; }
  tablaEstado.datos = datos;
  tablaEstado.vista = guardadoLocal("actual." + tablaEstado.nombre) || vistaPredeterminada(datos.columnas);
  tablaEstado.mostrar = TABLA_FILAS_POR_TANDA;
  pintarTablas();
}

function recordarVista() {
  guardadoLocal("actual." + tablaEstado.nombre, tablaEstado.vista);
}

function vistasGuardadas() {
  return guardadoLocal("guardadas." + tablaEstado.nombre) || {};
}

function pintarTablas() {
  const raiz = document.getElementById("tablas-raiz");
  const { datos, vista } = tablaEstado;
  const elegirTabla = selector(tablaEstado.nombre, TABLAS_DISPONIBLES);
  elegirTabla.id = "tablas-nombre";
  elegirTabla.addEventListener("change", () => { tablaEstado.nombre = elegirTabla.value; cargarTablas(); });

  const guardadas = vistasGuardadas();
  const elegirVista = selector("", [["", "— Elegir una vista guardada —"], ...Object.keys(guardadas).sort().map((n) => [n, n])]);
  elegirVista.id = "tablas-vista";
  elegirVista.addEventListener("change", () => {
    if (!elegirVista.value) return;
    tablaEstado.vista = JSON.parse(JSON.stringify(guardadas[elegirVista.value]));
    tablaEstado.mostrar = TABLA_FILAS_POR_TANDA;
    recordarVista();
    pintarTablas();
    mostrarAviso("Vista «" + elegirVista.value + "» aplicada.", "exito");
  });

  const buscar = entrada(vista.buscar, { type: "search", placeholder: "Buscar en las columnas visibles", autocomplete: "off" });
  buscar.id = "tablas-buscar";
  let espera = null;
  buscar.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(() => { vista.buscar = buscar.value; recordarVista(); pintarCuerpoTabla(); }, 200);
  });

  const controles = el("div", { clase: "panel formulario filtros" },
    el("div", { clase: "campo" }, el("label", { for: "tablas-nombre", texto: "Tabla" }), elegirTabla),
    el("div", { clase: "campo campo-buscar" }, el("label", { for: "tablas-buscar", texto: "Buscar" }), buscar),
    el("div", { clase: "campo" }, el("label", { for: "tablas-vista", texto: "Vistas guardadas" }), elegirVista),
    el("div", { clase: "acciones" },
      el("button", { type: "button", clase: "secundario", texto: "Guardar vista…", onclick: guardarVistaConNombre }),
      Object.keys(guardadas).length
        ? el("button", { type: "button", clase: "secundario", texto: "Borrar vista…", onclick: borrarVistaGuardada }) : null,
      el("button", { type: "button", clase: "secundario", texto: "Limpiar filtros", onclick: () => {
        vista.filtros = {}; vista.buscar = ""; recordarVista(); pintarTablas(); } }),
      el("button", { type: "button", clase: "secundario", texto: "Restablecer vista", onclick: () => {
        tablaEstado.vista = vistaPredeterminada(datos.columnas); recordarVista(); pintarTablas(); } }),
      el("button", { type: "button", texto: "Exportar a Excel", onclick: exportarTablaExcel }),
      el("button", { type: "button", clase: "secundario", id: "tablas-amplia",
        texto: document.body.classList.contains("vista-amplia") ? "Salir de la vista amplia" : "Ver más grande",
        "aria-pressed": document.body.classList.contains("vista-amplia") ? "true" : "false", onclick: alternarVistaAmplia })));

  const casillasColumnas = datos.columnas.map((c) => {
    const id = "tablas-col-" + c.clave;
    const control = el("input", { type: "checkbox", id });
    control.checked = vista.visibles.includes(c.clave);
    control.addEventListener("change", () => {
      const orden = datos.columnas.map((x) => x.clave);
      const visibles = new Set(vista.visibles);
      if (control.checked) visibles.add(c.clave); else visibles.delete(c.clave);
      vista.visibles = orden.filter((x) => visibles.has(x));
      recordarVista();
      pintarTablas();
      const otra = document.getElementById(id);
      if (otra) { otra.closest("details").open = true; otra.focus(); }
    });
    return el("div", { clase: "campo campo-casilla" }, control, el("label", { for: id, texto: c.titulo }));
  });
  const elegirColumnas = el("details", { clase: "panel elegir-columnas" },
    el("summary", { texto: "Columnas (" + vista.visibles.length + " de " + datos.columnas.length + ")" }),
    el("div", { clase: "grilla-columnas" }, ...casillasColumnas));

  vaciar(raiz, controles, elegirColumnas,
    el("p", { id: "tablas-resumen", clase: "texto-suave", role: "status" }),
    el("div", { id: "tablas-tabla" }));
  pintarCuerpoTabla(true);
}

function filtroDeColumna(columna, filas) {
  const { vista } = tablaEstado;
  const actual = vista.filtros[columna.clave] || "";
  const etiqueta = "Filtrar " + columna.titulo;
  const aplicar = (valor) => {
    if (valor) vista.filtros[columna.clave] = valor; else delete vista.filtros[columna.clave];
    tablaEstado.mostrar = TABLA_FILAS_POR_TANDA;
    recordarVista();
    pintarCuerpoTabla();
  };
  if (columna.tipo === "si_no") {
    const control = selector(actual, [["", "Todos"], ["1", "Sí"], ["0", "No"]]);
    control.setAttribute("aria-label", etiqueta);
    control.addEventListener("change", () => aplicar(control.value));
    return control;
  }
  if (columna.tipo === "texto") {
    const distintos = [...new Set(tablaEstado.datos.filas.map((f) => f[columna.clave] ?? ""))];
    if (distintos.length > 1 && distintos.length <= 15) {
      const opciones = [["", "Todos"], ...distintos.filter((v) => v !== "").sort().map((v) => ["=" + v, v])];
      if (distintos.includes("")) opciones.push(["(vacío)", "(vacío)"]);
      const control = selector(actual, opciones);
      control.setAttribute("aria-label", etiqueta);
      control.addEventListener("change", () => aplicar(control.value));
      return control;
    }
  }
  const pista = { moneda: "ej. >100000", numero: "ej. >10", cantidad: "ej. >0", fecha: "ej. >=01/08/2026", fecha_hora: "ej. >=01/08/2026" };
  const control = entrada(actual, { type: "search", "aria-label": etiqueta, placeholder: pista[columna.tipo] || "contiene…",
    autocomplete: "off" });
  let espera = null;
  control.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => aplicar(control.value.trim()), 300); });
  return control;
}

function celdaTabla(columna, fila) {
  const texto = textoCelda(columna, fila[columna.clave]);
  const numerica = ["moneda", "numero", "cantidad"].includes(columna.tipo);
  const clases = [numerica ? "numero" : "", COLUMNAS_A_LA_IZQUIERDA.has(columna.clave) ? "izq" : "",
    ["fecha", "fecha_hora", "moneda"].includes(columna.tipo) ? "sin-corte" : ""].filter(Boolean).join(" ");
  const td = el("td", { clase: clases || null });
  const nombre = tablaEstado.nombre;
  if (nombre === "expedientes" && columna.clave === "id") {
    td.append(el("button", { type: "button", clase: "secundario boton-celda", texto, "aria-label": "Abrir el expediente " + texto,
      onclick: () => irAExpediente(fila.id) }));
  } else if (columna.clave === "oc" && fila.oc || (nombre === "oc" && columna.clave === "numero")) {
    const numero = nombre === "oc" ? fila.numero : fila.oc;
    td.append(el("button", { type: "button", clase: "secundario boton-celda", texto, "aria-label": "Ver la OC " + numero,
      onclick: () => irAOC(numero) }));
  } else if (nombre === "expedientes" && columna.clave === "estado" && fila.estado) {
    td.append(pastillaEstado(fila.estado));
  } else if (nombre === "entregas" && columna.clave === "estado") {
    td.append(el("span", { clase: "pastilla pastilla-" + (texto.startsWith("Abierta") ? "aviso" : "exito"), texto }));
  } else {
    td.textContent = texto;
  }
  return td;
}

function irAExpediente(id) {
  expEstado.exp = null;
  mostrarPantalla("pantalla-expedientes", false);
  abrirExpediente(id, null);
}

function irAOC(numero) {
  ocEstado.ficha = null;
  mostrarPantalla("pantalla-oc", false);
  abrirFichaOC(numero);
}

function pintarCuerpoTabla(conEncabezado) {
  const contenedor = document.getElementById("tablas-tabla");
  if (!contenedor) return;
  const { vista } = tablaEstado;
  const { visibles, filas } = filasVisibles();
  const total = tablaEstado.datos.filas.length;
  document.getElementById("tablas-resumen").textContent = filas.length === total
    ? total + " filas"
    : filas.length + " de " + total + " filas (con filtros)";

  let tabla = contenedor.querySelector("table");
  if (conEncabezado || !tabla) {
    const encabezados = visibles.map((c) => {
      const orden = vista.orden && vista.orden.clave === c.clave ? (vista.orden.asc ? "ascending" : "descending") : null;
      const flecha = orden === "ascending" ? " ▲" : orden === "descending" ? " ▼" : "";
      return el("th", { scope: "col", "aria-sort": orden || "none", clase: COLUMNAS_A_LA_IZQUIERDA.has(c.clave) ? "izq" : null },
        el("button", { type: "button", clase: "orden-columna", texto: c.titulo + flecha,
          "aria-label": "Ordenar por " + c.titulo + (orden === "ascending" ? " (de mayor a menor)" : " (de menor a mayor)"),
          onclick: () => {
            const asc = !(vista.orden && vista.orden.clave === c.clave && vista.orden.asc);
            vista.orden = { clave: c.clave, asc };
            recordarVista();
            pintarCuerpoTabla(true);
          } }));
    });
    const filtros = visibles.map((c) => el("td", {}, filtroDeColumna(c)));
    tabla = el("table", { clase: "tabla-datos" },
      el("caption", { clase: "solo-lectores", texto: tablaEstado.datos.titulo }),
      el("thead", {}, el("tr", {}, ...encabezados), el("tr", { clase: "fila-filtros" }, ...filtros)),
      el("tbody"), el("tfoot"));
    vaciar(contenedor, el("div", { clase: "tabla-desplazable" }, tabla), el("div", { id: "tablas-mas" }));
  }
  const tbody = tabla.querySelector("tbody");
  vaciar(tbody, ...filas.slice(0, tablaEstado.mostrar).map((fila) => el("tr", {}, ...visibles.map((c) => celdaTabla(c, fila)))));
  if (!filas.length) {
    tbody.append(el("tr", {}, el("td", { colspan: String(Math.max(1, visibles.length)), texto: "No hay filas con estos filtros." })));
  }
  const conTotales = visibles.some((c) => c.tipo === "moneda");
  vaciar(tabla.querySelector("tfoot"), conTotales && filas.length
    ? el("tr", {}, ...visibles.map((c, i) => {
      if (c.tipo === "moneda") {
        const suma = filas.reduce((acc, f) => acc + (Number(f[c.clave]) || 0), 0);
        return el("td", { clase: "numero total", texto: formatoPesos(suma) });
      }
      return el("td", { texto: i === 0 ? "Total" : "" });
    }))
    : null);
  const mas = document.getElementById("tablas-mas");
  vaciar(mas, filas.length > tablaEstado.mostrar
    ? el("div", { clase: "acciones" },
      el("p", { clase: "texto-suave", texto: "Se muestran " + tablaEstado.mostrar + " de " + filas.length
        + " filas. Excel exporta todas las filas filtradas." }),
      el("button", { type: "button", clase: "secundario", texto: "Mostrar " + Math.min(TABLA_FILAS_POR_TANDA, filas.length - tablaEstado.mostrar) + " más",
        onclick: () => { tablaEstado.mostrar += TABLA_FILAS_POR_TANDA; pintarCuerpoTabla(); } }))
    : null);
}

/** Vista amplia: oculta el menú y el encabezado para que la tabla use toda la pantalla (Esc también sale). */
function alternarVistaAmplia() {
  const amplia = document.body.classList.toggle("vista-amplia");
  const boton = document.getElementById("tablas-amplia");
  if (boton) {
    boton.textContent = amplia ? "Salir de la vista amplia" : "Ver más grande";
    boton.setAttribute("aria-pressed", amplia ? "true" : "false");
    boton.focus();
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.body.classList.contains("vista-amplia") && !document.querySelector("dialog[open]")) alternarVistaAmplia();
});

function guardarVistaConNombre() {
  const nombre = (prompt("Nombre para esta vista (columnas, orden y filtros):") || "").trim();
  if (!nombre) return;
  const guardadas = vistasGuardadas();
  guardadas[nombre] = JSON.parse(JSON.stringify(tablaEstado.vista));
  guardadoLocal("guardadas." + tablaEstado.nombre, guardadas);
  pintarTablas();
  mostrarAviso("Vista «" + nombre + "» guardada en esta PC.", "exito");
}

function borrarVistaGuardada() {
  const elegida = document.getElementById("tablas-vista").value;
  const guardadas = vistasGuardadas();
  const nombre = elegida || (prompt("¿Qué vista borro? (" + Object.keys(guardadas).join(", ") + ")") || "").trim();
  if (!nombre || !(nombre in guardadas)) return;
  if (!confirm("¿Borrar la vista «" + nombre + "»?")) return;
  delete guardadas[nombre];
  guardadoLocal("guardadas." + tablaEstado.nombre, guardadas);
  pintarTablas();
  mostrarAviso("Vista «" + nombre + "» borrada.", "exito");
}

function describirFiltros() {
  const { datos, vista } = tablaEstado;
  const titulos = new Map(datos.columnas.map((c) => [c.clave, c.titulo]));
  const partes = Object.entries(vista.filtros).map(([clave, filtro]) => (titulos.get(clave) || clave) + " " + filtro);
  if (vista.buscar) partes.unshift("búsqueda «" + vista.buscar + "»");
  if (estado.efector !== "Ambos") partes.unshift(estado.efector);
  return partes.join("; ");
}

/** Descarga un .xlsx con las columnas visibles y TODAS las filas filtradas, en el orden de la pantalla.
 * Se envía con un formulario (no con fetch) para que el navegador descargue el archivo. */
function exportarTablaExcel() {
  const { visibles, filas } = filasVisibles();
  if (!visibles.length) { mostrarAviso("Elegí al menos una columna para exportar.", "aviso"); return; }
  const pedido = {
    nombre: tablaEstado.nombre, titulo: tablaEstado.datos.titulo, filtros: describirFiltros(),
    columnas: visibles.map((c) => ({ titulo: c.titulo, tipo: c.tipo })),
    filas: filas.map((fila) => visibles.map((c) => fila[c.clave] ?? null)),
  };
  const formulario = el("form", { method: "post", action: "/api/tablas/exportar.xlsx", hidden: true },
    el("input", { type: "hidden", name: "datos", value: JSON.stringify(pedido) }));
  document.body.append(formulario);
  formulario.submit();
  formulario.remove();
  mostrarAviso("Exportando " + filas.length + " filas a Excel…", "exito");
}

// --- Arranque ---------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  iniciarEfector();
  iniciarImportar();
  iniciarExpedientes();
  iniciarCalendario();
  iniciarCentralizadas();
  iniciarNavegacion();
});

// --- Servicios CASPH: autorizaciones de AySA y Edenor (dentro de Expedientes) ---------------

function pintarServiciosCasph() {
  const contenedor = document.getElementById("expedientes-servicios-casph");
  if (!contenedor) return;
  if (estado.efector === "HBI") { vaciar(contenedor); return; }
  if (contenedor.querySelector("details")) return; // conserva lo que se estaba cargando
  const hoy = new Date();
  const anterior = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
  const resultado = el("div", { id: "servicios-casph-resultado", "aria-live": "polite" });
  const formulario = el("form", { clase: "formulario filtros", novalidate: true, onsubmit: (e) => generarServicioCasph(e, resultado) },
    campoFormulario("casph-empresa", "Empresa", selector("AYSA", [["AYSA", "AySA (cloaca)"], ["EDENOR", "Edenor (energía eléctrica)"]])),
    campoFormulario("casph-factura", "N° de factura", entrada("", { autocomplete: "off", placeholder: "0001-00012345" })),
    campoFormulario("casph-importe", "Importe $", entrada("", { inputmode: "decimal", clase: "entrada-corta" })),
    campoFormulario("casph-mes", "Mes", selector(MESES[anterior.getMonth()], MESES.map((m) => [m, m]))),
    campoFormulario("casph-anio", "Año", entrada(String(anterior.getFullYear()), { inputmode: "numeric", clase: "entrada-corta" })),
    campoFormulario("casph-expediente", "Expediente (EX)", entrada("", { autocomplete: "off" })),
    el("div", { clase: "acciones" }, el("button", { type: "submit", texto: "Generar autorización" })));
  vaciar(contenedor, el("details", { clase: "panel" },
    el("summary", { texto: "Servicios CASPH (AySA / Edenor)" }),
    formulario, resultado));
}

async function generarServicioCasph(evento, destino) {
  evento.preventDefault();
  limpiarAvisos();
  const centavos = pesosACentavos(document.getElementById("casph-importe").value);
  if (centavos === null || Number.isNaN(centavos)) { mostrarAviso("El importe no es válido.", "error"); return; }
  const anio = Number(document.getElementById("casph-anio").value.trim());
  if (!Number.isInteger(anio)) { mostrarAviso("El año no es válido.", "error"); return; }
  const empresa = document.getElementById("casph-empresa").value;
  const datos = await api("POST", "/api/textos/servicio-casph", {
    empresa,
    factura: document.getElementById("casph-factura").value.trim(),
    centavos,
    mes: document.getElementById("casph-mes").value,
    anio,
    expediente: document.getElementById("casph-expediente").value.trim(),
  });
  if (!datos) { vaciar(destino); return; }
  const nombre = empresa === "AYSA" ? "AySA" : "Edenor";
  vaciar(destino, bloqueTexto("Autorización de pago " + nombre, datos.parrafos.join("\n"), true));
}
