"""Trámite del expediente en el orden real: CV en firma → caratular (EX) → GDE → autorización en firma/firmada → pase.

El pase al buzón de Contable deja el expediente COMPLETO; la entrega se envía después, con todos los expedientes completos.
"""
from gestor import db, negocio
from tests import ayudas, datos_prueba

EX = "EX-2026-11112222- -INSSJP-GESP#INSSJP"
IF_CV = "IF-2026-33334444-INSSJP-GESP#INSSJP"
IF_AUT = "IF-2026-55556666-INSSJP-GESP#INSSJP"
IF_CONT = "IF-2026-77778888-INSSJP-GESP#INSSJP"


class PruebaTramite(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.exp = datos_prueba.armar_expediente_efia(self.con)

    def _tramitar(self, accion, **valores):
        resp = self.servidor.post("/api/expedientes/%d/tramite" % self.exp["id"],
                                  dict(valores, version=self.exp["version"], accion=accion))
        if resp.estado == 200:
            self.exp = resp.json()["datos"]
        return resp

    def test_circuito_completo(self):
        self.assertEqual(self._tramitar("cv_en_firma", hecho=True).estado, 200)
        self.assertTrue(self.exp["datos"]["tramite"]["cv_en_firma"])
        self._tramitar("cv_firmado", gde=IF_CV)
        self._tramitar("ingreso_sap", hecho=True)
        self.assertEqual(self.exp["estado"], "BORRADOR")
        self.assertEqual(self._tramitar("caratular", expediente=EX).estado, 200)
        self.assertEqual((self.exp["estado"], self.exp["datos"]["gde"]["expediente"]), ("CONTROLADO", EX))
        self.assertEqual(self.exp["datos"]["gde"]["cv"], IF_CV)
        # La carga en GDE suma números sin borrar los otros.
        self._tramitar("gde", gde={"factura": "IF-2026-10000001-INSSJP-GESP#INSSJP"})
        # El pase pide todos los IF: se cargan los que faltan.
        remito = self.exp["datos"]["remitos"][0]["numero"]
        self._tramitar("gde", gde={"sii": "IF-2026-10000002-INSSJP-GESP#INSSJP", "vale_hoja": "IF-2026-10000003-INSSJP-GESP#INSSJP",
                                   "remitos": {remito: "IF-2026-10000004-INSSJP-GESP#INSSJP"}})
        self.assertEqual((self.exp["datos"]["gde"]["factura"], self.exp["datos"]["gde"]["expediente"]),
                         ("IF-2026-10000001-INSSJP-GESP#INSSJP", EX))
        self._tramitar("factura_sap", hecho=True)
        self._tramitar("autorizacion_en_firma")
        self.assertEqual(self.exp["estado"], "EN_FIRMA")
        self._tramitar("autorizacion_firmada", gde=IF_AUT)
        self.assertEqual((self.exp["estado"], self.exp["datos"]["gde"]["autorizacion"]), ("FIRMADO", IF_AUT))
        self._tramitar("pase", gde=IF_CONT)
        self.assertEqual((self.exp["estado"], self.exp["datos"]["gde"]["contabilizacion"]), ("COMPLETO", IF_CONT))
        self.assertTrue(self.exp["datos"]["tramite"]["pase"])
        # Completo entra en la entrega y al enviarla pasa a ENVIADO.
        entrega = self.servidor.post("/api/entregas", {"efector": "HBI", "nombre": ""}).json()["datos"]
        entrega = self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                     {"version": entrega["version"], "expedientes": [self.exp["id"]]}).json()["datos"]
        enviada = self.servidor.post("/api/entregas/%d/enviar" % entrega["id"], {"version": entrega["version"], "fecha": "2026-10-20"})
        self.assertEqual(enviada.estado, 200, enviada.texto())
        self.assertEqual(negocio.obtener_expediente(self.con, self.exp["id"])["estado"], "ENVIADO")

    def test_pasos_fuera_de_orden(self):
        resp = self._tramitar("autorizacion_en_firma")
        self.assertEqual(resp.estado, 422)
        self.assertIn("expediente", resp.json()["error"]["mensaje"])
        self.assertEqual(self._tramitar("pase", gde=IF_CONT).estado, 422)
        self.assertEqual(self._tramitar("caratular", expediente="").estado, 400)
        self.assertEqual(self._tramitar("otra_cosa").estado, 400)

    def test_textos_del_tramite(self):
        self._tramitar("caratular", expediente=EX)
        textos = self.servidor.get("/api/expedientes/%d/tramite" % self.exp["id"]).json()["datos"]
        self.assertEqual(textos["caratulacion"]["codigo_tramite"], "PAMI00058")
        self.assertEqual(textos["factura_sap"]["expediente"], EX)
        self.assertEqual(textos["entrada_sap"]["tipo"], "SERVICIO")
        self.assertIn("CERTIFICADO DE VALIDACIÓN", textos["referencia_cv"])
        self.assertIn("AUTORIZO", textos["autorizacion"]["cuerpo"])

    def test_antes_de_la_factura_ya_hay_cv_e_ingreso(self):
        nuevo = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": self.exp["oc"]}).json()["datos"]
        resp = self.servidor.get("/api/expedientes/%d/tramite" % nuevo["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        textos = resp.json()["datos"]
        self.assertIn("caratula_error", textos)
        self.assertIn("factura_sap_error", textos)
