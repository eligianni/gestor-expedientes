"""Centralizadas: validación por OC + efector + mes (remitos → CV → IF firmado → nota), sin expediente de pago.

Líderes: cada renglón es de un efector. Aqualine: los mismos renglones, con la cantidad de cada efector según el pliego.
"""
from gestor import db, importar, negocio
from tests import ayudas

EX = "EX-2025-22222222- -INSSJP-GESP#INSSJP"


def _oc(numero, renglones):
    return {
        "numero": numero, "efector": "HBI", "sap": "900002", "razon_social": "AQUALINE S.A.", "fecha_oc": "2025-12-15",
        "vig_desde": "2026-01-01", "vig_hasta": "2026-12-31", "ca": "20-2025", "expediente_contratacion": EX,
        "objeto": "servicio de provisión de agua", "objeto_articulo": "al", "tipo": "SERVICIO", "centralizada": 1,
        "leyenda_cv": "Servicio contratado por Nivel Central.", "doc_requerida_central": ["Remito"],
        "renglones": renglones,
    }


class PruebaValidacionCentralizada(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        # Aqualine: un renglón compartido (12 HBI + 8 CASPH); Líderes: un renglón por efector.
        ficha = negocio.crear_oc_manual(self.con, _oc("4500000101", [
            {"pos": 1, "descripcion": "BIDONES DE AGUA", "cantidad": "20", "unidad": "UN", "precio_centavos": 100000}]))
        negocio.guardar_por_efector(self.con, "4500000101", 1, ficha["renglones"][0]["version"], {"HBI": "12", "CASPH": "8"})
        ficha = negocio.crear_oc_manual(self.con, _oc("4500000102", [
            {"pos": 1, "descripcion": "SERVICIO HBI", "cantidad": "12", "unidad": "MES", "precio_centavos": 100000},
            {"pos": 2, "descripcion": "SERVICIO CASPH", "cantidad": "12", "unidad": "MES", "precio_centavos": 100000}]))
        renglones = {r["pos"]: r for r in ficha["renglones"]}
        negocio.guardar_por_efector(self.con, "4500000102", 1, renglones[1]["version"], {"HBI": "12", "CASPH": "0"})
        negocio.guardar_por_efector(self.con, "4500000102", 2, renglones[2]["version"], {"HBI": "0", "CASPH": "12"})

    def _validacion(self, oc, efector, periodo, pos, cantidad):
        resp = self.servidor.post("/api/expedientes", {"tipo": "CENTRALIZADA", "oc": oc, "efector": efector, "periodo": periodo})
        self.assertEqual(resp.estado, 200, resp.texto())
        exp = resp.json()["datos"]
        self.assertEqual((exp["efector"], exp["periodo"], exp["periodo_manual"]), (efector, periodo, 1))
        remitos = [{"numero": "0001-%08d" % exp["id"], "fecha": periodo + "-20", "fecha_firma": None, "es_equipo_comodato": False,
                    "aclara_periodo": False, "items": [{"pos": pos, "cantidad": cantidad, "codigo": ""}]}]
        return negocio.actualizar_expediente(self.con, exp["id"], exp["version"], {"datos": {"remitos": remitos}})

    def test_la_oc_aparece_en_la_lista_de_cada_efector(self):
        for efector in ("HBI", "CASPH"):
            numeros = {f["numero"] for f in negocio.listar_oc(self.con, efector=efector)}
            self.assertTrue({"4500000101", "4500000102"} <= numeros, efector)
        self.assertEqual(negocio.ficha_oc(self.con, "4500000101")["oc"]["efectores"], ["HBI", "CASPH"])

    def test_consumo_y_certificado_por_efector(self):
        hbi = self._validacion("4500000101", "HBI", "2026-03", 1, "3")
        casph = self._validacion("4500000101", "CASPH", "2026-03", 1, "2")
        consumo_hbi = negocio.consumo_oc(self.con, "4500000101", "HBI")["renglones"][0]
        consumo_casph = negocio.consumo_oc(self.con, "4500000101", "CASPH")["renglones"][0]
        self.assertEqual((consumo_hbi["cantidad_oc"], consumo_hbi["validado"], consumo_hbi["saldo"]), ("12", "3", "9"))
        self.assertEqual((consumo_casph["cantidad_oc"], consumo_casph["validado"], consumo_casph["saldo"]), ("8", "2", "6"))
        filas = negocio.datos_cv(self.con, casph["id"])["datos"]["renglones"]
        self.assertEqual([(f["cantidad_oc"], f["cantidad_entregada"]) for f in filas], [("8", "2")])
        self.assertTrue(hbi["id"])

    def test_lideres_cada_certificado_con_sus_renglones(self):
        casph = self._validacion("4500000102", "CASPH", "2026-04", 2, "1")
        filas = negocio.datos_cv(self.con, casph["id"])["datos"]["renglones"]
        self.assertEqual([(f["renglon"], f["descripcion"]) for f in filas], [("2", "SERVICIO CASPH")])
        consumo = negocio.consumo_oc(self.con, "4500000102", "CASPH")["renglones"]
        self.assertEqual([f["pos"] for f in consumo], [2])

    def test_circuito_if_nota_y_validado(self):
        exp = self._validacion("4500000101", "HBI", "2026-05", 1, "1")
        self.assertEqual(exp["estado"], "BORRADOR")
        ruta = "/api/expedientes/%d/centralizada" % exp["id"]
        exp = self.servidor.put(ruta, {"version": exp["version"], "centralizada": {
            "numero_cv": "IF-2026-12345678-INSSJP-GESP#INSSJP", "numero_nota": "", "fecha_envio": None}}).json()["datos"]
        self.assertEqual(exp["estado"], "FIRMADO")
        nota = self.servidor.get("/api/expedientes/%d/nota-central" % exp["id"])
        self.assertEqual(nota.estado, 200, nota.texto())
        self.assertIn("AQUALINE S.A.", nota.json()["datos"]["referencia"])
        exp = self.servidor.put(ruta, {"version": exp["version"], "centralizada": {
            "numero_cv": "IF-2026-12345678-INSSJP-GESP#INSSJP", "numero_nota": "NO-2026-87654321-INSSJP-GESP#INSSJP",
            "fecha_envio": "2026-06-05"}}).json()["datos"]
        self.assertEqual(exp["estado"], "ENVIADO")
        # No es un expediente de pago: no aparece en «Expedientes», sí en el tablero.
        self.assertNotIn(exp["id"], [e["id"] for e in negocio.listar_expedientes(self.con)])
        self.assertIn(exp["id"], [e["id"] for e in negocio.listar_expedientes(self.con, tipo="CENTRALIZADA")])
        tablero = self.servidor.get("/api/centralizadas/tablero?anio=2026&efector=HBI").json()["datos"]
        fila = next(f for f in tablero["filas"] if f["oc"] == "4500000101" and f["efector"] == "HBI")
        mayo = fila["celdas"][4]
        self.assertEqual((mayo["estado"], mayo["expediente_id"], mayo["numero_nota"]),
                         ("validado", exp["id"], "NO-2026-87654321-INSSJP-GESP#INSSJP"))
        self.assertNotIn("CASPH", {f["efector"] for f in tablero["filas"]})

    def test_reparto_se_conserva_al_importar_y_solo_en_centralizadas(self):
        actual = db.leer_fila(self.con, "renglon", {"oc": "4500000101", "pos": 1})
        nuevo = importar._con_subrenglones_guardados(actual, {"crudo": {"Centro": "0010"}})
        self.assertEqual(nuevo["crudo"]["_por_efector"], {"HBI": "12", "CASPH": "8"})
        comun = negocio.crear_oc_manual(self.con, dict(_oc("4500000103", [
            {"pos": 1, "descripcion": "X", "cantidad": "1", "unidad": "UN", "precio_centavos": 1}]), centralizada=0))
        with self.assertRaises(negocio.ErrorNegocio):
            negocio.guardar_por_efector(self.con, "4500000103", 1, comun["renglones"][0]["version"], {"HBI": "1"})
