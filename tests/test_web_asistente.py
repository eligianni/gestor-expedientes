"""Paso 15: asistente del expediente, pasos 1 a 4 en la interfaz."""
import unittest

from gestor import db
from tests import ayudas, datos_prueba


class PruebaWebAsistente(ayudas.CasoConServidor):

    def test_index_tiene_los_7_pasos(self):
        resp = self.servidor.get("/")
        self.assertEqual(resp.estado, 200)
        html = resp.texto()
        for n in range(1, 8):
            self.assertIn('id="asistente-paso-%d"' % n, html)
        self.assertIn('id="pantalla-expedientes"', html)

    def test_app_js_usa_las_rutas_del_asistente(self):
        resp = self.servidor.get("/app.js")
        self.assertEqual(resp.estado, 200)
        script = resp.texto()
        for ruta in ("/remitos/pegar", "/api/comprobantes/analizar", "/controles", "/notas"):
            self.assertIn(ruta, script)
        self.assertNotIn(".innerHTML", script)
        self.assertEqual(script.count("fetch("), 1)  # solo dentro de api()

    def test_style_tiene_las_clases_de_nivel(self):
        css = self.servidor.get("/style.css").texto()
        for clase in (".nivel-error", ".nivel-salvable", ".nivel-aviso", ".nivel-verificar"):
            self.assertIn(clase, css)

    def test_flujo_pasos_1_a_4_por_api_efia(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
        finally:
            con.close()
        # 1) alta
        alta = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": datos_prueba.OC_EFIA_MANUAL["numero"]})
        self.assertEqual(alta.estado, 200, alta.texto())
        exp = alta.json()["datos"]
        # 2) pegado del remito y cantidades
        pegado = self.servidor.post("/api/expedientes/%d/remitos/pegar" % exp["id"],
                                    {"version": exp["version"], "texto": "00001-00029461;31/08/2026"})
        self.assertEqual(pegado.estado, 200, pegado.texto())
        exp = pegado.json()["datos"]
        self.assertEqual(exp["periodo"], "2026-08")
        remitos = exp["datos"]["remitos"]
        remitos[0]["items"] = [{"pos": 1, "cantidad": "1", "codigo": ""}]
        exp = self.servidor.put("/api/expedientes/%d" % exp["id"],
                                {"version": exp["version"], "cambios": {"datos": {"remitos": remitos}}}).json()["datos"]
        # 3) análisis del texto SII y guardado de factura + SII
        texto = ayudas.texto_fixture("EX-2026-89654857_EFIA", "0004_IF-*.txt")
        analisis = self.servidor.post("/api/comprobantes/analizar", {"texto": texto})
        self.assertEqual(analisis.estado, 200, analisis.texto())
        sii = analisis.json()["datos"]
        factura = {
            "numero": "0003B00031812", "fecha": sii["fecha_emision"], "centavos": sii["monto_centavos"], "cae": sii["cae"],
            "vto_cae": None, "destinatario": "INSSJP", "domicilio": "PERU 169 CABA",
        }
        guardado = self.servidor.put("/api/expedientes/%d" % exp["id"],
                                     {"version": exp["version"], "cambios": {"datos": {"factura": factura, "sii": sii}}})
        self.assertEqual(guardado.estado, 200, guardado.texto())
        self.assertEqual(guardado.json()["datos"]["factura"], "0003B00031812")
        # 4) controles
        controles = self.servidor.get("/api/expedientes/%d/controles" % exp["id"])
        self.assertEqual(controles.estado, 200, controles.texto())
        resumen = controles.json()["datos"]["resumen"]
        self.assertEqual((resumen["error"], resumen["salvable"]), (0, 0), controles.json()["datos"]["resultados"])


if __name__ == "__main__":
    unittest.main()
