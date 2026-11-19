"""Paso 28: mantenimiento correctivo — estados, informe económico, % convalidado, referencia e informe mensual."""
import unittest

from gestor import db, negocio, textos
from tests import ayudas, datos_prueba

OC_ASCENSORES = "4500587755"
EX_CORRECTIVO = "EX-2026-75399232- -INSSJP-GESP#INSSJP"
OBJETO_OC = "servicio de mantenimiento preventivo, predictivo y correctivo de ascensores"
CORRECTIVO = {
    "procedimiento": "CAM 12/2026",
    "objeto_correctivo": "reparación de puertas de cabina del ascensor 2",
    "presupuestos": [{"proveedor": "ASCENSORES BATTAGLIA SA", "centavos": 500000000},
                     {"proveedor": "ELEVAR S.R.L.", "centavos": 870000000}],
    "informes": ["IF-2026-75400001-INSSJP-GESP#INSSJP"],
    "monto_convalidado": 500000000,
}

GOLDEN_INFORME = (
    "INFORME ECONÓMICO - MANTENIMIENTO CORRECTIVO\n"
    "Orden de Compra N° 4500587755 - ASCENSORES BATTAGLIA SA (SAP 115819) - reparación de puertas de cabina del ascensor 2\n"
    "Presupuesto menor: $ 5.000.000,00\n"
    "Presupuesto mayor: $ 8.700.000,00\n"
    "Diferencia entre presupuestos: $ 3.700.000,00 (74 %).\n"
    "Monto a convalidar frente al renglón de correctivo: $ 5.000.000,00 de $ 5.000.000,00 (100 %)."
)
GOLDEN_REFERENCIA = ("115819 ASCENSORES BATTAGLIA SA - OC 4500587755 - CAM 12/2026 - " + OBJETO_OC
                     + " - MANTENIMIENTO CORRECTIVO - reparación de puertas de cabina del ascensor 2")


def preparar_oc_ascensores(con):
    """OC del reporte 2026 con objeto, prórroga y el renglón 2 (MANT. CORRECTIVO) marcado es_correctivo."""
    datos_prueba.importar_hbi_2026(con)
    oc = negocio.ficha_oc(con, OC_ASCENSORES)["oc"]
    negocio.actualizar_oc(con, OC_ASCENSORES, oc["version"], {"objeto": OBJETO_OC, "prorroga": "2026-12-31"})
    renglon = next(r for r in negocio.ficha_oc(con, OC_ASCENSORES)["renglones"] if r["pos"] == 2)
    negocio.actualizar_renglon(con, OC_ASCENSORES, 2, renglon["version"], {"es_correctivo": 1})


def factura_y_sii(con):
    parametros = db.leer_parametros(con)
    sii = parametros["sii"]
    return {
        "factura": {"numero": "0005B00001234", "fecha": "2026-09-05", "centavos": 500000000, "cae": "76123456789012",
                    "vto_cae": "2026-09-15", "destinatario": "INSSJP", "domicilio": "Perú 169 CABA"},
        "sii": {"orden_compra": OC_ASCENSORES, "nro_comprobante": "0005-00001234", "cae": "76123456789012",
                "monto_centavos": 500000000, "periodo": "2026-08", "area": sii["area"],
                "tipo_servicio": sii["tipo_servicio"], "concepto": sii["concepto"]},
        "gde": {"expediente": EX_CORRECTIVO},
    }


