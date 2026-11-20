"""Lectura de la OC desde el texto de su PDF (gestor.oc_pdf) con las tres OC reales de las fixtures."""
import unittest
from pathlib import Path

from gestor import oc_pdf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "expedientes"


def texto_oc(carpeta):
    return next((FIXTURES / carpeta).glob("0005_*.txt")).read_text(encoding="utf-8")


class PruebaOcEfia(unittest.TestCase):
    """Servicio anual partido en meses: el renglón dice 1 UP y el subrenglón 3 (o 9) MES × $ 1.224.990,00."""

    @classmethod
    def setUpClass(cls):
        cls.oc = oc_pdf.leer_oc(texto_oc("EX-2026-89654857_EFIA"))

    def test_cabecera(self):
        oc = self.oc
        self.assertEqual(oc["numero"], "4500555861")
        self.assertEqual(oc["fecha_oc"], "2025-09-04")
        self.assertEqual((oc["vig_desde"], oc["vig_hasta"]), ("2025-10-01", "2026-09-30"))
        self.assertEqual(oc["prorroga"], "SI POR IGUAL PERIODO")
        self.assertEqual(oc["ca"], "195-2025")
        self.assertEqual(oc["procedimiento"], "Compulsa Abreviada")
        self.assertEqual(oc["expediente_contratacion"], "EX-2025-70356979- -INSSJP-GESP#INSSJP")
        self.assertEqual(oc["sap"], "77170")
        self.assertEqual(oc["razon_social"], "GRUPO EFIA S.R.L.")
        self.assertEqual(oc["cuit"], "30-62557427-3")
        self.assertEqual(oc["gde_pdf_oc"], "IF-2025-98344682-INSSJP-GESP#INSSJP")
        self.assertEqual(oc["importe_total_centavos"], 1469988000)
        self.assertEqual(oc["avisos"], [])

    def test_objeto(self):
        self.assertTrue(self.oc["objeto_completo"].startswith("SERVICIO DE CONTROL INTEGRAL DE PLAGAS"))
        self.assertTrue(self.oc["objeto_completo"].endswith("PROVINCIA DE BUENOS AIRES."))
        self.assertEqual(self.oc["objeto"], "servicio de control integral de plagas, fumigación, desinsectación y desratización")
        self.assertEqual(self.oc["objeto_articulo"], "al")

    def test_renglones_con_subrenglon_mensual(self):
        r1, r2 = self.oc["renglones"]
        self.assertEqual((r1["pos"], r1["cantidad"], r1["unidad"], r1["importe_centavos"]), (1, "1", "UP", 367497000))
        self.assertEqual(r1["descripcion"], "SERV INTEGRAL CONTROL DE PLAGAS - 2025")
        self.assertEqual(r1["desglose"], {"cantidad": "3", "unidad": "MES", "precio_centavos": 122499000})
        self.assertEqual(r1["subrenglones"][0]["codigo"], "1000029")
        self.assertEqual((r1["sol_ped"], r1["pos_sol_ped"]), ("830000517", "1"))
        # El total del renglón 2 quedó en una línea aparte y el subrenglón solo trae el precio unitario.
        self.assertEqual((r2["pos"], r2["importe_centavos"]), (2, 1102491000))
        self.assertEqual(r2["desglose"], {"cantidad": "9", "unidad": "MES", "precio_centavos": 122499000})
        self.assertEqual(r2["subrenglones"][0]["importe_centavos"], 1102491000)


class PruebaOcBienes(unittest.TestCase):
    def test_macatex(self):
        oc = oc_pdf.leer_oc(texto_oc("EX-2026-99349179_MACATEX"))
        self.assertEqual(oc["numero"], "4500594643")
        self.assertEqual((oc["vig_desde"], oc["vig_hasta"]), ("2026-08-25", None))
        self.assertEqual(oc["ca"], "49-2026")
        self.assertEqual(oc["sap"], "118896")
        self.assertEqual(oc["objeto"], "adquisición de Telas e Hilos")
        self.assertEqual(oc["objeto_articulo"], "a la")
        self.assertEqual(len(oc["renglones"]), 6)
        r1 = oc["renglones"][0]
        self.assertEqual((r1["cantidad"], r1["unidad"], r1["codigo"], r1["descripcion"]),
                         ("2000", "U", "2003513", "TELA ACROCELL BLANCO 1,5 M"))
        self.assertEqual((r1["precio_centavos"], r1["importe_centavos"], r1["desglose"]), (406000, 812000000, None))
        self.assertEqual(sum(r["importe_centavos"] for r in oc["renglones"]), oc["importe_total_centavos"])
        self.assertEqual(oc["avisos"], [])

    def test_biofab(self):
        oc = oc_pdf.leer_oc(texto_oc("EX-2026-94963848_BIOFAB"))
        self.assertEqual(oc["numero"], "4500587121")
        self.assertEqual(oc["gde_pdf_oc"], "IF-2026-62815888-INSSJP-GESP#INSSJP")
        self.assertEqual(oc["objeto"], "provisión de Determinaciones de Inmunoensayo por Fluorescencia")
        self.assertEqual([r["cantidad"] for r in oc["renglones"]], ["1000", "400", "200", "150"])


