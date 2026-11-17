"""Paso 4: lector .xlsx con los dos reportes z_compras2 reales."""
import io
import unittest

from gestor import xlsx
from tests import ayudas

ENCABEZADOS_HBI_2026 = [
    "Número de Expediente GDE", "Clase de Pedido", "Licitacion", "Precio unitario", "Año Licit",
    "Proveedor", "Razón Social Proveed", "N° O/C", "F.O.Compra", "In. Periodo Validez", "Fin Periodo Validez", "Posición.", "Código",
    "Elemento", "Cant", "Importe", "Moneda", "Org.Compras", "Centro", "Entrega final", "Factura Final", "Por entregar (cantid",
    "Entregadas (cantidad", "Por entregar (valor)", "Entregadas (valor)", "Por Facturar (cantid", "Facturadas (cantidad",
]

ENCABEZADOS_POR_PARTIDA = [
    "Partida Presupuestar", "Número de Expediente GDE", "Clase de Pedido", "Licitacion", "Año Licit",
    "Proveedor", "Razón Social Proveed", "N° O/C", "F.O.Compra", "In. Periodo Validez", "Fin Periodo Validez", "Posición.", "Código",
    "Elemento", "Cant", "Importe", "Moneda", "Org.Compras", "Centro", "Entrega final", "Factura Final", "Por entregar (cantid",
    "Entregadas (cantidad", "Por entregar (valor)", "Entregadas (valor)", "Por Facturar (cantid", "Facturadas (cantidad",
    "Tipo de Imputación", "Expte", "Número de Expediente",
]


class PruebaXlsx(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.hbi = xlsx.leer_tabla(ayudas.XLSX_HBI_2026)
        cls.partida = xlsx.leer_tabla(ayudas.XLSX_POR_PARTIDA)

    def test_encabezados_hbi_2026(self):
        encabezados, _ = self.hbi
        self.assertEqual(len(ENCABEZADOS_HBI_2026), 27)
        self.assertEqual(encabezados, ENCABEZADOS_HBI_2026)

    def test_encabezados_por_partida(self):
        encabezados, _ = self.partida
        self.assertEqual(len(ENCABEZADOS_POR_PARTIDA), 30)
        self.assertEqual(encabezados, ENCABEZADOS_POR_PARTIDA)
        self.assertNotIn("Precio unitario", encabezados)

    def test_cantidad_de_filas(self):
        self.assertEqual(len(self.hbi[1]), 3074)
        self.assertEqual(len(self.partida[1]), 5897)
        # también acepta un archivo binario abierto
        with open(ayudas.XLSX_HBI_2026, "rb") as archivo:
            self.assertEqual(len(xlsx.leer_tabla(archivo)[1]), 3074)

    def test_valores_como_texto(self):
        _, filas = self.hbi
        proveedores = {fila["Proveedor"] for fila in filas}
        self.assertIn("0000115819", proveedores)
        expedientes = {fila["Número de Expediente GDE"] for fila in filas}
        self.assertIn("EX-2025-18959064-   -INSSJP-GESP#INSSJP", expedientes)
        for fila in filas:
            for valor in fila.values():
                self.assertTrue(valor is None or isinstance(valor, str))

    def test_archivo_invalido(self):
        for contenido in (b"esto no es un zip", io.BytesIO(b"esto tampoco")):
            with self.subTest(contenido=type(contenido).__name__):
                with self.assertRaises(xlsx.XlsxError) as contexto:
                    xlsx.leer_tabla(contenido)
                self.assertEqual(str(contexto.exception), "El archivo no es un Excel .xlsx válido.")


if __name__ == "__main__":
    unittest.main()
