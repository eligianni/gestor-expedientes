"""Paso 7: estáticos de la interfaz, sobre de la API, parámetros e importación por multipart."""
import unittest

from gestor import db
from tests import ayudas

PANTALLAS = (
    "pantalla-inicio", "pantalla-calendario", "pantalla-oc", "pantalla-expedientes",
    "pantalla-centralizadas", "pantalla-entregas", "pantalla-importar", "pantalla-configuracion",
)


class PruebaWebImportar(ayudas.CasoConServidor):

    def _contar(self, tabla):
        con = db.conectar(self.entorno.ruta_base)
        try:
            return con.execute("SELECT COUNT(*) FROM %s" % tabla).fetchone()[0]
        finally:
            con.close()

    def test_raiz_sirve_las_8_pantallas(self):
        resp = self.servidor.get("/")
        self.assertEqual(resp.estado, 200)
        self.assertEqual(resp.cabeceras["Content-Type"], "text/html; charset=utf-8")
        html = resp.texto()
        for fragmento in ('lang="es"', 'id="selector-efector"', 'id="avisos"', 'aria-live="polite"', 'href="#contenido"'):
            self.assertIn(fragmento, html)
        for pantalla in PANTALLAS:
            self.assertIn('id="%s"' % pantalla, html)
        self.assertEqual(html.count('<section id="pantalla-'), 8)

    def test_estaticos_con_content_type(self):
        esperados = {
            "/app.js": "text/javascript; charset=utf-8",
            "/style.css": "text/css; charset=utf-8",
        }
        for ruta, tipo in esperados.items():
            with self.subTest(ruta=ruta):
                resp = self.servidor.get(ruta)
                self.assertEqual(resp.estado, 200)
                self.assertEqual(resp.cabeceras["Content-Type"], tipo)
                self.assertEqual(resp.cabeceras.get("Cache-Control"), "no-store")
                self.assertGreater(len(resp.cuerpo), 0)
        self.assertIn("async function api(metodo, ruta, cuerpo)", self.servidor.get("/app.js").texto())
        self.assertIn("--primario: #1F4E8C", self.servidor.get("/style.css").texto())

    def test_ruta_fuera_de_web_da_404(self):
        for ruta in ("/config.json", "/index.html", "/../config.json", "/gestor/db.py", "/web/app.js"):
            with self.subTest(ruta=ruta):
                resp = self.servidor.get(ruta)
                self.assertEqual(resp.estado, 404)
                self.assertEqual(resp.json()["error"]["codigo"], "no_encontrado")

    def test_vista_previa_no_escribe_y_confirmar_importa(self):
        resp = self.servidor.subir("/api/importar/vista-previa", ayudas.XLSX_HBI_2026, {"efector": "HBI"})
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["datos"]["quedan"], 433)
        self.assertEqual(self._contar("renglon"), 0)
        self.assertEqual(self._contar("importacion"), 0)

        resp = self.servidor.subir("/api/importar/confirmar", ayudas.XLSX_HBI_2026, {"efector": "HBI"})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["altas"], 433)
        self.assertEqual(self._contar("renglon"), 433)
        self.assertEqual(self._contar("importacion"), 1)

        lista = self.servidor.get("/api/importaciones").json()["datos"]
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["archivo"], "z_compras2_hbi_2026.xlsx")
        self.assertEqual(lista[0]["efector"], "HBI")
        self.assertEqual(set(lista[0].keys()), {"id", "fecha", "archivo", "efector", "usuario"})

        sin_efector = self.servidor.subir("/api/importar/vista-previa", ayudas.XLSX_HBI_2026, {})
        self.assertEqual(sin_efector.estado, 400)
        self.assertEqual(sin_efector.json()["error"]["codigo"], "validacion")

    def test_casph_sin_centros_pide_configurarlos(self):
        resp = self.servidor.subir("/api/importar/vista-previa", ayudas.XLSX_HBI_2026, {"efector": "CASPH"})
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json(), {
            "ok": False,
            "error": {"codigo": "negocio", "mensaje": "Configurá los centros SAP de CASPH antes de importar."},
        })
        self.assertEqual(self._contar("renglon"), 0)

    def test_parametros_con_version_vieja_da_409(self):
        datos = self.servidor.get("/api/parametros").json()["datos"]
        self.assertEqual(datos["parametros"]["dias_gracia"], 10)
        version = datos["versiones"]["dias_gracia"]

        ok = self.servidor.put("/api/parametros", {"clave": "dias_gracia", "valor": 12, "version": version})
        self.assertEqual(ok.estado, 200, ok.texto())
        self.assertEqual(ok.json()["datos"]["parametros"]["dias_gracia"], 12)
        self.assertEqual(ok.json()["datos"]["versiones"]["dias_gracia"], version + 1)

        vieja = self.servidor.put("/api/parametros", {"clave": "dias_gracia", "valor": 15, "version": version})
        self.assertEqual(vieja.estado, 409)
        self.assertEqual(vieja.json(), {
            "ok": False,
            "error": {
                "codigo": "conflicto_version",
                "mensaje": "Otra persona guardó cambios en este registro. Recargá para ver la última versión.",
            },
        })
        self.assertEqual(self.servidor.get("/api/parametros").json()["datos"]["parametros"]["dias_gracia"], 12)


class PruebaSubidaGrande(unittest.TestCase):

    def setUp(self):
        self.entorno = ayudas.EntornoTemporal(tamano_maximo_subida_mb=0.01)
        self.addCleanup(self.entorno.cerrar)
        self.servidor = ayudas.ServidorDePrueba()
        self.addCleanup(self.servidor.cerrar)

    def test_subida_demasiado_grande_da_413(self):
        resp = self.servidor.subir("/api/importar/confirmar", ayudas.XLSX_HBI_2026, {"efector": "HBI"})
        self.assertEqual(resp.estado, 413)
        error = resp.json()["error"]
        self.assertEqual(error["codigo"], "demasiado_grande")
        self.assertEqual(error["mensaje"], "El archivo supera el máximo de 0.01 MB.")
        con = db.conectar(self.entorno.ruta_base)
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM renglon").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacion").fetchone()[0], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