class PruebaAvisosYErrores(unittest.TestCase):
    def test_texto_que_no_es_oc(self):
        with self.assertRaises(oc_pdf.OcIlegible):
            oc_pdf.leer_oc("FACTURA B N° 0003-00001234\nTotal $ 1.000,00")

    def test_total_que_no_cierra(self):
        texto = texto_oc("EX-2026-99349179_MACATEX").replace("8.120.000,00", "8.120.001,00", 1)
        avisos = oc_pdf.leer_oc(texto)["avisos"]
        self.assertTrue(any(a.startswith("Renglón 1:") for a in avisos), avisos)
        self.assertTrue(any("no coincide con el importe total" in a for a in avisos), avisos)

    def test_subrenglones_distintos_no_desglosan(self):
        texto = ("DETALLE DE LA ORDEN DE COMPRA\n"
                 "0001  1,00  UP  SERVICIO 2026  300,00  300,00\n"
                 "10    1,00  MES 1000029 - SERVICIO  100,00  100,00\n"
                 "20    2,00  HS  1000030 - HORAS  100,00  200,00\n"
                 "Importe Total: ARS 300,00\n")
        oc = oc_pdf.leer_oc(texto)
        self.assertIsNone(oc["renglones"][0]["desglose"])
        self.assertIn("distinta unidad o precio", oc["avisos"][0])

    def test_varios_subrenglones_iguales_se_suman(self):
        texto = ("DETALLE DE LA ORDEN DE COMPRA\n"
                 "0001  1,00  UP  SERVICIO 2026  300,00  300,00\n"
                 "10    1,00  MES 1000029 - SERVICIO  100,00  100,00\n"
                 "20    2,00  MES 1000029 - SERVICIO  100,00  200,00\n"
                 "Importe Total: ARS 300,00\n")
        oc = oc_pdf.leer_oc(texto)
        self.assertEqual(oc["renglones"][0]["desglose"], {"cantidad": "3", "unidad": "MES", "precio_centavos": 10000})

    def test_uoc_nivel_central_es_centralizada(self):
        texto = texto_oc("EX-2026-89654857_EFIA")
        self.assertEqual(oc_pdf.leer_oc(texto)["centralizada"], 0)
        central = oc_pdf.leer_oc(texto.replace("UOC: Hospital del Bicentenario Ituzaingó", "UOC: Nivel Central", 1))
        self.assertEqual((central["uoc"], central["centralizada"]), ("Nivel Central", 1))

    def test_articulo_por_regla(self):
        self.assertEqual(oc_pdf.articulo_sugerido("SERVICIO DE MANTENIMIENTO CON ADQUISICIÓN DE REPUESTOS"), "al")
        self.assertEqual(oc_pdf.articulo_sugerido("Provisión de determinaciones con servicio técnico"), "a la")
        self.assertEqual(oc_pdf.articulo_sugerido("ADQUISICION DE TELAS"), "a la")
        self.assertEqual(oc_pdf.dia_inicio_periodo("2025-07-17"), 17)
        self.assertEqual(oc_pdf.dia_inicio_periodo("2025-10-01"), 1)

    def test_objeto_y_articulo_sugeridos(self):
        self.assertEqual(oc_pdf.objeto_sugerido("ALQUILER DE EQUIPO, PARA EL HOSPITAL."), "alquiler de equipo")
        self.assertEqual(oc_pdf.articulo_sugerido("insumos de limpieza"), "a los")
        self.assertEqual(oc_pdf.articulo_sugerido("reparación de bombas"), "a la")


if __name__ == "__main__":
    unittest.main()
