"""Paso 6: desglose mensual de servicios, por entregar sin negativos e inferencias de la OC."""
import unittest
from datetime import date
from decimal import Decimal

from gestor import db, importar
from tests import ayudas


class PruebaDesglose(ayudas.CasoConEntorno):

    @classmethod
    def setUpClass(cls):
        cls._entorno = ayudas.EntornoTemporal()
        cls.parametros = cls._entorno.config["parametros_iniciales"]
        db.inicializar(cls._entorno.ruta_base, cls.parametros)
        con = db.conectar(cls._entorno.ruta_base)
        try:
            importar.importar(con, ayudas.XLSX_HBI_2026, "HBI", cls.parametros)
        finally:
            con.close()

    @classmethod
    def tearDownClass(cls):
        cls._entorno.cerrar()

    def setUp(self):
        super().setUp()
        self.con = db.conectar(self._entorno.ruta_base)
        self.addCleanup(self.con.close)

    def _renglon(self, oc, pos):
        fila = db.leer_fila(self.con, "renglon", {"oc": oc, "pos": pos})
        self.assertIsNotNone(fila, "%s/%s" % (oc, pos))
        return fila

    def test_anio_final_con_y_sin_guion(self):
        self.assertEqual(importar.anio_final("SERV. ESTERIL. POR ETO 2026"), 2026)
        self.assertEqual(importar.anio_final("SERV. ESTERIL. POR VAPOR HUMEDO - 2027"), 2027)
        self.assertEqual(importar.anio_final("SERV INTEGRAL CONTROL DE PLAGAS - 2026 "), 2026)
        self.assertIsNone(importar.anio_final("DETERMINACIONES DE TROPONINA I"))
        self.assertIsNone(importar.anio_final(""))

    def test_meses_entre(self):
        self.assertEqual(importar.meses_entre(date(2026, 4, 9), date(2026, 8, 8)), Decimal(4))
        self.assertEqual(importar.meses_entre(date(2026, 10, 1), date(2026, 12, 31)), Decimal(3))
        self.assertEqual(importar.meses_entre("2027-01-01", "2027-09-30"), Decimal(9))
        self.assertIsNone(importar.meses_entre(date(2025, 9, 9), date(2025, 12, 31)))

    def test_efia_4500600299_tres_y_nueve_meses(self):
        uno = self._renglon("4500600299", 1)
        self.assertEqual(uno["desglose_cantidad"], "3")
        self.assertEqual(uno["desglose_unidad"], "MES")
        self.assertEqual(uno["desglose_precio_centavos"], 122499000)
        self.assertEqual(uno["revisar_desglose"], 0)
        dos = self._renglon("4500600299", 2)
        self.assertEqual(dos["desglose_cantidad"], "9")
        self.assertEqual(dos["desglose_unidad"], "MES")
        self.assertEqual(dos["desglose_precio_centavos"], 122499000)
        self.assertEqual(dos["revisar_desglose"], 0)

    def test_esterisur_eto_sin_guion_se_desglosa(self):
        eto = self._renglon("4500596317", 1)
        self.assertEqual(eto["descripcion"], "SERV. ESTERIL. POR ETO 2026")
        self.assertEqual(eto["desglose_cantidad"], "4")
        self.assertEqual(eto["desglose_unidad"], "MES")
        self.assertEqual(eto["desglose_precio_centavos"], 210980000)
        eto_2027 = self._renglon("4500596317", 3)
        self.assertEqual(eto_2027["desglose_cantidad"], "8")
        self.assertEqual(eto_2027["desglose_precio_centavos"], 210980000)

    def test_sin_por_entregar_negativo(self):
        valores = [fila[0] for fila in self.con.execute("SELECT sap_por_entregar FROM renglon")]
        self.assertEqual(len(valores), 433)
        for valor in valores:
            self.assertGreaterEqual(Decimal(valor), 0, valor)
        # ascensores: cantidad 1, entregado 4, período 2025 que no da meses enteros → revisar y exceso
        ascensores = self._renglon("4500563620", 1)
        self.assertEqual(ascensores["sap_por_entregar"], "0")
        self.assertEqual(ascensores["exceso_sap"], 1)
        self.assertEqual(ascensores["revisar_desglose"], 1)
        self.assertIsNone(ascensores["desglose_cantidad"])
        # ETO sin año: cantidad 1 con 6 entregados → toda la vigencia (6 meses) y nada por entregar
        eto = self._renglon("4500576139", 1)
        self.assertEqual((eto["desglose_cantidad"], eto["sap_por_entregar"], eto["exceso_sap"]), ("6", "0", 0))

    def test_inferencia_tipo_y_comodato(self):
        bio_fab = db.leer_fila(self.con, "oc", {"numero": "4500587121"})
        self.assertEqual(bio_fab["tipo"], "BIEN")
        self.assertEqual(bio_fab["comodato"], 0)
        self.assertEqual(bio_fab["centralizada"], 0)
        efia = db.leer_fila(self.con, "oc", {"numero": "4500600299"})
        self.assertEqual((efia["tipo"], efia["comodato"]), ("SERVICIO", 0))

        sintetico = importar.inferir_oc(
            {"org_compras": "1900"},
            [{"codigo": "5009999", "descripcion": "EQUIPO EN COMODATO"}],
            self.parametros,
        )
        self.assertEqual(sintetico, {"tipo": "PROVISION", "comodato": 1, "centralizada": 0})
        central = importar.inferir_oc({"org_compras": "0100"}, [{"codigo": "", "descripcion": "SERVICIO"}], self.parametros)
        self.assertEqual(central, {"tipo": "SERVICIO", "comodato": 0, "centralizada": 1})


if __name__ == "__main__":
    unittest.main()
