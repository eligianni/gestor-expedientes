"""El certificado de validación se puede bajar antes de cargar la factura y la carga en el SII."""
from gestor import db, negocio
from tests import ayudas, datos_prueba


class PruebaCvSinFactura(ayudas.CasoConServidor):

    def test_con_remitos_y_cantidades_alcanza(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
            exp = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": datos_prueba.OC_EFIA_MANUAL["numero"]})
        finally:
            con.close()
        ruta = "/api/expedientes/%d" % exp["id"]
        # Sin remitos todavía: avisa qué falta, sin bajar nada.
        resp = self.servidor.get(ruta + "/cv/verificar")
        self.assertEqual(resp.estado, 422)
        self.assertIn("período", resp.json()["error"]["mensaje"])
        exp = self.servidor.post(ruta + "/remitos/pegar", {"version": exp["version"], "remitos": [
            {"numero": "00001-00029461", "fecha": "2026-08-31"}]}).json()["datos"]
        remitos = exp["datos"]["remitos"]
        remitos[0]["items"] = [{"pos": 1, "cantidad": "1", "codigo": ""}]
        self.servidor.put(ruta, {"version": exp["version"], "cambios": {"datos": {"remitos": remitos}}})
        resp = self.servidor.get(ruta + "/cv/verificar")
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["archivo"], "08-26 - CERTIFICADO DE VALIDACIÓN - GRUPO EFIA S.R.L..docx")
        docx = self.servidor.get(ruta + "/cv.docx")
        self.assertEqual(docx.estado, 200)
        self.assertTrue(docx.cuerpo.startswith(b"PK"))
