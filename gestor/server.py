"""Servidor HTTP local del gestor: ThreadingHTTPServer en 127.0.0.1 y despacho por la lista RUTAS."""
import email.parser
import email.policy
import getpass
import http.server
import io
import json
import os
import re
import unicodedata
import socket
import sqlite3
import threading
import urllib.request
from urllib.parse import parse_qs, quote, urlsplit

from gestor import (APP_ID, __version__, comprobantes, config, controles, db, docx_gen, exportes, factura_pdf, importar, migracion, negocio,
                    oc_pdf, pdf_texto, tablas, textos, xlsx, xlsx_escritor)

WEB = config.RAIZ / "web"

# Únicos archivos que se sirven fuera de /api/ (nada fuera de web/).
ESTATICOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    # Fuente Inter (OFL, ver web/fuentes/LICENSE-Inter.txt) guardada en la app: se ve igual sin internet.
    "/fuentes/inter.woff2": ("fuentes/inter.woff2", "font/woff2"),
}

_TAMANO_DESCARTE = 64 * 1024


class SinPuertoLibre(Exception):
    """Ningún puerto del rango está libre ni tiene al gestor corriendo."""


class ErrorHTTP(Exception):
    """Error con estado HTTP, código y mensaje para la usuaria."""

    def __init__(self, estado, codigo, mensaje):
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje


def validacion(mensaje):
    return ErrorHTTP(400, "validacion", mensaje)


def huella_codigo():
    """(archivo, fecha, tamaño) del código Python: si cambia en el disco (un `git pull`), el programa abierto quedó viejo."""
    archivos = sorted((config.RAIZ / "gestor").glob("*.py")) + [config.RAIZ / "app.py"]
    huella = []
    for archivo in archivos:
        try:
            dato = archivo.stat()
        except OSError:
            continue
        huella.append((archivo.name, dato.st_mtime_ns, dato.st_size))
    return tuple(huella)


def responder(h, estado, cuerpo, tipo):
    h.send_response(estado)
    h.send_header("Content-Type", tipo)
    h.send_header("Content-Length", str(len(cuerpo)))
    h.send_header("Cache-Control", "no-store")
    if getattr(h.server, "huella", None) is not None and huella_codigo() != h.server.huella:
        h.send_header("X-Gestor-Desactualizado", "1")
    h.end_headers()
    h.wfile.write(cuerpo)


