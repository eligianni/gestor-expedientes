"""Paso 9: API de expedientes (alta, versión, historial, anulación, filtros)."""
import getpass
import json
import unittest

from gestor import db
from tests import ayudas, datos_prueba

CONFLICTO = "Otra persona guardó cambios en este registro. Recargá para ver la última versión."


class PruebaExpedientesApi(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
        finally:
            con.close()

    def _crear(self, **extra):
        cuerpo = {"tipo": "COMUN", "oc": "4500555861"}
        cuerpo.update(extra)
        resp = self.servidor.post("/api/expedientes", cuerpo)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _eventos(self, id_expediente, accion):
        con = db.conectar(self.entorno.ruta_base)
        try:
            return con.execute(
                "SELECT COUNT(*) FROM evento WHERE tabla = 'expediente' AND clave = ? AND accion = ?",
                (json.dumps({"id": id_expediente}), accion),
            ).fetchone()[0]
        finally:
            con.close()

    def test_crear_expediente_borrador(self):
        exp = self._crear()
        self.assertEqual(exp["estado"], "BORRADOR")
        self.assertEqual(exp["version"], 1)
        self.assertEqual(exp["sap"], "77170")
        self.assertEqual(exp["efector"], "HBI")
        self.assertEqual(exp["usuario"], getpass.getuser())
        self.assertEqual(exp["razon_social"], "GRUPO EFIA S.R.L.")
        self.assertEqual(exp["creado"], exp["actualizado"])
        datos = exp["datos"]
        self.assertEqual(
            set(datos.keys()),
            {"remitos", "factura", "sii", "gde", "sap", "notas_aclaratorias", "checklist", "correctivo", "eventual",
             "centralizada", "historial"},
        )
        self.assertEqual(datos["remitos"], [])
        self.assertEqual(len(datos["historial"]), 1)
        self.assertEqual(datos["historial"][0]["accion"], "ALTA")
        self.assertEqual(datos["historial"][0]["estado"], "BORRADOR")
        self.assertEqual(self._eventos(exp["id"], "ALTA"), 1)

        sin_oc = self.servidor.post("/api/expedientes", {"tipo": "COMUN"})
        self.assertEqual(sin_oc.estado, 400)
        oc_inexistente = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": "1"})
        self.assertEqual(oc_inexistente.estado, 404)
        self.assertEqual(self.servidor.get("/api/expedientes/%d" % exp["id"]).json()["datos"]["id"], exp["id"])

    def test_editar_incrementa_version_y_audita(self):
        exp = self._crear()
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 1, "cambios": {
            "periodo": "2026-08", "periodo_manual": 1,
            "datos": {"factura": {"numero": "0003B00031812", "centavos": 122499000}},
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        nuevo = resp.json()["datos"]
        self.assertEqual(nuevo["version"], 2)
        self.assertEqual(nuevo["periodo"], "2026-08")
        self.assertEqual(nuevo["factura"], "0003B00031812")
        self.assertEqual(nuevo["datos"]["factura"]["centavos"], 122499000)
        self.assertEqual(nuevo["datos"]["remitos"], [])  # las claves que no llegan se conservan
        self.assertEqual([h["accion"] for h in nuevo["datos"]["historial"]], ["ALTA", "PERIODO_MANUAL"])
        self.assertEqual(self._eventos(exp["id"], "MODIFICACION"), 1)

        otra = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 2, "cambios": {
            "datos": {"factura": {"numero": "0002 - 00003908"}},
        }})
        self.assertEqual(otra.json()["datos"]["factura"], "000200003908")

    def test_editar_con_version_vieja_da_409(self):
        exp = self._crear()
        primera = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 1, "cambios": {"periodo": "2026-08"}})
        self.assertEqual(primera.estado, 200)
        vieja = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 1, "cambios": {"periodo": "2026-09"}})
        self.assertEqual(vieja.estado, 409)
        self.assertEqual(vieja.json(), {"ok": False, "error": {"codigo": "conflicto_version", "mensaje": CONFLICTO}})
        self.assertEqual(self.servidor.get("/api/expedientes/%d" % exp["id"]).json()["datos"]["periodo"], "2026-08")
        self.assertEqual(self._eventos(exp["id"], "MODIFICACION"), 1)

    def test_anular_sin_motivo_da_400(self):
        exp = self._crear()
        for motivo in ("", "   ", None):
            with self.subTest(motivo=motivo):
                resp = self.servidor.post("/api/expedientes/%d/anular" % exp["id"], {"version": 1, "motivo": motivo})
                self.assertEqual(resp.estado, 400)
                self.assertEqual(resp.json()["error"], {"codigo": "validacion", "mensaje": "Indicá el motivo de la anulación."})
        self.assertEqual(self.servidor.get("/api/expedientes/%d" % exp["id"]).json()["datos"]["estado"], "BORRADOR")

    def test_anular_conserva_la_fila(self):
        exp = self._crear()
        resp = self.servidor.post("/api/expedientes/%d/anular" % exp["id"], {"version": 1, "motivo": "Cargado por error"})
        self.assertEqual(resp.estado, 200, resp.texto())
        anulado = resp.json()["datos"]
        self.assertEqual(anulado["estado"], "ANULADO")
        self.assertEqual(anulado["motivo_anulacion"], "Cargado por error")
        self.assertEqual(anulado["datos"]["historial"][-1]["accion"], "ANULACION")
        self.assertEqual(self._eventos(exp["id"], "ANULACION"), 1)
        lista = self.servidor.get("/api/expedientes?estado=ANULADO").json()["datos"]
        self.assertEqual([e["id"] for e in lista], [exp["id"]])

    def test_listar_filtra_por_estado_y_periodo(self):
        agosto = self._crear(periodo="2026-08")
        self._crear(periodo="2026-09")
        tercero = self._crear(periodo="2026-08")
        self.servidor.post("/api/expedientes/%d/anular" % tercero["id"], {"version": 1, "motivo": "duplicado"})
        lista = self.servidor.get("/api/expedientes?estado=BORRADOR&periodo=2026-08").json()["datos"]
        self.assertEqual([e["id"] for e in lista], [agosto["id"]])
        for exp in lista:
            self.assertEqual((exp["estado"], exp["periodo"]), ("BORRADOR", "2026-08"))
            self.assertNotIn("datos", exp)
        self.assertEqual(len(self.servidor.get("/api/expedientes").json()["datos"]), 3)
        self.assertEqual(self.servidor.get("/api/expedientes?efector=CASPH").json()["datos"], [])
        self.assertEqual(len(self.servidor.get("/api/expedientes?sap=0000077170").json()["datos"]), 3)

    def test_editar_anulado_da_422(self):
        exp = self._crear()
        self.servidor.post("/api/expedientes/%d/anular" % exp["id"], {"version": 1, "motivo": "error"})
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 2, "cambios": {"periodo": "2026-08"}})
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"], {"codigo": "negocio", "mensaje": "El expediente está anulado."})
        otra_vez = self.servidor.post("/api/expedientes/%d/anular" % exp["id"], {"version": 2, "motivo": "otra vez"})
        self.assertEqual(otra_vez.estado, 422)


if __name__ == "__main__":
    unittest.main()
