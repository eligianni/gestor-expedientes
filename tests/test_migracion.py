"""Migración del seguimiento en Excel (NUMERACIÓN + solapa HBI 20252026) con planillas inventadas de la misma forma."""
import uuid

from gestor import db, migracion, negocio, xlsx
from tests import ayudas, datos_prueba
from tests.xlsx_prueba import xlsx_con_hojas


AGO_2026, SEP_2026, OCT_2026, OCT_2025 = 46235, 46266, 46296, 45931  # seriales de Excel (1° de cada mes)
EFIA, MACATEX, BIOFAB = "4500555861", datos_prueba.OC_MACATEX, datos_prueba.OC_BIOFAB

ENC_NUM = ["", "N° REMITO", "CARGA EN SII", "MOTIVO", "PERIODO", "OC", "SAP", "PROVEEDOR", "FECHA DOC", "N° FACTURA",
           "FECHA CONTAB.", "IMPORTE", "EE", "FACTURA", "COMPROBANTE DE CARGA EN SII", "ORDEN DE COMPRA", "REMITO", "CV",
           "VALE/HOJA DE ENTRADA", "AUTORIZACIÓN DE PAGO", "CONST. CONTABILIZACIÓN (IFGRA)", "Observaciones",
           "FACTURA", "REMITO"]


def fila_num(n, remito, oc, sap, proveedor, periodo, factura, importe, contab=None, gde=True, obs=""):
    gdes = (["EX-2026-60729006-   -INSSJP-GESP#INSSJP", "DOCFI-2026-60805831-INSSJP-GESP#INSSJP",
             "IF-2026-60806644-INSSJP-GESP#INSSJP", "IF-2026-30956871-INSSJP-GESP#INSSJP",
             "RM-2026-60807761-INSSJP-GESP#INSSJP", "IF-2026-62191734-INSSJP-GESP#INSSJP",
             "IF-2026-60808563-INSSJP-GESP#INSSJP", "IF-2026-62192471-INSSJP-GESP#INSSJP",
             "IF-2026-73681759-INSSJP-GESP#INSSJP" if contab else None] if gde else [None] * 9)
    return [n, remito, "RKS1995084", "SERVICIO", periodo, oc, sap, proveedor, periodo, factura, contab, importe] + gdes + [
        obs, "08-AA - FC %s" % factura, "08-AA - RTO %s" % remito]


def numeracion():
    return xlsx_con_hojas([
        ("ENTREGA 1", [["", "ENTREGA 1"], ENC_NUM,
                       fila_num(1, "00001-00029461", EFIA, 77170, "GRUPO EFIA S.R.L.", AGO_2026, "0003B00031812", 1224990,
                                contab=46300),
                       fila_num(2, "0002-00000160 y 0002-00000161", MACATEX, 118896, "MACATEX S.A", SEP_2026,
                                "0002B00000160", 8120000, gde=False),
                       [None, None, None, None, None, None, None, None, None, None, None, 9344990]]),
        ("ENTREGA (2)", [["", "copia"], ENC_NUM,
                         fila_num(1, "00001-00099999", EFIA, 77170, "GRUPO EFIA S.R.L.", AGO_2026, "0003B00099999", 1)]),
        ("PENDIENTES !!", [["", "pendientes"], ENC_NUM,
                           fila_num(1, "0001-00003354", BIOFAB, 116467, "BIO FAB S.R.L", AGO_2026, "00002B00003908",
                                    21095000, gde=False, obs="Falta la nota de crédito")]),
        ("PAGO EVENTUAL TECNEL", [["", "eventual"], ["N° REMITO", "CARGA EN SII", "PERIODO", "SAP", "PROVEEDOR",
                                                     "N° FACTURA", "FECHA CONTAB.", "IMPORTE", "EE"],
                                  ["-", "ABC1234567", AGO_2026, None, "GRUPO EFIA S.R.L.", "0003B00000196", 46300, 500000,
                                   "EX-2026-11111111-   -INSSJP-GESP#INSSJP"]]),
    ])


