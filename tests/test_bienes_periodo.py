"""Período sugerido por la fecha del remito, y certificado de bienes (sin vigencia, mes del remito, entrega total o parcial)."""
from gestor import db, negocio
from tests import ayudas


def _oc(numero, tipo, cantidad="1400", **extra):
    datos = {"numero": numero, "efector": "HBI", "sap": "89023", "razon_social": "BIO PROTEC SRL",
             "expediente_contratacion": "EX-2026-10444574- -INSSJP-GESP#INSSJP", "ca": "52-2026",
             "objeto": "adquisición de sondas, equipos de infusión, tubuladoras y otros descartables",
             "objeto_articulo": "a la", "tipo": tipo,
             "renglones": [{"pos": 1, "descripcion": "EQUIPO DE CIRUGIA GENERAL", "cantidad": cantidad, "unidad": "UN",
                            "precio_centavos": 100}]}
    datos.update(extra)
    return datos


class PruebaPeriodoPorRemito(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _con_remito(self, oc, fecha, firma=None, cantidad="1400"):
        exp = negocio.crear_expediente(self.con, {"tipo": "COMUN", "oc": oc})
        exp = negocio.pegar_remitos(self.con, exp["id"], exp["version"], None,
                                    remitos=[{"numero": "0009-00000268", "fecha": fecha, "fecha_firma": firma}])
        remitos = exp["datos"]["remitos"]
        remitos[0]["items"] = [{"pos": 1, "cantidad": cantidad, "codigo": ""}]
        return negocio.actualizar_expediente(self.con, exp["id"], exp["version"], {"datos": {"remitos": remitos}})

    def test_bien_mes_del_remito_y_certificado(self):
        # La OC tiene fecha 03/09 (de ahí salía un «día de inicio» 3): en bienes no cuenta, va el mes del remito.
        negocio.crear_oc_manual(self.con, _oc("4500595494", "BIEN", vig_desde="2026-09-03", dia_inicio_periodo=3))
        exp = self._con_remito("4500595494", "2026-09-10")
        self.assertEqual((exp["periodo"], exp["periodo_desde"], exp["periodo_hasta"]), ("2026-09", "2026-09-01", "2026-09-30"))
        cv = negocio.datos_cv(self.con, exp["id"])["datos"]
        self.assertEqual((cv["vigencia"], cv["periodo_texto"], cv["entrega"]), ("-", "SEPTIEMBRE 2026", "Total"))
        self.assertEqual((cv["renglones"][0]["cantidad_entregada"], cv["renglones"][0]["fecha_entrega"]), ("1400", "10/09/2026"))

    def test_bien_entrega_parcial(self):
        negocio.crear_oc_manual(self.con, _oc("4500595495", "BIEN"))
        exp = self._con_remito("4500595495", "2026-09-10", cantidad="400")
        self.assertEqual(negocio.datos_cv(self.con, exp["id"])["datos"]["entrega"], "Parcial")

    def test_servicio_periodo_especifico_del_15_al_14(self):
        negocio.crear_oc_manual(self.con, _oc("4500595496", "SERVICIO", cantidad="12", vig_desde="2026-01-15",
                                              vig_hasta="2027-01-14", dia_inicio_periodo=15))
        exp = self._con_remito("4500595496", "2026-09-30", cantidad="1")
        self.assertEqual((exp["periodo_desde"], exp["periodo_hasta"]), ("2026-09-15", "2026-10-14"))
        self.assertEqual(exp["remitos_fuera_de_periodo"], [])

    def test_fuera_de_periodo_salvo_que_la_firma_entre(self):
        negocio.crear_oc_manual(self.con, _oc("4500595497", "BIEN"))
        exp = self._con_remito("4500595497", "2026-09-10")
        exp = negocio.actualizar_expediente(self.con, exp["id"], exp["version"], {"periodo": "2026-10"})
        self.assertEqual(exp["remitos_fuera_de_periodo"], ["0009-00000268"])
        remitos = exp["datos"]["remitos"]
        remitos[0]["fecha_firma"] = "2026-10-02"  # el remito es de septiembre pero se firmó en octubre: está bien
        exp = negocio.actualizar_expediente(self.con, exp["id"], exp["version"], {"datos": {"remitos": remitos}})
        self.assertEqual(exp["remitos_fuera_de_periodo"], [])