def responder_json(h, estado, dic):
    responder(h, estado, json.dumps(dic, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TIPO_CSV = "text/csv; charset=utf-8"


class Archivo:
    """Respuesta binaria de una ruta (descarga) en lugar del sobre JSON."""

    def __init__(self, contenido, tipo, nombre, en_linea=False):
        self.contenido, self.tipo, self.nombre, self.en_linea = contenido, tipo, nombre, en_linea


def responder_archivo(h, archivo):
    h.send_response(200)
    h.send_header("Content-Type", archivo.tipo)
    h.send_header("Content-Length", str(len(archivo.contenido)))
    disposicion = "inline" if archivo.en_linea else "attachment"
    # Nombre sin tildes de respaldo (filename=) y el nombre exacto (filename*=) para los navegadores que lo entienden.
    respaldo = unicodedata.normalize("NFKD", archivo.nombre).encode("ascii", "ignore").decode("ascii").replace('"', "")
    h.send_header("Content-Disposition", '%s; filename="%s"; filename*=UTF-8\'\'%s'
                  % (disposicion, respaldo, quote(archivo.nombre, safe="")))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(archivo.contenido)


def _error(codigo, mensaje):
    return {"ok": False, "error": {"codigo": codigo, "mensaje": mensaje}}


def _ok(datos):
    return {"ok": True, "datos": datos}


# --- Cuerpos ---------------------------------------------------------------

def leer_json(h, cuerpo):
    if not cuerpo:
        return {}
    try:
        datos = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise validacion("El cuerpo del pedido no es JSON válido.") from None
    if not isinstance(datos, dict):
        raise validacion("El cuerpo del pedido debe ser un objeto JSON.")
    return datos


def leer_multipart(h, cuerpo):
    """multipart/form-data → (campos de texto, {nombre: (nombre_de_archivo, bytes)})."""
    tipo = h.headers.get("Content-Type") or ""
    if not tipo.lower().startswith("multipart/form-data"):
        raise validacion("Se esperaba un formulario con un archivo (multipart/form-data).")
    crudo = b"Content-Type: " + tipo.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + cuerpo
    mensaje = email.parser.BytesParser(policy=email.policy.default).parsebytes(crudo)
    if not mensaje.is_multipart():
        raise validacion("El formulario enviado no se pudo leer.")
    campos, archivos = {}, {}
    for parte in mensaje.iter_parts():
        nombre = parte.get_param("name", header="content-disposition")
        if not nombre:
            continue
        contenido = parte.get_payload(decode=True) or b""
        nombre_archivo = parte.get_filename()
        if nombre_archivo is not None:
            archivos[nombre] = (nombre_archivo, contenido)
        else:
            campos[nombre] = contenido.decode("utf-8")
    return campos, archivos


# --- Rutas -----------------------------------------------------------------

def salud(h, m, cuerpo):
    return 200, {
        "app": APP_ID,
        "version": __version__,
        "db": h.server.estado_db,
        "usuario": getpass.getuser(),
    }


def base_estado(h, m, cuerpo):
    ultimo = db.ultimo_backup(config.ruta(h.server.cfg, "carpeta_backups"))
    return 200, _ok({
        "integridad": "ok" if h.server.integridad else "falla",
        "ultimo_backup": ultimo.name if ultimo is not None else None,
        "ultimo_backup_diario": _nombre(db.ultimo_backup_diario(config.ruta(h.server.cfg, "carpeta_backups"))),
    })


def _nombre(ruta):
    return ruta.name if ruta is not None else None


def base_restaurar(h, m, cuerpo):
    cfg = h.server.cfg
    ultimo = db.ultimo_backup(config.ruta(cfg, "carpeta_backups"))
    if ultimo is None:
        return 422, _error("negocio", "No hay copias de seguridad para restaurar.")
    ruta_base = config.ruta(cfg, "base_datos")
    db.restaurar_backup(ultimo, ruta_base)
    con = h.conexion()
    h.server.integridad = db.verificar_integridad(con)
    h.server.estado_db = "ok"
    return 200, _ok({"restaurado": ultimo.name})


def base_backup(h, m, cuerpo):
    cfg = h.server.cfg
    destino = db.hacer_backup(config.ruta(cfg, "base_datos"), config.ruta(cfg, "carpeta_backups"),
                              int(cfg.get("backups_a_conservar", 30)))
    return 200, _ok({"backup": destino.name})


CLAVES_CONFIG_LOCAL = ("base_datos", "carpeta_backups", "backups_a_conservar", "carpeta_salidas", "puerto_preferido",
                       "puerto_maximo")


def config_local_leer(h, m, cuerpo):
    guardada = config.cargar_config()
    en_uso = h.server.cfg
    return 200, _ok({
        "archivo": guardada["_ruta"],
        "guardada": {clave: guardada.get(clave) for clave in CLAVES_CONFIG_LOCAL},
        "en_uso": {"base_datos": str(config.ruta(en_uso, "base_datos")),
                   "carpeta_backups": str(config.ruta(en_uso, "carpeta_backups"))},
    })


def config_local_guardar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    base = datos.get("base_datos")
    if not isinstance(base, str) or not base.strip():
        raise validacion("Indicá la ubicación de la base de datos (por ejemplo una carpeta compartida).")
    base = base.strip()
    if not base.lower().endswith(".db"):
        raise validacion("La base de datos tiene que ser un archivo .db.")
    cfg = config.cargar_config()
    cfg["base_datos"] = base
    config.guardar_config(cfg)
    return 200, _ok({"base_datos": base, "mensaje": "Guardado. La nueva ubicación rige al volver a abrir el programa."})


def apagar(h, m, cuerpo):
    servidor = h.server

    def detener():
        servidor.shutdown()  # desde otro thread: el que atiende este pedido no puede llamarlo
        servidor.server_close()

    threading.Thread(target=detener, daemon=True).start()
    return 200, _ok({"apagando": True})


def pendientes(h, m, cuerpo):
    return 200, _ok(negocio.pendientes(h.conexion(), hoy=_consulta(h).get("hoy") or None))


def _datos_parametros(con):
    return {"parametros": db.leer_parametros(con), "versiones": db.versiones_parametros(con)}


def parametros_leer(h, m, cuerpo):
    return 200, _ok(_datos_parametros(h.conexion()))


def parametros_guardar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    clave = datos.get("clave")
    if not isinstance(clave, str) or not clave:
        raise validacion("Falta la clave del parámetro.")
    if "valor" not in datos:
        raise validacion("Falta el valor del parámetro.")
    version = datos.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise validacion("Falta la versión del parámetro.")
    con = h.conexion()
    if clave not in db.versiones_parametros(con):
        raise ErrorHTTP(404, "no_encontrado", "No existe el parámetro %s." % clave)
    db.guardar_parametro(con, clave, datos["valor"], version)
    return 200, _ok(_datos_parametros(con))


def _pedido_importacion(h, cuerpo):
    """Valida el formulario de importación y devuelve (efector, nombre_archivo, contenido, parametros)."""
    campos, archivos = leer_multipart(h, cuerpo)
    efector = (campos.get("efector") or "").strip()
    if efector not in ("HBI", "CASPH"):
        raise validacion("Elegí el efector (HBI o CASPH) antes de importar.")
    if "archivo" not in archivos or not archivos["archivo"][1]:
        raise validacion("Elegí el archivo z_compras2 (.xlsx) a importar.")
    nombre, contenido = archivos["archivo"]
    parametros = db.leer_parametros(h.conexion())
    try:
        encabezados, _ = xlsx.leer_tabla(io.BytesIO(contenido))
    except xlsx.XlsxError:
        encabezados = []  # el importador da el error del archivo
    falta = importar.falta_configuracion(efector, parametros, encabezados)
    if falta:
        raise ErrorHTTP(422, "negocio", falta)
    return efector, nombre, contenido, parametros


def importar_vista_previa(h, m, cuerpo):
    efector, _, contenido, parametros = _pedido_importacion(h, cuerpo)
    informe = importar.analizar(io.BytesIO(contenido), efector, parametros, con=h.conexion())
    return 200, _ok(informe)


def importar_confirmar(h, m, cuerpo):
    efector, nombre, contenido, parametros = _pedido_importacion(h, cuerpo)
    informe = importar.importar(h.conexion(), io.BytesIO(contenido), efector, parametros, archivo=nombre)
    return 200, _ok(informe)


def _pedido_migracion(h, cuerpo):
    _, archivos = leer_multipart(h, cuerpo)
    faltan = [nombre for clave, nombre in (("numeracion", "la NUMERACIÓN"), ("remitos", "el seguimiento de remitos"))
              if not (archivos.get(clave) and archivos[clave][1])]
    if faltan:
        raise validacion("Elegí %s (.xlsx)." % " y ".join(faltan))
    try:
        hojas_num, hojas_rem = migracion.leer_archivos(archivos["numeracion"][1], archivos["remitos"][1])
    except migracion.ErrorMigracion as error:
        raise validacion(str(error)) from None
    return hojas_num, hojas_rem, "%s + %s" % (archivos["numeracion"][0], archivos["remitos"][0])


def _pedido_centralizadas(h, cuerpo):
    _, archivos = leer_multipart(h, cuerpo)
    if not (archivos.get("archivo") and archivos["archivo"][1]):
        raise validacion("Elegí el seguimiento de centralizadas (.xlsx).")
    nombre, contenido = archivos["archivo"]
    try:
        return xlsx.leer_hojas(io.BytesIO(contenido)), nombre
    except xlsx.XlsxError as error:
        raise validacion(str(error)) from None


def centralizadas_vista_previa(h, m, cuerpo):
    hojas, _ = _pedido_centralizadas(h, cuerpo)
    try:
        return 200, _ok(migracion.planificar_centralizadas(h.conexion(), hojas))
    except migracion.ErrorMigracion as error:
        raise validacion(str(error)) from None


def centralizadas_confirmar(h, m, cuerpo):
    hojas, nombre = _pedido_centralizadas(h, cuerpo)
    try:
        return 200, _ok(migracion.migrar_centralizadas(h.conexion(), hojas, nombre))
    except migracion.ErrorMigracion as error:
        raise validacion(str(error)) from None


def migracion_vista_previa(h, m, cuerpo):
    hojas_num, hojas_rem, _ = _pedido_migracion(h, cuerpo)
    try:
        return 200, _ok(migracion.planificar(h.conexion(), hojas_num, hojas_rem))
    except migracion.ErrorMigracion as error:
        raise validacion(str(error)) from None


def migracion_confirmar(h, m, cuerpo):
    hojas_num, hojas_rem, nombres = _pedido_migracion(h, cuerpo)
    try:
        return 200, _ok(migracion.migrar(h.conexion(), hojas_num, hojas_rem, nombres))
    except migracion.ErrorMigracion as error:
        raise validacion(str(error)) from None


def importaciones(h, m, cuerpo):
    return 200, _ok(db.listar_importaciones(h.conexion()))


def _consulta(h):
    return {clave: valores[-1] for clave, valores in parse_qs(urlsplit(h.path).query).items()}


def oc_listar(h, m, cuerpo):
    q = _consulta(h)
    efector = q.get("efector") or None
    return 200, _ok(negocio.listar_oc(
        h.conexion(), efector=efector, texto=q.get("q", ""), incluir_excluidas=q.get("excluidas") == "1",
    ))


def oc_crear(h, m, cuerpo):
    return 200, _ok(negocio.crear_oc_manual(h.conexion(), leer_json(h, cuerpo)))


def oc_ficha(h, m, cuerpo):
    return 200, _ok(negocio.ficha_oc(h.conexion(), m.group("numero")))


def oc_consumo(h, m, cuerpo):
    return 200, _ok(negocio.consumo_oc(h.conexion(), m.group("numero"), _consulta(h).get("efector")))


def oc_editar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.actualizar_oc(h.conexion(), m.group("numero"), datos.get("version"), datos.get("cambios")))


def oc_pdf_leer(h, m, cuerpo):
    """PDF digital de la OC (o su texto pegado) → comparación con la base, sin guardar nada."""
    campos, archivos = leer_multipart(h, cuerpo)
    nombre = ""
    if archivos.get("archivo") and archivos["archivo"][1]:
        nombre, contenido = archivos["archivo"]
        try:
            texto = pdf_texto.texto_de_pdf(contenido)
        except pdf_texto.PdfError as error:
            raise ErrorHTTP(422, "negocio", str(error)) from None
    else:
        texto = (campos.get("texto") or "").strip()
        if not texto:
            raise validacion("Elegí el PDF de la OC o pegá su texto.")
    try:
        leido = oc_pdf.leer_oc(texto)
    except oc_pdf.OcIlegible as error:
        raise ErrorHTTP(422, "negocio", str(error)) from None
    comparacion = negocio.comparar_oc_pdf(h.conexion(), m.group("numero"), leido)
    comparacion["archivo"] = nombre
    return 200, _ok(comparacion)


def _leer_pdf_de_pedido(h, cuerpo):
    """(nombre del archivo, datos de la OC leídos) de un formulario con el PDF (`archivo`) o su texto (`texto`)."""
    campos, archivos = leer_multipart(h, cuerpo)
    nombre = ""
    if archivos.get("archivo") and archivos["archivo"][1]:
        nombre, contenido = archivos["archivo"]
        try:
            texto = pdf_texto.texto_de_pdf(contenido)
        except pdf_texto.PdfError as error:
            raise ErrorHTTP(422, "negocio", str(error)) from None
    else:
        texto = (campos.get("texto") or "").strip()
        if not texto:
            raise validacion("Elegí el PDF de la OC o pegá su texto.")
    try:
        return nombre, oc_pdf.leer_oc(texto)
    except oc_pdf.OcIlegible as error:
        raise ErrorHTTP(422, "negocio", str(error)) from None


def oc_nueva_leer(h, m, cuerpo):
    """PDF de una OC nueva → datos para confirmar en la ventana «Nueva OC» (no guarda nada)."""
    nombre, leido = _leer_pdf_de_pedido(h, cuerpo)
    if not leido.get("numero"):
        raise ErrorHTTP(422, "negocio", "No se encontró el número de la OC en el PDF.")
    existe = db.leer_fila(h.conexion(), "oc", {"numero": leido["numero"]}) is not None
    return 200, _ok({"leido": leido, "existe": existe, "archivo": nombre})


def oc_nueva_crear(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.crear_oc_desde_pdf(h.conexion(), datos.get("oc"), datos.get("archivo") or "", datos.get("leido"),
                                               datos.get("subrenglones")))


def renglon_por_efector(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_por_efector(h.conexion(), m.group("numero"), m.group("pos"), datos.get("version"),
                                                datos.get("por_efector")))


def renglon_subrenglones(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_subrenglones(h.conexion(), m.group("numero"), m.group("pos"), datos.get("version"),
                                                 datos.get("subrenglones")))


def oc_pdf_aplicar(h, m, cuerpo):
    return 200, _ok(negocio.aplicar_oc_pdf(h.conexion(), m.group("numero"), leer_json(h, cuerpo)))


def tabla_ver(h, m, cuerpo):
    try:
        return 200, _ok(tablas.tabla(h.conexion(), m.group("nombre"), _efector_filtro(_consulta(h).get("efector"))))
    except tablas.TablaDesconocida as error:
        raise ErrorHTTP(404, "no_encontrado", str(error)) from None


def tabla_exportar(h, m, cuerpo):
    """Formulario (campo `datos` con JSON) → .xlsx de lo que se ve en la tabla. Se envía con un <form>, no con fetch,
    para que el navegador descargue el archivo."""
    try:
        campos = parse_qs(cuerpo.decode("utf-8"), keep_blank_values=True)
        pedido = json.loads((campos.get("datos") or [""])[0])
        contenido, nombre = tablas.exportar_xlsx(pedido)
    except (UnicodeDecodeError, ValueError) as error:
        raise validacion("No se pudo exportar la tabla: %s" % error) from None
    return 200, Archivo(contenido, xlsx_escritor.TIPO_XLSX, nombre)


def renglon_agregar(h, m, cuerpo):
    return 200, _ok(negocio.agregar_renglon(h.conexion(), m.group("numero"), leer_json(h, cuerpo)))


def inicio_alertas(h, m, cuerpo):
    q = _consulta(h)
    return 200, _ok(negocio.alertas(h.conexion(), hoy=q.get("hoy") or None, integridad_ok=bool(h.server.integridad)))


def calendario(h, m, cuerpo):
    q = _consulta(h)
    efector = q.get("efector") or None
    return 200, _ok(negocio.calendario(
        h.conexion(), q.get("anio") or "", efector=None if efector == "Ambos" else efector,
        tipo=q.get("tipo") or None, sap=q.get("sap") or None, hoy=q.get("hoy") or None,
    ))


def expedientes_listar(h, m, cuerpo):
    q = _consulta(h)
    filtros = {clave: q.get(clave) or None for clave in ("estado", "tipo", "periodo", "sap", "entrega", "efector")}
    if filtros["efector"] == "Ambos":
        filtros["efector"] = None
    return 200, _ok(negocio.listar_expedientes(h.conexion(), **filtros))


def expediente_crear(h, m, cuerpo):
    return 200, _ok(negocio.crear_expediente(h.conexion(), leer_json(h, cuerpo)))


def expediente_obtener(h, m, cuerpo):
    return 200, _ok(negocio.obtener_expediente(h.conexion(), m.group("id")))


def expediente_editar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.actualizar_expediente(h.conexion(), m.group("id"), datos.get("version"), datos.get("cambios")))


