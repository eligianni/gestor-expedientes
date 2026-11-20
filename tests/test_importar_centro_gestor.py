"""Importación del z_compras2 por centro gestor (4500 HBI, 4900 CASPH) y día de inicio del período."""
import copy
import io

from gestor import db, importar, negocio, xlsx
from tests import ayudas
from tests.xlsx_prueba import xlsx_con_hojas

ASCENSORES = "4500563620"     # centro 1900, org 1900, vigencia desde 09/09/2025
CENTRALIZADA = "4500565075"   # centro 1000, org 0110: con el filtro por centro se perdía (es de «otro centro»)
DE_OTRO_GESTOR = "4500563687"
HABITAT = "4500570841"        # centro 1900, org 0100: residuos patogénicos, compra de Nivel Central
SERVICIO_MES = "4500600299"   # EFIA, vigencia desde 01/10/2026


def reporte_con_centro_gestor():
    """El z_compras2 de prueba con la columna Centro Gestor, como sale por centro gestor desde SAP."""
    filas = xlsx.leer_filas(ayudas.XLSX_HBI_2026)
    encabezados = list(filas[0]) + ["Centro Gestor"]
    clave = [importar.util.clave_encabezado(x or "") for x in filas[0]]
    i_oc, i_centro, i_org = clave.index("n o c"), clave.index("centro"), clave.index("org compras")
    salida = [encabezados]
    for fila in filas[1:]:
        fila = list(fila) + [None] * (len(filas[0]) - len(fila))
        gestor = "9999" if fila[i_oc] == DE_OTRO_GESTOR else "4500" if fila[i_centro] in ("1900", "1000") else "4700"
        salida.append(fila + [gestor])
    # Una OC de Hurlingham: centro 0010, organización de compras propia del CASPH.
    nueva = list(salida[1])
    nueva[i_oc], nueva[i_centro], nueva[i_org], nueva[-1] = "4500999001", "0010", "1300", "4900"
    salida.append(nueva)
    return xlsx_con_hojas([("Sheet1", salida)])


