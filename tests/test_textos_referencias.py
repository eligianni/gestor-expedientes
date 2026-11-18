"""Paso 16: carátula, referencias GDE y nombres de archivo (goldens del blueprint §5)."""
import unittest

from gestor import db, textos
from tests import ayudas, datos_prueba


def _ctx(**cambios):
    ctx = {
        "efector": "HBI",
        "sap": "77170",
        "razon": "GRUPO EFIA S.R.L.",
        "oc": "4500555861",
        "factura": "0003B00031812",
        "periodo": "2026-08",
        "remitos": ["00001-00029461"],
        "remito_equipo": None,
        "primera_validacion": True,
        "tipo_oc": "SERVICIO",
    }
    ctx.update(cambios)
    return ctx


BIOFAB = dict(sap="116467", razon="BIO FAB S.R.L", oc="4500587121", factura="00002B00003908",
              remitos=["0001-00003354"], remito_equipo="0001-00003281", tipo_oc="BIEN")
MACATEX = dict(sap="118896", razon="MACATEX S.A", oc="4500594643", factura="0002B00000160", periodo="2026-09",
               remitos=["0001-00004409"], tipo_oc="BIEN")

REFERENCIAS_EFIA = [
    "08-26 - FC 0003B00031812 - GRUPO EFIA S.R.L.",
    "08-26 - CARGA EN SII - GRUPO EFIA S.R.L.",
    "08-26 - RTO 00001-00029461 - GRUPO EFIA S.R.L.",
    "08-26 - CERTIFICADO DE VALIDACIÓN - GRUPO EFIA S.R.L.",
    "08-26 - HOJA DE ENTRADA - GRUPO EFIA S.R.L.",
    "AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26",
    "08-26 - CONSTANCIA DE CONTABILIZACIÓN - GRUPO EFIA S.R.L.",
]


def _textos(ctx):
    return [r["referencia"] for r in textos.referencias(ctx)]


class PruebaReferencias(unittest.TestCase):

    def test_caratulas_de_los_tres_expedientes(self):
        self.assertEqual(textos.caratula(_ctx()), "PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861")
        self.assertEqual(textos.caratula(_ctx(**BIOFAB)), "PAGO SAP 116467 BIO FAB S.R.L - FC 00002B00003908 - 4500587121")
        self.assertEqual(textos.caratula(_ctx(**MACATEX)), "PAGO SAP 118896 MACATEX S.A - FC 0002B00000160 - 4500594643")

    def test_referencias_efia(self):
        referencias = textos.referencias(_ctx())
        self.assertEqual([r["referencia"] for r in referencias], REFERENCIAS_EFIA)
        self.assertEqual(referencias[0]["archivo"], "08-26 - FC 0003B00031812 - GRUPO EFIA S.R.L..pdf")
        self.assertEqual(len({r["clave"] for r in referencias}), len(referencias))

    def test_varios_remitos_un_solo_documento(self):
        generadas = _textos(_ctx(remitos=["0001-00000001", "0001-00000002"]))
        self.assertIn("08-26 - REMITOS - GRUPO EFIA S.R.L.", generadas)
        self.assertFalse([r for r in generadas if " RTO " in r])
        self.assertEqual(len(generadas), 7)
        # bien/provisión → vale de entrada
        self.assertIn("09-26 - VALE DE ENTRADA - MACATEX S.A", _textos(_ctx(**MACATEX)))

    def test_remito_de_equipo_en_comodato(self):
        generadas = _textos(_ctx(**BIOFAB))
        self.assertEqual(generadas[2:4], [
            "08-26 - RTO 0001-00003354 - BIO FAB S.R.L",
            "08-26 - REMITO POR EQUIPO EN COMODATO - BIO FAB S.R.L",
        ])
        self.assertEqual(len(generadas), 8)
        # fuera de la primera validación el remito del equipo no va
        self.assertNotIn("08-26 - REMITO POR EQUIPO EN COMODATO - BIO FAB S.R.L",
                         _textos(_ctx(**dict(BIOFAB, primera_validacion=False))))

    def test_prefijo_casph(self):
        generadas = _textos(_ctx(efector="CASPH"))
        self.assertTrue(all(r.startswith("CASPH - ") for r in generadas))
        self.assertIn("CASPH - AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26", generadas)
        self.assertEqual(textos.caratula(_ctx(efector="CASPH")),
                         "CASPH - PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861")

    def test_nombre_archivo_reemplaza_invalidos(self):
        self.assertEqual(textos.nombre_archivo("08-26 - RTO 1/2 - X:Y"), "08-26 - RTO 1-2 - X-Y.pdf")
        self.assertEqual(textos.nombre_archivo('a\\b*c?d"e<f>g|h'), "a-b-c-d-e-f-g-h.pdf")

    def test_datos_faltantes(self):
        with self.assertRaises(textos.TextoIncompleto):
            textos.caratula(_ctx(factura=""))
        with self.assertRaises(textos.TextoIncompleto):
            textos.referencias(_ctx(periodo=None))
        with self.assertRaises(textos.TextoIncompleto):
            textos.referencias(_ctx(remitos=[]))


class PruebaTextosApi(ayudas.CasoConServidor):

    def test_textos_efia_por_api(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
        finally:
            con.close()
        resp = self.servidor.get("/api/expedientes/%d/textos" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()["datos"]
        self.assertEqual(datos["caratula"], "PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861")
        self.assertEqual([r["referencia"] for r in datos["referencias"]], REFERENCIAS_EFIA)

    def test_textos_biofab_y_texto_incompleto(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            biofab = datos_prueba.armar_expediente_biofab(con)
            vacio = datos_prueba.armar_expediente_macatex(con)
        finally:
            con.close()
        datos = self.servidor.get("/api/expedientes/%d/textos" % biofab["id"]).json()["datos"]
        self.assertEqual(datos["caratula"], "PAGO SAP 116467 BIO FAB S.R.L - FC 00002B00003908 - 4500587121")
        self.assertIn("08-26 - REMITO POR EQUIPO EN COMODATO - BIO FAB S.R.L", [r["referencia"] for r in datos["referencias"]])
        nuevo = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": vacio["oc"]}).json()["datos"]
        incompleto = self.servidor.get("/api/expedientes/%d/textos" % nuevo["id"])
        self.assertEqual(incompleto.estado, 422)
        self.assertEqual(incompleto.json()["error"]["codigo"], "negocio")


if __name__ == "__main__":
    unittest.main()
