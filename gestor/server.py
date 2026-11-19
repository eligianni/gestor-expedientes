"""Servidor HTTP local del gestor: ThreadingHTTPServer en 127.0.0.1 y despacho por la lista RUTAS."""
import email.parser
import email.policy
import getpass
import http.server
import io
import json
import os
import re
import socket
import sqlite3
import urllib.request
from urllib.parse import parse_qs, quote, urlsplit

from gestor import APP_ID, __version__, comprobantes, config, controles, db, docx_gen, importar, negocio, textos, xlsx

WEB = config.RAIZ / "web"

# Únicos archivos que se sirven fuera de /api/ (nada fuera de web/).
ESTATICOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
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


def responder(h, estado, cuerpo, tipo):
    h.send_response(estado)
    h.send_header("Content-Type", tipo)
    h.send_header("Content-Length", str(len(cuerpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(cuerpo)


def responder_json(h, estado, dic):
    responder(h, estado, json.dumps(dic, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Archivo:
    """Respuesta binaria de una ruta (descarga) en lugar del sobre JSON."""

    def __init__(self, contenido, tipo, nombre):
        self.contenido, self.tipo, self.nombre = contenido, tipo, nombre


def responder_archivo(h, archivo):
    h.send_response(200)
    h.send_header("Content-Type", archivo.tipo)
    h.send_header("Content-Length", str(len(archivo.contenido)))
    h.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(archivo.nombre, safe=""))
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
    })


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
    centros = ((parametros.get("efectores") or {}).get(efector) or {}).get("centros") or []
    if not centros:
        raise ErrorHTTP(422, "negocio", "Configurá los centros SAP de %s antes de importar." % efector)
    return efector, nombre, contenido, parametros


def importar_vista_previa(h, m, cuerpo):
    efector, _, contenido, parametros = _pedido_importacion(h, cuerpo)
    informe = importar.analizar(io.BytesIO(contenido), efector, parametros, con=h.conexion())
    return 200, _ok(informe)


def importar_confirmar(h, m, cuerpo):
    efector, nombre, contenido, parametros = _pedido_importacion(h, cuerpo)
    informe = importar.importar(h.conexion(), io.BytesIO(contenido), efector, parametros, archivo=nombre)
    return 200, _ok(informe)


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
    return 200, _ok(negocio.consumo_oc(h.conexion(), m.group("numero")))


def oc_editar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.actualizar_oc(h.conexion(), m.group("numero"), datos.get("version"), datos.get("cambios")))


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


def expediente_autorizacion_docx(h, m, cuerpo):
    autorizacion = negocio.datos_autorizacion(h.conexion(), m.group("id"))
    contenido = docx_gen.generar_autorizacion_docx(autorizacion["referencia"], autorizacion["cuerpo"])
    return 200, Archivo(contenido, TIPO_DOCX, autorizacion["archivo"])


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


def comprobantes_analizar(h, m, cuerpo):
    texto = leer_json(h, cuerpo).get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise validacion("Pegá el texto de la factura cargada en el SII.")
    return 200, _ok(comprobantes.analizar_texto_sii(texto))


def remitos_pegar(h, m, cuerpo):
    datos = leer_json(h, cuerpo)
    return 200, _ok(negocio.pegar_remitos(
        h.conexion(), m.group("id"), datos.get("version"), datos.get("texto"), datos.get("es_equipo_comodato", False),
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
    ("GET", re.compile(r"/api/parametros"), parametros_leer),
    ("PUT", re.compile(r"/api/parametros"), parametros_guardar),
    ("POST", re.compile(r"/api/importar/vista-previa"), importar_vista_previa),
    ("POST", re.compile(r"/api/importar/confirmar"), importar_confirmar),
    ("GET", re.compile(r"/api/importaciones"), importaciones),
    ("GET", re.compile(r"/api/oc"), oc_listar),
    ("POST", re.compile(r"/api/oc"), oc_crear),
    ("GET", re.compile(r"/api/oc/(?P<numero>\d+)"), oc_ficha),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)"), oc_editar),
    ("GET", re.compile(r"/api/oc/(?P<numero>\d+)/consumo"), oc_consumo),
    ("POST", re.compile(r"/api/oc/(?P<numero>\d+)/renglones"), renglon_agregar),
    ("PUT", re.compile(r"/api/oc/(?P<numero>\d+)/renglones/(?P<pos>\d+)"), renglon_editar),
    ("GET", re.compile(r"/api/inicio/alertas"), inicio_alertas),
    ("GET", re.compile(r"/api/calendario"), calendario),
    ("GET", re.compile(r"/api/expedientes"), expedientes_listar),
    ("POST", re.compile(r"/api/expedientes"), expediente_crear),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)"), expediente_obtener),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)"), expediente_editar),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/anular"), expediente_anular),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/remitos/pegar"), remitos_pegar),
    ("POST", re.compile(r"/api/comprobantes/analizar"), comprobantes_analizar),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/controles"), expediente_controles),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/notas"), expediente_nota),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/textos"), expediente_textos),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/estado"), expediente_estado),
    ("POST", re.compile(r"/api/expedientes/(?P<id>\d+)/reanudar"), expediente_reanudar),
    ("PUT", re.compile(r"/api/expedientes/(?P<id>\d+)/gde"), expediente_gde),
    ("GET", re.compile(r"/api/expedientes/(?P<id>\d+)/cv\.docx"), expediente_cv_docx),
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
