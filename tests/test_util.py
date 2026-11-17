"""Paso 3: utilidades de textos, montos, fechas, períodos, facturas y GDE."""
import unittest
from datetime import date
from decimal import Decimal

from gestor import util


class PruebaUtil(unittest.TestCase):

    def test_periodo_mes_calendario(self):
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 8, 31)),
            util.Periodo("2026-08", date(2026, 8, 1), date(2026, 8, 31)),
        )
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 2, 10), dia_inicio=1),
            util.Periodo("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
        )
        self.assertEqual(util.mm_aa("2026-08"), "08-26")
        self.assertEqual(util.mm_barra_aa("2026-08"), "08/26")
        self.assertEqual(util.mm_aaaa("2026-08"), "08-2026")
        self.assertEqual(util.MESES[7], "agosto")

    def test_periodo_especifico_dia_17(self):
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 10, 20), dia_inicio=17),
            util.Periodo("2026-11", date(2026, 10, 17), date(2026, 11, 16)),
        )
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 11, 16), dia_inicio=17),
            util.Periodo("2026-11", date(2026, 10, 17), date(2026, 11, 16)),
        )
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 11, 17), dia_inicio=17),
            util.Periodo("2026-12", date(2026, 11, 17), date(2026, 12, 16)),
        )
        # cruce de año
        self.assertEqual(
            util.periodo_de_fecha(date(2026, 12, 20), dia_inicio=17),
            util.Periodo("2027-01", date(2026, 12, 17), date(2027, 1, 16)),
        )

    def test_a_centavos_y_formato_pesos(self):
        self.assertEqual(util.a_centavos("1.224.990,01"), 122499001)
        self.assertEqual(util.a_centavos("1224990.01"), 122499001)
        self.assertEqual(util.a_centavos(1224990), 122499000)
        self.assertEqual(util.a_centavos(Decimal("10.005")), 1001)
        self.assertEqual(util.a_decimal("3.600,5"), Decimal("3600.50"))
        self.assertEqual(util.a_decimal("3600.001", decimales=None), Decimal("3600.001"))
        self.assertEqual(util.formato_pesos(122499001), "1.224.990,01")
        self.assertEqual(util.formato_pesos(122499000), "1.224.990,00")
        self.assertEqual(util.formato_pesos(5), "0,05")
        with self.assertRaises(TypeError):
            util.a_centavos(1.5)

    def test_normalizar_factura(self):
        self.assertEqual(util.normalizar_factura("0003B00031812"), (3, "B", 31812))
        self.assertEqual(util.normalizar_factura("00002B00003908"), (2, "B", 3908))
        self.assertEqual(util.normalizar_factura("0002 - 00003908"), (2, None, 3908))
        self.assertTrue(util.misma_factura("00002B00003908", "0002 - 00003908"))
        self.assertFalse(util.misma_factura("0002B00003908", "0002C00003908"))
        self.assertFalse(util.misma_factura("0002B00003908", "0002B00003909"))
        self.assertEqual(util.sap_sin_ceros("0000077170"), "77170")

    def test_normalizar_y_validar_gde(self):
        normalizado = util.normalizar_gde("EX-2025-18959064-   -INSSJP-GESP%INSSJP")
        self.assertEqual(normalizado, "EX-2025-18959064- -INSSJP-GESP#INSSJP")
        self.assertTrue(util.validar_gde("EX-2025-18959064-   -INSSJP-GESP%INSSJP"))
        self.assertTrue(util.validar_gde("no-2026-38484415-inssjp-gesp#inssjp"))
        self.assertFalse(util.validar_gde("EX-2026-12-INSSJP"))

    def test_clave_encabezado(self):
        self.assertEqual(util.clave_encabezado("N° O/C"), "n o c")
        self.assertEqual(util.clave_encabezado("Nº O/C"), "n o c")
        self.assertEqual(util.clave_encabezado("Año Licit"), "ano licit")
        self.assertEqual(util.clave_encabezado("Razón Social Proveed"), "razon social proveed")
        self.assertEqual(util.clave_encabezado("Posición."), "posicion")
        self.assertEqual(util.normalizar_texto("  Ituzaingó   HBI "), "ituzaingo hbi")

    def test_fecha_serial_excel(self):
        self.assertEqual(util.fecha_desde_serial_excel(45971), date(2025, 11, 10))
        self.assertEqual(util.fecha_desde_texto("31/08/2026"), date(2026, 8, 31))
        self.assertEqual(util.fecha_desde_texto("2026-08-31"), date(2026, 8, 31))
        self.assertEqual(util.fecha_desde_texto("31.08.2026"), date(2026, 8, 31))
        d = date(2026, 8, 31)
        self.assertEqual(util.iso(d), "2026-08-31")
        self.assertEqual(util.ddmmaaaa(d), "31/08/2026")
        self.assertEqual(util.fecha_sap(d), "31.08.2026")


if __name__ == "__main__":
    unittest.main()
