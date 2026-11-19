"""Estilo: la fuente Inter se sirve desde la app (sin internet) y el CSS no pide nada de afuera."""
import re

from gestor import config
from tests import ayudas


class PruebaEstilo(ayudas.CasoConServidor):

    def test_fuente_local(self):
        resp = self.servidor.get("/fuentes/inter.woff2")
        self.assertEqual(resp.estado, 200)
        self.assertEqual(resp.cabeceras["Content-Type"], "font/woff2")
        self.assertEqual(resp.cuerpo[:4], b"wOF2")
        self.assertTrue((config.RAIZ / "web" / "fuentes" / "LICENSE-Inter.txt").is_file())

    def test_css_sin_recursos_externos(self):
        css = self.servidor.get("/style.css").texto()
        self.assertIn('url("/fuentes/inter.woff2")', css)
        self.assertEqual(re.findall(r"url\(\s*[\"']?https?:", css), [])
        html = self.servidor.get("/").texto()
        self.assertEqual(re.findall(r"(?:src|href)=\"https?:", html), [])

    def test_estados_con_palabra(self):
        script = self.servidor.get("/app.js").texto()
        self.assertIn("function pastillaEstado", script)
        self.assertIn("texto: ESTADOS_TEXTO[estadoExp] || estadoExp", script)
