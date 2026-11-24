"""Consumo cargado a mano en meses ya facturados que no tienen remitos (p. ej. expedientes migrados)."""
from gestor import db, negocio
from tests import ayudas, datos_prueba


class PruebaConsumoManual(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        datos_prueba.cargar_efia(self.con)
        self.oc = datos_prueba.OC_EFIA_MANUAL["numero"]
        self.exp = negocio.crear_expediente(self.con, {"tipo": "COMUN", "oc": self.oc})

    def _guardar(self, cantidades, version=None):
        return self.servidor.put("/api/expedientes/%s/consumo-manual" % self.exp["id"],
                                        {"version": version or self.exp["version"], "cantidades": cantidades})

    def test_carga_y_suma_al_consumo_de_la_oc(self):
        ficha = negocio.ficha_oc(self.con, self.oc)
        fila = next(x for x in ficha["expedientes"] if x["id"] == self.exp["id"])
        self.assertEqual((fila["consumo_remitos"], fila["consumo_manual"], fila["importe_centavos"]), (False, {}, None))
        pos = ficha["renglones"][0]["pos"]
        resp = self._guardar({str(pos): "1,5"})
        self.assertEqual(resp.estado, 200, resp.texto())
        consumo = negocio.consumo_oc(self.con, self.oc)
        renglon = next(r for r in consumo["renglones"] if r["pos"] == pos)
        self.assertEqual(renglon["validado"], "1.5")
        fila = next(x for x in negocio.ficha_oc(self.con, self.oc)["expedientes"] if x["id"] == self.exp["id"])
        self.assertEqual(fila["consumo_manual"], {str(pos): "1.5"})
        evento = self.con.execute("SELECT accion FROM evento WHERE tabla = 'expediente' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(evento["accion"], "MODIFICACION")

    def test_valida_renglon_cantidad_y_version(self):
        self.assertEqual(self._guardar({"99": "1"}).estado, 400)
        pos = negocio.ficha_oc(self.con, self.oc)["renglones"][0]["pos"]
        self.assertEqual(self._guardar({str(pos): "abc"}).estado, 400)
        self.assertEqual(self._guardar({str(pos): "-1"}).estado, 400)
        self.assertEqual(self._guardar({str(pos): "1"}, version=self.exp["version"] + 5).estado, 409)

    def test_con_remitos_no_se_carga_a_mano(self):
        con_remitos = datos_prueba.armar_expediente_efia(self.con)
        pos = negocio.ficha_oc(self.con, self.oc)["renglones"][0]["pos"]
        resp = self.servidor.put("/api/expedientes/%s/consumo-manual" % con_remitos["id"],
                                        {"version": con_remitos["version"], "cantidades": {str(pos): "1"}})
        self.assertEqual(resp.estado, 422)
        fila = next(x for x in negocio.ficha_oc(self.con, self.oc)["expedientes"] if x["id"] == con_remitos["id"])
        self.assertTrue(fila["consumo_remitos"])
        self.assertEqual(fila["importe_centavos"], 122499000)


class PruebaPdfEnLista(ayudas.CasoConServidor):

    def test_lista_marca_si_tiene_pdf(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
            fila = next(f for f in negocio.listar_oc(con) if f["numero"] == datos_prueba.OC_EFIA_MANUAL["numero"])
            self.assertFalse(fila["pdf_cargado"])
            self.assertIn("concepto_corto", fila)
            with db.transaccion(con):
                db.registrar_evento(con, "IMPORTACION", "oc", {"numero": fila["numero"]}, None,
                                    {"fuente": "pdf_oc", "archivo": "oc.pdf"})
            fila = next(f for f in negocio.listar_oc(con) if f["numero"] == fila["numero"])
            self.assertTrue(fila["pdf_cargado"])
            self.assertEqual(negocio.ultimo_pdf_oc(con, fila["numero"])["archivo"], "oc.pdf")
        finally:
            con.close()