def remitos():
    enc = ["OC", "DURACIÓN", "DESCRIPCIÓN", "SAP", "PROVEEDOR", "REMITO", "PERIODO", "N° FACTURA", "CARGA EN SII",
           "INGRESO AL SII", "IMPORTE", "N° ENTREGA", "Enviado a gerencia", "Observaciones"]
    return xlsx_con_hojas([
        ("TABLERO CONTROL", [["nada que ver"]]),
        ("HBI 20252026", [
            ["", "", "datos de las ORDENES DE COMPRA.", "", "", "datos del REMITO"], enc,
            [4500555861.0, "12 meses", "SERV", 77170.0, "GRUPO EFIA S.R.L.", "00001-00029461", AGO_2026, "0003B00031812",
             "RKS1995084", AGO_2026, 1224990.0, 1.0, "SI", ""],
            # La factura tiene un error de tipeo: se cruza por el número de remito de la NUMERACIÓN.
            [4500594643.0, "BIEN", "TELA", 118896.0, "MACATEX S.A", "0002-00000160", SEP_2026, "0002BB0000160", "X",
             SEP_2026, 8120000.0, 1.0, "SI", ""],
            [4500587121.0, "BIEN", "DET", 116467.0, "BIO FAB S.R.L", "0001-00009999", OCT_2026, "PENDIENTE", "-", None,
             None, None, None, "esperando factura"],
            [4500587121.0, "BIEN", "DET", 116467.0, "BIO FAB S.R.L", "0001-00009998", OCT_2026, "PENDIENTE", "-", None,
             None, None, None, ""],
            [4500594643.0, "BIEN", "TELA", 118896.0, "MACATEX S.A", "0002-00000001", OCT_2025, "0002B00000001", "Y",
             OCT_2025, 100.0, 11.0, "SI", ""],
            ["SIN OC", "", "", 59639.0, "SATELITE S.R.L.", "00001-00056730", OCT_2026, "PENDIENTE", "-", None, None, None,
             None, "SIN OC"],
        ]),
    ])


