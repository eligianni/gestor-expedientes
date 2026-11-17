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

// --- Arranque ---------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  iniciarEfector();
  iniciarImportar();
  iniciarNavegacion();
});