def expediente_controles(h, m, cuerpo):
    return 200, _ok(controles.controlar(h.conexion(), m.group("id")))


def expediente_nota(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    con = h.conexion()
    expediente = negocio.guardar_nota(
        con, m.group("id"), datos.get("version"), datos.get("codigo"), datos.get("referencia"), datos.get("texto"),
    )
    respuesta = controles.controlar(con, expediente["id"])
    respuesta["expediente"] = expediente
    return 200, _ok(respuesta)


def expediente_textos(h, m, cuerpo):
    return 200, _ok(negocio.textos_del_expediente(h.conexion(), m.group("id")))


def expediente_cv_docx(h, m, cuerpo):
    cv = negocio.datos_cv(h.conexion(), m.group("id"))
    contenido = docx_gen.generar_cv(config.RAIZ / cv["plantilla"], cv["datos"])
    return 200, Archivo(contenido, TIPO_DOCX, cv["archivo"])


def expediente_cv_verificar(h, m, cuerpo):
    """¿Se puede armar el certificado de validación? Devuelve el nombre del archivo o el dato que falta (422)."""
    return 200, _ok({"archivo": negocio.datos_cv(h.conexion(), m.group("id"))["archivo"]})


def expediente_autorizacion_docx(h, m, cuerpo):
    autorizacion = negocio.datos_autorizacion(h.conexion(), m.group("id"))
    contenido = docx_gen.generar_autorizacion_docx(autorizacion["referencia"], autorizacion["cuerpo"])
    return 200, Archivo(contenido, TIPO_DOCX, autorizacion["archivo"])


def _efector_filtro(valor):
    return None if valor in (None, "", "Ambos") else valor


def entregas_listar(h, m, cuerpo):
    q = _consulta(h)
    con = h.conexion()
    efector = _efector_filtro(q.get("efector"))
    return 200, _ok({"entregas": negocio.listar_entregas(con, efector),
                     "firmados_sin_entrega": negocio.firmados_sin_entrega(con, efector)})


def entrega_crear(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.crear_entrega(h.conexion(), datos.get("efector"), datos.get("nombre") or ""))


def entrega_obtener(h, m, cuerpo):
    return 200, _ok(negocio.obtener_entrega(h.conexion(), m.group("id")))


def entrega_asignar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.asignar_a_entrega(h.conexion(), m.group("id"), datos.get("version"), datos.get("expedientes")))


