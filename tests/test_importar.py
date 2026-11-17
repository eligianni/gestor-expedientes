"""Paso 5: importador z_compras2 (conteos con los dos reportes reales, upsert, campos manuales, crudo)."""
import json
import unittest
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

from gestor import db, importar, xlsx
from tests import ayudas

AVISO = (
    "Este reporte no tiene la partida presupuestaria; no se pueden descartar honorarios (3490000). "
    "Agregá la columna al layout del z_compras2."
)


def _letra_columna(numero):
    letras = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(ord("A") + resto) + letras
    return letras


def crear_xlsx(ruta, encabezados, filas):
    """Arma un .xlsx mínimo (una hoja, celdas inlineStr) con zipfile."""
    def fila_xml(numero, valores):
        celdas = []
        for i, valor in enumerate(valores, start=1):
            if valor is None:
                continue
            ref = "%s%d" % (_letra_columna(i), numero)
            celdas.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, escape(str(valor))))
        return '<row r="%d">%s</row>' % (numero, "".join(celdas))

    filas_xml = [fila_xml(1, encabezados)] + [fila_xml(i + 2, fila) for i, fila in enumerate(filas)]
    hoja = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>%s</sheetData></worksheet>" % "".join(filas_xml)
    )
    libro = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", libro)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/worksheets/sheet1.xml", hoja)
    return ruta


