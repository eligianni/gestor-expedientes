"""Paso 20: estados del expediente, pendiente/reanudar y números GDE."""
import unittest

from gestor import db, negocio
from tests import ayudas, datos_prueba


class PruebaEstados(ayudas.CasoConServidor):

    def _armar(self, funcion, **kwargs):
        con = db.conectar(self.entorno.ruta_base)
        try:
            return funcion(con, **kwargs)
        finally:
            con.close()

    def _estado(self, exp, estado, **extra):
        cuerpo = {"version": exp["version"], "estado": estado}
        cuerpo.update(extra)
        return self.servidor.post("/api/expedientes/%d/estado" % exp["id"], cuerpo)

    def _avanzar(self, exp, estado):
        resp = self._estado(exp, estado)
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_efia_recorre_hasta_firmado(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        largo = len(exp["datos"]["historial"])
        for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
            exp = self._avanzar(exp, estado)
            self.assertEqual(exp["estado"], estado)
            largo += 1
            self.assertEqual(len(exp["datos"]["historial"]), largo)
            self.assertEqual(exp["datos"]["historial"][-1]["estado"], estado)
        self.assertEqual([h["desde"] for h in exp["datos"]["historial"][-3:]], ["BORRADOR", "CONTROLADO", "EN_FIRMA"])
        # versión vieja en un cambio válido → 409
        vieja = self._estado(dict(exp, version=1), "PENDIENTE", motivo="x", fecha_seguimiento="2026-12-01")
        self.assertEqual(vieja.estado, 409)

    def test_controlado_bloqueado_por_errores(self):
        exp = self._armar(datos_prueba.armar_expediente_macatex)
        resp = self._estado(exp, "CONTROLADO")
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "No se puede pasar a CONTROLADO: hay 1 errores y 0 salvables sin nota.")
        # salvable sin nota también bloquea (BIO FAB)
        biofab = self._armar(datos_prueba.armar_expediente_biofab)
        bloqueado = self._estado(biofab, "CONTROLADO")
        self.assertEqual(bloqueado.json()["error"]["mensaje"], "No se puede pasar a CONTROLADO: hay 0 errores y 1 salvables sin nota.")
        con_nota = self.servidor.post("/api/expedientes/%d/notas" % biofab["id"], {
            "version": biofab["version"], "codigo": "codigo_remito_distinto", "referencia": "2", "texto": "Error de tipeo.",
        }).json()["datos"]["expediente"]
        self.assertEqual(self._avanzar(con_nota, "CONTROLADO")["estado"], "CONTROLADO")

    def test_transicion_invalida(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        resp = self._estado(exp, "FIRMADO")
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "No se puede pasar de BORRADOR a FIRMADO.")
        self.assertEqual(self._estado(exp, "INVENTADO").estado, 400)

    def test_pendiente_y_reanudar(self):
        exp = self._avanzar(self._armar(datos_prueba.armar_expediente_efia), "CONTROLADO")
        sin_motivo = self._estado(exp, "PENDIENTE", fecha_seguimiento="2026-12-01")
        self.assertEqual(sin_motivo.estado, 400)
        pendiente = self._avanzar_pendiente(exp)
        self.assertEqual((pendiente["estado"], pendiente["motivo_pendiente"], pendiente["fecha_seguimiento"]),
                         ("PENDIENTE", "Falta la firma del jefe", "2026-12-01"))
        self.assertEqual(pendiente["datos"]["historial"][-1]["estado_previo"], "CONTROLADO")
        resp = self.servidor.post("/api/expedientes/%d/reanudar" % exp["id"], {"version": pendiente["version"]})
        self.assertEqual(resp.estado, 200, resp.texto())
        reanudado = resp.json()["datos"]
        self.assertEqual((reanudado["estado"], reanudado["motivo_pendiente"], reanudado["fecha_seguimiento"]),
                         ("CONTROLADO", "", None))
        otra = self.servidor.post("/api/expedientes/%d/reanudar" % exp["id"], {"version": reanudado["version"]})
        self.assertEqual(otra.json()["error"]["mensaje"], "El expediente no está pendiente.")

    def _avanzar_pendiente(self, exp):
        resp = self._estado(exp, "PENDIENTE", motivo="Falta la firma del jefe", fecha_seguimiento="01/12/2026")
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def test_enviado_solo_por_entrega(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
            exp = self._avanzar(exp, estado)
        resp = self._estado(exp, "ENVIADO")
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "Asigná el expediente a una entrega para marcarlo como enviado.")

    def test_gde_normaliza_y_valida(self):
        exp = self._armar(datos_prueba.armar_expediente_efia)
        resp = self.servidor.put("/api/expedientes/%d/gde" % exp["id"], {"version": exp["version"], "gde": {
            "expediente": "ex-2026-89654857-   -INSSJP-GESP#INSSJP",
            "sii": "IF-2026-90061259-INSSJP-GESP%INSSJP",
            "remitos": {"00001-00029461": "RM-2026-90634238-INSSJP-GESP#INSSJP"},
            "orden_remito_equipo": "7",
        }})
        self.assertEqual(resp.estado, 200, resp.texto())
        gde = resp.json()["datos"]["datos"]["gde"]
        self.assertEqual(gde["sii"], "IF-2026-90061259-INSSJP-GESP#INSSJP")
        self.assertEqual(gde["expediente"], "EX-2026-89654857- -INSSJP-GESP#INSSJP")
        self.assertEqual(gde["remitos"], {"00001-00029461": "RM-2026-90634238-INSSJP-GESP#INSSJP"})
        self.assertEqual((gde["orden_remito_equipo"], gde["cv"]), (7, ""))
        malo = self.servidor.put("/api/expedientes/%d/gde" % exp["id"],
                                 {"version": resp.json()["datos"]["version"], "gde": {"sii": "IF-2026-12"}})
        self.assertEqual(malo.estado, 400)
        self.assertEqual(malo.json()["error"]["mensaje"], 'El número GDE "IF-2026-12" no tiene un formato válido.')

    def test_gde_oc_pdf_desde_la_oc(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
            oc = negocio.ficha_oc(con, exp["oc"])["oc"]
            negocio.actualizar_oc(con, exp["oc"], oc["version"], {"gde_pdf_oc": "IF-2025-98344682-INSSJP-GESP#INSSJP"})
        finally:
            con.close()
        resp = self.servidor.put("/api/expedientes/%d/gde" % exp["id"], {"version": exp["version"], "gde": {"oc_pdf": ""}})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json()["datos"]["datos"]["gde"]["oc_pdf"], "IF-2025-98344682-INSSJP-GESP#INSSJP")


if __name__ == "__main__":
    unittest.main()
