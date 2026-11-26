"""Tramitación desde la entrega: se agregan expedientes con remito, factura y EX; los IF se cargan por fila; la factura en
SAP lleva su N° de documento (preliminar → definitiva) y, con todos los IF, se marca el pase a Contable.
"""
from gestor import db, negocio
from tests import ayudas, datos_prueba

EX = "EX-2026-11112222- -INSSJP-GESP#INSSJP"


def _if(n):
    return "IF-2026-%08d-INSSJP-GESP#INSSJP" % n


class PruebaTramitacionEntrega(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.exp = datos_prueba.armar_expediente_efia(self.con)

    def _ok(self, resp):
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _tramitar(self, accion, **valores):
        resp = self.servidor.post("/api/expedientes/%d/tramite" % self.exp["id"],
                                  dict(valores, version=self.exp["version"], accion=accion))
        if resp.estado == 200:
            self.exp = resp.json()["datos"]
        return resp

    def _entrega(self):
        return self._ok(self.servidor.post("/api/entregas", {"efector": "HBI", "nombre": ""}))

    def test_se_agrega_con_remito_factura_y_ex(self):
        entrega = self._entrega()
        sin_ex = self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                    {"version": entrega["version"], "expedientes": [self.exp["id"]]})
        self.assertEqual(sin_ex.estado, 422)
        self.assertIn("EX", sin_ex.json()["error"]["mensaje"])
        self._tramitar("caratular", expediente=EX)
        listos = self._ok(self.servidor.get("/api/entregas?efector=HBI"))["firmados_sin_entrega"]
        self.assertEqual([x["id"] for x in listos], [self.exp["id"]])
        entrega = self._ok(self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                              {"version": entrega["version"], "expedientes": [self.exp["id"]]}))
        self.assertEqual([x["id"] for x in entrega["expedientes"]], [self.exp["id"]])

    def test_if_por_fila_factura_y_pase(self):
        self._tramitar("caratular", expediente=EX)
        entrega = self._entrega()
        self._ok(self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                    {"version": entrega["version"], "expedientes": [self.exp["id"]]}))
        self.exp = negocio.obtener_expediente(self.con, self.exp["id"])  # la asignación le cambió la versión
        tramitacion = self._ok(self.servidor.get("/api/entregas/%d/tramitacion" % entrega["id"]))
        fila = tramitacion["expedientes"][0]
        self.assertEqual(fila["factura_sap"]["expediente"], EX)
        self.assertIn("autorizacion", fila["faltan_if"])
        self.assertEqual(self._tramitar("pase", gde=_if(9)).estado, 422)
        # La fila: todos los IF juntos; con la autorización queda FIRMADO.
        remito = self.exp["datos"]["remitos"][0]["numero"]
        self.assertEqual(self._tramitar("gde_fila", gde={
            "factura": _if(1), "sii": _if(2), "remitos": {remito: _if(3)}, "cv": _if(4), "vale_hoja": _if(5),
            "autorizacion": _if(6)}).estado, 200)
        self.assertEqual(self.exp["estado"], "FIRMADO")
        fila = self._ok(self.servidor.get("/api/entregas/%d/tramitacion" % entrega["id"]))["expedientes"][0]
        self.assertEqual(fila["faltan_if"], ["contabilizacion"])
        self._tramitar("gde_fila", gde={"contabilizacion": _if(7)})
        self.assertEqual(self._tramitar("pase", gde=_if(7)).estado, 200)
        self.assertEqual(self.exp["estado"], "COMPLETO")
        self._tramitar("sin_pase")
        self.assertEqual((self.exp["estado"], self.exp["datos"]["tramite"]["pase"]), ("FIRMADO", None))
        # Factura en SAP: N° de documento → preliminar; después definitiva.
        self.assertEqual(self._tramitar("factura_doc", documento="").estado, 400)
        self._tramitar("factura_doc", documento="5105600123")
        tramite = self.exp["datos"]["tramite"]
        self.assertEqual((tramite["factura_sap_doc"], tramite["factura_sap_estado"]), ("5105600123", "PRELIMINAR"))
        self._tramitar("factura_estado", estado="DEFINITIVA")
        self.assertEqual(self.exp["datos"]["tramite"]["factura_sap_estado"], "DEFINITIVA")

    def test_anular_entrega_vacia(self):
        entrega = self._entrega()
        self.assertEqual(self.servidor.post("/api/entregas/%d/anular" % entrega["id"],
                                            {"version": entrega["version"], "motivo": ""}).estado, 400)
        anulada = self._ok(self.servidor.post("/api/entregas/%d/anular" % entrega["id"],
                                              {"version": entrega["version"], "motivo": "Creada de más"}))
        self.assertTrue(anulada["anulada"])
        lista = self._ok(self.servidor.get("/api/entregas?efector=HBI"))["entregas"]
        self.assertTrue(lista[0]["anulada"])
        self._tramitar("caratular", expediente=EX)
        resp = self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                  {"version": anulada["version"], "expedientes": [self.exp["id"]]})
        self.assertEqual(resp.estado, 422)

    def test_no_se_anula_con_expedientes(self):
        self._tramitar("caratular", expediente=EX)
        entrega = self._entrega()
        entrega = self._ok(self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                              {"version": entrega["version"], "expedientes": [self.exp["id"]]}))
        resp = self.servidor.post("/api/entregas/%d/anular" % entrega["id"], {"version": entrega["version"], "motivo": "x"})
        self.assertEqual(resp.estado, 422)
