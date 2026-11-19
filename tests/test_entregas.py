"""Paso 24: entregas y CSV con formato NUMERACIÓN."""
import csv
import io
import unittest

from gestor import db, negocio
from tests import ayudas, datos_prueba

ENCABEZADO = ("REMITO;SII;PERIODO;SAP;OC;FACTURA;IMPORTE;TEXTO SAP;TXT CABECERA;EXPEDIENTE;GDE CARATULA;GDE FACTURA;"
              "GDE SII;GDE OC;GDE REMITOS;GDE CV;GDE VALE/HOJA;GDE AUTORIZACION;GDE CONTABILIZACION")


class PruebaEntregas(ayudas.CasoConServidor):

    def _efia(self, *estados):
        con = db.conectar(self.entorno.ruta_base)
        try:
            exp = datos_prueba.armar_expediente_efia(con)
            for estado in estados:
                exp = negocio.cambiar_estado(con, exp["id"], exp["version"], estado)
            return exp
        finally:
            con.close()

    def _ok(self, resp):
        self.assertEqual(resp.estado, 200, resp.texto())
        return resp.json()["datos"]

    def _nueva(self, efector="HBI", nombre=""):
        return self._ok(self.servidor.post("/api/entregas", {"efector": efector, "nombre": nombre}))

    def _efia_en_entrega(self):
        exp = self._efia("CONTROLADO", "EN_FIRMA", "FIRMADO")
        entrega = self._nueva()
        entrega = self._ok(self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                              {"version": entrega["version"], "expedientes": [exp["id"]]}))
        return exp, entrega

    def test_numero_correlativo_por_efector(self):
        primera, segunda, casph = self._nueva(), self._nueva(nombre="Semana 2"), self._nueva("CASPH")
        self.assertEqual([primera["numero"], segunda["numero"], casph["numero"]], [1, 2, 1])
        self.assertEqual((primera["nombre"], segunda["nombre"], primera["estado"]), ("Entrega 1", "Semana 2", "ABIERTA"))
        lista = self._ok(self.servidor.get("/api/entregas?efector=HBI"))["entregas"]
        self.assertEqual([e["numero"] for e in lista], [2, 1])
        self.assertEqual(self.servidor.post("/api/entregas", {"efector": "OTRO"}).estado, 400)

    def test_asignar_solo_firmados(self):
        exp = self._efia()
        entrega = self._nueva()
        resp = self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                  {"version": entrega["version"], "expedientes": [exp["id"]]})
        self.assertEqual(resp.estado, 422)
        self.assertEqual(resp.json()["error"]["mensaje"], "Solo se asignan expedientes FIRMADO del mismo efector.")
        # FIRMADO pero de otro efector
        con = db.conectar(self.entorno.ruta_base)
        try:
            for estado in ("CONTROLADO", "EN_FIRMA", "FIRMADO"):
                exp = negocio.cambiar_estado(con, exp["id"], exp["version"], estado)
        finally:
            con.close()
        casph = self._nueva("CASPH")
        otra = self.servidor.post("/api/entregas/%d/asignar" % casph["id"], {"version": casph["version"], "expedientes": [exp["id"]]})
        self.assertEqual(otra.json()["error"]["mensaje"], "Solo se asignan expedientes FIRMADO del mismo efector.")
        # el rechazo no dejó nada a medias
        self.assertEqual(self._ok(self.servidor.get("/api/entregas/%d" % entrega["id"]))["expedientes"], [])
        sin_entrega = self._ok(self.servidor.get("/api/entregas?efector=HBI"))["firmados_sin_entrega"]
        self.assertEqual([e["id"] for e in sin_entrega], [exp["id"]])

    def test_enviar_pasa_a_enviado(self):
        exp, entrega = self._efia_en_entrega()
        self.assertEqual([e["id"] for e in entrega["expedientes"]], [exp["id"]])
        vieja = self.servidor.post("/api/entregas/%d/enviar" % entrega["id"], {"version": 1, "fecha": "2026-10-05"})
        self.assertEqual(vieja.estado, 409)
        enviada = self._ok(self.servidor.post("/api/entregas/%d/enviar" % entrega["id"],
                                              {"version": entrega["version"], "fecha": "05/10/2026"}))
        self.assertEqual((enviada["estado"], enviada["fecha_envio"]), ("ENVIADA", "2026-10-05"))
        expediente = self._ok(self.servidor.get("/api/expedientes/%d" % exp["id"]))
        self.assertEqual(expediente["estado"], "ENVIADO")
        ultimo = expediente["datos"]["historial"][-1]
        self.assertEqual((ultimo["estado"], ultimo["desde"], ultimo["entrega"]), ("ENVIADO", "FIRMADO", "HBI 1"))
        otra = self.servidor.post("/api/entregas/%d/asignar" % entrega["id"],
                                  {"version": enviada["version"], "expedientes": [exp["id"]]})
        self.assertEqual(otra.estado, 422)
        # la celda del calendario lleva la marca ●
        calendario = self._ok(self.servidor.get("/api/calendario?anio=2026&hoy=2026-10-06"))
        fila = next(f for f in calendario["filas"] if f["oc"] == datos_prueba.OC_EFIA_MANUAL["numero"])
        self.assertTrue(fila["celdas"][7]["entrega_enviada"])
        self.assertEqual(fila["celdas"][7]["estado"], "validado")

    def test_csv_encabezado_y_bom(self):
        _, entrega = self._efia_en_entrega()
        resp = self.servidor.get("/api/entregas/%d/numeracion.csv" % entrega["id"])
        self.assertEqual(resp.estado, 200)
        self.assertEqual(resp.cabeceras["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", resp.cabeceras["Content-Disposition"])
        self.assertTrue(resp.cuerpo.startswith(b"\xef\xbb\xbf" + ENCABEZADO.encode("utf-8") + b"\r\n"))
        self.assertEqual(resp.cuerpo.count(b"\r\n"), 2)
        self.assertNotIn(b"\n", resp.cuerpo.replace(b"\r\n", b""))

    def test_csv_fila_efia(self):
        exp, entrega = self._efia_en_entrega()
        exp = self._ok(self.servidor.get("/api/expedientes/%d" % exp["id"]))
        self._ok(self.servidor.put("/api/expedientes/%d/gde" % exp["id"], {"version": exp["version"], "gde": {
            "expediente": datos_prueba.EX_EFIA,
            "remitos": {"00001-00029461": "RM-2026-90634238-INSSJP-GESP#INSSJP"},
        }}))
        cuerpo = self.servidor.get("/api/entregas/%d/numeracion.csv" % entrega["id"]).cuerpo.decode("utf-8-sig")
        filas = list(csv.DictReader(io.StringIO(cuerpo, newline=""), delimiter=";"))
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        esperado = {
            "REMITO": "00001-00029461", "PERIODO": "08-26", "SAP": "77170", "OC": "4500555861",
            "FACTURA": "0003B00031812", "IMPORTE": "1.224.990,00",
            "TEXTO SAP": "HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26",
            "TXT CABECERA": "08/26 HBI OC 4500555861", "SII": "HXW2037078",
            "EXPEDIENTE": datos_prueba.EX_EFIA, "GDE REMITOS": "RM-2026-90634238-INSSJP-GESP#INSSJP", "GDE CV": "",
        }
        self.assertEqual({k: fila[k] for k in esperado}, esperado)


if __name__ == "__main__":
    unittest.main()