def entrega_quitar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.quitar_de_entrega(h.conexion(), m.group("id"), datos.get("version"), datos.get("expedientes")))


def entrega_enviar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.enviar_entrega(h.conexion(), m.group("id"), datos.get("version"), datos.get("fecha")))


def entrega_numeracion_csv(h, m, cuerpo):
    con = h.conexion()
    entrega = negocio.obtener_entrega(con, m.group("id"))
    contenido = exportes.a_csv(exportes.ENCABEZADOS_NUMERACION, exportes.filas_numeracion(con, entrega["id"]))
    return 200, Archivo(contenido, TIPO_CSV, exportes.nombre_csv_numeracion(entrega))


def exporte(h, m, cuerpo):
    try:
        contenido, tipo, nombre, en_linea = exportes.generar(h.conexion(), m.group("nombre"), m.group("formato"), _consulta(h))
    except exportes.ExporteDesconocido as error:
        raise ErrorHTTP(404, "no_encontrado", str(error)) from None
    return 200, Archivo(contenido, tipo, nombre, en_linea)


def centralizadas(h, m, cuerpo):
    q = _consulta(h)
    return 200, _ok(negocio.centralizadas_por_periodo(h.conexion(), q.get("anio") or "", _efector_filtro(q.get("efector"))))


def centralizadas_tablero(h, m, cuerpo):
    q = _consulta(h)
    return 200, _ok(negocio.tablero_centralizadas(h.conexion(), q.get("anio") or "", _efector_filtro(q.get("efector"))))


