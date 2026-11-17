"""Paso 10: carga rápida de remitos pegados y período sugerido."""
import copy
import unittest

from gestor import db, negocio
from tests import ayudas, datos_prueba


def _oc_manual(numero, dia_inicio, razon_social="PROVEEDOR DE PRUEBA", sap="99001"):
    datos = copy.deepcopy(datos_prueba.OC_EFIA_MANUAL)
    datos.update(numero=numero, sap=sap, razon_social=razon_social, dia_inicio_periodo=dia_inicio,
                 vig_desde="2026-01-01", vig_hasta="2027-12-31")
    return datos


class PruebaPeriodoRemitos(ayudas.CasoConServidor):

    def _expediente(self, oc_datos=None):
        con = db.conectar(self.entorno.ruta_base)
        try:
            if oc_datos is None:
                datos_prueba.cargar_efia(con)
                numero = datos_prueba.OC_EFIA_MANUAL["numero"]
            else:
                negocio.crear_oc_manual(con, oc_datos)
                numero = oc_datos["numero"]
        finally:
            con.close()
        resp = self.servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": numero})
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _pegar(self, exp, texto, version=None, **extra):
        cuerpo = {"version": version if version is not None else exp["version"], "texto": texto}
        cuerpo.update(extra)
        return self.servidor.post("/api/expedientes/%d/remitos/pegar" % exp["id"], cuerpo)

    def test_pegar_tres_lineas_con_fecha_firma(self):
        exp = self._expediente()
        texto = "0001-00000001;05/08/2026\n\n0001-00000002;28/08/2026;02/09/2026\n0001-00000003;10/08/2026\n"
        resp = self._pegar(exp, texto)
        self.assertEqual(resp.estado, 200, resp.texto())
        datos = resp.json()["datos"]
        remitos = datos["datos"]["remitos"]
        self.assertEqual([r["numero"] for r in remitos], ["0001-00000001", "0001-00000002", "0001-00000003"])
        self.assertEqual(remitos[1], {
            "numero": "0001-00000002", "fecha": "2026-08-28", "fecha_firma": "2026-09-02",
            "es_equipo_comodato": False, "aclara_periodo": False, "items": [],
        })
        self.assertIsNone(remitos[0]["fecha_firma"])
        # la fecha base más nueva es la firma del 02/09/2026
        self.assertEqual(datos["periodo_sugerido"], {"periodo": "2026-09", "desde": "2026-09-01", "hasta": "2026-09-30"})
        self.assertEqual((datos["periodo"], datos["periodo_manual"]), ("2026-09", 0))
        self.assertEqual(datos["version"], 2)

        # con solo las dos primeras líneas, también 2026-09 (criterio del blueprint)
        otro = self._expediente()
        dos = self._pegar(otro, "0001-00000001;05/08/2026\n0001-00000002;28/08/2026;02/09/2026").json()["datos"]
        self.assertEqual(len(dos["datos"]["remitos"]), 2)
        self.assertEqual(dos["periodo"], "2026-09")

    def test_linea_invalida_informa_numero(self):
        exp = self._expediente()
        resp = self._pegar(exp, "0001-00000001;05/08/2026\n0001-00000003")
        self.assertEqual(resp.estado, 400)
        self.assertEqual(resp.json()["error"], {
            "codigo": "validacion", "mensaje": 'Línea 2: se esperaba "numero;fecha[;fecha_firma]".',
        })
        fecha_mala = self._pegar(exp, "0001-00000001;32/08/2026")
        self.assertEqual(fecha_mala.json()["error"]["mensaje"], 'Línea 1: se esperaba "numero;fecha[;fecha_firma]".')
        guardado = self.servidor.get("/api/expedientes/%d" % exp["id"]).json()["datos"]
        self.assertEqual(guardado["datos"]["remitos"], [])
        self.assertEqual(guardado["version"], 1)

    def test_periodo_sugerido_usa_remito_mas_reciente(self):
        oc = {"dia_inicio_periodo": 1}
        remitos = negocio.parsear_remitos_pegados("A;30/09/2026\nB;03/10/2026\nC;15/09/2026")
        self.assertEqual(negocio.periodo_sugerido(oc, remitos).periodo, "2026-10")
        remitos[1]["es_equipo_comodato"] = True  # el remito del equipo no cuenta
        self.assertEqual(negocio.periodo_sugerido(oc, remitos).periodo, "2026-09")
        self.assertEqual(negocio.fecha_base({"fecha": "2026-08-28", "fecha_firma": "2026-09-02"}), "2026-09-02")
        self.assertEqual(negocio.fecha_base({"fecha": "2026-08-28", "fecha_firma": None}), "2026-08-28")
        self.assertIsNone(negocio.periodo_sugerido(oc, []))

    def test_periodo_especifico_dia_17(self):
        exp = self._expediente(_oc_manual("4500900017", 17))
        datos = self._pegar(exp, "R-1;20/10/2026").json()["datos"]
        self.assertEqual(
            (datos["periodo"], datos["periodo_desde"], datos["periodo_hasta"]),
            ("2026-11", "2026-10-17", "2026-11-16"),
        )
        self.assertEqual(datos["fuera_de_periodo"], [])

    def test_esterisur_quince_mas_uno(self):
        exp = self._expediente(_oc_manual("4500900099", 1, razon_social="ESTERISUR S.A.", sap="99002"))
        lineas = ["0002-%08d;%02d/08/2026" % (i, i) for i in range(1, 16)]
        lineas.append("0002-00000099;28/07/2026")
        datos = self._pegar(exp, "\n".join(lineas)).json()["datos"]
        self.assertEqual(len(datos["datos"]["remitos"]), 16)
        self.assertEqual(datos["periodo"], "2026-08")
        self.assertEqual(datos["fuera_de_periodo"], ["0002-00000099"])
        periodo = negocio.periodo_sugerido({"dia_inicio_periodo": 1}, datos["datos"]["remitos"])
        self.assertEqual(negocio.remitos_fuera_de_periodo(periodo, datos["datos"]["remitos"]), ["0002-00000099"])
        # un remito que aclara el período no se informa
        remitos = datos["datos"]["remitos"]
        remitos[-1]["aclara_periodo"] = True
        self.assertEqual(negocio.remitos_fuera_de_periodo(periodo, remitos), [])

    def test_periodo_manual_queda_registrado(self):
        exp = self._expediente()
        resp = self.servidor.put("/api/expedientes/%d" % exp["id"], {"version": 1, "cambios": {"periodo": "2026-07"}})
        self.assertEqual(resp.estado, 200, resp.texto())
        manual = resp.json()["datos"]
        self.assertEqual(manual["periodo_manual"], 1)
        self.assertEqual((manual["periodo_desde"], manual["periodo_hasta"]), ("2026-07-01", "2026-07-31"))
        self.assertEqual(manual["datos"]["historial"][-1]["accion"], "PERIODO_MANUAL")

        despues = self._pegar(manual, "0001-00000010;15/09/2026").json()["datos"]
        self.assertEqual(despues["periodo"], "2026-07")  # el pegado no pisa el período manual
        self.assertEqual(despues["periodo_sugerido"]["periodo"], "2026-09")
        self.assertEqual(despues["fuera_de_periodo"], ["0001-00000010"])


if __name__ == "__main__":
    unittest.main()
