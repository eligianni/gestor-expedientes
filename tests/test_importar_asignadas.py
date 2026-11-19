"""Importación del z_compras2: OC asignadas a un efector aunque tengan otro centro, y día de inicio del período."""
import copy

from gestor import db, importar
from tests import ayudas

ASCENSORES = "4500563620"   # centro 1900, vigencia desde 09/09/2025
HONORARIOS = "4500567012"   # centro 0010 (de otro efector)
SERVICIO_MES = "4500600299"  # EFIA, vigencia desde 01/10/2026


class PruebaImportarAsignadas(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.parametros = copy.deepcopy(self.entorno.config["parametros_iniciales"])
        self.parametros["efectores"]["CASPH"]["centros"] = ["1300"]
        db.inicializar(self.entorno.ruta_base, self.parametros)
        self.con = db.conectar(self.entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _importar(self, efector):
        importar.importar(self.con, ayudas.XLSX_HBI_2026, efector, self.parametros, archivo="z.xlsx")

    def _oc(self, numero):
        return db.leer_fila(self.con, "oc", {"numero": numero})

    def test_oc_asignada_al_casph_no_entra_al_hbi_y_entra_al_casph(self):
        self.parametros["efectores"]["CASPH"]["oc_asignadas"] = [ASCENSORES, HONORARIOS]
        self._importar("HBI")
        self.assertIsNone(self._oc(ASCENSORES))
        self.assertIsNone(self._oc(HONORARIOS))
        self._importar("CASPH")
        self.assertEqual(self._oc(ASCENSORES)["efector"], "CASPH")
        self.assertEqual(self._oc(HONORARIOS)["efector"], "CASPH")
        # Sin asignar, el centro 1300 no trae nada del reporte del HBI.
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM oc WHERE efector = 'CASPH'").fetchone()[0], 2)

    def test_oc_asignada_al_hbi_con_otro_centro(self):
        self.parametros["efectores"]["HBI"]["oc_asignadas"] = [HONORARIOS]
        self._importar("HBI")
        self.assertEqual(self._oc(HONORARIOS)["efector"], "HBI")
        self.assertEqual(importar.oc_asignadas(self.parametros, "CASPH"), (set(), {HONORARIOS}))

    def test_dia_de_inicio_del_periodo_sale_de_la_vigencia(self):
        self._importar("HBI")
        self.assertEqual(self._oc(ASCENSORES)["dia_inicio_periodo"], 9)
        self.assertEqual(self._oc(SERVICIO_MES)["dia_inicio_periodo"], 1)
        self.assertEqual(importar.dia_inicio_periodo("2026-03-30"), 1)
        self.assertEqual(importar.dia_inicio_periodo(None), 1)

    def test_dia_editado_a_mano_no_se_pisa(self):
        from gestor import negocio
        self._importar("HBI")
        oc = self._oc(ASCENSORES)
        negocio.actualizar_oc(self.con, ASCENSORES, oc["version"], {"dia_inicio_periodo": 1})
        self._importar("HBI")
        self.assertEqual(self._oc(ASCENSORES)["dia_inicio_periodo"], 1)