class PruebaMigracion(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        db.inicializar(self.entorno.ruta_base, ayudas.config_del_proyecto()["parametros_iniciales"])
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        datos_prueba.cargar_efia(self.con)
        datos_prueba.preparar_biofab(self.con)
        self.hojas = (xlsx.leer_hojas(numeracion()), xlsx.leer_hojas(remitos()))

    def _por_factura(self, informe):
        return {p["factura"] or ("%s %s" % (p["oc"], p["periodo"])): p for p in informe["expedientes"]}

    def test_vista_previa(self):
        informe = migracion.planificar(self.con, *self.hojas)
        self.assertEqual(informe["hojas_ignoradas"], ["ENTREGA (2)"])
        exp = self._por_factura(informe)
        efia = exp["0003B00031812"]
        self.assertEqual((efia["estado"], efia["entrega"], efia["tipo"], efia["periodo"]), ("CERRADO", 1, "COMUN", "2026-08"))
        self.assertEqual(efia["remitos"], ["00001-00029461"])
        # 1 renglón con desglose 9 MES × $ 1.224.990,00: la factura de $ 1.224.990,00 es 1 mes.
        self.assertEqual(efia["items"], [{"pos": 1, "cantidad": "1", "codigo": ""}])
        self.assertEqual(efia["gde"]["expediente"], "EX-2026-60729006- -INSSJP-GESP#INSSJP")
        self.assertEqual(efia["gde"]["contabilizacion"], "IF-2026-73681759-INSSJP-GESP#INSSJP")

        macatex = exp["0002B00000160"]
        self.assertEqual(macatex["estado"], "ENVIADO")
        self.assertEqual(macatex["remitos"], ["0002-00000160"])
        self.assertTrue(any("se cruzó por número" in a for a in macatex["avisos"]))
        self.assertEqual(macatex["items"], [])

        self.assertEqual(exp["0002B00003908"]["estado"], "PENDIENTE")
        self.assertEqual(exp["0002B00003908"]["motivo_pendiente"], "Falta la nota de crédito")
        eventual = exp["0003B00000196"]
        self.assertEqual((eventual["tipo"], eventual["estado"], eventual["sap"]), ("EVENTUAL", "FINALIZADO", "77170"))

        borrador = exp["%s 2026-10" % BIOFAB]
        self.assertEqual((borrador["estado"], borrador["remitos"]), ("BORRADOR", ["0001-00009999", "0001-00009998"]))

        motivos = [x["motivo"] for x in informe["no_importados"]]
        self.assertTrue(any("2025-10" in m for m in motivos), motivos)
        self.assertTrue(any("SIN OC" in m for m in motivos), motivos)
        self.assertEqual(informe["resumen"]["por_estado"],
                         {"CERRADO": 1, "ENVIADO": 1, "PENDIENTE": 1, "FINALIZADO": 1, "BORRADOR": 1})
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM expediente").fetchone()[0], 0)

    def test_migrar_y_repetir_no_duplica(self):
        informe = migracion.migrar(self.con, *self.hojas, archivos="numeracion.xlsx + remitos.xlsx")
        self.assertEqual(informe["resumen"]["creados"], 5)
        entrega = db.leer_fila(self.con, "entrega", {"efector": "HBI", "numero": 1})
        self.assertEqual(entrega["estado"], "ENVIADA")
        fila = self.con.execute("SELECT id FROM expediente WHERE factura = '0003B00031812'").fetchone()
        exp = negocio.obtener_expediente(self.con, fila["id"])
        self.assertEqual((exp["estado"], exp["entrega_id"], exp["periodo_manual"]), ("CERRADO", entrega["id"], 1))
        self.assertEqual(exp["datos"]["factura"]["centavos"], 122499000)
        self.assertEqual(exp["datos"]["sii"]["cod_tramite"], "RKS1995084")
        self.assertEqual(exp["datos"]["gde"]["remitos"], {"00001-00029461": "RM-2026-60807761-INSSJP-GESP#INSSJP"})
        self.assertEqual(exp["datos"]["historial"][0]["accion"], "MIGRACION")
        # El consumo de la OC toma la cantidad deducida.
        consumo = negocio.consumo_por_renglon(self.con, EFIA)[0]
        self.assertEqual(consumo["validado"], "1")
        # Siguiente entrega nueva del gestor: continúa la numeración.
        self.assertEqual(negocio.crear_entrega(self.con, "HBI")["numero"], 2)

        otra = migracion.migrar(self.con, *self.hojas, archivos="otra vez")
        self.assertEqual((otra["resumen"]["creados"], otra["resumen"]["ya_existentes"]), (0, 5))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM expediente").fetchone()[0], 5)

    def test_archivo_sin_la_solapa(self):
        with self.assertRaises(migracion.ErrorMigracion) as error:
            migracion.planificar(self.con, self.hojas[0], xlsx.leer_hojas(xlsx_con_hojas([("Hoja1", [["a"]])])))
        self.assertIn("HBI 20252026", str(error.exception))


class PruebaMigracionApi(ayudas.CasoConServidor):

    def _subir(self, ruta, archivos):
        limite = "----gestor" + uuid.uuid4().hex
        partes = []
        for campo, (nombre, contenido) in archivos.items():
            partes.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: "
                           "application/octet-stream\r\n\r\n" % (limite, campo, nombre)).encode("utf-8") + contenido + b"\r\n")
        partes.append(("--%s--\r\n" % limite).encode("utf-8"))
        return self.servidor.pedir("POST", ruta, b"".join(partes), {"Content-Type": "multipart/form-data; boundary=%s" % limite})

    def test_vista_previa_y_confirmar(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            datos_prueba.cargar_efia(con)
            datos_prueba.preparar_biofab(con)
        finally:
            con.close()
        archivos = {"numeracion": ("NUMERACION.xlsx", numeracion()), "remitos": ("SEGUIMIENTO.xlsx", remitos())}
        previa = self._subir("/api/importar/seguimiento/vista-previa", archivos)
        self.assertEqual(previa.estado, 200, previa.texto())
        self.assertEqual(previa.json()["datos"]["resumen"]["expedientes"], 5)
        hecha = self._subir("/api/importar/seguimiento/confirmar", archivos)
        self.assertEqual(hecha.estado, 200, hecha.texto())
        self.assertEqual(hecha.json()["datos"]["resumen"]["creados"], 5)
        historial = self.servidor.get("/api/importaciones").json()["datos"]
        self.assertEqual(historial[0]["archivo"], "NUMERACION.xlsx + SEGUIMIENTO.xlsx")

    def test_falta_un_archivo(self):
        resp = self._subir("/api/importar/seguimiento/vista-previa", {"numeracion": ("N.xlsx", numeracion())})
        self.assertEqual(resp.estado, 400)
        self.assertIn("seguimiento de remitos", resp.json()["error"]["mensaje"])
