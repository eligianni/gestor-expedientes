"""Paso 17: autorización de pago, constancia de comodato y copiar con formato."""
import unittest

from gestor import db, textos
from tests import ayudas, datos_prueba

DESTINO_HBI = "al Hospital del Bicentenario de Ituzaingó"

GOLDEN_EFIA = (
    "Por medio del expediente EX-2026-89654857- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 0003B00031812 por la "
    "suma de PESOS UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100 CENTAVOS ($ 1.224.990,00-) del "
    "proveedor GRUPO EFIA S.R.L. correspondiente al servicio de control integral de plagas, fumigación, desinsectación y "
    "desratización, conforme al remito N° 00001-00029461, con destino al Hospital del Bicentenario de Ituzaingó, en el mes "
    "de agosto del 2026 de acuerdo a la Orden de compra N° 4500555861."
)

GOLDEN_BIOFAB = (
    "Por medio del expediente EX-2026-94963848- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 00002B00003908 por la "
    "suma de PESOS VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100 CENTAVOS ($ 21.095.000,00-) del proveedor BIO FAB "
    "S.R.L correspondiente a la provisión de inmunoensayo por fluorescencia, conforme al remito N° 0001-00003354, y el "
    "remito n° 0001-00003281, correspondiente al equipo entregado en calidad de comodato, con destino al Hospital del "
    "Bicentenario de Ituzaingó, en el mes de agosto del 2026 de acuerdo a la Orden de compra N° 4500587121."
)


def ctx_efia(**cambios):
    ctx = {
        "efector": "HBI", "destino": DESTINO_HBI, "sap": "77170", "razon": "GRUPO EFIA S.R.L.", "oc": "4500555861",
        "factura": "0003B00031812", "centavos": 122499000, "periodo": "2026-08", "periodo_desde": "2026-08-01",
        "periodo_hasta": "2026-08-31", "dia_inicio": 1, "remitos": ["00001-00029461"], "remito_equipo": None,
        "comodato": False, "primera_validacion": True, "tipo_oc": "SERVICIO",
        "objeto": "servicio de control integral de plagas, fumigación, desinsectación y desratización", "articulo": "al",
        "expediente": "EX-2026-89654857- -INSSJP-GESP#INSSJP", "orden_remito_equipo": None,
        "nota_comodato": "NO-2026-38484415-INSSJP-GESP#INSSJP",
    }
    ctx.update(cambios)
    return ctx


def ctx_biofab(**cambios):
    datos = dict(
        sap="116467", razon="BIO FAB S.R.L", oc="4500587121", factura="00002B00003908", centavos=2109500000,
        remitos=["0001-00003354"], remito_equipo="0001-00003281", comodato=True, tipo_oc="BIEN",
        objeto="provisión de inmunoensayo por fluorescencia", articulo="a la",
        expediente="EX-2026-94963848- -INSSJP-GESP#INSSJP", orden_remito_equipo="7",
    )
    datos.update(cambios)
    return ctx_efia(**datos)


def _parrafo(texto, desde, hasta):
    inicio = texto.index(desde)
    fin = texto.index(hasta, inicio) + len(hasta)
    return ayudas.normalizar_espacios(texto[inicio:fin])


