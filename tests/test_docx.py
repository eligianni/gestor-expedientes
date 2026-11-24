"""Paso 18: certificado de validación (CV) desde la plantilla y autorización en Word."""
import copy
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

from gestor import config, db, docx_gen, negocio
from tests import ayudas, datos_prueba

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PLANTILLA_HBI = Path(config.RAIZ) / "plantillas" / "cv_hbi.docx"
PLANTILLA_CASPH = Path(config.RAIZ) / "plantillas" / "cv_casph.docx"
EX_EFIA = "EX-2026-89654857- -INSSJP-GESP#INSSJP"


def _documento(contenido):
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        return z.read("word/document.xml")


def _texto(contenido):
    raiz = ET.fromstring(_documento(contenido))
    return "\n".join("".join(t.text or "" for t in p.iter(W + "t")) for p in raiz.iter(W + "p"))


def _filas_de_renglones(contenido):
    raiz = ET.fromstring(_documento(contenido))
    for tabla in raiz.iter(W + "tbl"):
        filas = tabla.findall(W + "tr")
        primera = "".join(t.text or "" for t in filas[0].iter(W + "t"))
        if primera.startswith("Renglón"):
            return [["".join(t.text or "" for t in tc.iter(W + "t")) for tc in fila.findall(W + "tc")] for fila in filas[1:]]
    raise AssertionError("no está la tabla de renglones")


def _datos_cv(**cambios):
    datos = {
        "fecha": date(2026, 9, 1), "proveedor": "PROVEEDOR S.A.", "sap": "99001", "expediente": "EX-2026-1- -INSSJP-GESP#INSSJP",
        "ca": "1-2026", "oc": "4500000001", "vigencia": "01/01/2026 a 31/12/2026", "rubro": "Bienes", "entrega": "Parcial",
        "periodo_texto": "agosto 2026", "objeto": "provisión de insumos",
        "renglones": [{"renglon": "1", "descripcion": "INSUMO", "cantidad_oc": "10", "cantidad_entregada": "2",
                       "fecha_entrega": "05/08/2026"}],
        "observacion": "", "remitos": ["0001-00000001"],
    }
    datos.update(cambios)
    return datos


