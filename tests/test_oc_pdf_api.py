"""PDF de la OC por la API: leer y comparar con la base, aplicar lo elegido y que la importación no lo pise."""
import tempfile
from pathlib import Path

from gestor import db, negocio
from tests import ayudas, datos_prueba, pdf_prueba

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "expedientes"


def texto_oc(carpeta):
    return next((FIXTURES / carpeta).glob("0005_*.txt")).read_text(encoding="utf-8")


class PruebaOcPdfApi(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def _pdf(self, carpeta, **variante):
        ruta = Path(self.carpeta.name) / ("%s.pdf" % carpeta)
        ruta.write_bytes(pdf_prueba.pdf_desde_texto(texto_oc(carpeta), fuente="cid", envolver=True, **variante))
        return ruta

    def _leer(self, numero, carpeta):
        resp = self.servidor.subir("/api/oc/%s/pdf" % numero, self._pdf(carpeta))
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_macatex_objeto_y_unidades_desde_el_pdf(self):
        datos_prueba.preparar_macatex(self.con)
        comparacion = self._leer(datos_prueba.OC_MACATEX, "EX-2026-99349179_MACATEX")
        self.assertEqual(comparacion["archivo"], "EX-2026-99349179_MACATEX.pdf")
        self.assertIsNone(comparacion["ultimo_pdf"])
        campos = {c["campo"]: c for c in comparacion["campos_oc"]}
        self.assertEqual(campos["objeto"]["actual"], "")
        self.assertEqual(campos["objeto"]["pdf"], "adquisición de Telas e Hilos")
        self.assertTrue(campos["objeto"]["distinto"])
        self.assertEqual(campos["gde_pdf_oc"]["pdf"], "IF-2026-82026919-INSSJP-GESP#INSSJP")
        self.assertFalse(campos["ca"]["distinto"])
        self.assertEqual(len(comparacion["renglones"]), 6)
        r1 = comparacion["renglones"][0]
        self.assertTrue(r1["existe"])
        # El z_compras2 trae bien cantidad y precio; del PDF solo falta la unidad.
        self.assertEqual([d["campo"] for d in r1["diferencias"]], ["unidad"])
        self.assertEqual(comparacion["avisos"], [])

        oc = comparacion["oc"]
        resp = self.servidor.post("/api/oc/%s/pdf/aplicar" % oc["numero"], {
            "version": oc["version"], "archivo": comparacion["archivo"], "leido": comparacion["leido"],
            "oc": {"objeto": "adquisición de telas e hilos", "objeto_articulo": "a la",
                   "gde_pdf_oc": campos["gde_pdf_oc"]["pdf"]},
            "renglones": [{"pos": r["pos"], "version": r["version"], "cambios": {"unidad": r["propuesta"]["unidad"]}}
                          for r in comparacion["renglones"]],
        })
        self.assertEqual(resp.estado, 200, resp.texto())
        ficha = resp.json()["datos"]
        self.assertEqual(ficha["oc"]["objeto"], "adquisición de telas e hilos")
        self.assertIn("objeto", ficha["oc"]["campos_manuales"])
        self.assertEqual({r["unidad"] for r in ficha["renglones"]}, {"U"})
        self.assertEqual(ficha["pdf_oc"]["archivo"], "EX-2026-99349179_MACATEX.pdf")

        # Reimportar el z_compras2 no pisa lo que vino del PDF.
        datos_prueba.importar_hbi_2026(self.con)
        ficha = negocio.ficha_oc(self.con, datos_prueba.OC_MACATEX)
        self.assertEqual(ficha["oc"]["objeto"], "adquisición de telas e hilos")
        self.assertEqual(ficha["oc"]["gde_pdf_oc"], "IF-2026-82026919-INSSJP-GESP#INSSJP")
        self.assertEqual({r["unidad"] for r in ficha["renglones"]}, {"U"})

    def test_efia_subrenglones_corrigen_desglose_y_agregan_renglon(self):
        ficha = datos_prueba.cargar_efia(self.con)
        comparacion = self._leer("4500555861", "EX-2026-89654857_EFIA")
        r1, r2 = comparacion["renglones"]
        self.assertTrue(r1["existe"])
        self.assertFalse(r2["existe"])
        cambios_r1 = {d["campo"]: (d["actual"], d["pdf"]) for d in r1["diferencias"]}
        self.assertEqual(cambios_r1["desglose_cantidad"], ("9", "3"))
        self.assertEqual(cambios_r1["importe_centavos"], (1102491000, 367497000))
        self.assertEqual(r2["propuesta"]["desglose_cantidad"], "9")

        resp = self.servidor.post("/api/oc/4500555861/pdf/aplicar", {
            "version": comparacion["oc"]["version"], "archivo": "oc.pdf",
            "renglones": [
                {"pos": 1, "version": r1["version"], "cambios": {d["campo"]: d["pdf"] for d in r1["diferencias"]}},
                {"pos": 2, "version": None, "cambios": r2["propuesta"]},
            ],
        })
        self.assertEqual(resp.estado, 200, resp.texto())
        renglones = resp.json()["datos"]["renglones"]
        self.assertEqual([(r["pos"], r["desglose_cantidad"], r["desglose_unidad"], r["desglose_precio_centavos"])
                          for r in renglones], [(1, "3", "MES", 122499000), (2, "9", "MES", 122499000)])
        self.assertEqual(renglones[1]["descripcion"], "SERV INTEGRAL CONTROL DE PLAGAS - 2026")
        self.assertEqual(renglones[1]["sap_por_entregar"], "9")
        self.assertEqual(ficha["oc"]["version"], resp.json()["datos"]["oc"]["version"])

    def test_pdf_de_otra_oc(self):
        datos_prueba.preparar_biofab(self.con)
        resp = self.servidor.subir("/api/oc/%s/pdf" % datos_prueba.OC_BIOFAB, self._pdf("EX-2026-99349179_MACATEX"))
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "El PDF es de la OC 4500594643, no de la 4500587121.")

    def test_texto_pegado_y_errores(self):
        datos_prueba.preparar_biofab(self.con)
        ruta = Path(self.carpeta.name) / "vacio.txt"
        ruta.write_bytes(b"")
        resp = self.servidor.subir("/api/oc/%s/pdf" % datos_prueba.OC_BIOFAB, ruta,
                                   {"texto": texto_oc("EX-2026-94963848_BIOFAB")})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(len(resp.json()["datos"]["renglones"]), 4)

        ruta.write_bytes(b"no soy un pdf")
        resp = self.servidor.subir("/api/oc/%s/pdf" % datos_prueba.OC_BIOFAB, ruta)
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "El archivo no es un PDF.")

    def test_conflicto_de_version(self):
        datos_prueba.preparar_macatex(self.con)
        comparacion = self._leer(datos_prueba.OC_MACATEX, "EX-2026-99349179_MACATEX")
        resp = self.servidor.post("/api/oc/%s/pdf/aplicar" % datos_prueba.OC_MACATEX, {
            "version": comparacion["oc"]["version"] - 1, "oc": {"objeto": "x"}})
        self.assertEqual(resp.estado, 409)

    def test_reimportar_respeta_desglose_del_pdf_y_recalcula_por_entregar(self):
        datos_prueba.importar_hbi_2026(self.con)
        antes = negocio.ficha_oc(self.con, "4500600299")["renglones"][0]
        self.assertEqual((antes["desglose_cantidad"], antes["sap_entregado"], antes["sap_por_entregar"]), ("3", "0", "3"))
        oc = db.leer_fila(self.con, "oc", {"numero": "4500600299"})
        negocio.aplicar_oc_pdf(self.con, "4500600299", {"version": oc["version"], "renglones": [
            {"pos": 1, "version": antes["version"], "cambios": {"desglose_cantidad": "6", "desglose_unidad": "MES",
                                                                "desglose_precio_centavos": 61249500}}]})
        renglon = negocio.ficha_oc(self.con, "4500600299")["renglones"][0]
        self.assertEqual((renglon["desglose_cantidad"], renglon["sap_por_entregar"]), ("6", "6"))
        datos_prueba.importar_hbi_2026(self.con)
        renglon = negocio.ficha_oc(self.con, "4500600299")["renglones"][0]
        self.assertEqual((renglon["desglose_cantidad"], renglon["sap_por_entregar"], renglon["exceso_sap"]), ("6", "6", 0))


