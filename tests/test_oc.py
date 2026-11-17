"""Paso 8: órdenes de compra (alta manual, campos manuales, versión, validaciones, lista y exclusión)."""
import unittest

from gestor import db
from tests import ayudas, datos_prueba

CONFLICTO = "Otra persona guardó cambios en este registro. Recargá para ver la última versión."


class PruebaOC(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _ficha(self, numero):
        resp = self.servidor.get("/api/oc/%s" % numero)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_alta_manual_efia(self):
        resp = self.servidor.post("/api/oc", datos_prueba.OC_EFIA_MANUAL)
        self.assertEqual(resp.estado, 200, resp.texto())
        oc = resp.json()["datos"]["oc"]
        self.assertEqual(oc["origen"], "MANUAL")
        self.assertEqual(oc["ca"], "195-2025")
        self.assertEqual(oc["expediente_contratacion"], "EX-2025-70356979- -INSSJP-GESP#INSSJP")
        self.assertEqual((oc["vig_desde"], oc["vig_hasta"]), ("2025-10-01", "2026-09-30"))
        self.assertEqual(oc["sap"], "77170")
        self.assertIn("objeto", oc["campos_manuales"])
        proveedor = resp.json()["datos"]["proveedor"]
        self.assertEqual(proveedor["razon_social"], "GRUPO EFIA S.R.L.")
        renglon = resp.json()["datos"]["renglones"][0]
        self.assertEqual(renglon["pos"], 1)
        self.assertEqual(renglon["desglose_cantidad"], "9")
        self.assertEqual(renglon["desglose_unidad"], "MES")
        self.assertEqual(renglon["desglose_precio_centavos"], 122499000)

        repetida = self.servidor.post("/api/oc", datos_prueba.OC_EFIA_MANUAL)
        self.assertEqual(repetida.estado, 422)
        self.assertEqual(repetida.json()["error"], {"codigo": "negocio", "mensaje": "La OC 4500555861 ya existe."})

        nuevo = self.servidor.post("/api/oc/4500555861/renglones", {
            "descripcion": "RENGLÓN EXTRA", "cantidad": "2", "precio_centavos": 1000,
        })
        self.assertEqual(nuevo.estado, 200, nuevo.texto())
        self.assertEqual([r["pos"] for r in nuevo.json()["datos"]["renglones"]], [1, 2])

    def test_editar_marca_campo_manual_y_reimportar_no_lo_pisa(self):
        datos_prueba.importar_hbi_2026(self.con)
        oc = self._ficha("4500600299")["oc"]
        self.assertEqual(oc["objeto"], "")
        resp = self.servidor.put("/api/oc/4500600299", {"version": oc["version"], "cambios": {
            "objeto": "servicio integral de control de plagas", "vig_hasta": "2027-12-31",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        editada = resp.json()["datos"]["oc"]
        self.assertEqual(editada["version"], oc["version"] + 1)
        self.assertIn("objeto", editada["campos_manuales"])
        self.assertIn("vig_hasta", editada["campos_manuales"])

        datos_prueba.importar_hbi_2026(self.con)
        despues = self._ficha("4500600299")["oc"]
        self.assertEqual(despues["objeto"], "servicio integral de control de plagas")
        self.assertEqual(despues["vig_hasta"], "2027-12-31")

        renglon = self._ficha("4500600299")["renglones"][0]
        resp = self.servidor.put("/api/oc/4500600299/renglones/1", {"version": renglon["version"], "cambios": {
            "consumo_previo": "2",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["renglones"][0]["consumo_previo"], "2")
        self.assertIn("consumo_previo", resp.json()["datos"]["renglones"][0]["campos_manuales"])

    def test_editar_con_version_vieja_da_409(self):
        datos_prueba.cargar_efia(self.con)
        version = self._ficha("4500555861")["oc"]["version"]
        primera = self.servidor.put("/api/oc/4500555861", {"version": version, "cambios": {"leyenda_cv": "A"}})
        self.assertEqual(primera.estado, 200, primera.texto())
        vieja = self.servidor.put("/api/oc/4500555861", {"version": version, "cambios": {"leyenda_cv": "B"}})
        self.assertEqual(vieja.estado, 409)
        self.assertEqual(vieja.json(), {"ok": False, "error": {"codigo": "conflicto_version", "mensaje": CONFLICTO}})
        self.assertEqual(self._ficha("4500555861")["oc"]["leyenda_cv"], "A")

    def test_dia_inicio_fuera_de_rango_da_400(self):
        datos_prueba.cargar_efia(self.con)
        version = self._ficha("4500555861")["oc"]["version"]
        resp = self.servidor.put("/api/oc/4500555861", {"version": version, "cambios": {"dia_inicio_periodo": 29}})
        self.assertEqual(resp.estado, 400)
        self.assertEqual(resp.json()["error"], {
            "codigo": "validacion", "mensaje": "El día de inicio del período debe estar entre 1 y 28.",
        })
        mal_gde = self.servidor.put("/api/oc/4500555861", {"version": version, "cambios": {"gde_pdf_oc": "EX-2026-12-INSSJP"}})
        self.assertEqual(mal_gde.estado, 400)
        mal_articulo = self.servidor.put("/api/oc/4500555861", {"version": version, "cambios": {"objeto_articulo": "el"}})
        self.assertEqual(mal_articulo.estado, 400)
        self.assertEqual(self._ficha("4500555861")["oc"]["version"], version)
        self.assertEqual(self.servidor.get("/api/oc/9999999999").estado, 404)

    def test_listar_filtra_por_efector_y_texto(self):
        datos_prueba.importar_hbi_2026(self.con)
        lista = self.servidor.get("/api/oc?efector=HBI&q=EFIA").json()["datos"]
        numeros = {oc["numero"] for oc in lista}
        self.assertIn("4500600299", numeros)
        for oc in lista:
            self.assertIn("EFIA", oc["razon_social"].upper())
        self.assertEqual(self.servidor.get("/api/oc?efector=CASPH").json()["datos"], [])
        todas = self.servidor.get("/api/oc").json()["datos"]
        self.assertEqual(len(todas), 107)
        # sin tildes ni mayúsculas
        biofab = self.servidor.get("/api/oc?q=bio%20fab").json()["datos"]
        self.assertIn(datos_prueba.OC_BIOFAB, {oc["numero"] for oc in biofab})

    def test_excluir_oc_la_oculta(self):
        datos_prueba.importar_hbi_2026(self.con)
        version = self._ficha("4500600299")["oc"]["version"]
        resp = self.servidor.put("/api/oc/4500600299", {"version": version, "cambios": {
            "excluida": 1, "motivo_exclusion": "prueba",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        por_defecto = {oc["numero"] for oc in self.servidor.get("/api/oc?efector=HBI").json()["datos"]}
        self.assertNotIn("4500600299", por_defecto)
        con_excluidas = {oc["numero"] for oc in self.servidor.get("/api/oc?efector=HBI&excluidas=1").json()["datos"]}
        self.assertIn("4500600299", con_excluidas)
        # reimportar no la vuelve a mostrar (excluida queda como campo manual)
        datos_prueba.importar_hbi_2026(self.con)
        self.assertNotIn("4500600299", {oc["numero"] for oc in self.servidor.get("/api/oc").json()["datos"]})

    def test_datos_prueba_biofab_y_macatex(self):
        biofab = datos_prueba.preparar_biofab(self.con)["oc"]
        self.assertEqual((biofab["comodato"], biofab["objeto_articulo"]), (1, "a la"))
        self.assertEqual(biofab["objeto"], "provisión de inmunoensayo por fluorescencia")
        macatex = datos_prueba.preparar_macatex(self.con)["oc"]
        self.assertEqual(macatex["objeto"], "")


if __name__ == "__main__":
    unittest.main()
