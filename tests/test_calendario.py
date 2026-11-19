"""Paso 22: calendario anual OC × meses con estados accesibles."""
import unittest

from gestor import db, negocio
from tests import ayudas, datos_prueba

LETRAS = {"fuera": "-", "validado": "V", "en_curso": "C", "pendiente_motivo": "M",
          "pendiente_en_plazo": "P", "atrasado": "A", "sin_iniciar": "·"}


class PruebaCalendario(ayudas.CasoConServidor):

    def _con(self):
        return db.conectar(self.entorno.ruta_base)

    def _efia_firmado(self):
        con = self._con()
        try:
            exp = datos_prueba.armar_expediente_efia(con)
            for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
                exp = negocio.cambiar_estado(con, exp["id"], exp["version"], estado)
            return exp
        finally:
            con.close()

    def _cargar_efia(self):
        con = self._con()
        try:
            datos_prueba.cargar_efia(con)
        finally:
            con.close()

    def _calendario(self, hoy, anio=2026):
        resp = self.servidor.get("/api/calendario?anio=%d&hoy=%s" % (anio, hoy))
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _fila_efia(self, datos):
        filas = [f for f in datos["filas"] if f["oc"] == datos_prueba.OC_EFIA_MANUAL["numero"]]
        self.assertEqual(len(filas), 1)
        return filas[0]

    def _parametros(self):
        con = self._con()
        try:
            return db.leer_parametros(con)
        finally:
            con.close()

    def test_estados_efia_2026(self):
        exp = self._efia_firmado()
        fila = self._fila_efia(self._calendario("2026-09-20"))
        estados = [c["estado"] for c in fila["celdas"]]
        self.assertEqual(len(estados), 12)
        self.assertEqual(estados[7], "validado")
        self.assertEqual(fila["celdas"][7]["expediente_id"], exp["id"])
        self.assertEqual(estados[6], "atrasado")
        self.assertEqual(estados[8], "pendiente_en_plazo")
        self.assertEqual(estados[9:], ["fuera", "fuera", "fuera"])
        self.assertEqual(estados[:6], ["atrasado"] * 6)
        self.assertIsNone(fila["celdas"][6]["expediente_id"])
        self.assertEqual((fila["celdas"][7]["periodo"], fila["celdas"][7]["desde"], fila["celdas"][7]["hasta"]),
                         ("2026-08", "2026-08-01", "2026-08-31"))
        # un expediente en curso o pendiente cambia la celda
        con = self._con()
        try:
            borrador = negocio.crear_expediente(con, {"oc": datos_prueba.OC_EFIA_MANUAL["numero"], "periodo": "2026-07",
                                                     "periodo_desde": "2026-07-01", "periodo_hasta": "2026-07-31"})
            controlado = negocio.crear_expediente(con, {"oc": datos_prueba.OC_EFIA_MANUAL["numero"], "periodo": "2026-06",
                                                       "periodo_desde": "2026-06-01", "periodo_hasta": "2026-06-30"})
        finally:
            con.close()
        self.servidor.post("/api/expedientes/%d/anular" % controlado["id"],
                           {"version": controlado["version"], "motivo": "Duplicado"})
        fila = self._fila_efia(self._calendario("2026-09-20"))
        self.assertEqual((fila["celdas"][6]["estado"], fila["celdas"][6]["expediente_id"]), ("en_curso", borrador["id"]))
        self.assertEqual(fila["celdas"][5]["estado"], "atrasado")  # el anulado no cuenta

    def test_vence_pronto(self):
        self._cargar_efia()
        self.assertEqual(self._parametros().get("dias_aviso_vencimiento_oc"), 60)
        self.assertTrue(self._fila_efia(self._calendario("2026-09-20"))["vence_pronto"])
        self.assertFalse(self._fila_efia(self._calendario("2026-06-01"))["vence_pronto"])

    def test_letras_por_estado(self):
        self._efia_firmado()
        for hoy, anio in (("2026-09-20", 2026), ("2025-09-15", 2025), ("2026-01-05", 2026)):
            datos = self._calendario(hoy, anio)
            self.assertEqual(datos["estados"], LETRAS)
            for fila in datos["filas"]:
                for celda in fila["celdas"]:
                    self.assertEqual(celda["letra"], LETRAS[celda["estado"]])
                    self.assertIn("expediente_id", celda)
        sin_iniciar = self._fila_efia(self._calendario("2026-01-05"))["celdas"]
        self.assertEqual([c["letra"] for c in sin_iniciar[1:9]], ["·"] * 6 + ["V", "·"])  # agosto ya tiene expediente
        self.assertEqual(sin_iniciar[0]["letra"], "P")
        # año inválido → 400
        self.assertEqual(self.servidor.get("/api/calendario?anio=dos").estado, 400)

    def test_leyenda_en_app_js(self):
        resp = self.servidor.get("/app.js")
        self.assertEqual(resp.estado, 200)
        texto = resp.texto()
        self.assertIn("leyenda-calendario", texto)
        for estado in LETRAS:
            self.assertIn('"%s"' % estado, texto)
        self.assertIn("aria-label", texto)
        css = self.servidor.get("/style.css").texto()
        for estado in list(LETRAS) + ["vence_pronto"]:
            self.assertIn(".cal-%s" % estado, css)

    def test_atrasado_respeta_dias_gracia(self):
        self._cargar_efia()
        self.assertEqual(self._parametros().get("dias_gracia"), 10)
        julio = 6  # el período 2026-07 termina el 31/07
        self.assertEqual(self._fila_efia(self._calendario("2026-08-09"))["celdas"][julio]["estado"], "pendiente_en_plazo")
        self.assertEqual(self._fila_efia(self._calendario("2026-08-10"))["celdas"][julio]["estado"], "pendiente_en_plazo")
        self.assertEqual(self._fila_efia(self._calendario("2026-08-11"))["celdas"][julio]["estado"], "atrasado")


if __name__ == "__main__":
    unittest.main()
