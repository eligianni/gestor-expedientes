"""Servidor HTTP local del gestor: ThreadingHTTPServer en 127.0.0.1 y despacho por la lista RUTAS."""
import getpass
import http.server
import json
import os
import re
import socket
import sqlite3
import urllib.request
from urllib.parse import urlsplit

from gestor import APP_ID, __version__, config, db


class SinPuertoLibre(Exception):
    """Ningún puerto del rango está libre ni tiene al gestor corriendo."""


def responder_json(h, estado, dic):
    cuerpo = json.dumps(dic, ensure_ascii=False).encode("utf-8")
    h.send_response(estado)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(cuerpo)))
    h.end_headers()
    h.wfile.write(cuerpo)


def _error(codigo, mensaje):
    return {"ok": False, "error": {"codigo": codigo, "mensaje": mensaje}}


# --- Rutas -----------------------------------------------------------------

def _ok(datos):
    return {"ok": True, "datos": datos}


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


RUTAS = [
    ("GET", re.compile(r"/api/salud"), salud),
    ("GET", re.compile(r"/api/base/estado"), base_estado),
    ("POST", re.compile(r"/api/base/restaurar"), base_restaurar),
]


# --- Manejador -------------------------------------------------------------

class Manejador(http.server.BaseHTTPRequestHandler):

    def log_message(self, formato, *args):
        # Con pythonw no hay consola: no se escribe nada.
        pass

    def _leer_cuerpo(self):
        largo = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(largo) if largo > 0 else b""

    def conexion(self):
        """Conexión propia de este pedido; se abre al primer uso y se cierra al responder."""
        if self._con is None:
            self._con = db.conectar(config.ruta(self.server.cfg, "base_datos"))
        return self._con

    def _despachar(self, metodo):
        ruta = urlsplit(self.path).path
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
        except db.ConflictoVersion as error:
            estado, dic = 409, _error("conflicto_version", str(error))
        except Exception as error:  # noqa: BLE001 — cualquier falla imprevista es un 500
            estado, dic = 500, _error("interno", "Error interno: %s" % type(error).__name__)
        finally:
            if self._con is not None:
                self._con.close()
                self._con = None
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
