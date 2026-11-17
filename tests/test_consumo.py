"""Paso 12: consumo, saldo y grilla renglón × período."""
import unittest

from gestor import db, negocio
from tests import ayudas, datos_prueba

OC = datos_prueba.OC_EFIA_MANUAL["numero"]


class PruebaConsumo(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
        finally:
            con.close()

    def _expediente(self, periodo="2026-08", cantidad="1", equipo=None):
        exp = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": OC}).json()["datos"]
        remitos = [{
            "numero": "0001-%08d" % exp["id"], "fecha": periodo + "-05", "fecha_firma": None,
            "es_equipo_comodato": False, "aclara_periodo": False,
            "items": [{"pos": 1, "cantidad": cantidad, "codigo": ""}],
        }]
        if equipo is not None:
            remitos.append({
                "numero": "0001-99999999", "fecha": periodo + "-01", "fecha_firma": None,
                "es_equipo_comodato": True, "aclara_periodo": False,
                "items": [{"pos": 1, "cantidad": equipo, "codigo": ""}],
            })
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"], {
            "version": exp["version"], "cambios": {"periodo": periodo, "datos": {"remitos": remitos}},
        })
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _consumo(self):
        resp = self.servidor.get("/api/oc/%s/consumo" % OC)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _renglon(self, pos=1):
        return next(r for r in self._consumo()["renglones"] if r["pos"] == pos)

    def _consumo_previo(self, cantidad):
        renglon = self.servidor.get("/api/oc/%s" % OC).json()["datos"]["renglones"][0]
        resp = self.servidor.put("/api/oc/%s/renglones/1" % OC, {
            "version": renglon["version"], "cambios": {"consumo_previo": cantidad},
        })
        self.assertEqual(resp.estado, 200, resp.texto())

    def test_efia_un_mes_validado(self):
        self._expediente(equipo="1")  # el remito del equipo no suma consumo
        r = self._renglon()
        self.assertEqual((r["cantidad_oc"], r["unidad"]), ("9", "MES"))
        self.assertEqual((r["validado"], r["saldo"], r["ideal_mes"], r["pct_consumido"]), ("1", "8", "1", 11))
        self.assertEqual(r["por_periodo"], {"2026-08": "1"})
        self.assertFalse(r["por_agotarse"])

    def test_anulado_no_cuenta(self):
        exp = self._expediente()
        resp = self.servidor.post("/api/expedientes/%d/anular" % exp["id"], {"version": exp["version"], "motivo": "Duplicado"})
        self.assertEqual(resp.estado, 200, resp.texto())
        r = self._renglon()
        self.assertEqual((r["validado"], r["saldo"], r["pct_consumido"]), ("0", "9", 0))
        self.assertEqual(r["por_periodo"], {})

    def test_consumo_previo_reduce_saldo(self):
        self._expediente()
        self._consumo_previo("5")
        r = self._renglon()
        self.assertEqual((r["consumo_previo"], r["validado"], r["saldo"]), ("5", "1", "3"))
        self.assertEqual(r["por_periodo"], {"2026-08": "1"})

    def test_grilla_doce_periodos_de_vigencia(self):
        self._expediente()
        grilla = self._consumo()["grilla"]
        self.assertEqual(len(grilla["periodos"]), 12)
        self.assertEqual((grilla["periodos"][0], grilla["periodos"][-1]), ("2025-10", "2026-09"))
        fila = grilla["filas"][0]
        self.assertEqual(fila["celdas"]["2026-08"], "1")
        self.assertEqual(fila["celdas"]["2026-07"], "0")

        con = db.conectar(self.entorno.ruta_base)
        try:
            sin_fin = {"numero": "X", "vig_desde": "2026-01-01", "vig_hasta": None, "dia_inicio_periodo": 1}
            self.assertEqual(negocio.periodos_de_vigencia(sin_fin), [])
            self.assertEqual(negocio.grilla(con, OC)["periodos"], grilla["periodos"])
        finally:
            con.close()

    def test_por_agotarse(self):
        self._expediente()
        self._consumo_previo("6")  # 6 + 1 = 7 de 9 → 78 %, saldo 2 ≥ ideal 1
        self.assertFalse(self._renglon()["por_agotarse"])
        self._expediente(periodo="2026-09", cantidad="2")  # saldo 0 < ideal 1
        r = self._renglon()
        self.assertEqual((r["saldo"], r["pct_consumido"]), ("0", 100))
        self.assertTrue(r["por_agotarse"])
        self.assertTrue(self._consumo()["grilla"]["filas"][0]["por_agotarse"])

    def test_por_agotarse_por_umbral(self):
        self._expediente()
        self._consumo_previo("7")  # 8 de 9 → 89 % ≥ 85 %, aunque el saldo (1) no es menor al ideal
        r = self._renglon()
        self.assertEqual((r["saldo"], r["pct_consumido"]), ("1", 89))
        self.assertTrue(r["por_agotarse"])

    def test_oc_inexistente(self):
        self.assertEqual(self.servidor.get("/api/oc/4599999999/consumo").estado, 404)


if __name__ == "__main__":
    unittest.main()
