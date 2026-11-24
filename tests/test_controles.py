"""Paso 13: motor de controles con cuatro niveles, sobre los expedientes reales."""
import copy
import unittest

from gestor import controles, db, negocio
from tests import ayudas, datos_prueba


def _por_codigo(informe, codigo):
    return [r for r in informe["resultados"] if r["codigo"] == codigo]


class PruebaControles(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        db.inicializar(self.entorno.ruta_base, self.entorno.config["parametros_iniciales"])
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _controlar(self, exp):
        return controles.controlar(self.con, exp["id"])

    def test_efia_sin_errores_ni_salvables(self):
        exp = datos_prueba.armar_expediente_efia(self.con)
        self.assertEqual(exp["periodo"], "2026-08")
        informe = self._controlar(exp)
        self.assertEqual((informe["resumen"]["error"], informe["resumen"]["salvable"]), (0, 0), informe["resultados"])
        cae = _por_codigo(informe, "vencimiento_cae")
        self.assertEqual([r["nivel"] for r in cae], ["verificar"])
        self.assertEqual(_por_codigo(informe, "periodo_factura"), [])
        self.assertEqual(_por_codigo(informe, "menciones_factura"), [])

    def test_biofab_codigo_distinto_es_salvable(self):
        exp = datos_prueba.armar_expediente_biofab(self.con)
        informe = self._controlar(exp)
        self.assertEqual(informe["resumen"]["error"], 0, informe["resultados"])
        salvables = [r for r in informe["resultados"] if r["nivel"] == "salvable"]
        self.assertEqual(len(salvables), 1)
        self.assertEqual(salvables[0]["codigo"], "codigo_remito_distinto")
        self.assertEqual(salvables[0]["referencia"], "2")
        self.assertEqual(
            salvables[0]["mensaje"],
            "El remito 0001-00003354 indica el código 5002383 en el renglón 2; la OC tiene 5003283.",
        )

    def test_biofab_sin_remito_de_equipo_es_error(self):
        exp = datos_prueba.armar_expediente_biofab(self.con, con_equipo=False)
        errores = [r for r in self._controlar(exp)["resultados"] if r["nivel"] == "error"]
        self.assertEqual([r["codigo"] for r in errores], ["comodato_sin_remito_equipo"])
        self.assertEqual(errores[0]["mensaje"], "Primera validación de OC con comodato sin remito del equipo.")

        # si otro expediente de la OC ya está CONTROLADO, ya no es la primera validación
        ctx = controles.armar_contexto(self.con, exp["id"])
        ctx["otros_de_la_oc"] = [{"id": 99, "estado": "CONTROLADO", "periodo": "2026-07", "factura": ""}]
        self.assertEqual(controles.control_comodato_sin_remito_equipo(ctx), [])

    def test_macatex_objeto_faltante(self):
        exp = datos_prueba.armar_expediente_macatex(self.con)
        self.assertEqual(exp["periodo"], "2026-09")
        informe = self._controlar(exp)
        errores = [r for r in informe["resultados"] if r["nivel"] == "error"]
        self.assertEqual(len(errores), 1, errores)
        self.assertEqual(errores[0]["codigo"], "objeto_faltante")
        self.assertEqual(errores[0]["mensaje"], "Falta el objeto de la contratación en la OC 4500594643")
        self.assertEqual(informe["resumen"]["salvable"], 0)

    def test_un_centavo_de_diferencia_es_error_no_salvable(self):
        exp = datos_prueba.armar_expediente_efia(self.con, centavos=122499001)
        informe = self._controlar(exp)
        importe = _por_codigo(informe, "importe_factura")
        self.assertEqual(len(importe), 1)
        self.assertEqual(importe[0]["nivel"], "error")
        self.assertEqual(
            importe[0]["mensaje"],
            "El importe de la factura ($ 1.224.990,01) no coincide con cantidad × precio ($ 1.224.990,00).",
        )
        self.assertEqual(informe["resumen"]["salvable"], 0)

    def test_esterisur_un_remito_fuera_de_periodo(self):
        oc = copy.deepcopy(datos_prueba.OC_EFIA_MANUAL)
        oc.update(numero="4500900099", sap="99002", razon_social="ESTERISUR S.A.", vig_desde="2026-01-01",
                  vig_hasta="2027-12-31")
        negocio.crear_oc_manual(self.con, oc)
        exp = negocio.crear_expediente(self.con, {"tipo": "COMUN", "oc": oc["numero"]})
        lineas = ["0002-%08d;%02d/08/2026" % (i, i) for i in range(1, 16)] + ["0002-00000099;28/07/2026"]
        exp = negocio.pegar_remitos(self.con, exp["id"], exp["version"], "\n".join(lineas))
        self.assertEqual(exp["periodo"], "2026-08")
        fuera = _por_codigo(self._controlar(exp), "remito_fuera_de_periodo")
        self.assertEqual(len(fuera), 1)
        self.assertEqual((fuera[0]["nivel"], fuera[0]["referencia"]), ("error", "0002-00000099"))
        self.assertEqual(fuera[0]["mensaje"], "El remito 0002-00000099 (28/07/2026) está fuera del período 2026-08.")

    def test_factura_repetida_y_duplicado(self):
        primero = datos_prueba.armar_expediente_efia(self.con)
        segundo = datos_prueba.armar_expediente_efia(self.con)
        informe = self._controlar(segundo)
        self.assertEqual([r["referencia"] for r in _por_codigo(informe, "factura_repetida")], [str(primero["id"])])
        self.assertEqual([r["nivel"] for r in _por_codigo(informe, "expediente_duplicado")], ["aviso"])


class PruebaControlesApi(ayudas.CasoConServidor):

    def test_get_controles(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_macatex(con)
        finally:
            con.close()
        resp = self.servidor.get("/api/expedientes/%d/controles" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()["datos"]
        self.assertEqual(datos["resumen"]["error"], 1)
        self.assertEqual(set(datos["resultados"][0]), {"codigo", "nivel", "ambito", "mensaje", "referencia"})
        self.assertEqual(self.servidor.get("/api/expedientes/999/controles").estado, 404)


if __name__ == "__main__":
    unittest.main()


class PruebaPeriodoSii(unittest.TestCase):
    """En el SII se carga el mes en que termina el período validado (si es un período específico, el mes del «hasta»)."""

    def _ctx(self, periodo, desde, hasta, periodo_sii):
        return {"expediente": {"periodo": periodo, "periodo_desde": desde, "periodo_hasta": hasta,
                               "datos": {"sii": {"periodo": periodo_sii}}}}

    def test_periodo_especifico_se_carga_con_el_mes_de_fin(self):
        ctx = self._ctx("2026-09", "2026-09-15", "2026-10-14", "2026-10")
        self.assertEqual(controles.control_sii_periodo(ctx), [])

    def test_mes_calendario(self):
        self.assertEqual(controles.control_sii_periodo(self._ctx("2026-08", "2026-08-01", "2026-08-31", "2026-08")), [])
        mal = controles.control_sii_periodo(self._ctx("2026-08", "2026-08-01", "2026-08-31", "2026-07"))
        self.assertEqual([(r.codigo, r.nivel) for r in mal], [("sii_periodo", "error")])
        self.assertEqual(mal[0].mensaje, "El período cargado en el SII (2026-07) no es el del período validado (2026-08).")

    def test_periodo_especifico_mal_cargado(self):
        mal = controles.control_sii_periodo(self._ctx("2026-09", "2026-09-15", "2026-10-14", "2026-09"))
        self.assertEqual(mal[0].mensaje, "El período cargado en el SII (2026-09) no es el del período validado (2026-10, "
                                         "el mes en que termina el 15/09/2026 al 14/10/2026).")
