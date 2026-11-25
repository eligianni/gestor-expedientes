"""Carga del SEGUIMIENTO_CENTRALIZADAS (Excel) y reglas del tablero: meses calendario y 10 días de gracia."""
from gestor import db, migracion, negocio, util, xlsx
from tests import ayudas, xlsx_prueba

ENCABEZADOS = ["OC", "DESTINO", "cod_oc", "SAP", "RAZON SOCIAL", "DESCRIPCION DEL SERVICIO", "PERIODO", "RTO N°",
               "CV (IFGFC)", "NOTA", "FECHA", "OBSERVACIONES", "DESDE", "HASTA"]


def _excel():
    notas = [
        ["NOTAS ENVIADAS A CENTRAL"],
        ENCABEZADOS,
        # 46143 = 2026-05-01 · 46174 = 2026-06-01 · 46175 = 2026-06-02
        ["4.500577336E9", "HBI", "x", "96398", "LIDERES", "SEGURIDAD", "46143.0", "0001-00000010", "IF-2026-11111111-INSSJP-GESP#INSSJP",
         "NO-2026-22222222-INSSJP-GESP#INSSJP", "46175.0", "-", "-", "-"],
        ["4.500577336E9", "HUR", "x", "96398", "LIDERES", "SEGURIDAD", "46143.0", "-", "IF-2026-33333333-INSSJP-GESP%INSSJP",
         "-", "-", "-", "-", "-"],
        ["4.500000999E9", "HBI", "x", "1", "SIN OC", "X", "46143.0", "-", "-", "NO-2026-44444444-INSSJP-GESP#INSSJP", "-", "-", "-", "-"],
    ]
    unicas = [
        ["OC", "SAP", "RAZON SOCIAL", "N° REMITO", "PERIODO", "CONTROL", "CV (IFGFC)", "NOTA", "FECHA ENVIO"],
        ["4.500577336E9", "96398", "LIDERES", "0004-0031573", "46174.0", "OK", "IF-2026-55555555-INSSJP-GESP#INSSJP",
         "NO-2026-66666666-INSSJP-GESP#INSSJP", "46175.0"],
    ]
    return xlsx.leer_hojas(xlsx_prueba.xlsx_con_hojas([("NOTAS ENVIADAS", notas), ("ENTREGAS UNICAS", unicas)]))


class PruebaMigracionCentralizadas(ayudas.CasoConServidor):

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        negocio.crear_oc_manual(self.con, {
            "numero": "4500577336", "efector": "HBI", "sap": "96398", "razon_social": "LIDERES CONSULTORES",
            "vig_desde": "2026-02-14", "vig_hasta": "2027-02-13", "objeto": "servicio de seguridad", "objeto_articulo": "al",
            "tipo": "SERVICIO", "renglones": [{"pos": 1, "descripcion": "VIGILANCIA", "cantidad": "1", "unidad": "UN",
                                               "precio_centavos": 1}]})

    def test_planifica_carga_y_no_repite(self):
        plan = migracion.planificar_centralizadas(self.con, _excel())
        self.assertEqual(plan["resumen"]["a_crear"], 3)
        self.assertEqual([x["oc"] for x in plan["sin_oc"]], ["4500000999"])
        porclave = {(p["efector"], p["periodo"]): p for p in plan["validaciones"]}
        self.assertEqual(porclave[("HBI", "2026-05")]["estado"], "ENVIADO")
        self.assertEqual(porclave[("CASPH", "2026-05")]["estado"], "FIRMADO")
        self.assertEqual(porclave[("CASPH", "2026-05")]["numero_cv"], "IF-2026-33333333-INSSJP-GESP#INSSJP")  # «%» corregido
        self.assertEqual(porclave[("HBI", "2026-06")]["hoja"], "ENTREGAS ÚNICAS")
        informe = migracion.migrar_centralizadas(self.con, _excel(), "seg.xlsx")
        self.assertEqual(informe["resumen"]["creados"], 3)
        self.assertEqual(db.leer_fila(self.con, "oc", {"numero": "4500577336"})["centralizada"], 1)
        mayo = negocio.obtener_expediente(self.con, _id(self.con, "HBI", "2026-05"))
        self.assertEqual(mayo["datos"]["centralizada"]["fecha_envio"], "2026-06-02")
        self.assertEqual([r["numero"] for r in mayo["datos"]["remitos"]], ["0001-00000010"])
        self.assertEqual(migracion.planificar_centralizadas(self.con, _excel())["resumen"]["a_crear"], 0)

    def test_por_api(self):
        contenido = xlsx_prueba.xlsx_con_hojas([("NOTAS ENVIADAS", [ENCABEZADOS])])
        resp = self.servidor.pedir("POST", "/api/importar/centralizadas/vista-previa", *_multipart(contenido))
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["resumen"]["a_crear"], 0)

    def test_tablero_meses_calendario_y_gracia(self):
        migracion.migrar_centralizadas(self.con, _excel(), "seg.xlsx")
        self.assertEqual(negocio.obtener_expediente(self.con, _id(self.con, "HBI", "2026-05"))["periodo_desde"], "2026-05-01")
        # Febrero arranca el 14 (vigencia): mes calendario recortado.
        self.assertEqual(negocio.limites_centralizada(db.leer_fila(self.con, "oc", {"numero": "4500577336"}), "2026-02"),
                         (util.fecha_desde_texto("2026-02-14"), util.fecha_desde_texto("2026-02-28")))
        tablero = negocio.tablero_centralizadas(self.con, 2026, "HBI", hoy=util.fecha_desde_texto("2026-12-10"))
        celdas = {c["periodo"]: c["estado"] for c in tablero["filas"][0]["celdas"]}
        self.assertEqual((celdas["2026-01"], celdas["2026-05"], celdas["2026-10"], celdas["2026-11"], celdas["2026-12"]),
                         ("fuera", "validado", "atrasado", "pendiente", "pendiente"))
        tablero = negocio.tablero_centralizadas(self.con, 2026, "HBI", hoy=util.fecha_desde_texto("2026-12-11"))
        self.assertEqual(tablero["filas"][0]["celdas"][10]["estado"], "atrasado")  # noviembre, pasado el 10/12


def _id(con, efector, periodo):
    return con.execute("SELECT id FROM expediente WHERE tipo = 'CENTRALIZADA' AND efector = ? AND periodo = ?",
                       (efector, periodo)).fetchone()["id"]


def _multipart(contenido):
    limite = "limiteprueba"
    cuerpo = ("--%s\r\nContent-Disposition: form-data; name=\"archivo\"; filename=\"seg.xlsx\"\r\n"
              "Content-Type: application/octet-stream\r\n\r\n" % limite).encode() + contenido + ("\r\n--%s--\r\n" % limite).encode()
    return cuerpo, {"Content-Type": "multipart/form-data; boundary=%s" % limite}