class PruebaImportar(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.parametros = self.entorno.config["parametros_iniciales"]
        db.inicializar(self.entorno.ruta_base, self.parametros)
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _contar(self, sql, parametros=()):
        return self.con.execute(sql, parametros).fetchone()[0]

    def test_analizar_hbi_2026_cuenta_descartes(self):
        informe = importar.analizar(ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        self.assertEqual(informe["filas"], 3074)
        self.assertEqual(informe["descartes"], {"sin_oc": 2, "partida": 0, "centro": 2639, "exclusion_manual": 0})
        self.assertEqual(informe["quedan"], 433)
        self.assertEqual(informe["oc_distintas"], 107)
        self.assertEqual(informe["duplicados"], 0)
        self.assertIn(AVISO, informe["avisos"])
        self.assertEqual(self._contar("SELECT COUNT(*) FROM renglon"), 0)  # vista previa: no escribe

    def test_analizar_por_partida_cuenta_descartes(self):
        informe = importar.analizar(ayudas.XLSX_POR_PARTIDA, "HBI", self.parametros)
        self.assertEqual(informe["filas"], 5897)
        self.assertEqual(informe["descartes"], {"sin_oc": 16, "partida": 5402, "centro": 192, "exclusion_manual": 0})
        self.assertEqual(informe["quedan"], 287)
        self.assertEqual(informe["oc_distintas"], 108)
        self.assertEqual(informe["duplicados"], 0)
        self.assertNotIn(AVISO, informe["avisos"])

    def test_aviso_sin_partida(self):
        informe = importar.analizar(ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        self.assertEqual(informe["avisos"].count(AVISO), 1)
        self.assertEqual(informe["descartes"]["partida"], 0)
        self.assertEqual(informe["quedan"], 433)

    def test_importar_ambos_y_reimportar(self):
        for orden in ((ayudas.XLSX_HBI_2026, ayudas.XLSX_POR_PARTIDA), (ayudas.XLSX_POR_PARTIDA, ayudas.XLSX_HBI_2026)):
            with self.subTest(primero=orden[0].name):
                entorno = ayudas.EntornoTemporal()
                self.addCleanup(entorno.cerrar)
                db.inicializar(entorno.ruta_base, self.parametros)
                con = db.conectar(entorno.ruta_base)
                try:
                    for ruta in orden:
                        importar.importar(con, ruta, "HBI", self.parametros, archivo=ruta.name)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM renglon").fetchone()[0], 574)
                    for ruta in orden:
                        informe = importar.importar(con, ruta, "HBI", self.parametros, archivo=ruta.name)
                        self.assertEqual(informe["altas"], 0)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM renglon").fetchone()[0], 574)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM importacion").fetchone()[0], 4)
                    self.assertEqual(
                        con.execute("SELECT COUNT(*) FROM evento WHERE accion = 'IMPORTACION'").fetchone()[0], 4,
                    )
                    sin_ceros = con.execute("SELECT COUNT(*) FROM proveedor WHERE sap LIKE '0%'").fetchone()[0]
                    self.assertEqual(sin_ceros, 0)
                finally:
                    con.close()

    def test_falta_columna_obligatoria(self):
        encabezados, filas = xlsx.leer_tabla(ayudas.XLSX_HBI_2026)
        sin_importe = [e for e in encabezados if e != "Importe"]
        ruta = crear_xlsx(
            self.entorno.dir / "sin_importe.xlsx",
            sin_importe,
            [[fila[e] for e in sin_importe] for fila in filas[:20]],
        )
        with self.assertRaises(importar.ErrorImportacion) as contexto:
            importar.importar(self.con, ruta, "HBI", self.parametros)
        self.assertEqual(str(contexto.exception), 'Falta la columna obligatoria "Importe" en el reporte.')
        for tabla in ("proveedor", "oc", "renglon", "importacion", "evento"):
            self.assertEqual(self._contar("SELECT COUNT(*) FROM %s" % tabla), 0, tabla)

    def test_precio_derivado_cuando_falta_columna(self):
        importar.importar(self.con, ayudas.XLSX_POR_PARTIDA, "HBI", self.parametros)
        filas = self.con.execute("SELECT cantidad, precio_centavos, crudo FROM renglon").fetchall()
        self.assertEqual(len(filas), 287)
        revisadas = 0
        for fila in filas:
            crudo = json.loads(fila["crudo"])
            cantidad = Decimal(crudo["Cant"])
            if cantidad == 0:
                continue
            esperado = (Decimal(crudo["Importe"]) / cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.assertEqual(fila["precio_centavos"], int(esperado * 100), crudo)
            revisadas += 1
        self.assertGreater(revisadas, 0)

    def test_campos_manuales_no_se_pisan(self):
        importar.importar(self.con, ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        oc = db.leer_fila(self.con, "oc", {"numero": "4500563620"})
        self.assertIsNotNone(oc)
        renglon = db.leer_fila(self.con, "renglon", {"oc": "4500563620", "pos": 1})
        with db.transaccion(self.con):
            db.actualizar_con_version(self.con, "oc", {"numero": "4500563620"}, oc["version"], {
                "vig_hasta": "2026-12-31", "campos_manuales": ["vig_hasta"],
            })
            db.actualizar_con_version(self.con, "renglon", {"oc": "4500563620", "pos": 1}, renglon["version"], {
                "descripcion": "EDITADO A MANO", "campos_manuales": ["descripcion"],
            })
        importar.importar(self.con, ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        self.assertEqual(db.leer_fila(self.con, "oc", {"numero": "4500563620"})["vig_hasta"], "2026-12-31")
        self.assertEqual(
            db.leer_fila(self.con, "renglon", {"oc": "4500563620", "pos": 1})["descripcion"], "EDITADO A MANO",
        )

    def test_exclusion_manual_por_oc(self):
        parametros = json.loads(json.dumps(self.parametros))
        parametros["exclusiones"] = {"sap": [], "oc": ["4500563620"]}
        base = importar.analizar(ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        informe = importar.importar(self.con, ayudas.XLSX_HBI_2026, "HBI", parametros)
        self.assertGreater(informe["descartes"]["exclusion_manual"], 0)
        self.assertEqual(informe["quedan"] + informe["descartes"]["exclusion_manual"], base["quedan"])
        self.assertEqual(informe["oc_distintas"], base["oc_distintas"] - 1)
        self.assertIsNone(db.leer_fila(self.con, "oc", {"numero": "4500563620"}))
        # también por SAP (sin ceros a la izquierda o con ellos)
        parametros["exclusiones"] = {"sap": ["0000115819"], "oc": []}
        por_sap = importar.analizar(ayudas.XLSX_HBI_2026, "HBI", parametros)
        self.assertGreater(por_sap["descartes"]["exclusion_manual"], 0)

    def test_crudo_guarda_fila_original(self):
        importar.importar(self.con, ayudas.XLSX_HBI_2026, "HBI", self.parametros)
        encabezados, _ = xlsx.leer_tabla(ayudas.XLSX_HBI_2026)
        for fila in self.con.execute("SELECT crudo FROM renglon").fetchall():
            crudo = json.loads(fila["crudo"])
            self.assertEqual(set(crudo.keys()), set(encabezados))
        fila = db.leer_fila(self.con, "renglon", {"oc": "4500563620", "pos": 1})
        crudo = json.loads(fila["crudo"])
        self.assertEqual(crudo["Proveedor"], "0000115819")
        self.assertEqual(crudo["Número de Expediente GDE"], "EX-2025-18959064-   -INSSJP-GESP#INSSJP")
        oc = db.leer_fila(self.con, "oc", {"numero": "4500563620"})
        self.assertEqual(oc["sap"], "115819")
        self.assertEqual(oc["expediente_contratacion"], "EX-2025-18959064- -INSSJP-GESP#INSSJP")
        self.assertEqual(oc["ca"], "43-2025")
        self.assertEqual(oc["fecha_oc"], "2025-11-10")


if __name__ == "__main__":
    unittest.main()
