"""Paso 2: remitos cargados uno por uno, cada uno con su casilla de equipo en comodato, hasta 20 por expediente."""
from gestor import db, negocio
from tests import ayudas, datos_prueba


class PruebaRemitosFormulario(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
            self.exp = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": datos_prueba.OC_EFIA_MANUAL["numero"]})
        finally:
            con.close()

    def _agregar(self, remitos, version=None):
        return self.servidor.post("/api/expedientes/%d/remitos/pegar" % self.exp["id"],
                                  {"version": version or self.exp["version"], "remitos": remitos})

    def test_cada_remito_con_su_comodato(self):
        resp = self._agregar([
            {"numero": "00001-00029461", "fecha": "2026-08-31", "fecha_firma": "", "es_equipo_comodato": False},
            {"numero": "00001-00029462", "fecha": "2026-08-31", "fecha_firma": "2026-09-02", "es_equipo_comodato": True},
        ])
        self.assertEqual(resp.estado, 200, resp.texto())
        exp = resp.json()["datos"]
        remitos = exp["datos"]["remitos"]
        self.assertEqual([(r["numero"], r["es_equipo_comodato"], r["fecha_firma"]) for r in remitos],
                         [("00001-00029461", False, None), ("00001-00029462", True, "2026-09-02")])
        self.assertEqual(exp["periodo"], "2026-08")

    def test_mismo_numero_conserva_cantidades(self):
        exp = self._agregar([{"numero": "R-1", "fecha": "2026-08-31"}]).json()["datos"]
        remitos = exp["datos"]["remitos"]
        remitos[0]["items"] = [{"pos": 1, "cantidad": "1", "codigo": ""}]
        exp = self.servidor.put("/api/expedientes/%d" % exp["id"],
                                {"version": exp["version"], "cambios": {"datos": {"remitos": remitos}}}).json()["datos"]
        exp = self._agregar([{"numero": "R-1", "fecha": "2026-08-30"}], version=exp["version"]).json()["datos"]
        self.assertEqual(exp["datos"]["remitos"][0]["fecha"], "2026-08-30")
        self.assertEqual(exp["datos"]["remitos"][0]["items"][0]["cantidad"], "1")

    def test_validaciones_y_maximo_20(self):
        self.assertEqual(self._agregar([{"numero": "", "fecha": "2026-08-31"}]).estado, 400)
        self.assertEqual(self._agregar([{"numero": "R-1", "fecha": "31-31-2026"}]).estado, 400)
        self.assertEqual(self._agregar([]).estado, 400)
        veinte = [{"numero": "R-%02d" % n, "fecha": "2026-08-%02d" % n} for n in range(1, 21)]
        resp = self._agregar(veinte)
        self.assertEqual(resp.estado, 200, resp.texto())
        exp = resp.json()["datos"]
        resp = self._agregar([{"numero": "R-99", "fecha": "2026-08-31"}], version=exp["version"])
        self.assertEqual(resp.estado, 400)
        self.assertIn("20", resp.json()["error"]["mensaje"])
