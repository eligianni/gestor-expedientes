"""Servidor HTTP local del gestor: ThreadingHTTPServer en 127.0.0.1 y despacho por la lista RUTAS."""
import getpass
import http.server
import json
import os
import re
import socket
import urllib.request
from urllib.parse import urlsplit

from gestor import APP_ID, __version__, config


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

def salud(h, m, cuerpo):
    cfg = h.server.cfg
    hay_base = config.ruta(cfg, "base_datos").is_file()
    return 200, {
        "app": APP_ID,
        "version": __version__,
        "db": "ok" if hay_base else "sin_base",
        "usuario": getpass.getuser(),
    }


RUTAS = [
    ("GET", re.compile(r"/api/salud"), salud),
]


# --- Manejador -------------------------------------------------------------

class Manejador(http.server.BaseHTTPRequestHandler):

    def log_message(self, formato, *args):
        # Con pythonw no hay consola: no se escribe nada.
        pass

    def _leer_cuerpo(self):
        largo = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(largo) if largo > 0 else b""

    def _despachar(self, metodo):
        ruta = urlsplit(self.path).path
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
        except Exception as error:  # noqa: BLE001 — cualquier falla imprevista es un 500
            estado, dic = 500, _error("interno", "Error interno: %s" % type(error).__name__)
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