class PruebaNuevaOcDesdePdf(ayudas.CasoConServidor):
    """«Nueva OC»: se lee el PDF, se confirman los datos y se crea la OC con lo confirmado."""

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def _subir(self, carpeta):
        ruta = Path(self.carpeta.name) / "oc.pdf"
        ruta.write_bytes(pdf_prueba.pdf_desde_texto(texto_oc(carpeta), fuente="cid", envolver=True))
        return self.servidor.subir("/api/oc/pdf", ruta)

    def test_lee_crea_y_la_importacion_no_pisa(self):
        resp = self._subir("EX-2026-99349179_MACATEX")
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()["datos"]
        leido = datos["leido"]
        self.assertFalse(datos["existe"])
        self.assertEqual((leido["numero"], leido["efector"], leido["tipo"], leido["centralizada"]), ("4500594643", "HBI", "BIEN", 0))
        renglones = [{"pos": r["pos"], "codigo": r["codigo"], "descripcion": r["descripcion"], "cantidad": r["cantidad"],
                      "unidad": r["unidad"], "precio_centavos": r["precio_centavos"], "importe_centavos": r["importe_centavos"]}
                     for r in leido["renglones"]]
        oc = {"numero": leido["numero"], "efector": "HBI", "sap": leido["sap"], "razon_social": leido["razon_social"],
              "fecha_oc": leido["fecha_oc"], "tipo": leido["tipo"], "ca": leido["ca"],
              "expediente_contratacion": leido["expediente_contratacion"], "gde_pdf_oc": leido["gde_pdf_oc"],
              "objeto": "adquisición de telas e hilos", "objeto_articulo": leido["objeto_articulo"], "centralizada": 0,
              "renglones": renglones}
        creada = self.servidor.post("/api/oc/desde-pdf", {"oc": oc, "archivo": "oc.pdf", "leido": {"numero": leido["numero"]}})
        self.assertEqual(creada.estado, 200, creada.texto())
        ficha = creada.json()["datos"]
        self.assertEqual((ficha["oc"]["origen"], ficha["oc"]["objeto_articulo"]), ("MANUAL", "a la"))
        self.assertEqual(ficha["pdf_oc"]["archivo"], "oc.pdf")
        self.assertEqual(len(ficha["renglones"]), 6)
        self.assertIn("unidad", ficha["renglones"][0]["campos_manuales"])
        # El z_compras2 trae la misma OC: no pisa lo confirmado desde el PDF.
        datos_prueba.importar_hbi_2026(self.con)
        ficha = negocio.ficha_oc(self.con, "4500594643")
        self.assertEqual({r["unidad"] for r in ficha["renglones"]}, {"U"})
        self.assertEqual(ficha["oc"]["objeto"], "adquisición de telas e hilos")
        # Leerlo de nuevo avisa que ya existe.
        self.assertTrue(self._subir("EX-2026-99349179_MACATEX").json()["datos"]["existe"])

    def test_servicio_y_efector(self):
        leido = self._subir("EX-2026-89654857_EFIA").json()["datos"]["leido"]
        self.assertEqual((leido["tipo"], leido["efector"], leido["dia_inicio_periodo"]), ("SERVICIO", "HBI", 1))

    def test_texto_que_no_es_oc(self):
        ruta = Path(self.carpeta.name) / "x.pdf"
        ruta.write_bytes(pdf_prueba.pdf_desde_texto("FACTURA B 0003-00001234"))
        resp = self.servidor.subir("/api/oc/pdf", ruta)
        self.assertEqual(resp.estado, 422)
