"""Paso 23: pantalla Inicio con alertas ordenadas por urgencia."""
import unittest
from datetime import date

from gestor import db, negocio
from tests import ayudas, datos_prueba

OC_EFIA = datos_prueba.OC_EFIA_MANUAL["numero"]


class PruebaInicio(ayudas.CasoConServidor):

    def _con(self):
        return db.conectar(self.entorno.ruta_base)

    def _efia(self, *estados, **pendiente):
        con = self._con()
        try:
            exp = datos_prueba.armar_expediente_efia(con)
            for estado in estados:
                extra = pendiente if estado == "PENDIENTE" else {}
                exp = negocio.cambiar_estado(con, exp["id"], exp["version"], estado, **extra)
            return exp
        finally:
            con.close()

    def _alertas(self, hoy):
        resp = self.servidor.get("/api/inicio/alertas?hoy=%s" % hoy)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _de_tipo(self, alertas, tipo):
        return [a for a in alertas if a["tipo"] == tipo]

    def test_orden_por_urgencia(self):
        self._efia("CONTROLADO", "EN_FIRMA", "FIRMADO")
        alertas = self._alertas("2026-09-20")
        urgencias = [a["urgencia"] for a in alertas]
        self.assertEqual(urgencias, sorted(urgencias))
        self.assertEqual(sorted(set(urgencias)), [1, 2, 3])
        for alerta in alertas:
            self.assertEqual(set(alerta), {"tipo", "urgencia", "mensaje", "oc", "expediente_id", "fecha"})
        atrasado = self._de_tipo(alertas, "periodo_atrasado")
        self.assertEqual(len(atrasado), 1)
        self.assertEqual((atrasado[0]["urgencia"], atrasado[0]["oc"]), (1, OC_EFIA))
        self.assertIn("2025-10", atrasado[0]["mensaje"])
        self.assertIn("2026-07", atrasado[0]["mensaje"])
        self.assertNotIn("2026-08", atrasado[0]["mensaje"])
        vence = self._de_tipo(alertas, "oc_por_vencer")
        self.assertEqual(len(vence), 1)
        self.assertEqual(vence[0]["mensaje"], "La OC %s (GRUPO EFIA S.R.L.) vence el 30/09/2026 (en 10 días)." % OC_EFIA)
        self.assertEqual(vence[0]["urgencia"], 2)

    def test_pendiente_vencido(self):
        exp = self._efia("CONTROLADO", "PENDIENTE", motivo="Falta la firma del jefe", fecha_seguimiento="2026-09-01")
        alertas = self._de_tipo(self._alertas("2026-09-20"), "pendiente_vencido")
        self.assertEqual(len(alertas), 1)
        self.assertEqual((alertas[0]["urgencia"], alertas[0]["expediente_id"], alertas[0]["oc"]), (1, exp["id"], OC_EFIA))
        self.assertIn("Falta la firma del jefe", alertas[0]["mensaje"])
        self.assertIn("01/09/2026", alertas[0]["mensaje"])
        self.assertEqual(self._de_tipo(self._alertas("2026-09-01"), "pendiente_vencido"), [])

    def test_listo_sin_entrega(self):
        exp = self._efia("CONTROLADO", "EN_FIRMA", "FIRMADO")
        alertas = self._de_tipo(self._alertas("2026-09-20"), "listo_sin_entrega")
        self.assertEqual(len(alertas), 1)
        self.assertEqual((alertas[0]["urgencia"], alertas[0]["expediente_id"]), (3, exp["id"]))
        self.assertTrue(alertas[0]["mensaje"].startswith("Expediente %d (OC %s, GRUPO EFIA S.R.L., período 2026-08)"
                                                         % (exp["id"], OC_EFIA)))

    def test_informe_correctivos_dias_habiles(self):
        self.assertEqual(negocio.dia_habil_del_mes(date(2026, 9, 7)), 5)
        self.assertEqual(negocio.dia_habil_del_mes(date(2026, 9, 5)), 0)  # sábado
        for hoy, esperado in (("2026-09-01", True), ("2026-09-07", True), ("2026-09-05", False), ("2026-09-08", False)):
            informe = self._de_tipo(self._alertas(hoy), "informe_correctivos")
            self.assertEqual(bool(informe), esperado, hoy)
        informe = self._de_tipo(self._alertas("2026-09-07"), "informe_correctivos")[0]
        self.assertEqual((informe["urgencia"], informe["mensaje"]),
                         (2, "Enviar a GESP el informe mensual de correctivos del mes anterior."))

    def test_base_con_errores_primero(self):
        self._efia("CONTROLADO", "EN_FIRMA", "FIRMADO")
        self.servidor.httpd.integridad = False
        try:
            alertas = self._alertas("2026-09-20")
        finally:
            self.servidor.httpd.integridad = True
        self.assertEqual(alertas[0]["tipo"], "base_con_errores")
        self.assertEqual(alertas[0]["urgencia"], 1)
        self.assertEqual(alertas[0]["mensaje"], "La base de datos tiene errores de integridad. "
                                                "Restaurá la última copia de seguridad desde Configuración.")
        self.assertEqual(self._de_tipo(self._alertas("2026-09-20"), "base_con_errores"), [])

    def test_alertas_de_oc(self):
        con = self._con()
        try:
            datos_prueba.preparar_biofab(con)
            alertas = negocio.alertas(con, hoy="2026-09-20")
        finally:
            con.close()
        comodato = self._de_tipo(alertas, "comodato_sin_equipo")
        self.assertIn("4500587121", [a["oc"] for a in comodato])
        self.assertTrue(all(a["urgencia"] == 2 for a in comodato))

    def test_inicio_en_app_js(self):
        texto = self.servidor.get("/app.js").texto()
        for palabra in ("/api/inicio/alertas", "Urgente", "Atención", "Para mirar", "Restaurar última copia"):
            self.assertIn(palabra, texto)


if __name__ == "__main__":
    unittest.main()
