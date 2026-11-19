"""Lector de texto de PDF (gestor.pdf_texto) sobre PDF armados con las variantes de GDE."""
import unittest
import zlib
from pathlib import Path

from gestor import oc_pdf, pdf_texto
from tests import pdf_prueba

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "expedientes"
EFIA = next((FIXTURES / "EX-2026-89654857_EFIA").glob("0005_*.txt"))
MACATEX = next((FIXTURES / "EX-2026-99349179_MACATEX").glob("0005_*.txt"))


def leer(ruta):
    return ruta.read_text(encoding="utf-8")


class PruebaPdfTexto(unittest.TestCase):
    def test_lineas_y_columnas_winansi(self):
        datos = pdf_prueba.pdf_desde_texto("Renglón Cantidad\n0001  2.000,00  U   TELA BLANCA")
        texto = pdf_texto.texto_de_pdf(datos)
        lineas = texto.splitlines()
        self.assertEqual(lineas[0], "Renglón Cantidad")
        self.assertEqual(lineas[1], "0001  2.000,00  U   TELA BLANCA")

    def test_fuente_cid_con_tounicode(self):
        datos = pdf_prueba.pdf_desde_texto("OBJETO DE CONTRATACIÓN: SERVICIO DE DESRATIZACIÓN", fuente="cid")
        self.assertEqual(pdf_texto.texto_de_pdf(datos), "OBJETO DE CONTRATACIÓN: SERVICIO DE DESRATIZACIÓN")

    def test_xobjeto_flujo_de_objetos_y_actualizacion_incremental(self):
        datos = pdf_prueba.pdf_desde_texto("Número: 4500555861\nDesde: 01/10/2025", fuente="cid", envolver=True,
                                           flujo_objetos=True, actualizacion=True)
        texto = pdf_texto.texto_de_pdf(datos)
        self.assertNotIn("VERSION VIEJA", texto)
        self.assertIn("Número: 4500555861", texto)

    def test_paginas_separadas(self):
        datos = pdf_prueba.pdf_desde_texto("primera\fsegunda")
        self.assertEqual(pdf_texto.paginas(datos), ["primera", "segunda"])

    def test_no_es_pdf(self):
        with self.assertRaises(pdf_texto.PdfError) as error:
            pdf_texto.texto_de_pdf(b"PK\x03\x04 esto es un zip")
        self.assertEqual(str(error.exception), "El archivo no es un PDF.")

    def test_pdf_sin_texto(self):
        imagen = zlib.compress(b"\x00" * 100)
        flujo = b"4 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(imagen)
        datos = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                 b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                 b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
                 + flujo + imagen
                 + b"\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")
        with self.assertRaises(pdf_texto.PdfError) as error:
            pdf_texto.texto_de_pdf(datos)
        self.assertIn("parece escaneado", str(error.exception))

    def test_pdf_cifrado(self):
        datos = pdf_prueba.pdf_desde_texto("hola").replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 99 0 R")
        with self.assertRaises(pdf_texto.PdfError) as error:
            pdf_texto.texto_de_pdf(datos)
        self.assertIn("contraseña", str(error.exception))

    def test_oc_efia_ida_y_vuelta_por_pdf(self):
        """El texto real de la OC EFIA pasado a PDF (como GDE) se vuelve a leer con los mismos datos."""
        esperado = oc_pdf.leer_oc(leer(EFIA))
        for variante in ({}, {"fuente": "cid", "envolver": True, "flujo_objetos": True}):
            with self.subTest(**variante):
                leido = oc_pdf.leer_oc(pdf_texto.texto_de_pdf(pdf_prueba.pdf_desde_texto(leer(EFIA), **variante)))
                for campo in ("numero", "vig_desde", "vig_hasta", "ca", "expediente_contratacion", "gde_pdf_oc", "sap",
                              "objeto", "importe_total_centavos"):
                    self.assertEqual(leido[campo], esperado[campo], campo)
                self.assertEqual([r["desglose"] for r in leido["renglones"]], [r["desglose"] for r in esperado["renglones"]])

    def test_oc_macatex_ida_y_vuelta_por_pdf(self):
        esperado = oc_pdf.leer_oc(leer(MACATEX))
        leido = oc_pdf.leer_oc(pdf_texto.texto_de_pdf(pdf_prueba.pdf_desde_texto(leer(MACATEX), fuente="cid")))
        self.assertEqual(
            [(r["pos"], r["cantidad"], r["precio_centavos"], r["importe_centavos"]) for r in leido["renglones"]],
            [(r["pos"], r["cantidad"], r["precio_centavos"], r["importe_centavos"]) for r in esperado["renglones"]])


if __name__ == "__main__":
    unittest.main()
