"""Paso 14: notas aclaratorias redactadas para los controles salvables."""
import unittest

from gestor import controles, db
from tests import ayudas, datos_prueba

NOTA_BIOFAB = (
    "Se deja constancia de que en el remito N° 0001-00003354 el renglón 2 figura con el código 5002383, cuando el "
    "código correcto según la Orden de Compra N° 4500587121 es 5003283. Se trata de un error de tipeo que no afecta "
    "lo entregado."
)


class PruebaNotas(ayudas.CasoConServidor):

    def _armar(self, funcion, **kwargs):
        con = db.conectar(self.entorno.ruta_base)
        try:
            return funcion(con, **kwargs)
        finally:
            con.close()

    def _controles(self, exp):
        resp = self.servidor.get("/api/expedientes/%d/controles" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _editar_factura(self, exp, **cambios):
        factura = dict(exp["datos"]["factura"], **cambios)
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"],
                                 {"version": exp["version"], "cambios": {"datos": {"factura": factura}}})
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_nota_biofab_codigo_exacta(self):
        exp = self._armar(datos_prueba.armar_expediente_biofab)
        salvable = [r for r in self._controles(exp)["resultados"] if r["nivel"] == "salvable"]
        self.assertEqual(len(salvable), 1)
        self.assertEqual(salvable[0]["nota_sugerida"], NOTA_BIOFAB)
        self.assertIsNone(salvable[0]["nota_guardada"])

    def test_nota_guardada_cuenta_como_resuelta(self):
        exp = self._armar(datos_prueba.armar_expediente_biofab)
        antes = self._controles(exp)
        self.assertEqual(antes["resumen"]["salvable_con_nota"], 0)
        resp = self.servidor.post("/api/expedientes/%d/notas" % exp["id"], {
            "version": exp["version"], "codigo": "codigo_remito_distinto", "referencia": "2", "texto": NOTA_BIOFAB,
        })
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()["datos"]
        self.assertEqual(datos["resumen"]["salvable_con_nota"], 1)
        resultado = next(r for r in datos["resultados"] if r["codigo"] == "codigo_remito_distinto")
        self.assertEqual(resultado["nota_guardada"]["texto"], NOTA_BIOFAB)
        self.assertEqual(datos["expediente"]["datos"]["historial"][-1]["accion"], "NOTA_ACLARATORIA")

        # guardar otra vez la misma nota la reemplaza (no la duplica)
        otra = self.servidor.post("/api/expedientes/%d/notas" % exp["id"], {
            "version": datos["expediente"]["version"], "codigo": "codigo_remito_distinto", "referencia": "2",
            "texto": "Otra redacción.",
        }).json()["datos"]
        self.assertEqual(len(otra["expediente"]["datos"]["notas_aclaratorias"]), 1)
        self.assertEqual(otra["resumen"]["salvable_con_nota"], 1)

        # versión vieja → 409
        vieja = self.servidor.post("/api/expedientes/%d/notas" % exp["id"], {
            "version": exp["version"], "codigo": "codigo_remito_distinto", "referencia": "2", "texto": "x",
        })
        self.assertEqual(vieja.estado, 409)

    def test_error_de_importe_no_tiene_nota(self):
        exp = self._armar(datos_prueba.armar_expediente_efia, centavos=122499001)
        importe = next(r for r in self._controles(exp)["resultados"] if r["codigo"] == "importe_factura")
        self.assertEqual(importe["nivel"], "error")
        self.assertNotIn("nota_sugerida", importe)
        resp = self.servidor.post("/api/expedientes/%d/notas" % exp["id"], {
            "version": exp["version"], "codigo": "importe_factura", "referencia": None, "texto": "Aclaración",
        })
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "Un error de importe no se salva con nota aclaratoria.")
        otro = self.servidor.post("/api/expedientes/%d/notas" % exp["id"], {
            "version": exp["version"], "codigo": "objeto_faltante", "referencia": None, "texto": "Aclaración",
        })
        self.assertEqual((otro.estado, otro.json()["error"]["mensaje"]), (422, "Ese control no admite nota aclaratoria."))

    def test_nota_periodo_factura_exacta(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        exp = self._editar_factura(exp, periodo_desde="2026-07-01", periodo_hasta="2026-07-31")
        periodo = [r for r in self._controles(exp)["resultados"] if r["codigo"] == "periodo_factura"]
        self.assertEqual(len(periodo), 1)
        self.assertEqual(periodo[0]["nivel"], "salvable")
        self.assertEqual(
            periodo[0]["nota_sugerida"],
            "Se deja constancia de que la factura N° 0003B00031812 indica el período 2026-07, cuando el período "
            "validado según remito es 2026-08.",
        )
        self.assertEqual(controles.periodo_de_factura_texto("2026-07-15", "2026-08-14"), "15/07/2026 al 14/08/2026")

    def test_nota_menciones_factura(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        exp = self._editar_factura(exp, menciona={"oc": "4500555861", "remito": "00001-00029999"})
        menciones = [r for r in self._controles(exp)["resultados"] if r["codigo"] == "menciones_factura"]
        self.assertEqual([r["referencia"] for r in menciones], ["remito"])
        self.assertEqual(
            menciones[0]["nota_sugerida"],
            "Se deja constancia de que la factura N° 0003B00031812 menciona el remito N° 00001-00029999, cuando "
            "corresponde 00001-00029461.",
        )


if __name__ == "__main__":
    unittest.main()
