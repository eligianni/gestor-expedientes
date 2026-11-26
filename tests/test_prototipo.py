"""Paso 21 — gate del prototipo: los tres expedientes reales de punta a punta por HTTP."""
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from tests import ayudas, datos_prueba
from tests.test_autorizacion import GOLDEN_BIOFAB, GOLDEN_EFIA
from tests.test_textos_referencias import REFERENCIAS_EFIA

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _texto_docx(contenido):
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        raiz = ET.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(W + "t")) for p in raiz.iter(W + "p"))


class PruebaPrototipo(ayudas.CasoConServidor):

    def _get(self, ruta):
        resp = self.servidor.get(ruta)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _estado(self, id_exp, estado):
        exp = self._get("/api/expedientes/%d" % id_exp)
        return self.servidor.post("/api/expedientes/%d/estado" % id_exp, {"version": exp["version"], "estado": estado})

    def _avanzar(self, id_exp, estado):
        resp = self._estado(id_exp, estado)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_efia_de_punta_a_punta(self):
        id_exp = datos_prueba.flujo_por_api(self.servidor, "efia")
        exp = self._get("/api/expedientes/%d" % id_exp)
        self.assertEqual(exp["periodo"], "2026-08")
        resumen = self._get("/api/expedientes/%d/controles" % id_exp)["resumen"]
        self.assertEqual((resumen["error"], resumen["salvable"]), (0, 0))

        textos = self._get("/api/expedientes/%d/textos" % id_exp)
        self.assertEqual(textos["caratula"], "PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861")
        self.assertEqual([r["referencia"] for r in textos["referencias"]], REFERENCIAS_EFIA)
        self.assertEqual(textos["autorizacion"]["cuerpo"], GOLDEN_EFIA)
        self.assertEqual(textos["sap"]["ingreso"]["texto"], "HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26")

        cv = self.servidor.get("/api/expedientes/%d/cv.docx" % id_exp)
        self.assertEqual(cv.estado, 200)
        self.assertIn("Se valida con remito 00001-00029461 correspondiente al período AGOSTO 2026.", _texto_docx(cv.cuerpo))
        autorizacion = self.servidor.get("/api/expedientes/%d/autorizacion.docx" % id_exp)
        self.assertIn(GOLDEN_EFIA, _texto_docx(autorizacion.cuerpo))

        for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
            exp = self._avanzar(id_exp, estado)
        self.assertEqual(exp["estado"], "FIRMADO")

    def test_biofab_de_punta_a_punta(self):
        id_exp = datos_prueba.flujo_por_api(self.servidor, "biofab")
        informe = self._get("/api/expedientes/%d/controles" % id_exp)
        self.assertEqual(informe["resumen"]["error"], 0)
        salvable = [r for r in informe["resultados"] if r["nivel"] == "salvable"]
        self.assertEqual([r["codigo"] for r in salvable], ["codigo_remito_distinto"])
        self.assertEqual(self._estado(id_exp, "CONTROLADO").estado, 422)

        exp = self._get("/api/expedientes/%d" % id_exp)
        resp = self.servidor.post("/api/expedientes/%d/notas" % id_exp, {
            "version": exp["version"], "codigo": salvable[0]["codigo"], "referencia": salvable[0]["referencia"],
            "texto": salvable[0]["nota_sugerida"],
        })
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["resumen"]["salvable_con_nota"], 1)
        self.assertEqual(self._avanzar(id_exp, "CONTROLADO")["estado"], "CONTROLADO")

        textos = self._get("/api/expedientes/%d/textos" % id_exp)
        self.assertEqual(textos["caratula"], "PAGO SAP 116467 BIO FAB S.R.L - FC 00002B00003908 - 4500587121")
        self.assertEqual(textos["autorizacion"]["cuerpo"], GOLDEN_BIOFAB)
        self.assertIn("08-26 - REMITO POR EQUIPO EN COMODATO - BIO FAB S.R.L", [r["referencia"] for r in textos["referencias"]])
        self.assertEqual(textos["sap_error"], "Falta el concepto corto (Texto SAP) en la OC 4500587121.")

    def test_macatex_bloqueado_hasta_cargar_objeto(self):
        id_exp = datos_prueba.flujo_por_api(self.servidor, "macatex")
        self.assertEqual(self._get("/api/expedientes/%d" % id_exp)["periodo"], "2026-09")
        textos = self._get("/api/expedientes/%d/textos" % id_exp)
        self.assertEqual(textos["autorizacion_error"], "Falta el objeto de la contratación en la OC 4500594643")
        self.assertNotIn("autorizacion", textos)
        rechazo = self._estado(id_exp, "CONTROLADO")
        self.assertEqual(rechazo.estado, 422)
        self.assertEqual(rechazo.json()["error"]["mensaje"], "No se puede pasar a CONTROLADO: hay 1 errores y 0 salvables sin nota.")

        oc = self._get("/api/oc/4500594643")["oc"]
        resp = self.servidor.put("/api/oc/4500594643", {"version": oc["version"], "cambios": {
            "objeto": "provisión de insumos textiles", "objeto_articulo": "a la",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(self._avanzar(id_exp, "CONTROLADO")["estado"], "CONTROLADO")
        cuerpo = self._get("/api/expedientes/%d/textos" % id_exp)["autorizacion"]["cuerpo"]
        self.assertIn("correspondiente a la provisión de insumos textiles, conforme al remito N° 0001-00004409", cuerpo)
        self.assertNotIn("correspondiente al , conforme", cuerpo)


if __name__ == "__main__":
    unittest.main()
