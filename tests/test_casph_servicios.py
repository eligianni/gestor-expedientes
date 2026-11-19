"""Paso 30: modelos de autorización AySA y Edenor del CASPH (dos párrafos literales de §5)."""
import unittest

from gestor import textos
from tests import ayudas

FACTURA = "0001-00012345"
CENTAVOS = 4512300
EX = "EX-2026-11111111- -INSSJP-GESP#INSSJP"

GOLDEN_AYSA = (
    "Por medio de la presente se autoriza el pago de la factura N° 0001-00012345 de la empresa AySA (AGUA Y SANEAMIENTOS "
    "ARGENTINOS S.A.), SAP 70262, por un monto de PESOS CUARENTA Y CINCO MIL CIENTO VEINTITRES con 00/100 CENTAVOS "
    "($ 45.123,00-) correspondiente al mes de AGOSTO 2026, por el servicio de CLOACA del Centro Ambulatorio de Salud PAMI "
    "Hurlingham de acuerdo a la factura vinculada al EX-2026-11111111- -INSSJP-GESP#INSSJP."
)
GOLDEN_EDENOR = (
    "Por medio de la presente se autoriza el pago de la factura N° 0001-00012345 de la EMPRESA DISTRIBUIDORA Y "
    "COMERCIALIZADORA NORTE S.A. por un monto de PESOS CUARENTA Y CINCO MIL CIENTO VEINTITRES CON 00/100 CENTAVOS "
    "($ 45.123,00-), correspondiente al mes de AGOSTO 2026, por el servicio de provisión de energía eléctrica del Centro "
    "Ambulatorio de Salud PAMI Hurlingham, de acuerdo a la factura vinculada al expediente "
    "EX-2026-11111111- -INSSJP-GESP#INSSJP."
)
GOLDEN_RESOL = (
    "Atento a que por el artículo 5 de la RESOL-2023-926-INSSJP-DE#INSSJP se estableció que el Centro Ambulatorio de Salud "
    "PAMI Hurlingham, funcionará transitoriamente como una unidad orgánica anexa del Hospital de Alta complejidad del "
    "Bicentenario Ituzaingó dependiente de la Gerencia de Efectores Sanitarios Propios, exclusivamente para proveer los "
    "bienes y servicios esenciales necesarios que permitan su efectivo y habitual funcionamiento. Sin más, se eleva para su "
    "intervención."
)


def generar(empresa):
    return textos.autorizacion_servicio_casph(empresa, FACTURA, CENTAVOS, "AGOSTO", 2026, EX)


class PruebaServiciosCasph(unittest.TestCase):

    def test_aysa_golden(self):
        parrafos = generar("AYSA")
        self.assertEqual(len(parrafos), 2)
        self.assertEqual(parrafos[0], GOLDEN_AYSA)

    def test_edenor_golden(self):
        parrafos = generar("EDENOR")
        self.assertEqual(len(parrafos), 2)
        self.assertEqual(parrafos[0], GOLDEN_EDENOR)

    def test_parrafo_resol_identico_en_ambos(self):
        aysa, edenor = generar("AYSA"), generar("EDENOR")
        self.assertEqual(aysa[1], GOLDEN_RESOL)
        self.assertEqual(edenor[1], aysa[1])
        self.assertIn("RESOL-2023-926-INSSJP-DE#INSSJP", aysa[1])
        self.assertTrue(aysa[1].endswith("Sin más, se eleva para su intervención."))
        # el mes se escribe en mayúsculas aunque llegue en minúsculas
        self.assertIn("mes de AGOSTO 2026", textos.autorizacion_servicio_casph("AYSA", FACTURA, CENTAVOS, "agosto", 2026, EX)[0])

    def test_empresa_desconocida(self):
        with self.assertRaises(ValueError):
            generar("METROGAS")
        with self.assertRaises(ValueError):
            generar("")


class PruebaServiciosCasphApi(ayudas.CasoConServidor):

    def test_endpoint(self):
        cuerpo = {"empresa": "EDENOR", "factura": FACTURA, "centavos": CENTAVOS, "mes": "agosto", "anio": 2026, "expediente": EX}
        resp = self.servidor.post("/api/textos/servicio-casph", cuerpo)
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["parrafos"], [GOLDEN_EDENOR, GOLDEN_RESOL])
        self.assertEqual(self.servidor.post("/api/textos/servicio-casph", dict(cuerpo, empresa="METROGAS")).estado, 400)
        self.assertEqual(self.servidor.post("/api/textos/servicio-casph", dict(cuerpo, centavos=45123.5)).estado, 400)


if __name__ == "__main__":
    unittest.main()
