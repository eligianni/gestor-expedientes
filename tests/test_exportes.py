"""Paso 26: escritor .xlsx propio, vista imprimible y seis exportes."""
import io
import unittest
import zipfile

from gestor import db, exportes, negocio, xlsx, xlsx_escritor
from tests import ayudas, datos_prueba

OC_EFIA = datos_prueba.OC_EFIA_MANUAL["numero"]
NOMBRES = ("consumo-oc", "seguimiento-oc", "pendientes", "entrega", "calendario", "centralizadas")


def _celda_esperada(valor, moneda):
    if valor is None or valor == "":
        return None
    if moneda and isinstance(valor, int):
        return xlsx_escritor.valor_monto(valor)
    return str(valor)


def _sin_vacios_al_final(fila):
    fila = list(fila)
    while fila and fila[-1] in (None, ""):
        fila.pop()
    return fila


class PruebaExportes(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
            for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
                exp = negocio.cambiar_estado(con, exp["id"], exp["version"], estado)
            entrega = negocio.crear_entrega(con, "HBI")
            self.entrega = negocio.asignar_a_entrega(con, entrega["id"], entrega["version"], [exp["id"]])
            self.exp = exp
        finally:
            con.close()

    def _parametros(self, nombre):
        return {"consumo-oc": "?oc=%s" % OC_EFIA, "entrega": "?id=%d" % self.entrega["id"], "calendario": "?anio=2026",
                "centralizadas": "?periodo=2026-08", "seguimiento-oc": "?efector=HBI"}.get(nombre, "")

    def test_xlsx_roundtrip_consumo_efia(self):
        resp = self.servidor.get("/api/exportes/consumo-oc.xlsx?oc=%s" % OC_EFIA)
        self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
        self.assertEqual(resp.cabeceras["Content-Type"], xlsx_escritor.TIPO_XLSX)
        con = db.conectar(self.entorno.ruta_base)
        try:
            titulo, encabezados, filas, moneda = exportes.exportar(con, "consumo-oc", {"oc": OC_EFIA})
        finally:
            con.close()
        leidas = xlsx.leer_filas(resp.cuerpo)
        self.assertEqual(leidas[0], [titulo])
        self.assertIn("Emitido el", titulo)
        self.assertIn(OC_EFIA, titulo)
        self.assertEqual(leidas[1], encabezados)
        esperadas = [_sin_vacios_al_final(_celda_esperada(v, encabezados[i] in moneda) for i, v in enumerate(f)) for f in filas]
        self.assertEqual([_sin_vacios_al_final(f) for f in leidas[2:]], esperadas)
        self.assertTrue(filas)
        # el período validado del EFIA (2026-08) aparece con su consumo y el expediente
        columna = encabezados.index("Consumido 2026-08")
        self.assertEqual(filas[0][columna], "1")
        self.assertEqual(filas[0][encabezados.index("Expedientes")], str(self.exp["id"]))
        precio = filas[0][encabezados.index("Precio unitario")]
        self.assertIsInstance(precio, int)

    def test_xlsx_partes_minimas(self):
        contenido = self.servidor.get("/api/exportes/pendientes.xlsx").cuerpo
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            nombres = set(zf.namelist())
            hoja = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
            estilos = zf.read("xl/styles.xml").decode("utf-8")
        for parte in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels",
                      "xl/styles.xml", "xl/worksheets/sheet1.xml"):
            self.assertIn(parte, nombres)
        self.assertNotIn("xl/sharedStrings.xml", nombres)
        self.assertIn('t="inlineStr"', hoja)
        self.assertIn('formatCode="#,##0.00"', estilos)
        # montos como número con el estilo 2
        bytes_ = xlsx_escritor.contenido_xlsx("Prueba", "Título", ["Concepto", "Importe"], [["Factura", 122499000]], ("Importe",))
        with zipfile.ZipFile(io.BytesIO(bytes_)) as zf:
            hoja = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn('<c r="B3" s="2"><v>1224990.00</v></c>', hoja)
        self.assertIn('<c r="A2" t="inlineStr" s="1">', hoja)
        self.assertEqual(xlsx.leer_filas(bytes_), [["Título"], ["Concepto", "Importe"], ["Factura", "1224990.00"]])

    def test_csv_bom_y_punto_y_coma(self):
        resp = self.servidor.get("/api/exportes/consumo-oc.csv?oc=%s" % OC_EFIA)
        self.assertEqual(resp.estado, 200)
        self.assertTrue(resp.cuerpo.startswith(b"\xef\xbb\xbf"))
        primera = resp.cuerpo[3:].split(b"\r\n")[0].decode("utf-8")
        self.assertTrue(primera.startswith("Pos;Descripción;Cantidad OC;Unidad;Precio unitario;"))
        self.assertIn(";", resp.cuerpo.split(b"\r\n")[1].decode("utf-8"))

    def test_html_imprimible(self):
        resp = self.servidor.get("/api/exportes/calendario.html?anio=2026")
        self.assertEqual(resp.estado, 200)
        self.assertTrue(resp.cabeceras["Content-Type"].startswith("text/html"))
        self.assertTrue(resp.cabeceras["Content-Disposition"].startswith("inline"))
        texto = resp.texto()
        self.assertIn("<table>", texto)
        self.assertIn("@media print", texto)
        self.assertIn("window.print()", texto)
        self.assertIn(OC_EFIA, texto)
        # los datos se escapan
        pagina = exportes.a_html("<b>T</b>", ["A"], [["<script>x</script>"]]).decode("utf-8")
        self.assertNotIn("<script>x", pagina)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", pagina)

    def test_seis_exportes_responden(self):
        for nombre in NOMBRES:
            for formato in ("xlsx", "csv", "html"):
                with self.subTest(nombre=nombre, formato=formato):
                    resp = self.servidor.get("/api/exportes/%s.%s%s" % (nombre, formato, self._parametros(nombre)))
                    self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
                    self.assertTrue(resp.cuerpo)
        entrega = self.servidor.get("/api/exportes/entrega.csv?id=%d" % self.entrega["id"]).cuerpo.decode("utf-8-sig")
        self.assertTrue(entrega.startswith("REMITO;SII;PERIODO;"))
        self.assertIn("00001-00029461", entrega)

    def test_exporte_desconocido_404(self):
        resp = self.servidor.get("/api/exportes/inexistente.xlsx")
        self.assertEqual(resp.estado, 404)
        self.assertEqual(resp.json()["error"]["codigo"], "no_encontrado")
        self.assertEqual(self.servidor.get("/api/exportes/pendientes.pdf").estado, 404)
        self.assertEqual(self.servidor.get("/api/exportes/consumo-oc.xlsx").estado, 400)


if __name__ == "__main__":
    unittest.main()
