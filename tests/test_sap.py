"""Paso 19: textos para SAP — ingreso, contabilización, MIGO y ML81N."""
import unittest

from gestor import db, textos
from tests import ayudas, datos_prueba


def ctx_efia(**cambios):
    ctx = {
        "efector": "HBI", "sigla": "HBI", "oc": "4500555861", "concepto_corto": "SERV. FUMIGACIÓN", "centavos": 122499000,
        "periodo": "2026-08", "periodo_desde": "2026-08-01", "periodo_hasta": "2026-08-31", "dia_inicio": 1,
        "tipo_oc": "SERVICIO", "fecha_base_remitos": "2026-08-31", "cantidades": [{"pos": 1, "cantidad": "1"}],
    }
    ctx.update(cambios)
    return ctx


class PruebaSap(unittest.TestCase):

    def test_texto_ingreso_efia(self):
        ingreso = textos.textos_sap(ctx_efia(), 50)["ingreso"]
        self.assertEqual(ingreso["texto"], "HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26")
        self.assertEqual(ingreso["fecha_documento"], "01.08.2026")
        self.assertEqual(ingreso["importe"], "1.224.990,00")
        self.assertEqual(ingreso["asignacion"], "OC 4500555861")
        self.assertEqual(ingreso["txt_cabecera"], "0000-0000-0000000-0")
        self.assertEqual(ingreso["clase"], "KE")
        self.assertEqual(ingreso["largo_texto"], 46)
        self.assertIsNone(ingreso["aviso_largo"])

    def test_txt_cabecera_contabilizada_efia(self):
        self.assertEqual(textos.textos_sap(ctx_efia(), 50)["contabilizada"]["txt_cabecera"], "08/26 HBI OC 4500555861")

    def test_casph_reemplaza_hbi(self):
        sap = textos.textos_sap(ctx_efia(efector="CASPH", sigla="CASPH"), 50)
        self.assertEqual(sap["contabilizada"]["txt_cabecera"], "08/26 CASPH OC 4500555861")
        self.assertEqual(sap["ingreso"]["texto"], "CASPH - OC 4500555861 - SERV. FUMIGACIÓN - 08/26")

    def test_aviso_de_largo(self):
        largo = textos.textos_sap(ctx_efia(concepto_corto="SERVICIO INTEGRAL DE CONTROL DE PLAGAS"), 50)["ingreso"]
        self.assertEqual(largo["largo_texto"], len(largo["texto"]))
        self.assertGreater(largo["largo_texto"], 50)
        self.assertEqual(largo["aviso_largo"],
                         "El Texto tiene %d caracteres; el límite configurado es 50." % largo["largo_texto"])
        self.assertIsNone(textos.textos_sap(ctx_efia(), 46)["ingreso"]["aviso_largo"])
        with self.assertRaises(textos.TextoIncompleto):
            textos.textos_sap(ctx_efia(concepto_corto=""), 50)

    def test_ml81n_y_migo(self):
        entrada = textos.textos_sap(ctx_efia(), 50)["entrada"]
        self.assertEqual(entrada, {
            "transaccion": "ML81N", "fecha_documento": "01.08.2026", "fecha_contabilizacion": "31.08.2026",
            "renglones": [{"pos": 1, "cantidad": "1"}], "periodo": "08/2026", "texto_breve": "SERV. FUMIGACIÓN - 08/26",
        })
        bien = textos.textos_sap(ctx_efia(tipo_oc="BIEN"), 50)["entrada"]
        self.assertEqual(bien["transaccion"], "MIGO")
        self.assertEqual(textos.textos_sap(ctx_efia(tipo_oc="PROVISION"), 50)["entrada"]["transaccion"], "MIGO")
        especifico = textos.textos_sap(ctx_efia(dia_inicio=17, periodo="2026-11", periodo_desde="2026-10-17",
                                                periodo_hasta="2026-11-16"), 50)["entrada"]
        self.assertEqual(especifico["periodo"], "17.10.2026 - 16.11.2026")
        self.assertEqual(especifico["fecha_documento"], "01.11.2026")



class PruebaSapApi(ayudas.CasoConServidor):

    def test_textos_sap_efia_por_api(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
        finally:
            con.close()
        sap = self.servidor.get("/api/expedientes/%d/textos" % exp["id"]).json()["datos"]["sap"]
        self.assertEqual(sap["ingreso"]["texto"], "HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26")
        self.assertEqual(sap["contabilizada"]["txt_cabecera"], "08/26 HBI OC 4500555861")
        self.assertEqual(sap["entrada"]["fecha_contabilizacion"], "31.08.2026")
        self.assertEqual(sap["entrada"]["renglones"], [{"pos": 1, "cantidad": "1"}])


if __name__ == "__main__":
    unittest.main()
