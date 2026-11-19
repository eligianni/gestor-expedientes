"""Paso 29: pago eventual — estados, carátula, solicitud (8 párrafos) y uno por proveedor y año."""
import copy
import unittest

from gestor import controles, db, negocio, textos
from tests import ayudas, datos_prueba

OC_VENCIDA = "4500600001"
SAP = "99001"
RAZON = "PROVEEDOR DE PRUEBA S.A."
EX_EVENTUAL = "EX-2026-23468433- -INSSJP-GESP#INSSJP"
FACTURA = "1000-00006268"
CENTAVOS = 2210187213

EVENTUAL = {
    "tipo_factura": "B",
    "establecimiento": "HOSPITAL BERNARDINO RIVADAVIA",
    "establecimiento_detallado": "Hospital Bernardino Rivadavia, sede Av. Las Heras 2670",
    "tipo_servicio": "MANTENIMIENTO PREVENTIVO DE LOS EQUIPOS DE RAYOS X",
    "docfi": "DOCFI-2026-00012345-INSSJP-GESP#INSSJP",
    "orden_docfi": "3",
    "remito": "0001-00009876",
    "documento_remito": "IF-2026-23468500-INSSJP-GESP#INSSJP",
    "orden_remito": "4",
    "providencia_informe": "PV-2026-23468600-INSSJP-GESP#INSSJP",
    "orden_informe": "5",
    "cargo_responsable": "Jefe de Ingeniería Clínica",
    "responsable": "Juan Pérez",
    "cuit": "30-71234567-8",
    "vencimiento_oc": "2026-06-30",
    "expediente_anterior": "EX-2025-11112222- -INSSJP-GESP#INSSJP",
    "providencia_prorroga": "PV-2026-23468700-INSSJP-GESP#INSSJP",
    "orden_prorroga": "12",
    "gerencia": "Gerencia de Efectores Sanitarios Propios",
    "nota_autorizacion": "NO-2026-23468800-INSSJP-GESP#INSSJP",
    "orden_autorizacion": "6",
}

MONTO_P1 = "$ 22.101.872,13.- (PESOS VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100 CENTAVOS)"
GOLDEN_P1 = (
    'Por la presente se solicita el pago eventual de la Factura tipo "B" N° 1000-00006268, de fecha 10/09/2026, '
    "por la suma total de " + MONTO_P1 + ", correspondiente al período del 01/08/2026 al 31/08/2026, "
    "del proveedor PROVEEDOR DE PRUEBA S.A. (SAP 99001), vinculada al expediente EX-2026-23468433- -INSSJP-GESP#INSSJP, "
    "a través del DOCFI-2026-00012345-INSSJP-GESP#INSSJP, vinculado en orden 3."
)
GOLDEN_P5 = (
    "La Orden de Compra N° 4500600001 se encontraba vencida el día 30/06/2026, habiendo sido tramitada por el expediente "
    "EX-2025-11112222- -INSSJP-GESP#INSSJP. No obstante, el proveedor siguió prestando el servicio, manteniéndose el precio "
    "y las bases y condiciones de la contratación. Asimismo, se solicitó la prórroga de dicha Orden de Compra mediante la "
    "PV-2026-23468700-INSSJP-GESP#INSSJP, en orden 12 del citado expediente."
)
GOLDEN_P7 = ("Finalmente, se deja constancia de que este Efector no ha cursado durante el corriente año ningún pedido de "
             "pago eventual a la firma mencionada.")
GOLDEN_P8 = ("Con el Visto Bueno de esta Dirección, y atento a la urgencia y necesidad del caso, por no encontrarse la "
             "prestación bajo marco contractual, se giran las presentes actuaciones para su consideración y prosecución "
             "del trámite.")
GOLDEN_REFERENCIA = ("SOLICITUD PAGO EVENTUAL - EX-2026-23468433- -INSSJP-GESP#INSSJP - HOSPITAL BERNARDINO RIVADAVIA - "
                     "PROVEEDOR DE PRUEBA S.A.")
