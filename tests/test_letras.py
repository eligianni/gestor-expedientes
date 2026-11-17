"""Paso 3: importe en letras (goldens del blueprint §5, "Importe en letras")."""
import unittest

from gestor import letras


class PruebaLetras(unittest.TestCase):

    def test_importe_efia_completo(self):
        self.assertEqual(
            letras.importe_en_letras(122499000),
            "PESOS UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100 CENTAVOS ($ 1.224.990,00-)",
        )

    def test_casos_del_blueprint(self):
        casos = [
            (2109500000, "VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100"),
            (3388160000, "TREINTA Y TRES MILLONES OCHOCIENTOS OCHENTA Y UN MIL SEISCIENTOS CON 00/100"),
            (2210187213, "VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100"),
            (100000, "MIL CON 00/100"),
            (10000, "CIEN CON 00/100"),
            (370000000, "TRES MILLONES SETECIENTOS MIL CON 00/100"),
        ]
        for centavos, esperado in casos:
            with self.subTest(centavos=centavos):
                self.assertEqual(letras.letras_con_centavos(centavos), esperado)

    def test_veinti_y_cientos(self):
        casos = {
            21: "VEINTIUN",
            22: "VEINTIDOS",
            23: "VEINTITRES",
            26: "VEINTISEIS",
            101: "CIENTO UN",
            500: "QUINIENTOS",
            700: "SETECIENTOS",
            900: "NOVECIENTOS",
            1000: "MIL",
            1000000: "UN MILLÓN",
            2000000: "DOS MILLONES",
            21000: "VEINTIUN MIL",
            31: "TREINTA Y UN",
        }
        for numero, esperado in casos.items():
            with self.subTest(numero=numero):
                self.assertEqual(letras.numero_a_letras(numero), esperado)


if __name__ == "__main__":
    unittest.main()