class PruebaAutorizacion(unittest.TestCase):

    def test_golden_efia(self):
        autorizacion = textos.autorizacion(ctx_efia())
        self.assertEqual(autorizacion["referencia"], "AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26")
        self.assertEqual(autorizacion["cuerpo"], GOLDEN_EFIA)

    def test_efia_coincide_con_original_salvo_diferencias_aceptadas(self):
        original = _parrafo(ayudas.texto_fixture("EX-2026-89654857_EFIA", "0009_IF-2026-91157933*.txt"),
                            "Por medio del expediente", "4500555861.")
        generado = textos.autorizacion(ctx_efia())["cuerpo"]
        generado = generado.replace(", con destino al Hospital del Bicentenario de Ituzaingó,", "").replace("del 2026", "2026")
        self.assertEqual(ayudas.normalizar_espacios(generado), original)

    def test_golden_biofab_con_comodato(self):
        self.assertEqual(textos.autorizacion(ctx_biofab())["cuerpo"], GOLDEN_BIOFAB)
        # sin primera validación, la frase del comodato no va
        sin = textos.autorizacion(ctx_biofab(primera_validacion=False))["cuerpo"]
        self.assertNotIn("comodato", sin)

    def test_macatex_sin_objeto_no_genera(self):
        ctx = ctx_efia(oc="4500594643", razon="MACATEX S.A", objeto="", articulo="al")
        with self.assertRaises(textos.TextoIncompleto) as error:
            textos.autorizacion(ctx)
        self.assertEqual(str(error.exception), "Falta el objeto de la contratación en la OC 4500594643")
        for faltante in ({"remitos": []}, {"factura": ""}, {"expediente": ""}):
            with self.assertRaises(textos.TextoIncompleto):
                textos.autorizacion(ctx_efia(**faltante))

    def test_frase_remitos_uno_dos_tres(self):
        self.assertEqual(textos.frase_remitos(["A"]), "conforme al remito N° A")
        self.assertEqual(textos.frase_remitos(["A", "B"]), "conforme a los remitos N° A y B")
        self.assertEqual(textos.frase_remitos(["A", "B", "C"]), "conforme a los remitos N° A, B y C")

    def test_periodo_especifico(self):
        ctx = ctx_efia(dia_inicio=17, periodo="2026-11", periodo_desde="2026-10-17", periodo_hasta="2026-11-16")
        self.assertEqual(textos.frase_periodo(ctx), "en el período del 17/10/2026 al 16/11/2026")
        self.assertIn("en el período del 17/10/2026 al 16/11/2026 de acuerdo", textos.autorizacion(ctx)["cuerpo"])
        self.assertEqual(textos.frase_periodo(ctx_efia()), "en el mes de agosto del 2026")

    def test_referencia_casph(self):
        autorizacion = textos.autorizacion(ctx_efia(efector="CASPH", destino="al Centro Ambulatorio de Salud PAMI Hurlingham"))
        self.assertEqual(autorizacion["referencia"], "CASPH - AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26")
        self.assertIn(", con destino al Centro Ambulatorio de Salud PAMI Hurlingham, en el mes", autorizacion["cuerpo"])

    def test_constancia_biofab_coincide_con_original(self):
        constancia = textos.constancia_comodato(ctx_biofab())
        self.assertEqual(constancia["referencia"], "CONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC 4500587121, BIO FAB S.R.L")
        self.assertEqual(constancia["cuerpo"].count("\n"), 1)
        original = _parrafo(ayudas.texto_fixture("EX-2026-94963848_BIOFAB", "0008_PV-2026-96851161*.txt"),
                            "Por medio de la presente", "validación.").replace("BIO FAB S.R.L.", "BIO FAB S.R.L")
        self.assertEqual(ayudas.normalizar_espacios(constancia["cuerpo"]), original)
        with self.assertRaises(textos.TextoIncompleto):
            textos.constancia_comodato(ctx_biofab(orden_remito_equipo=None))


class PruebaCopiarConFormato(ayudas.CasoConServidor):

    def test_app_js_copia_html_justificado(self):
        script = self.servidor.get("/app.js").texto()
        self.assertIn("ClipboardItem", script)
        self.assertIn("text-align: justify", script)

    def test_textos_por_api_con_autorizacion_y_constancia(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_biofab(con)
        finally:
            con.close()
        sin_ex = self.servidor.get("/api/expedientes/%d/textos" % exp["id"]).json()["datos"]
        self.assertNotIn("autorizacion", sin_ex)
        self.assertIn("expediente", sin_ex["autorizacion_error"])
        gde = {"expediente": "EX-2026-94963848- -INSSJP-GESP#INSSJP", "orden_remito_equipo": "7"}
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": exp["version"], "cambios": {"datos": {"gde": gde}}})
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = self.servidor.get("/api/expedientes/%d/textos" % exp["id"]).json()["datos"]
        self.assertEqual(datos["autorizacion"]["cuerpo"], GOLDEN_BIOFAB)
        self.assertEqual(datos["constancia_comodato"]["referencia"],
                         "CONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC 4500587121, BIO FAB S.R.L")


if __name__ == "__main__":
    unittest.main()