def expediente_nota_central(h, m, cuerpo):
    return 200, _ok(negocio.nota_central_del_expediente(h.conexion(), m.group("id")))


def expediente_centralizada(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_centralizada(h.conexion(), m.group("id"), datos.get("version"), datos.get("centralizada")))


def correctivos_informe_mensual(h, m, cuerpo):
    return 200, _ok(negocio.informe_mensual_correctivos(h.conexion(), _consulta(h).get("mes") or ""))


def ayuda(h, m, cuerpo):
    """El instructivo (docs/INSTRUCTIVO.md) tal cual, para la pantalla Ayuda."""
    try:
        markdown = (config.RAIZ / "docs" / "INSTRUCTIVO.md").read_bytes().decode("utf-8")
    except OSError:
        raise ErrorHTTP(404, "no_encontrado", "No se encontró el instructivo (docs/INSTRUCTIVO.md).") from None
    return 200, _ok({"markdown": markdown})


def texto_servicio_casph(h, m, cuerpo):
    return 200, _ok(negocio.texto_servicio_casph(leer_json(h, cuerpo)))


def expediente_eventual(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_eventual(h.conexion(), m.group("id"), datos.get("version"), datos.get("eventual")))


def expediente_correctivo(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_correctivo(h.conexion(), m.group("id"), datos.get("version"), datos.get("correctivo")))


