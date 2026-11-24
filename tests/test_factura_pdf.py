"""Paso 3: datos de la factura y de la carga en el SII leídos de sus PDF, y control inmediato contra el expediente."""
import tempfile
from pathlib import Path

from gestor import db, factura_pdf
from tests import ayudas, datos_prueba, pdf_prueba

FIXTURES = Path(__file__).parent / "fixtures" / "expedientes"


def texto_doc(carpeta, prefijo):
    return next((FIXTURES / carpeta).glob(prefijo + "_*.txt")).read_text(encoding="utf-8")


class PruebaLeerFactura(ayudas.CasoConEntorno):

    def _leer(self, carpeta):
        return factura_pdf.leer_factura(texto_doc(carpeta, "0003"))

    def test_efia_formato_propio(self):
        f = self._leer("EX-2026-89654857_EFIA")
        self.assertEqual((f["numero"], f["fecha"], f["centavos"], f["cae"]), ("0003B00031812", "2026-09-10", 122499000, "86372407008783"))
        self.assertIsNone(f["vto_cae"])  # en el PDF figura cortado («Vto. 20/09/2»)
        self.assertEqual((f["destinatario"], f["domicilio"]), ("INSSJP", "PERU 169"))
        self.assertEqual((f["periodo_desde"], f["periodo_hasta"]), ("2026-08-01", "2026-08-31"))
        self.assertEqual((f["cuit_emisor"], f["menciona"]), ("30625574273", {"oc": "4500555861"}))
        self.assertEqual(f["faltantes"], ["vencimiento del CAE"])

    def test_biofab_formato_arca(self):
        # El punto de venta va como figura en la factura (5 dígitos); el SII lo muestra con 4, pero es la misma.
        f = self._leer("EX-2026-94963848_BIOFAB")
        self.assertEqual((f["numero"], f["fecha"], f["centavos"]), ("00002B00003908", "2026-09-11", 2109500000))
        self.assertEqual((f["cae"], f["vto_cae"], f["cuit_emisor"]), ("86372594419176", "2026-09-21", "30711726604"))
        self.assertEqual(f["faltantes"], [])

    def test_macatex_sin_letra_ni_rotulo_de_total(self):
        f = self._leer("EX-2026-99349179_MACATEX")
        self.assertEqual((f["numero"], f["fecha"], f["centavos"]), ("0002-00000160", "2026-10-09", 3388160000))
        self.assertEqual((f["cae"], f["vto_cae"], f["cuit_emisor"]), ("86416949757962", "2026-10-19", None))
        self.assertEqual(len(f["avisos"]), 2)


class PruebaComprobantesApi(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def _pdf(self, texto, nombre):
        ruta = Path(self.carpeta.name) / nombre
        ruta.write_bytes(pdf_prueba.pdf_desde_texto(texto, fuente="cid", envolver=True))
        return ruta

    def test_lee_factura_y_sii_y_controla(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
        finally:
            con.close()
        carpeta = "EX-2026-89654857_EFIA"
        resp = self.servidor.subir("/api/comprobantes/factura-pdf", self._pdf(texto_doc(carpeta, "0003"), "factura.pdf"))
        self.assertEqual(resp.estado, 200, resp.texto())
        factura = resp.json()["datos"]["leido"]
        self.assertEqual((factura["numero"], factura["centavos"]), ("0003B00031812", 122499000))
        resp = self.servidor.subir("/api/comprobantes/sii-pdf", self._pdf(texto_doc(carpeta, "0004"), "sii.pdf"))
        self.assertEqual(resp.estado, 200, resp.texto())
        sii = resp.json()["datos"]["sii"]
        self.assertEqual((sii["cae"], sii["periodo"], sii["orden_compra"]), ("86372407008783", "2026-08", "4500555861"))
        revision = self.servidor.post("/api/expedientes/%d/comprobantes/revisar" % exp["id"],
                                      {"factura": factura, "sii": sii, "cuit_emisor": factura["cuit_emisor"]})
        self.assertEqual(revision.estado, 200, revision.texto())
        codigos = {r["codigo"] for r in revision.json()["datos"]["resultados"] if r["nivel"] == "error"}
        self.assertNotIn("sii_coincide", codigos)
        self.assertNotIn("formato_factura", codigos)
        # Un dato mal en el SII se avisa enseguida.
        sii_mal = dict(sii, monto_centavos=100, sap="99999")
        revision = self.servidor.post("/api/expedientes/%d/comprobantes/revisar" % exp["id"], {"factura": factura, "sii": sii_mal})
        mensajes = " ".join(r["mensaje"] for r in revision.json()["datos"]["resultados"])
        self.assertIn("El monto del SII", mensajes)
        self.assertIn("N° SAP del SII", mensajes)

    def test_pdf_que_no_es_factura(self):
        resp = self.servidor.subir("/api/comprobantes/factura-pdf", self._pdf("REMITO de entrega sin datos", "x.pdf"))
        self.assertEqual(resp.estado, 422)
        resp = self.servidor.subir("/api/comprobantes/sii-pdf", self._pdf("Hola", "y.pdf"))
        self.assertEqual(resp.estado, 422)
