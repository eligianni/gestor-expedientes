"""Paso 1: servidor HTTP, /api/salud, elección de puerto y python app.py --check."""
import getpass
import json
import socket
import subprocess
import sys
import unittest

from gestor import server
from tests import ayudas


class PruebaServidor(ayudas.CasoConServidor):

    def test_salud_devuelve_json_del_gestor(self):
        resp = self.servidor.get("/api/salud")
        self.assertEqual(resp.estado, 200)
        self.assertTrue(resp.cabeceras["Content-Type"].startswith("application/json"))
        datos = resp.json()
        self.assertEqual(list(datos.keys()), ["app", "version", "db", "usuario"])
        self.assertEqual(datos["app"], "gestor-expedientes")
        self.assertEqual(datos["version"], "0.1.0")
        self.assertIn(datos["db"], ("ok", "sin_base"))
        self.assertEqual(datos["usuario"], getpass.getuser())

    def test_servidor_escucha_solo_en_localhost(self):
        self.assertEqual(self.servidor.httpd.server_address[0], "127.0.0.1")

    def test_ruta_inexistente_devuelve_404_con_sobre_de_error(self):
        resp = self.servidor.get("/api/no-existe")
        self.assertEqual(resp.estado, 404)
        self.assertEqual(resp.json(), {
            "ok": False,
            "error": {"codigo": "no_encontrado", "mensaje": "Ruta no encontrada: /api/no-existe"},
        })


class PruebaPuertos(ayudas.CasoConEntorno):

    def test_elegir_puerto_saltea_puerto_ocupado_por_otra_app(self):
        ocupado = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(ocupado.close)
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen()
        p = ocupado.getsockname()[1]
        puerto, ya = server.elegir_puerto(p, p + 5)
        self.assertNotEqual(puerto, p)
        self.assertGreater(puerto, p)
        self.assertLessEqual(puerto, p + 5)
        self.assertFalse(ya)

    def test_elegir_puerto_detecta_gestor_ya_corriendo(self):
        servidor = ayudas.ServidorDePrueba()
        self.addCleanup(servidor.cerrar)
        p = servidor.puerto
        self.assertEqual(server.elegir_puerto(p, p), (p, True))


class PruebaCheck(ayudas.CasoConEntorno):

    def test_check_imprime_salud_y_sale_0(self):
        resultado = subprocess.run(
            [sys.executable, str(ayudas.RAIZ / "app.py"), "--check"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout.strip())["app"], "gestor-expedientes")


if __name__ == "__main__":
    unittest.main()


class PruebaProgramaDesactualizado(ayudas.CasoConServidor):
    """Después de un `git pull` con el programa abierto, cada respuesta avisa que hay que reiniciarlo."""

    def test_avisa_si_el_codigo_cambio_en_el_disco(self):
        self.assertNotIn("X-Gestor-Desactualizado", self.servidor.get("/api/salud").cabeceras)
        self.servidor.httpd.huella = (("otro.py", 0, 0),)
        self.assertEqual(self.servidor.get("/api/salud").cabeceras.get("X-Gestor-Desactualizado"), "1")