def expediente_estado(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.cambiar_estado(
        h.conexion(), m.group("id"), datos.get("version"), datos.get("estado"),
        datos.get("motivo", ""), datos.get("fecha_seguimiento"),
    ))


def expediente_reanudar(h, m, cuerpo):
    return 200, _ok(negocio.reanudar_expediente(h.conexion(), m.group("id"), leer_json(h, cuerpo).get("version")))


def expediente_gde(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_gde(h.conexion(), m.group("id"), datos.get("version"), datos.get("gde")))


def expediente_consumo_manual(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.guardar_consumo_manual(h.conexion(), m.group("id"), datos.get("version"), datos.get("cantidades")))


def comprobantes_analizar(h, m, cuerpo):
    texto = leer_json(h, cuerpo).get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise validacion("Pegá el texto de la factura cargada en el SII.")
    return 200, _ok(comprobantes.analizar_texto_sii(texto))


def _texto_pdf_de_pedido(h, cuerpo, que):
    """(nombre, texto) del PDF subido en `archivo` (o del texto pegado en `texto`)."""
    campos, archivos = leer_multipart(h, cuerpo)
    if archivos.get("archivo") and archivos["archivo"][1]:
        nombre, contenido = archivos["archivo"]
        try:
            return nombre, pdf_texto.texto_de_pdf(contenido)
        except pdf_texto.PdfError as error:
            raise ErrorHTTP(422, "negocio", str(error)) from None
    texto = (campos.get("texto") or "").strip()
    if not texto:
        raise validacion("Elegí el PDF %s." % que)
    return "", texto


def factura_pdf_leer(h, m, cuerpo):
    """PDF de la factura → datos para el paso 3 (no guarda nada)."""
    nombre, texto = _texto_pdf_de_pedido(h, cuerpo, "de la factura")
    destino = db.leer_parametros(h.conexion()).get("destinatario_factura") or {}
    leido = factura_pdf.leer_factura(texto, destino.get("nombre") or "INSSJP", destino.get("domicilio") or "PERU 169")
    if not any(leido.get(c) for c in ("numero", "cae", "centavos")):
        raise ErrorHTTP(422, "negocio", "No se encontraron datos de una factura en el PDF (¿es un escaneo?).")
    return 200, _ok({"leido": leido, "archivo": nombre})


def sii_pdf_leer(h, m, cuerpo):
    """PDF de la carga en el SII → datos del SII (no guarda nada)."""
    nombre, texto = _texto_pdf_de_pedido(h, cuerpo, "de la carga en el SII")
    sii = comprobantes.analizar_texto_sii(texto)
    if not sii.get("cae") and not sii.get("nro_comprobante"):
        raise ErrorHTTP(422, "negocio", "El PDF no parece la carga de la factura en el SII (no tiene CAE ni N° de comprobante).")
    return 200, _ok({"sii": sii, "archivo": nombre})


def comprobantes_revisar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.revisar_comprobantes(h.conexion(), m.group("id"), datos.get("factura"), datos.get("sii"),
                                                 datos.get("cuit_emisor")))


def remitos_pegar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.pegar_remitos(
        h.conexion(), m.group("id"), datos.get("version"), datos.get("texto"), datos.get("es_equipo_comodato", False),
        datos.get("remitos"),
    ))


def expediente_anular(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.anular_expediente(h.conexion(), m.group("id"), datos.get("version"), datos.get("motivo")))


def renglon_editar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.actualizar_renglon(
        h.conexion(), m.group("numero"), int(m.group("pos")), datos.get("version"), datos.get("cambios"),
    ))


