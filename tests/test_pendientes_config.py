"""Paso 25: pendientes, configuración local, copia manual, apagado e Iniciar.bat."""
import json
import socket
import time
import unittest
from pathlib import Path

from gestor import config, db, negocio
from tests import ayudas, datos_prueba


class PruebaPendientesConfig(ayudas.CasoConServidor):

    def _pendiente(self, con, armar, fecha, motivo):
        exp = armar(con)
        if exp["estado"] == "BORRADOR" and armar is datos_prueba.armar_expediente_efia:
            exp = negocio.cambiar_estado(con, exp["id"], exp["version"], "CONTROLADO")
        return negocio.cambiar_estado(con, exp["id"], exp["version"], "PENDIENTE", motivo=motivo, fecha_seguimiento=fecha)

    def test_pendientes_ordenados_por_demora(self):
        con = db.conectar(self.entorno.ruta_base)
        try:
            dos = self._pendiente(con, datos_prueba.armar_expediente_efia, "2026-09-18", "Falta la firma")
            cinco = self._pendiente(con, datos_prueba.armar_expediente_biofab, "2026-09-15", "Falta el remito del equipo")
            futuro = self._pendiente(con, datos_prueba.armar_expediente_macatex, "2026-09-30", "Esperando nota")
        finally:
            con.close()
        resp = self.servidor.get("/api/pendientes?hoy=2026-09-20")
        self.assertEqual(resp.estado, 200, resp.texto())
        lista = resp.json()["datos"]
        self.assertEqual([(p["id"], p["dias_demora"]) for p in lista], [(cinco["id"], 5), (dos["id"], 2), (futuro["id"], 0)])
        primero = lista[0]
        self.assertEqual((primero["proveedor"], primero["oc"], primero["periodo"], primero["motivo"], primero["fecha_seguimiento"]),
                         ("BIO FAB S.R.L", "4500587121", "2026-08", "Falta el remito del equipo", "2026-09-15"))
        self.assertEqual(set(primero) >= {"id", "proveedor", "oc", "periodo", "motivo", "fecha_seguimiento", "dias_demora"}, True)

    def test_config_local_guarda_base_datos(self):
        antes = json.loads(Path(self.entorno.ruta_config).read_text(encoding="utf-8"))
        leida = self.servidor.get("/api/config-local").json()["datos"]
        self.assertEqual(Path(leida["archivo"]), Path(self.entorno.ruta_config))
        self.assertEqual(leida["guardada"]["base_datos"], antes["base_datos"])
        nueva = str(self.entorno.dir / "compartida" / "expedientes.db")
        resp = self.servidor.put("/api/config-local", {"base_datos": nueva})
        self.assertEqual(resp.estado, 200, resp.texto())
        despues = json.loads(Path(self.entorno.ruta_config).read_text(encoding="utf-8"))
        self.assertEqual(despues["base_datos"], nueva)
        antes.pop("base_datos")
        despues.pop("base_datos")
        self.assertEqual(despues, antes)
        # rige al reiniciar: el servidor sigue usando la base anterior
        self.assertEqual(Path(self.servidor.httpd.cfg["base_datos"]), self.entorno.ruta_base)
        self.assertEqual(self.servidor.put("/api/config-local", {"base_datos": "  "}).estado, 400)

    def test_backup_manual(self):
        carpeta = config.ruta(config.cargar_config(), "carpeta_backups")
        antes = sorted(carpeta.glob("expedientes-*.db")) if carpeta.is_dir() else []
        resp = self.servidor.post("/api/base/backup", {})
        self.assertEqual(resp.estado, 200, resp.texto())
        nombre = resp.json()["datos"]["backup"]
        self.assertRegex(nombre, r"^expedientes-\d{8}-\d{6}\.db$")
        despues = sorted(carpeta.glob("expedientes-*.db"))
        self.assertEqual(len(despues), len(antes) + 1)
        self.assertIn(nombre, [p.name for p in despues])

    def test_apagar_detiene_el_servidor(self):
        resp = self.servidor.post("/api/apagar", {})
        self.assertEqual(resp.estado, 200)
        self.assertEqual(resp.json(), {"ok": True, "datos": {"apagando": True}})
        limite = time.monotonic() + 5
        detenido = False
        while time.monotonic() < limite:
            try:
                with socket.create_connection(("127.0.0.1", self.servidor.puerto), timeout=0.5) as s:
                    s.sendall(b"GET /api/salud HTTP/1.0\r\n\r\n")
                    s.settimeout(0.5)
                    if not s.recv(1):
                        detenido = True
                        break
            except OSError:
                detenido = True
                break
            time.sleep(0.1)
        self.assertTrue(detenido, "el servidor sigue aceptando conexiones")

    def test_iniciar_bat_prueba_los_tres_lanzadores_en_orden(self):
        crudo = (Path(config.RAIZ) / "Iniciar.bat").read_bytes()
        crudo.decode("ascii")
        texto = crudo.decode("ascii").replace("\r\n", "\n")
        posiciones = [texto.index(t) for t in ('start "" /b pythonw app.py', 'start "" /b pyw -3 app.py',
                                               'start "" /b py -3 app.py', "No se encontro Python 3.10 o superior en esta PC.")]
        self.assertEqual(posiciones, sorted(posiciones))
        self.assertTrue(texto.startswith("@echo off\n"))
        self.assertIn('cd /d "%~dp0"', texto)


if __name__ == "__main__":
    unittest.main()
