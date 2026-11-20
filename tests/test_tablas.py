"""Pantalla Tablas: expedientes, OC y renglones como tablas, y exportación a Excel de lo que se ve."""
import io
import json
from urllib.parse import urlencode

from gestor import db, tablas, xlsx
from tests import ayudas, datos_prueba


class PruebaTablas(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _tabla(self, nombre, consulta=""):
        resp = self.servidor.get("/api/tablas/%s%s" % (nombre, consulta))
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_expedientes(self):
        datos_prueba.armar_expediente_efia(self.con)
        datos_prueba.armar_expediente_biofab(self.con)
        tabla = self._tabla("expedientes")
        self.assertEqual(tabla["titulo"], "Expedientes")
        claves = [c["clave"] for c in tabla["columnas"]]
        for clave in ("id", "estado", "oc", "razon_social", "periodo", "factura", "factura_importe", "gde_expediente"):
            self.assertIn(clave, claves)
        self.assertEqual(len(tabla["filas"]), 2)
        efia = next(f for f in tabla["filas"] if f["oc"] == datos_prueba.OC_EFIA_MANUAL["numero"])
        self.assertEqual(efia["razon_social"], "GRUPO EFIA S.R.L.")
        self.assertEqual(efia["factura_importe"], 122499000)
        self.assertEqual(efia["remitos"], "00001-00029461")
        self.assertEqual(self._tabla("expedientes", "?efector=CASPH")["filas"], [])

    def test_oc_y_renglones(self):
        datos_prueba.importar_hbi_2026(self.con)
        datos_prueba.cargar_efia(self.con)
        oc = self._tabla("oc")
        fila = next(f for f in oc["filas"] if f["numero"] == datos_prueba.OC_MACATEX)
        self.assertEqual((fila["razon_social"], fila["renglones"], fila["importe_centavos"]), ("MACATEX S.A", 6, 3388160000))
        self.assertIsNone(fila["pdf_cargado"])
        renglones = self._tabla("renglones")
        efia = next(f for f in renglones["filas"] if f["oc"] == "4500555861")
        self.assertEqual((efia["desglose_cantidad"], efia["desglose_unidad"], efia["del_pdf"]), ("9", "MES", 0))

    def test_tabla_desconocida(self):
        resp = self.servidor.get("/api/tablas/proveedores")
        self.assertEqual(resp.estado, 404)

    def test_exportar_lo_que_se_ve(self):
        pedido = {
            "nombre": "oc", "titulo": "Órdenes de compra", "filtros": "Proveedor contiene macatex",
            "columnas": [{"titulo": "OC", "tipo": "texto"}, {"titulo": "Importe total", "tipo": "moneda"},
                         {"titulo": "Vigencia desde", "tipo": "fecha"}, {"titulo": "Cantidad", "tipo": "cantidad"},
                         {"titulo": "Excluida", "tipo": "si_no"}],
            "filas": [["4500594643", 3388160000, "2026-08-25", "1.5", 0], ["4500555861", None, None, "9", 1]],
        }
        cuerpo = urlencode({"datos": json.dumps(pedido, ensure_ascii=False)}).encode("utf-8")
        resp = self.servidor.pedir("POST", "/api/tablas/exportar.xlsx", cuerpo,
                                   {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(resp.estado, 200)
        self.assertIn("attachment", resp.cabeceras["Content-Disposition"])
        filas = list(xlsx.leer_filas(io.BytesIO(resp.cuerpo)))
        self.assertTrue(str(filas[0][0]).startswith("Órdenes de compra (Proveedor contiene macatex) — Emitido el "))
        self.assertEqual(list(filas[1]), ["OC", "Importe total", "Vigencia desde", "Cantidad", "Excluida"])
        self.assertEqual(list(filas[2])[:5], ["4500594643", "33881600.00", "25/08/2026", "1,5", "No"])
        self.assertEqual(list(filas[3])[3:5], ["9", "Sí"])

    def test_exportar_pedido_invalido(self):
        cuerpo = urlencode({"datos": "{no es json"}).encode("utf-8")
        resp = self.servidor.pedir("POST", "/api/tablas/exportar.xlsx", cuerpo,
                                   {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(resp.estado, 400)
        with self.assertRaises(ValueError):
            tablas.exportar_xlsx({"columnas": [{"titulo": "A"}], "filas": [["1", "2"]]})


class PruebaTablaEntregas(ayudas.CasoConServidor):

    def test_entregas_abiertas_y_enviadas(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            from gestor import negocio
            datos_prueba.armar_expediente_efia(con)
            abierta = negocio.crear_entrega(con, "HBI", "Entrega de prueba")
        finally:
            con.close()
        resp = self.servidor.get("/api/tablas/entregas")
        self.assertEqual(resp.estado, 200, resp.texto())
        filas = resp.json()["datos"]["filas"]
        self.assertEqual(len(filas), 1)
        self.assertEqual((filas[0]["numero"], filas[0]["estado"], filas[0]["expedientes"]), (abierta["numero"], "Abierta (en armado)", 0))
        claves = [c["clave"] for c in resp.json()["datos"]["columnas"]]
        self.assertIn("importe", claves)