RUTAS = [
    ("GET", re.compile(r"/api/salud"), salud),
    ("GET", re.compile(r"/api/base/estado"), base_estado),
    ("POST", re.compile(r"/api/base/restaurar"), base_restaurar),
    ("POST", re.compile(r"/api/base/backup"), base_backup),
    ("GET", re.compile(r"/api/config-local"), config_local_leer),
    ("PUT", re.compile(r"/api/config-local"), config_local_guardar),
    ("POST", re.compile(r"/api/apagar"), apagar),
    ("GET", re.compile(r"/api/pendientes"), pendientes),
    ("GET", re.compile(r"/api/ayuda"), ayuda),
    ("POST", re.compile(r"/api/textos/servicio-casph"), texto_servicio_casph),
    ("GET", re.compile(r"/api/parametros"), parametros_leer),
    ("PUT", re.compile(r"/api/parametros"), parametros_guardar),
    ("POST", re.compile(r"/api/importar/vista-previa"), importar_vista_previa),
    ("POST", re.compile(r"/api/importar/confirmar"), importar_confirmar),
    ("GET", re.compile(r"/api/importaciones"), importaciones),
    ("POST", re.compile(r"/api/importar/seguimiento/vista-previa"), migracion_vista_previa),
    ("POST", re.compile(r"/api/importar/seguimiento/confirmar"), migracion_confirmar),
    ("POST", re.compile(r"/api/importar/centralizadas/vista-previa"), centralizadas_vista_previa),
    ("POST", re.compile(r"/api/importar/centralizadas/confirmar"), centralizadas_confirmar),
    ("GET", re.compile(r"/api/oc"), oc_listar),
    ("POST", re.compile(r"/api/oc"), oc_crear),
    ("GET", re.compile(r"/api/oc/(?P<numero>\d+)"), oc_ficha),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)"), oc_editar),
    ("GET", re.compile(r"/api/oc/(?P<numero>\d+)/consumo"), oc_consumo),
    ("POST", re.compile(r"/api/oc/(?P<numero>\d+)/renglones"), renglon_agregar),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)/renglones/(?P<pos>\d+)/subrenglones"), renglon_subrenglones),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)/renglones/(?P<pos>\d+)/efectores"), renglon_por_efector),
    ("POST", re.compile(r"/api/oc/pdf"), oc_nueva_leer),
    ("POST", re.compile(r"/api/oc/desde-pdf"), oc_nueva_crear),
    ("POST", re.compile(r"/api/oc/(?P<numero>\d+)/pdf"), oc_pdf_leer),
    ("GET", re.compile(r"/api/tablas/(?P<nombre>[a-z]+)"), tabla_ver),
    ("POST", re.compile(r"/api/tablas/exportar\.xlsx"), tabla_exportar),
    ("POST", re.compile(r"/api/oc/(?P<numero>\d+)/pdf/aplicar"), oc_pdf_aplicar),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)/renglones/(?P<pos>\d+)"), renglon_editar),
    ("GET", re.compile(r"/api/inicio/alertas"), inicio_alertas),
    ("GET", re.compile(r"/api/calendario"), calendario),
    ("GET", re.compile(r"/api/expedientes"), expedientes_listar),
    ("POST", re.compile(r"/api/expedientes"), expediente_crear),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)"), expediente_obtener),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)"), expediente_editar),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/anular"), expediente_anular),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/remitos/pegar"), remitos_pegar),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/comprobantes/revisar"), comprobantes_revisar),
    ("POST", re.compile(r"/api/comprobantes/factura-pdf"), factura_pdf_leer),
    ("POST", re.compile(r"/api/comprobantes/sii-pdf"), sii_pdf_leer),
    ("POST", re.compile(r"/api/comprobantes/analizar"), comprobantes_analizar),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/controles"), expediente_controles),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/notas"), expediente_nota),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/textos"), expediente_textos),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/estado"), expediente_estado),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/reanudar"), expediente_reanudar),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/gde"), expediente_gde),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/consumo-manual"), expediente_consumo_manual),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/centralizada"), expediente_centralizada),
    ("GET", re.compile(r"/api/centralizadas/tablero"), centralizadas_tablero),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/nota-central"), expediente_nota_central),
    ("GET", re.compile(r"/api/centralizadas"), centralizadas),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/correctivo"), expediente_correctivo),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/eventual"), expediente_eventual),
    ("GET", re.compile(r"/api/correctivos/informe-mensual"), correctivos_informe_mensual),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/cv\.docx"), expediente_cv_docx),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/cv/verificar"), expediente_cv_verificar),
    ("GET", re.compile(r"/api/exportes/(?P<nombre>[a-z0-9-]+)\.(?P<formato>[a-z]+)"), exporte),
    ("GET", re.compile(r"/api/entregas"), entregas_listar),
    ("POST", re.compile(r"/api/entregas"), entrega_crear),
    ("GET", re.compile(r"/api/entregas/(?P<id>\d+)"), entrega_obtener),
    ("POST", re.compile(r"/api/entregas/(?P<id>\d+)/asignar"), entrega_asignar),
    ("POST", re.compile(r"/api/entregas/(?P<id>\d+)/quitar"), entrega_quitar),
    ("POST", re.compile(r"/api/entregas/(?P<id>\d+)/enviar"), entrega_enviar),
    ("GET", re.compile(r"/api/entregas/(?P<id>\d+)/numeracion\.csv"), entrega_numeracion_csv),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/autorizacion\.docx"), expediente_autorizacion_docx),
]


# --- Manejador -------------------------------------------------------------

