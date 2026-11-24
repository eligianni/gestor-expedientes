"""Subrenglones de la OC (1-10, 1-20…): se guardan desde el PDF, sobreviven a la importación y van al certificado."""
import json

from gestor import db, importar, negocio
from tests import ayudas

OC = {
    "numero": "4500581083", "efector": "HBI", "sap": "115819", "razon_social": "ASCENSORES BATTAGLIA SA",
    "fecha_oc": "2026-04-17", "vig_desde": "2026-04-09", "vig_hasta": "2027-04-08", "ca": "43-2025",
    "expediente_contratacion": "EX-2025-18959064- -INSSJP-GESP#INSSJP", "tipo": "SERVICIO", "dia_inicio_periodo": 9,
    "objeto": "servicio de mantenimiento predictivo, preventivo y correctivo de ascensores", "objeto_articulo": "al",
    "renglones": [
        {"pos": 1, "descripcion": "MANT. PREV. Y PRED. ASCENS. Y MONTACARGA", "cantidad": "1", "unidad": "UP",
         "precio_centavos": 3750000000, "desglose_cantidad": "12", "desglose_unidad": "MES", "desglose_precio_centavos": 312500000},
        {"pos": 2, "descripcion": "MANT. CORRECTIVO ASCENS. Y MONTACARGAS", "cantidad": "1", "unidad": "UP",
         "precio_centavos": 1500000000, "desglose_cantidad": "1", "desglose_unidad": "MES", "desglose_precio_centavos": 1500000000},
    ],
}
SUBRENGLONES = {
    "1": [{"pos": 10, "cantidad": "8", "unidad": "MES", "descripcion": "MANT. PRED. PREV DE ASCENSORES Y MONTACARGAS 2026",
           "precio_centavos": 312500000},
          {"pos": 20, "cantidad": "4", "unidad": "MES", "descripcion": "MANT. PRED. PREV DE ASCENSORES Y MONTACARGAS 2027",
           "precio_centavos": 312500000}],
    "2": [{"pos": 10, "cantidad": "1", "unidad": "MES", "descripcion": "MANT. CORRECTIVO PARA ASCENS. Y MONTACARGAS"}],
}


class PruebaSubrenglones(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.ficha = negocio.crear_oc_desde_pdf(self.con, OC, "oc.pdf", {"numero": OC["numero"]}, SUBRENGLONES)

    def _expediente(self, periodo, cantidad):
        exp = negocio.crear_expediente(self.con, {"tipo": "COMUN", "oc": OC["numero"]})
        remitos = [{"numero": "0001-%08d" % (exp["id"] + 100), "fecha": periodo + "-20", "fecha_firma": None,
                    "es_equipo_comodato": False, "aclara_periodo": False,
                    "items": [{"pos": 1, "cantidad": cantidad, "codigo": ""}]}]
        return negocio.actualizar_expediente(self.con, exp["id"], exp["version"], {
            "periodo": periodo, "datos": {"remitos": remitos}})

    def test_se_guardan_y_se_ven_en_la_ficha(self):
        renglones = {r["pos"]: r for r in self.ficha["renglones"]}
        self.assertEqual([(s["pos"], s["cantidad"]) for s in renglones[1]["subrenglones"]], [(10, "8"), (20, "4")])
        self.assertEqual(len(renglones[2]["subrenglones"]), 1)

    def test_el_certificado_desglosa_y_asigna_en_orden(self):
        primero = self._expediente("2026-05", "1")
        filas = negocio.datos_cv(self.con, primero["id"])["datos"]["renglones"]
        self.assertEqual([(f["renglon"], f["cantidad_oc"], f["cantidad_entregada"]) for f in filas],
                         [("1-10", "8", "1"), ("1-20", "4", "0"), ("2-10", "1", "0")])
        self.assertEqual(filas[0]["descripcion"], "MANT. PRED. PREV DE ASCENSORES Y MONTACARGAS 2026")
        # Con los 8 meses de 2026 ya validados, el mes siguiente va al 1-20.
        for mes in ("2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"):
            self._expediente(mes, "1")
        siguiente = self._expediente("2027-01", "1")
        filas = negocio.datos_cv(self.con, siguiente["id"])["datos"]["renglones"]
        self.assertEqual([(f["renglon"], f["cantidad_entregada"]) for f in filas], [("1-10", "0"), ("1-20", "1"), ("2-10", "0")])

    def test_editar_a_mano_y_la_importacion_no_los_borra(self):
        renglon = next(r for r in self.ficha["renglones"] if r["pos"] == 1)
        ficha = negocio.guardar_subrenglones(self.con, OC["numero"], 1, renglon["version"], [
            {"pos": 10, "cantidad": "8", "unidad": "mes", "descripcion": "2026"},
            {"pos": 20, "cantidad": "4", "unidad": "MES", "descripcion": "2027"}])
        renglon = next(r for r in ficha["renglones"] if r["pos"] == 1)
        self.assertEqual([s["descripcion"] for s in renglon["subrenglones"]], ["2026", "2027"])
        self.assertEqual(renglon["subrenglones"][0]["unidad"], "MES")
        # Lo que trae el z_compras2 reemplaza el crudo, pero conserva los subrenglones.
        actual = db.leer_fila(self.con, "renglon", {"oc": OC["numero"], "pos": 1})
        nuevo = importar._con_subrenglones_guardados(actual, {"crudo": {"Centro": "1900"}})
        self.assertEqual(nuevo["crudo"]["Centro"], "1900")
        self.assertEqual(len(nuevo["crudo"]["_subrenglones"]), 2)
        self.assertEqual(json.loads(actual["crudo"])["_subrenglones"][1]["descripcion"], "2027")

    def test_por_api_y_validacion(self):
        renglon = next(r for r in self.ficha["renglones"] if r["pos"] == 2)
        ruta = "/api/oc/%s/renglones/2/subrenglones" % OC["numero"]
        resp = self.servidor.put(ruta, {"version": renglon["version"], "subrenglones": [{"pos": 10, "cantidad": "x"}]})
        self.assertEqual(resp.estado, 400)
        resp = self.servidor.put(ruta, {"version": renglon["version"], "subrenglones": []})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(next(r for r in resp.json()["datos"]["renglones"] if r["pos"] == 2)["subrenglones"], [])

    def test_consumo_marca_agotado(self):
        exp = self._expediente("2026-05", "12")
        fila = next(f for f in negocio.consumo_oc(self.con, OC["numero"])["renglones"] if f["pos"] == 1)
        self.assertTrue(fila["agotado"])
        self.assertEqual(fila["pct_consumido"], 100)
        self.assertTrue(exp["id"])