class PruebaDocx(ayudas.CasoConServidor):

    def _con(self):
        con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(con.close)
        return con

    def _efia(self):
        exp = datos_prueba.armar_expediente_efia(self._con())
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"],
                                 {"version": exp["version"], "cambios": {"datos": {"gde": {"expediente": EX_EFIA}}}})
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_cv_efia_contenido(self):
        exp = self._efia()
        resp = self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
        self.assertEqual(resp.cabeceras["Content-Type"],
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertIn("filename*=UTF-8''08-26%20-%20CERTIFICADO%20DE%20VALIDACI%C3%93N", resp.cabeceras["Content-Disposition"])
        self.assertTrue(resp.cabeceras["Content-Disposition"].endswith(".docx"))
        texto = _texto(resp.cuerpo)
        for esperado in ("GRUPO EFIA S.R.L.", "4500555861", "77170", "195-2025", "Servicios", "Mensual",
                         "01/10/2025 a 30/09/2026",
                         "Objeto de Contratación: Servicio de control integral de plagas",
                         "Se valida con remito 00001-00029461 correspondiente al período agosto 2026."):
            self.assertIn(esperado, texto)
        self.assertNotIn("_____", texto)
        self.assertEqual(_filas_de_renglones(resp.cuerpo),
                         [["1", "SERV INTEGRAL CONTROL DE PLAGAS", "9", "1", "31/08/2026"]])
        # La fecha («24 de Septiembre del 2026») entra en un renglón: la celda se ensancha hacia la izquierda.
        documento = zipfile.ZipFile(io.BytesIO(resp.cuerpo)).read("word/document.xml").decode("utf-8")
        self.assertIn('<w:gridCol w:w="3098" />', documento.replace('"/>', '" />'))

    def test_cv_lleva_todos_los_renglones(self):
        # Los renglones sin entregas en el período también van, con cantidad entregada 0.
        exp = self._efia()
        negocio.agregar_renglon(self._con(), datos_prueba.OC_EFIA_MANUAL["numero"], {
            "descripcion": "SERV CONTROL DE PLAGAS ADICIONAL", "cantidad": "3", "unidad": "UN", "precio_centavos": 100000})
        filas = _filas_de_renglones(self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"]).cuerpo)
        self.assertEqual(filas, [["1", "SERV INTEGRAL CONTROL DE PLAGAS", "9", "1", "31/08/2026"],
                                 ["2", "SERV CONTROL DE PLAGAS ADICIONAL", "3", "0", ""]])

    def test_cv_conserva_partes_no_tocadas(self):
        exp = self._efia()
        contenido = self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"]).cuerpo
        with zipfile.ZipFile(PLANTILLA_HBI) as original, zipfile.ZipFile(io.BytesIO(contenido)) as generado:
            self.assertEqual(generado.namelist(), original.namelist())
            for nombre in original.namelist():
                if nombre != "word/document.xml":
                    self.assertEqual(generado.read(nombre), original.read(nombre), nombre)
            self.assertEqual(generado.read("word/media/image1.jpeg"), original.read("word/media/image1.jpeg"))
            self.assertEqual(generado.read("word/header1.xml"), original.read("word/header1.xml"))
            # el documento conserva todas las declaraciones de namespaces del original
            primera = generado.read("word/document.xml").decode("utf-8").split(">", 2)[1]
            for prefijo in ("w", "r", "mc", "w14", "wp"):
                if ("xmlns:%s=" % prefijo) in original.read("word/document.xml").decode("utf-8").split(">", 2)[1]:
                    self.assertIn("xmlns:%s=" % prefijo, primera)

    def test_cv_casph_conserva_footer2(self):
        contenido = docx_gen.generar_cv(PLANTILLA_CASPH, _datos_cv())
        with zipfile.ZipFile(PLANTILLA_CASPH) as original, zipfile.ZipFile(io.BytesIO(contenido)) as generado:
            self.assertEqual(generado.read("word/footer2.xml"), original.read("word/footer2.xml"))
        texto = _texto(contenido)
        self.assertIn("1 de Septiembre del 2026", texto)
        self.assertIn("CENTRO AMBULATORIO DE SALUD PAMI HURLINGHAM", texto)

    def test_cv_varios_remitos_y_filas(self):
        renglones = [{"renglon": str(i), "descripcion": "ITEM %d" % i, "cantidad_oc": "100", "cantidad_entregada": "10",
                      "fecha_entrega": "05/08/2026"} for i in range(1, 6)]
        contenido = docx_gen.generar_cv(PLANTILLA_HBI, _datos_cv(renglones=renglones, remitos=["A", "B", "C"]))
        self.assertIn("Se valida con remitos A, B y C correspondientes al período agosto 2026.", _texto(contenido))
        filas = _filas_de_renglones(contenido)
        self.assertEqual(len(filas), 5)
        self.assertEqual(filas[4], ["5", "ITEM 5", "100", "10", "05/08/2026"])
        self.assertEqual(docx_gen.frase_validacion(["A", "B"], "17/10/2026 al 16/11/2026"),
                         "Se valida con remitos A y B correspondientes al período 17/10/2026 al 16/11/2026.")

    def test_cv_anio_correcto(self):
        oc = copy.deepcopy(datos_prueba.OC_EFIA_MANUAL)
        oc.update(numero="4500900127", vig_desde="2027-01-01", vig_hasta="2027-12-31")
        con = self._con()
        negocio.crear_oc_manual(con, oc)
        exp = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": oc["numero"]})
        exp = negocio.pegar_remitos(con, exp["id"], exp["version"], "0001-00000077;15/03/2027")
        remitos = exp["datos"]["remitos"]
        remitos[0]["items"] = [{"pos": 1, "cantidad": "1", "codigo": ""}]
        factura = {"numero": "0003B00040000", "fecha": "2027-04-05", "centavos": 122499000}
        exp = negocio.actualizar_expediente(con, exp["id"], exp["version"], {"datos": {"remitos": remitos, "factura": factura}})
        resp = self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
        texto = _texto(resp.cuerpo)
        self.assertIn("31 de Marzo del 2027", texto)
        self.assertNotIn("del 2026", texto)
        self.assertIn("correspondiente al período marzo 2027.", texto)

    def test_autorizacion_docx_justificada(self):
        exp = self._efia()
        resp = self.servidor.get("/api/expedientes/%d/autorizacion.docx" % exp["id"])
        self.assertEqual(resp.estado, 200, resp.cuerpo[:300])
        self.assertIn("AUTORIZACI%C3%93N%20DE%20PAGO", resp.cabeceras["Content-Disposition"])
        raiz = ET.fromstring(_documento(resp.cuerpo))
        parrafos = list(raiz.iter(W + "p"))
        self.assertEqual("".join(t.text for t in parrafos[0].iter(W + "t")),
                         "AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26")
        self.assertIsNotNone(parrafos[0].find(W + "r/" + W + "rPr/" + W + "b"))
        cuerpo = parrafos[1]
        self.assertEqual(cuerpo.find(W + "pPr/" + W + "jc").get(W + "val"), "both")
        texto = "".join(t.text for t in cuerpo.iter(W + "t"))
        self.assertTrue(texto.startswith("Por medio del expediente " + EX_EFIA + " AUTORIZO se abone la factura N° 0003B00031812"))
        self.assertTrue(texto.endswith("de acuerdo a la Orden de compra N° 4500555861."))

    def test_sin_objeto_da_422(self):
        exp = datos_prueba.armar_expediente_macatex(self._con())
        resp = self.servidor.get("/api/expedientes/%d/cv.docx" % exp["id"])
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "Falta el objeto de la contratación en la OC 4500594643")


if __name__ == "__main__":
    unittest.main()