GOLDEN_CARATULA = "HBI - PAGO EVENTUAL - PROVEEDOR DE PRUEBA S.A. - FC N° 1000-00006268"


def oc_vencida():
    datos = copy.deepcopy(datos_prueba.OC_EFIA_MANUAL)
    datos.update(numero=OC_VENCIDA, sap=SAP, razon_social=RAZON, vig_desde="2025-07-01", vig_hasta="2026-06-30")
    return datos


class PruebaEventual(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        con = db.conectar(self.entorno.ruta_base)
        try:
            negocio.crear_oc_manual(con, oc_vencida())
        finally:
            con.close()

    def _crear(self, factura=FACTURA, fecha="2026-09-10", con_oc=True, eventual=EVENTUAL):
        con = db.conectar(self.entorno.ruta_base)
        try:
            alta = {"tipo": "EVENTUAL", "periodo": "2026-08", "periodo_desde": "2026-08-01",
                    "periodo_hasta": "2026-08-31", "periodo_manual": 1}
            alta.update({"oc": OC_VENCIDA} if con_oc else {"sap": SAP, "efector": "HBI"})
            exp = negocio.crear_expediente(con, alta)
            exp = negocio.actualizar_expediente(con, exp["id"], exp["version"], {"datos": {
                "factura": {"numero": factura, "fecha": fecha, "centavos": CENTAVOS},
                "gde": {"expediente": EX_EVENTUAL},
            }})
            if eventual is not None:
                exp = negocio.guardar_eventual(con, exp["id"], exp["version"], eventual)
            return exp
        finally:
            con.close()

    def _textos(self, exp):
        resp = self.servidor.get("/api/expedientes/%d/textos" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _estado(self, exp, estado):
        return self.servidor.post("/api/expedientes/%d/estado" % exp["id"], {"version": exp["version"], "estado": estado})

    def _repetidos(self, exp):
        con = db.conectar(self.entorno.ruta_base)
        try:
            resultados = controles.controlar(con, exp["id"])["resultados"]
        finally:
            con.close()
        return [r for r in resultados if r["codigo"] == "eventual_repetido"]

    def test_estados_del_eventual(self):
        exp = self._crear()
        self.assertEqual(exp["estado"], "ARMADO")
        self.assertEqual(exp["datos"]["historial"][0]["estado"], "ARMADO")
        self.assertEqual(exp["destinos"], ["EN_DTO_ECONOMICO_CONTABLE"])
        salto = self._estado(exp, "CONTABILIZADO")
        self.assertEqual(salto.estado, 422)
        self.assertEqual(salto.json()["error"]["mensaje"], "No se puede pasar de ARMADO a CONTABILIZADO.")
        for estado in ("EN_DTO_ECONOMICO_CONTABLE", "DEVUELTO", "CONTABILIZADO", "FINALIZADO"):
            resp = self._estado(exp, estado)
            self.assertEqual(resp.estado, 200, resp.texto())
            exp = resp.json()["datos"]
            self.assertEqual(exp["estado"], estado)
        self.assertEqual(exp["destinos"], [])
        # sin OC también nace en ARMADO; un COMUN no conoce los estados del eventual
        sin_oc = self._crear(con_oc=False, eventual=None)
        self.assertEqual(sin_oc["estado"], "ARMADO")
        self.assertIsNone(sin_oc["oc"])
        con = db.conectar(self.entorno.ruta_base)
        try:
            comun = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": OC_VENCIDA})
        finally:
            con.close()
        self.assertEqual(self._estado(comun, "EN_DTO_ECONOMICO_CONTABLE").json()["error"]["mensaje"],
                         "No se puede pasar de BORRADOR a EN_DTO_ECONOMICO_CONTABLE.")

    def test_monto_philips_con_centavos(self):
        solicitud = self._textos(self._crear())["solicitud_pago_eventual"]
        self.assertIn(MONTO_P1, solicitud["parrafos"][0])
        self.assertEqual(solicitud["parrafos"][0], GOLDEN_P1)
        self.assertEqual(solicitud["referencia"], GOLDEN_REFERENCIA)

    def test_solicitud_tiene_ocho_parrafos_sin_corchetes(self):
        solicitud = self._textos(self._crear())["solicitud_pago_eventual"]
        self.assertEqual(len(solicitud["parrafos"]), 8)
        for parrafo in solicitud["parrafos"] + [solicitud["referencia"]]:
            self.assertNotIn("[", parrafo)
            self.assertNotIn("]", parrafo)
            self.assertNotRegex(parrafo, r"^P\d:", parrafo)
        self.assertEqual(solicitud["parrafos"][4], GOLDEN_P5)
        self.assertEqual(solicitud["parrafos"][6], GOLDEN_P7)
        self.assertEqual(solicitud["parrafos"][7], GOLDEN_P8)
        # un campo faltante no deja corchetes: avisa cuál falta
        incompleto = self._crear(eventual=dict(EVENTUAL, docfi=""))
        datos = self._textos(incompleto)
        self.assertNotIn("solicitud_pago_eventual", datos)
        self.assertEqual(datos["solicitud_pago_eventual_error"],
                         "Falta N° DOCUMENTO FINANCIERO/DOCFI en la solicitud de pago eventual.")
        # la API rechaza campos desconocidos
        exp = self.servidor.get("/api/expedientes/%d" % incompleto["id"]).json()["datos"]
        malo = self.servidor.put("/api/expedientes/%d/eventual" % exp["id"],
                                 {"version": exp["version"], "eventual": {"inventado": "x"}})
        self.assertEqual(malo.estado, 400)
        bien = self.servidor.put("/api/expedientes/%d/eventual" % exp["id"],
                                 {"version": exp["version"], "eventual": EVENTUAL})
        self.assertEqual(bien.estado, 200, bien.texto())
        self.assertEqual(len(self._textos(exp)["solicitud_pago_eventual"]["parrafos"]), 8)

    def test_un_eventual_por_proveedor_por_anio(self):
        primero = self._crear()
        segundo = self._crear(factura="1000-00006301", con_oc=False)
        self.assertEqual(self._repetidos(primero), [])
        repetidos = self._repetidos(segundo)
        self.assertEqual(len(repetidos), 1)
        self.assertEqual(repetidos[0]["nivel"], "error")
        self.assertEqual(repetidos[0]["mensaje"],
                         "Ya hay un pago eventual para el proveedor SAP %s en 2026 (expediente %d)." % (SAP, primero["id"]))
        # otro año no cuenta
        de_2027 = self._crear(factura="1000-00007001", fecha="2027-01-15")
        self.assertEqual(self._repetidos(de_2027), [])
        # un COMUN del mismo proveedor no cuenta como eventual
        con = db.conectar(self.entorno.ruta_base)
        try:
            comun = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": OC_VENCIDA})
            negocio.actualizar_expediente(con, comun["id"], comun["version"], {"datos": {
                "factura": {"numero": "1000-00000001", "fecha": "2026-02-10", "centavos": 100}}})
        finally:
            con.close()
        self.assertEqual(len(self._repetidos(segundo)), 1)

    def test_caratula_eventual(self):
        self.assertEqual(textos.caratula_eventual({"sigla": "HBI", "razon": RAZON, "factura": FACTURA}), GOLDEN_CARATULA)
        with self.assertRaises(textos.TextoIncompleto):
            textos.caratula_eventual({"sigla": "HBI", "razon": RAZON, "factura": ""})
        self.assertEqual(self._textos(self._crear())["caratula"], GOLDEN_CARATULA)


if __name__ == "__main__":
    unittest.main()
