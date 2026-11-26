"""PDF cifrados que se abren sin contraseña (ARCA, SII): se descifran con RC4, AES-128 o AES-256 y se leen igual.

Los PDF de `tests/pdf_cifrados/` son la factura de EFIA de prueba cifrada con contraseña de propietario y contraseña de
usuario vacía (y uno con contraseña de usuario de verdad, que no se puede leer).
"""
import unittest
from pathlib import Path

from gestor import pdf_texto

CARPETA = Path(__file__).parent / "pdf_cifrados"


def _texto(nombre):
    return pdf_texto.texto_de_pdf((CARPETA / (nombre + ".pdf")).read_bytes())


class PruebaPdfCifrado(unittest.TestCase):

    def test_aes_vectores_fips_197(self):
        bloque = bytes.fromhex("00112233445566778899aabbccddeeff")
        clave128 = bytes(range(16))
        clave256 = bytes(range(32))
        cifrado128 = pdf_texto.aes_cbc(clave128, bytes(16), bloque, descifrar=False)
        cifrado256 = pdf_texto.aes_cbc(clave256, bytes(16), bloque, descifrar=False)
        self.assertEqual(cifrado128.hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(cifrado256.hex(), "8ea2b7ca516745bfeafc49904b496089")
        self.assertEqual(pdf_texto.aes_cbc(clave128, bytes(16), cifrado128), bloque)

    def test_se_leen_igual_que_el_original(self):
        original = _texto("original")
        self.assertIn("0003-00031812", original)
        for nombre in ("rc4_40", "rc4_128", "aes_128", "aes_256"):
            with self.subTest(nombre):
                self.assertEqual(_texto(nombre), original)

    def test_con_contrasena_de_verdad_avisa(self):
        with self.assertRaises(pdf_texto.PdfError) as error:
            _texto("con_contrasena")
        self.assertIn("contraseña", str(error.exception))