class Manejador(http.server.BaseHTTPRequestHandler):

    def log_message(self, formato, *args):
        # Con pythonw no hay consola: no se escribe nada.
        pass

    def _largo(self):
        try:
            return max(0, int(self.headers.get("Content-Length") or 0))
        except ValueError:
            raise validacion("Content-Length inválido.") from None

    def _descartar_cuerpo(self, largo):
        """Consume el cuerpo sin guardarlo, para que el cliente reciba la respuesta de error."""
        restante = largo
        while restante > 0:
            leido = self.rfile.read(min(_TAMANO_DESCARTE, restante))
            if not leido:
                break
            restante -= len(leido)

    def _leer_cuerpo(self):
        largo = self._largo()
        maximo_mb = self.server.cfg.get("tamano_maximo_subida_mb", 25)
        if largo > maximo_mb * 1024 * 1024:
            self._descartar_cuerpo(largo)
            raise ErrorHTTP(413, "demasiado_grande", "El archivo supera el máximo de %s MB." % ("%g" % maximo_mb))
        return self.rfile.read(largo) if largo > 0 else b""

    def conexion(self):
        """Conexión propia de este pedido; se abre al primer uso y se cierra al responder."""
        if self._con is None:
            self._con = db.conectar(config.ruta(self.server.cfg, "base_datos"))
        return self._con

    def _estatico(self, ruta):
        nombre, tipo = ESTATICOS[ruta]
        try:
            contenido = (WEB / nombre).read_bytes()
        except OSError:
            responder_json(self, 404, _error("no_encontrado", "Ruta no encontrada: %s" % ruta))
            return
        responder(self, 200, contenido, tipo)

    def _despachar(self, metodo):
        ruta = urlsplit(self.path).path
        if metodo == "GET" and ruta in ESTATICOS:
            self._estatico(ruta)
            return
        self._con = None
        try:
            cuerpo = self._leer_cuerpo() if metodo in ("POST", "PUT") else b""
            for metodo_ruta, patron, funcion in RUTAS:
                if metodo_ruta != metodo:
                    continue
                m = patron.fullmatch(ruta)
                if m is not None:
                    estado, dic = funcion(self, m, cuerpo)
                    break
            else:
                estado, dic = 404, _error("no_encontrado", "Ruta no encontrada: %s" % ruta)
        except ErrorHTTP as error:
            estado, dic = error.estado, _error(error.codigo, error.mensaje)
        except db.ConflictoVersion as error:
            estado, dic = 409, _error("conflicto_version", str(error))
        except (importar.ErrorImportacion, xlsx.XlsxError, negocio.ErrorValidacion) as error:
            estado, dic = 400, _error("validacion", str(error))
        except negocio.NoEncontrado as error:
            estado, dic = 404, _error("no_encontrado", str(error))
        except (negocio.ErrorNegocio, textos.TextoIncompleto, docx_gen.ErrorPlantilla) as error:
            estado, dic = 422, _error("negocio", str(error))
        except Exception as error:  # noqa: BLE001 — cualquier falla imprevista es un 500
            estado, dic = 500, _error("interno", "Error interno: %s" % type(error).__name__)
        finally:
            if self._con is not None:
                self._con.close()
                self._con = None
        if isinstance(dic, Archivo):
            responder_archivo(self, dic)
        else:
            responder_json(self, estado, dic)

    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def do_PUT(self):
        self._despachar("PUT")


class _Servidor(http.server.ThreadingHTTPServer):
    # En Windows SO_REUSEADDR permite "robar" un puerto ocupado por otro programa: no se usa ahí.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def crear_servidor(puerto, cfg):
    """Crea el servidor enlazado a 127.0.0.1:puerto (0 = el sistema elige) con la config en httpd.cfg."""
    httpd = _Servidor(("127.0.0.1", puerto), Manejador)
    httpd.daemon_threads = True
    httpd.cfg = cfg
    httpd.estado_db = "sin_base"
    httpd.integridad = False
    httpd.huella = huella_codigo()
    ruta_base = config.ruta(cfg, "base_datos")
    try:
        db.inicializar(ruta_base, cfg["parametros_iniciales"])
        con = db.conectar(ruta_base)
        try:
            httpd.integridad = db.verificar_integridad(con)
        finally:
            con.close()
        httpd.estado_db = "ok"
    except (sqlite3.Error, OSError, db.BaseNoDisponible):
        httpd.estado_db = "sin_base"
    return httpd


def consultar_salud(puerto, timeout=0.5):
    """GET /api/salud en 127.0.0.1:puerto; devuelve el dict o None ante cualquier error."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/salud" % puerto, timeout=timeout) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        return datos if isinstance(datos, dict) else None
    except Exception:  # noqa: BLE001
        return None


def elegir_puerto(preferido, maximo):
    """Primer puerto del rango que ya tenga al gestor (True) o que esté libre (False)."""
    for puerto in range(preferido, maximo + 1):
        salud_actual = consultar_salud(puerto)
        if salud_actual is not None and salud_actual.get("app") == APP_ID:
            return puerto, True
        prueba = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            prueba.bind(("127.0.0.1", puerto))
        except OSError:
            continue
        finally:
            prueba.close()
        return puerto, False
    raise SinPuertoLibre("No hay ningún puerto libre entre %d y %d." % (preferido, maximo))
