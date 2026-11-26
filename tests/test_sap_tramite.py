"""Datos para SAP por paso del trámite: ingreso del bien o servicio (MIGO / ML81N) e ingreso de la factura."""
import unittest

from gestor import textos


def ctx_servicio(**cambios):
    ctx = {
        "efector": "HBI", "sigla": "HBI", "oc": "4500585442", "concepto_corto": "MANT. GRUP. ELECT.", "centavos": 325255690,
        "periodo": "2026-09", "periodo_desde": "2026-09-01", "periodo_hasta": "2026-09-30", "dia_inicio": 1,
        "tipo_oc": "SERVICIO", "fecha_base_remitos": "2026-09-30", "cantidades": [{"pos": 1, "cantidad": "1"}],
        "fecha_factura": "2026-10-03", "expediente": "EX-2026-12345678- -INSSJP-GESP#INSSJP",
        "remitos_detalle": [{"numero": "0001-00000552", "fecha": "2026-09-30", "renglones": [{"pos": 1, "cantidad": "1"}]}],
    }
    ctx.update(cambios)
    return ctx


class PruebaEntradaSap(unittest.TestCase):

    def test_servicio_hoja_de_entrada(self):
        self.assertEqual(textos.entrada_sap(ctx_servicio()), {
            "tipo": "SERVICIO", "oc": "4500585442", "texto_breve": "MANT. GRUP. ELECT. - 09/26",
            "desde": "01.09.2026", "hasta": "30.09.2026", "centro": "HBI", "renglones": [{"pos": 1, "cantidad": "1"}],
        })

    def test_servicio_periodo_especifico_y_casph_es_hur(self):
        entrada = textos.entrada_sap(ctx_servicio(efector="CASPH", sigla="CASPH", dia_inicio=15,
                                                  periodo_desde="2026-09-15", periodo_hasta="2026-10-14"))
        self.assertEqual((entrada["desde"], entrada["hasta"], entrada["centro"]), ("15.09.2026", "14.10.2026", "HUR"))

    def test_bien_vale_de_entrada_por_remito(self):
        ctx = ctx_servicio(tipo_oc="BIEN", remitos_detalle=[
            {"numero": "0009-00000268", "fecha": "2026-09-10", "renglones": [{"pos": 1, "cantidad": "400"}]},
            {"numero": "0009-00000301", "fecha": "2026-09-24", "renglones": [{"pos": 1, "cantidad": "100"}, {"pos": 2, "cantidad": "5"}]},
        ])
        self.assertEqual(textos.entrada_sap(ctx), {
            "tipo": "BIEN", "oc": "4500585442", "fecha_documento": "01.09.2026",
            "remitos": [
                {"numero": "0009-00000268", "fecha": "10.09.2026", "renglones": [{"pos": 1, "cantidad": "400"}]},
                {"numero": "0009-00000301", "fecha": "24.09.2026",
                 "renglones": [{"pos": 1, "cantidad": "100"}, {"pos": 2, "cantidad": "5"}]},
            ],
        })

    def test_bien_sin_remitos_avisa(self):
        with self.assertRaises(textos.TextoIncompleto):
            textos.entrada_sap(ctx_servicio(tipo_oc="BIEN", remitos_detalle=[]))


class PruebaFacturaSap(unittest.TestCase):

    def test_ingreso_de_la_factura(self):
        self.assertEqual(textos.factura_sap(ctx_servicio(), 50), {
            "fecha_documento": "01.09.2026", "importe": "3.252.556,90",
            "texto": "HBI - OC 4500585442 - MANT. GRUP. ELECT. - 09/26", "largo_texto": 48, "aviso_largo": None,
            "asignacion": "OC 4500585442", "txt_cabecera_ingreso": "0000-0000-0000000-0",
            "txt_cabecera": "09/26 HBI OC 4500585442", "clase": "KE", "fecha_contabilizacion": "03.10.2026",
            "texto_breve": "MANT. GRUP. ELECT. - 09/26", "expediente": "EX-2026-12345678- -INSSJP-GESP#INSSJP",
        })

    def test_sin_expediente_o_sin_fecha_de_factura(self):
        with self.assertRaises(textos.TextoIncompleto) as error:
            textos.factura_sap(ctx_servicio(expediente=""), 50)
        self.assertIn("expediente", str(error.exception))
        with self.assertRaises(textos.TextoIncompleto):
            textos.factura_sap(ctx_servicio(fecha_factura=""), 50)


if __name__ == "__main__":
    unittest.main()