class PruebaCorrectivo(ayudas.CasoConServidor):

    def _armar(self, con_correctivo=True):
        con = db.conectar(self.entorno.ruta_base)
        try:
            preparar_oc_ascensores(con)
            exp = negocio.crear_expediente(con, {"tipo": "CORRECTIVO", "oc": OC_ASCENSORES, "periodo": "2026-08",
                                                 "periodo_desde": "2026-08-01", "periodo_hasta": "2026-08-31",
                                                 "periodo_manual": 1})
            exp = negocio.pegar_remitos(con, exp["id"], exp["version"], "0001-00004567;20/08/2026")
            exp = negocio.actualizar_expediente(con, exp["id"], exp["version"], {"datos": factura_y_sii(con)})
            if con_correctivo:
                exp = negocio.guardar_correctivo(con, exp["id"], exp["version"], CORRECTIVO)
            return exp
        finally:
            con.close()

    def _estado(self, exp, estado):
        return self.servidor.post("/api/expedientes/%d/estado" % exp["id"], {"version": exp["version"], "estado": estado})

    def _textos(self, exp):
        resp = self.servidor.get("/api/expedientes/%d/textos" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_estados_del_correctivo(self):
        exp = self._armar()
        self.assertEqual(exp["estado"], "RECIBIDO_MANTENIMIENTO")
        self.assertEqual(exp["datos"]["historial"][0]["estado"], "RECIBIDO_MANTENIMIENTO")
        salto = self._estado(exp, "PARA_FACTURAR")
        self.assertEqual(salto.estado, 422)
        self.assertEqual(salto.json()["error"]["mensaje"], "No se puede pasar de RECIBIDO_MANTENIMIENTO a PARA_FACTURAR.")
        for estado in ("INFORME_ECONOMICO", "DEVUELTO", "PARA_FACTURAR", "CONTROLADO"):
            resp = self._estado(exp, estado)
            self.assertEqual(resp.estado, 200, resp.texto())
            exp = resp.json()["datos"]
            self.assertEqual(exp["estado"], estado)
        # desde CONTROLADO sigue el flujo común
        exp = self._estado(exp, "EN_FIRMA").json()["datos"]
        self.assertEqual(exp["estado"], "EN_FIRMA")
        # un COMUN no conoce los estados del correctivo
        con = db.conectar(self.entorno.ruta_base)
        try:
            comun = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": OC_ASCENSORES})
        finally:
            con.close()
        self.assertEqual(comun["estado"], "BORRADOR")
        self.assertEqual(self._estado(comun, "INFORME_ECONOMICO").json()["error"]["mensaje"],
                         "No se puede pasar de BORRADOR a INFORME_ECONOMICO.")

    def test_informe_economico_ascensor(self):
        exp = self._armar()
        datos = self._textos(exp)
        self.assertEqual(datos["informe_economico"], GOLDEN_INFORME)
        self.assertIn("Diferencia entre presupuestos: $ 3.700.000,00 (74 %).", datos["informe_economico"].split("\n"))
        with self.assertRaises(textos.TextoIncompleto):
            textos.informe_economico({"sap": "1", "razon": "X", "oc": "2", "objeto_correctivo": "y",
                                      "presupuestos": [{"centavos": 1}], "monto_convalidado": 1,
                                      "importe_renglon_correctivo": 1})
        otro = self._armar_otro()
        con = db.conectar(self.entorno.ruta_base)
        try:
            ctx = negocio.contexto_textos(con, otro["id"])
        finally:
            con.close()
        with self.assertRaisesRegex(textos.TextoIncompleto, "^Falta cargar el objeto del correctivo.$"):
            textos.informe_economico(ctx)

    def _armar_otro(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            return negocio.crear_expediente(con, {"tipo": "CORRECTIVO", "oc": OC_ASCENSORES, "periodo": "2026-09",
                                                  "periodo_desde": "2026-09-01", "periodo_hasta": "2026-09-30"})
        finally:
            con.close()

    def test_porcentaje_convalidado(self):
        exp = self._armar()
        self.assertEqual(self._textos(exp)["correctivo"],
                         {"importe_renglon": 500000000, "monto_convalidado": 500000000, "porcentaje_convalidado": 100})
        self.assertEqual(negocio.porcentaje_convalidado(500000000, 500000000), 100)
        self.assertEqual(negocio.porcentaje_convalidado(250000001, 500000000), 50)
        self.assertEqual(negocio.porcentaje_convalidado(None, 500000000), None)
        # por la API: un importe con decimales (float) se rechaza
        exp = self.servidor.get("/api/expedientes/%d" % exp["id"]).json()["datos"]
        malo = self.servidor.put("/api/expedientes/%d/correctivo" % exp["id"],
                                 {"version": exp["version"], "correctivo": dict(CORRECTIVO, monto_convalidado=12.5)})
        self.assertEqual(malo.estado, 400)
        bien = self.servidor.put("/api/expedientes/%d/correctivo" % exp["id"],
                                 {"version": exp["version"], "correctivo": dict(CORRECTIVO, monto_convalidado=375000000)})
        self.assertEqual(bien.estado, 200, bien.texto())
        self.assertEqual(self._textos(exp)["correctivo"]["porcentaje_convalidado"], 75)

    def test_referencia_correctivo(self):
        exp = self._armar()
        self.assertEqual(self._textos(exp)["referencia_correctivo"], GOLDEN_REFERENCIA)

    def test_informe_mensual(self):
        exp = self._armar()
        self._armar_otro()  # 2026-09: no entra en agosto
        resp = self.servidor.get("/api/correctivos/informe-mensual?mes=2026-08")
        self.assertEqual(resp.estado, 200, resp.texto())
        filas = resp.json()["datos"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0], {
            "id": exp["id"], "expediente": EX_CORRECTIVO, "oc": OC_ASCENSORES, "procedimiento": "CAM 12/2026",
            "adjudicatario": "ASCENSORES BATTAGLIA SA", "detalle": "reparación de puertas de cabina del ascensor 2",
            "monto": 500000000,
        })
        self.assertEqual(self.servidor.get("/api/correctivos/informe-mensual?mes=agosto").estado, 400)


if __name__ == "__main__":
    unittest.main()
