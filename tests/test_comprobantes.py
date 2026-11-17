"""Paso 11: parser del texto pegado del SII y normalización de factura."""
import unittest

from gestor import comprobantes, util
from tests import ayudas


class PruebaComprobantes(unittest.TestCase):

    def _sii(self, carpeta):
        return comprobantes.analizar_texto_sii(ayudas.texto_fixture(carpeta, "0004_IF-*.txt"))

    def test_sii_efia(self):
        datos = self._sii("EX-2026-89654857_EFIA")
        self.assertEqual(datos["fecha_emision"], "2026-09-10")
        self.assertEqual(datos["periodo"], "2026-08")
        self.assertEqual(datos["monto_centavos"], 122499000)
        self.assertEqual(datos["tipo_comprobante"], "FACTURA B")
        self.assertEqual(datos["letra"], "B")
        self.assertEqual(datos["nro_comprobante"], "0003-00031812")
        self.assertEqual(datos["razon_social"], "GRUPO EFIA SRL")
        self.assertEqual(datos["cuit"], "30-62557427-3")
        self.assertEqual(datos["sap"], "77170")
        self.assertEqual(datos["area"], "GESP - MESA DE ENTRADAS Y SALIDAS - HOSPITAL DEL BICENTENARIO ITUZAINGO")
        self.assertEqual(datos["tipo_servicio"], "PROVEEDORES VARIOS")
        self.assertEqual(datos["concepto"], "Todos los conceptos")
        self.assertEqual(datos["orden_compra"], "4500555861")
        self.assertEqual(datos["cod_tramite"], "HXW2037078")
        self.assertTrue(comprobantes.cae_valido(datos["cae"]))
        self.assertEqual(datos["faltantes"], [])

    def test_sii_biofab(self):
        datos = self._sii("EX-2026-94963848_BIOFAB")
        self.assertEqual(datos["cae"], "86372594419176")
        self.assertEqual(datos["fecha_emision"], "2026-09-11")
        self.assertEqual(datos["monto_centavos"], 2109500000)
        self.assertEqual(datos["nro_comprobante"], "0002-00003908")
        self.assertEqual(datos["cuit"], "30-71172660-4")
        self.assertEqual(datos["orden_compra"], "4500587121")
        self.assertEqual(datos["faltantes"], [])

    def test_sii_macatex(self):
        datos = self._sii("EX-2026-99349179_MACATEX")
        self.assertEqual(datos["cae"], "86416949757962")
        self.assertEqual(datos["fecha_emision"], "2026-10-09")
        self.assertEqual(datos["periodo"], "2026-09")
        self.assertEqual(datos["monto_centavos"], 3388160000)
        self.assertEqual(datos["nro_comprobante"], "0002-00000160")
        self.assertEqual(datos["orden_compra"], "4500594643")
        self.assertEqual(datos["faltantes"], [])

    def test_texto_incompleto_lista_faltantes(self):
        datos = comprobantes.analizar_texto_sii("Fecha de emisión: 10/09/2026\nMonto: $1224990\n")
        self.assertIsNone(datos["cae"])
        self.assertIn("CAE", datos["faltantes"])
        self.assertIn("Nro Comprobante", datos["faltantes"])
        self.assertNotIn("Monto", datos["faltantes"])
        self.assertEqual(datos["monto_centavos"], 122499000)
        self.assertFalse(comprobantes.cae_valido(None))
        self.assertFalse(comprobantes.cae_valido("8637259441917"))
        self.assertIsNone(comprobantes.vencimiento_cae_ok("2026-09-10", None))
        self.assertTrue(comprobantes.vencimiento_cae_ok("2026-09-10", "20/09/2026"))
        self.assertFalse(comprobantes.vencimiento_cae_ok("2026-09-10", "2026-09-01"))

    def test_normalizar_domicilio(self):
        self.assertEqual(util.normalizar_domicilio("Perú 169, C.A.B.A."), "PERU 169 CABA")
        self.assertEqual(util.normalizar_domicilio("  Av.  Rivadavia 1234 - 3°/B; "), "AV RIVADAVIA 1234 3°B")

    def test_factura_equivale_a_nro_sii(self):
        self.assertTrue(util.misma_factura("0003B00031812", "0003-00031812"))
        self.assertFalse(util.misma_factura("0003B00031813", "0003-00031812"))


class PruebaComprobantesApi(ayudas.CasoConServidor):

    def test_analizar_por_api(self):
        texto = ayudas.texto_fixture("EX-2026-89654857_EFIA", "0004_IF-*.txt")
        resp = self.servidor.post("/api/comprobantes/analizar", {"texto": texto})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["nro_comprobante"], "0003-00031812")
        vacio = self.servidor.post("/api/comprobantes/analizar", {"texto": "  "})
        self.assertEqual(vacio.estado, 400)


if __name__ == "__main__":
    unittest.main()
