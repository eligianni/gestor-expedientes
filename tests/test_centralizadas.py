"""Paso 27: centralizadas — nota a Central (golden), controles, leyenda del CV y marca ◆ del calendario."""
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from gestor import controles, db, negocio, textos
from tests import ayudas

OC_CENTRAL = "4500000001"
EX_CENTRAL = "EX-2025-11111111- -INSSJP-GESP#INSSJP"
LEYENDA = "Servicio contratado por Nivel Central; el efector solo valida la prestación."

GOLDEN_REFERENCIA = ("VALIDACIÓN DE BIENES Y SERVICIOS PROVEEDOR CENTRAL S.A. - EX-2025-11111111- -INSSJP-GESP#INSSJP, "
                     "período 08-2026")
GOLDEN_CUERPO = (
    "Se envían como archivos embebidos la validación del servicio y remito correspondientes al proveedor "
    "PROVEEDOR CENTRAL S.A., del EX-2025-11111111- -INSSJP-GESP#INSSJP, con orden de compra 4500000001, período 08-2026."
    "\nDocumentación embebida:"
    "\n- Remito"
    "\n- Factura"
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def ctx_central(**cambios):
    ctx = {
        "razon": "PROVEEDOR CENTRAL S.A.", "expediente_contratacion": EX_CENTRAL, "oc": OC_CENTRAL,
        "periodo": "2026-08", "periodo_desde": "2026-08-01", "periodo_hasta": "2026-08-31", "dia_inicio": 1,
        "doc_requerida_central": ["Remito", "Factura"],
    }
    ctx.update(cambios)
    return ctx


def armar_central(con, leyenda=LEYENDA, checklist=None):
    """OC 4500000001 centralizada y su expediente CENTRALIZADA de 2026-08 con remito y factura."""
    negocio.crear_oc_manual(con, {
        "numero": OC_CENTRAL, "efector": "HBI", "sap": "900001", "razon_social": "PROVEEDOR CENTRAL S.A.",
        "fecha_oc": "2025-12-15", "vig_desde": "2026-01-01", "vig_hasta": "2026-12-31", "ca": "10-2025",
        "expediente_contratacion": EX_CENTRAL, "objeto": "servicio de mantenimiento centralizado", "objeto_articulo": "al",
        "concepto_corto": "SERV. CENTRAL", "centralizada": 1, "leyenda_cv": leyenda,
        "doc_requerida_central": ["Remito", "Factura"],
        "renglones": [{"pos": 1, "descripcion": "SERVICIO MENSUAL", "cantidad": "12", "unidad": "MES",
                       "precio_centavos": 10000000, "importe_centavos": 120000000}],
    })
    exp = negocio.crear_expediente(con, {"tipo": "CENTRALIZADA", "oc": OC_CENTRAL})
    exp = negocio.pegar_remitos(con, exp["id"], exp["version"], "0001-00001234;31/08/2026")
    remitos = exp["datos"]["remitos"]
    remitos[0]["items"] = [{"pos": 1, "cantidad": "1"}]
    return negocio.actualizar_expediente(con, exp["id"], exp["version"], {"datos": {
        "remitos": remitos,
        "factura": {"numero": "0001B00000123", "fecha": "2026-09-02", "centavos": 10000000},
        "checklist": {"Remito": True, "Factura": True} if checklist is None else checklist,
    }})


class PruebaCentralizadas(ayudas.CasoConServidor):

    def _con(self):
        return db.conectar(self.entorno.ruta_base)

    def _armar(self, **kwargs):
        con = self._con()
        try:
            return armar_central(con, **kwargs)
        finally:
            con.close()

    def _resultados(self, id_expediente):
        resp = self.servidor.get("/api/expedientes/%d/controles" % id_expediente)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]["resultados"]

    def test_nota_central_golden(self):
        nota = textos.nota_central(ctx_central())
        self.assertEqual(nota, {"referencia": GOLDEN_REFERENCIA, "cuerpo": GOLDEN_CUERPO})
        especifico = textos.nota_central(ctx_central(dia_inicio=17, periodo="2026-08", periodo_desde="2026-07-17",
                                                     periodo_hasta="2026-08-16"))
        self.assertTrue(especifico["referencia"].endswith("período 17/07/2026 al 16/08/2026"))
        self.assertIn("con orden de compra 4500000001, período 17/07/2026 al 16/08/2026.", especifico["cuerpo"])
        with self.assertRaises(textos.TextoIncompleto):
            textos.nota_central(ctx_central(expediente_contratacion=""))
        # por la API, solo para CENTRALIZADA
        exp = self._armar()
        datos = self.servidor.get("/api/expedientes/%d/textos" % exp["id"]).json()["datos"]
        self.assertEqual(datos["nota_central"], {"referencia": GOLDEN_REFERENCIA, "cuerpo": GOLDEN_CUERPO})

    def test_checklist_incompleto_es_error(self):
        exp = self._armar(checklist={"Remito": True, "Factura": False})
        errores = [r for r in self._resultados(exp["id"]) if r["codigo"] == "documentacion_centralizada"]
        self.assertEqual(len(errores), 1)
        self.assertEqual((errores[0]["nivel"], errores[0]["mensaje"]),
                         ("error", "Falta tildar como auditada la documentación: Factura."))

    def test_leyenda_faltante_es_error(self):
        exp = self._armar(leyenda="")
        errores = [r for r in self._resultados(exp["id"]) if r["codigo"] == "leyenda_cv_faltante"]
        self.assertEqual(len(errores), 1)
        self.assertEqual((errores[0]["nivel"], errores[0]["mensaje"]), ("error", "Falta la leyenda del CV en la OC 4500000001."))
        # con leyenda no aparece, y un expediente COMUN no la pide
        con = self._con()
        try:
            ctx = controles.armar_contexto(con, exp["id"])
        finally:
            con.close()
        ctx["oc"] = dict(ctx["oc"], leyenda_cv=LEYENDA)
        self.assertEqual(controles.control_leyenda_cv_faltante(ctx), [])
        ctx["oc"] = dict(ctx["oc"], leyenda_cv="")
        ctx["expediente"] = dict(ctx["expediente"], tipo="COMUN")
        self.assertEqual(controles.control_leyenda_cv_faltante(ctx), [])

    def test_cv_lleva_la_leyenda(self):
        exp = self._armar()
        resp = self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
        with zipfile.ZipFile(io.BytesIO(resp.cuerpo)) as z:
            raiz = ET.fromstring(z.read("word/document.xml"))
        parrafos = ["".join(t.text or "" for t in p.iter(W + "t")) for p in raiz.iter(W + "p")]
        self.assertIn("Observaciones: " + LEYENDA, parrafos)

    def test_rombo_en_calendario(self):
        exp = self._armar()
        ruta = "/api/expedientes/%d/centralizada" % exp["id"]
        malo = self.servidor.put(ruta, {"version": exp["version"], "centralizada": {"numero_nota": "NO-2026-1"}})
        self.assertEqual(malo.estado, 400)
        resp = self.servidor.put(ruta, {"version": exp["version"], "centralizada": {
            "numero_cv": "if-2026-90000001-INSSJP-GESP%INSSJP", "numero_nota": "NO-2026-90000002-INSSJP-GESP#INSSJP",
            "fecha_envio": "10/09/2026",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        central = resp.json()["datos"]["datos"]["centralizada"]
        self.assertEqual(central, {"numero_cv": "IF-2026-90000001-INSSJP-GESP#INSSJP",
                                   "numero_nota": "NO-2026-90000002-INSSJP-GESP#INSSJP", "fecha_envio": "2026-09-10"})
        calendario = self.servidor.get("/api/calendario?anio=2026&hoy=2026-09-20").json()["datos"]
        fila = next(f for f in calendario["filas"] if f["oc"] == OC_CENTRAL)
        self.assertTrue(fila["celdas"][7]["centralizada_enviada"])
        self.assertFalse(fila["celdas"][6]["centralizada_enviada"])
        lista = self.servidor.get("/api/centralizadas?anio=2026").json()["datos"]
        self.assertEqual([(c["id"], c["periodo"], c["enviada"]) for c in lista["expedientes"]], [(exp["id"], "2026-08", True)])
        # versión vieja → 409
        self.assertEqual(self.servidor.put(ruta, {"version": exp["version"], "centralizada": {}}).estado, 409)


if __name__ == "__main__":
    unittest.main()
