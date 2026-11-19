"""Paso 32: instructivo de una página, pantalla Ayuda (/api/ayuda) y pantalla Centralizadas."""
import unittest

from gestor import config
from tests import ayudas

INSTRUCTIVO = config.RAIZ / "docs" / "INSTRUCTIVO.md"
SECCIONES = (
    "## Instalar Python",
    "## Abrir el programa",
    "## Dónde está la base",
    "## Copias de seguridad",
    "## Flujo de un expediente",
    "## Revisión manual por pantalla",
)
PANTALLAS = ("inicio", "calendario", "oc", "expedientes", "centralizadas", "entregas", "importar", "configuracion")


class PruebaInstructivo(ayudas.CasoConServidor):

    def _texto(self):
        return INSTRUCTIVO.read_text(encoding="utf-8")

    def test_instructivo_tiene_las_secciones(self):
        lineas = self._texto().splitlines()
        for seccion in SECCIONES:
            self.assertIn(seccion, lineas)
        encabezados = [l for l in lineas if l.startswith("## ")]
        self.assertEqual(encabezados, list(SECCIONES))
        # una casilla por cada una de las 8 pantallas en la revisión manual
        revision = self._texto().split("## Revisión manual por pantalla", 1)[1]
        self.assertEqual(sum(1 for l in revision.splitlines() if l.startswith("- [ ]")), 8)

    def test_instructivo_entra_en_una_pagina(self):
        self.assertLessEqual(len(self._texto().splitlines()), 120)

    def test_api_ayuda_devuelve_el_instructivo(self):
        resp = self.servidor.get("/api/ayuda")
        self.assertEqual(resp.estado, 200, resp.texto())
        cuerpo = resp.json()
        self.assertTrue(cuerpo["ok"])
        self.assertEqual(cuerpo["datos"]["markdown"], INSTRUCTIVO.read_bytes().decode("utf-8"))

    def test_index_tiene_pantalla_ayuda(self):
        html = self.servidor.get("/").texto()
        self.assertIn('id="pantalla-ayuda"', html)
        self.assertIn('data-pantalla="pantalla-ayuda"', html)
        for pantalla in PANTALLAS:
            self.assertIn('id="pantalla-%s"' % pantalla, html)

    def test_app_js_usa_api_centralizadas(self):
        js = self.servidor.get("/app.js").texto()
        self.assertIn("/api/centralizadas", js)
        self.assertIn("/api/ayuda", js)


if __name__ == "__main__":
    unittest.main()
