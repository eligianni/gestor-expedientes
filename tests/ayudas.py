"""Ayudas compartidas por todos los tests del gestor de expedientes.

Archivo emitido por el blueprint (seccion 19.6): no lo reescribe ningun paso.
Solo biblioteca estandar. Crea una configuracion y una base TEMPORALES y apunta
la variable de entorno GESTOR_CONFIG a ellas, para que ningun test toque
datos/expedientes.db del proyecto.

Contrato que deben cumplir los pasos (gestor/config.py y gestor/server.py):
  - gestor.config.cargar_config() lee el archivo que indica GESTOR_CONFIG.
  - gestor.server.crear_servidor(puerto, cfg) devuelve un ThreadingHTTPServer
    ya enlazado a 127.0.0.1 (puerto 0 = el sistema elige uno libre).
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
XLSX_HBI_2026 = FIXTURES / "xlsx" / "z_compras2_hbi_2026.xlsx"
XLSX_POR_PARTIDA = FIXTURES / "xlsx" / "z_compras2_por_partida.xlsx"
EXPEDIENTES = FIXTURES / "expedientes"
MODELOS = FIXTURES / "modelos"


def config_del_proyecto():
    """Devuelve el contenido de config.json de la raiz del proyecto."""
    with open(RAIZ / "config.json", encoding="utf-8") as archivo:
        return json.load(archivo)


def texto_fixture(carpeta, patron):
    """Lee (UTF-8) el unico .txt de tests/fixtures/expedientes/<carpeta> que coincide con patron."""
    encontrados = sorted((EXPEDIENTES / carpeta).glob(patron))
    if len(encontrados) != 1:
        raise FileNotFoundError("se esperaba 1 archivo para %s/%s y hay %d" % (carpeta, patron, len(encontrados)))
    return encontrados[0].read_text(encoding="utf-8")


def normalizar_espacios(texto):
    """Colapsa espacios, tabulaciones y saltos de linea en un solo espacio."""
    return " ".join(texto.split())


class EntornoTemporal:
    """Directorio temporal con su propio config.json; GESTOR_CONFIG apunta a el."""

    def __init__(self, **cambios):
        self.dir = Path(tempfile.mkdtemp(prefix="gestor-test-"))
        cfg = config_del_proyecto()
        cfg["base_datos"] = str(self.dir / "datos" / "expedientes.db")
        cfg["carpeta_backups"] = str(self.dir / "datos" / "backups")
        cfg["carpeta_salidas"] = str(self.dir / "salidas")
        cfg.update(cambios)
        self.config = cfg
        self.ruta_config = self.dir / "config.json"
        with open(self.ruta_config, "w", encoding="utf-8") as archivo:
            json.dump(cfg, archivo, ensure_ascii=False, indent=2)
        self._anterior = os.environ.get("GESTOR_CONFIG")
        os.environ["GESTOR_CONFIG"] = str(self.ruta_config)

    @property
    def ruta_base(self):
        return Path(self.config["base_datos"])

    def cerrar(self):
        if self._anterior is None:
            os.environ.pop("GESTOR_CONFIG", None)
        else:
            os.environ["GESTOR_CONFIG"] = self._anterior
        shutil.rmtree(self.dir, ignore_errors=True)


class Respuesta:
    """Respuesta HTTP de prueba: estado, cabeceras y cuerpo crudo."""

    def __init__(self, estado, cabeceras, cuerpo):
        self.estado = estado
        self.cabeceras = cabeceras
        self.cuerpo = cuerpo

    def json(self):
        return json.loads(self.cuerpo.decode("utf-8"))

    def texto(self):
        return self.cuerpo.decode("utf-8")


class ServidorDePrueba:
    """Levanta gestor.server en un thread, en un puerto libre de 127.0.0.1."""

    def __init__(self):
        from gestor import config, server

        self.httpd = server.crear_servidor(0, config.cargar_config())
        self.puerto = self.httpd.server_address[1]
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()

    def url(self, ruta):
        return "http://127.0.0.1:%d%s" % (self.puerto, ruta)

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        pedido = urllib.request.Request(self.url(ruta), data=cuerpo, method=metodo, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resp:
                return Respuesta(resp.status, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as error:
            return Respuesta(error.code, dict(error.headers), error.read())

    def get(self, ruta):
        return self.pedir("GET", ruta)

    def enviar_json(self, metodo, ruta, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        return self.pedir(metodo, ruta, cuerpo, {"Content-Type": "application/json; charset=utf-8"})

    def post(self, ruta, datos):
        return self.enviar_json("POST", ruta, datos)

    def put(self, ruta, datos):
        return self.enviar_json("PUT", ruta, datos)

    def subir(self, ruta, ruta_archivo, campos=None):
        """POST multipart/form-data con un campo 'archivo' y campos de texto extra."""
        limite = "----gestor" + uuid.uuid4().hex
        partes = []
        for nombre, valor in (campos or {}).items():
            partes.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (limite, nombre, valor)).encode("utf-8"))
        contenido = Path(ruta_archivo).read_bytes()
        cabecera = "--%s\r\nContent-Disposition: form-data; name=\"archivo\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % (limite, Path(ruta_archivo).name)
        partes.append(cabecera.encode("utf-8") + contenido + b"\r\n")
        partes.append(("--%s--\r\n" % limite).encode("utf-8"))
        return self.pedir("POST", ruta, b"".join(partes), {"Content-Type": "multipart/form-data; boundary=%s" % limite})

    def cerrar(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CasoConEntorno(unittest.TestCase):
    """TestCase con config y base temporales (sin servidor)."""

    def setUp(self):
        self.entorno = EntornoTemporal()
        self.addCleanup(self.entorno.cerrar)


class CasoConServidor(CasoConEntorno):
    """TestCase con config y base temporales y el servidor corriendo en un thread."""

    def setUp(self):
        super().setUp()
        self.servidor = ServidorDePrueba()
        self.addCleanup(self.servidor.cerrar)