class PruebaImportarCentroGestor(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.parametros = copy.deepcopy(self.entorno.config["parametros_iniciales"])
        db.inicializar(self.entorno.ruta_base, self.parametros)
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        self.reporte = reporte_con_centro_gestor()

    def _importar(self, efector, origen=None):
        return importar.importar(self.con, io.BytesIO(origen or self.reporte), efector, self.parametros, archivo="z.xlsx")

    def _oc(self, numero):
        return db.leer_fila(self.con, "oc", {"numero": numero})

    def test_hbi_entra_todo_lo_de_su_centro_gestor(self):
        self._importar("HBI")
        self.assertIsNotNone(self._oc(ASCENSORES))
        otro_centro = self._oc(CENTRALIZADA)
        # Centro 1000 con otra organización de compras: entra (es del centro gestor) pero no es centralizada.
        self.assertEqual((otro_centro["efector"], otro_centro["centralizada"]), ("HBI", 0))
        self.assertEqual(self._oc(ASCENSORES)["centralizada"], 0)
        # Centro 1900 comprada por Nivel Central (org 0100): centralizada («UOC: Nivel Central BS» en su PDF).
        self.assertEqual(self._oc(HABITAT)["centralizada"], 1)
        self.assertIsNone(self._oc(DE_OTRO_GESTOR))
        self.assertIsNone(self._oc("4500999001"))

    def test_casph_por_centro_gestor_aunque_no_tenga_centros(self):
        self.assertEqual(self.parametros["efectores"]["CASPH"]["centros"], [])
        informe = self._importar("CASPH")
        self.assertEqual(informe["oc_distintas"], 1)
        oc = self._oc("4500999001")
        # Centro 0010 = Nivel Central: centralizada aunque la organización de compras sea la propia.
        self.assertEqual((oc["efector"], oc["centralizada"]), ("CASPH", 1))

    def test_base_vieja_sin_el_parametro_usa_los_centros_gestores_de_siempre(self):
        for datos in self.parametros["efectores"].values():
            datos.pop("centros_gestores", None)
            datos.pop("org_compras", None)
        self._importar("CASPH")
        self.assertEqual(self._oc("4500999001")["centralizada"], 1)
        self.assertIsNone(importar.falta_configuracion("CASPH", self.parametros, ["N° O/C", "Centro Gestor"]))

    def test_reporte_sin_centro_gestor_sigue_filtrando_por_centro(self):
        self.assertEqual(importar.falta_configuracion("CASPH", self.parametros, ["N° O/C", "Centro"]),
                         "Configurá los centros SAP de CASPH antes de importar.")
        self.parametros["efectores"]["HBI"]["centros_gestores"] = []
        self.assertEqual(importar.falta_configuracion("HBI", self.parametros, ["Centro Gestor"]),
                         "Configurá el centro gestor de HBI antes de importar.")
        importar.importar(self.con, ayudas.XLSX_HBI_2026, "HBI", self.parametros, archivo="z.xlsx")
        self.assertIsNotNone(self._oc(ASCENSORES))
        self.assertIsNone(self._oc(CENTRALIZADA))  # centro 1000: los reportes viejos solo traen el centro 1900

    def test_dia_de_inicio_del_periodo_sale_de_la_vigencia(self):
        self._importar("HBI")
        self.assertEqual(self._oc(ASCENSORES)["dia_inicio_periodo"], 9)
        self.assertEqual(self._oc(SERVICIO_MES)["dia_inicio_periodo"], 1)
        self.assertEqual(importar.dia_inicio_periodo("2026-03-30"), 1)
        self.assertEqual(importar.dia_inicio_periodo(None), 1)

    def test_dia_editado_a_mano_no_se_pisa(self):
        self._importar("HBI")
        negocio.actualizar_oc(self.con, ASCENSORES, self._oc(ASCENSORES)["version"], {"dia_inicio_periodo": 1})
        self._importar("HBI")
        self.assertEqual(self._oc(ASCENSORES)["dia_inicio_periodo"], 1)


class PruebaRenglonesDeOtroCentro(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.parametros = copy.deepcopy(self.entorno.config["parametros_iniciales"])
        db.inicializar(self.entorno.ruta_base, self.parametros)
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)
        reporte = reporte_con_centro_gestor()
        for efector in ("HBI", "CASPH"):
            importar.importar(self.con, io.BytesIO(reporte), efector, self.parametros, archivo="z.xlsx")

    def test_marca_en_la_ficha_la_lista_y_tablas(self):
        from gestor import tablas
        centralizada = negocio.ficha_oc(self.con, CENTRALIZADA)["renglones"][0]
        self.assertEqual((centralizada["centro"], centralizada["otro_centro"]), ("1000", 1))
        propio = negocio.ficha_oc(self.con, ASCENSORES)["renglones"][0]
        self.assertEqual((propio["centro"], propio["otro_centro"]), ("1900", 0))
        # CASPH: el propio es 1300 aunque no tenga centros cargados; el renglón de centro 0010 queda marcado.
        hur = negocio.ficha_oc(self.con, "4500999001")["renglones"][0]
        self.assertEqual((hur["centro"], hur["central"], hur["otro_centro"]), ("0010", 1, 0))
        lista = {o["numero"]: o for o in negocio.listar_oc(self.con)}
        self.assertEqual(lista[CENTRALIZADA]["renglones_otro_centro"], lista[CENTRALIZADA]["renglones"])
        self.assertEqual(lista[ASCENSORES]["renglones_otro_centro"], 0)
        filas = {(f["oc"], f["pos"]): f for f in tablas.tabla(self.con, "renglones")["filas"]}
        self.assertEqual((filas[(CENTRALIZADA, 1)]["centro"], filas[(CENTRALIZADA, 1)]["otro_centro"]), ("1000", 1))

    def test_renglon_cargado_a_mano_no_se_marca(self):
        self.assertEqual(negocio.marcar_otro_centro([{"crudo": {}}], {"1900"}),
                         [{"crudo": {}, "centro": "", "central": 0, "otro_centro": 0}])
