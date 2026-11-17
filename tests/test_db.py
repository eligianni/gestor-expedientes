"""Paso 2: capa de datos SQLite (esquema, versión optimista, auditoría, backups) y /api/base/*."""
import json
import re
import sqlite3
import unittest
from datetime import datetime, timedelta

from gestor import db
from tests import ayudas


def _contar(con, sql, parametros=()):
    return con.execute(sql, parametros).fetchone()[0]


class PruebaBase(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.ruta = self.entorno.ruta_base
        self.parametros = self.entorno.config["parametros_iniciales"]
        db.inicializar(self.ruta, self.parametros)
        self.con = db.conectar(self.ruta)
        self.addCleanup(self.con.close)

    def _alta_proveedor(self, sap="77170", razon_social="GRUPO EFIA S.R.L."):
        with db.transaccion(self.con):
            db.insertar(self.con, "proveedor", {"sap": sap, "razon_social": razon_social})

    def test_inicializar_crea_todas_las_tablas(self):
        tablas = {fila[0] for fila in self.con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for tabla in db.TABLAS:
            self.assertIn(tabla, tablas)
        self.assertEqual(len(db.TABLAS), 8)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(self.con.execute("PRAGMA journal_mode").fetchone()[0].lower(), "delete")
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertIn("version", db.COLUMNAS["oc"])
        self.assertIn("crudo", db.COLUMNAS["renglon"])

    def test_inicializar_es_idempotente(self):
        db.inicializar(self.ruta, self.parametros)
        db.inicializar(self.ruta, self.parametros)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM config"), len(self.parametros))
        for clave in self.parametros:
            self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM config WHERE clave = ?", (clave,)), 1)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_parametros_iniciales_sembrados(self):
        parametros = db.leer_parametros(self.con)
        self.assertEqual(parametros, json.loads(json.dumps(self.parametros)))
        self.assertEqual(parametros["partidas_excluidas"], ["3490000"])
        self.assertEqual(parametros["dias_gracia"], 10)
        self.assertEqual(parametros["efectores"]["HBI"]["centros"], ["1900"])
        valor = self.con.execute("SELECT valor FROM config WHERE clave = 'efectores'").fetchone()[0]
        self.assertEqual(valor, json.dumps(self.parametros["efectores"], ensure_ascii=False, sort_keys=True))
        self.assertIn("Ituzaingó", valor)

    def test_actualizar_con_version_incrementa_y_audita(self):
        self._alta_proveedor()
        eventos_antes = _contar(self.con, "SELECT COUNT(*) FROM evento")
        with db.transaccion(self.con):
            nueva = db.actualizar_con_version(self.con, "proveedor", {"sap": "77170"}, 1, {"email": "a@b.com"})
        self.assertEqual(nueva["version"], 2)
        self.assertEqual(nueva["email"], "a@b.com")
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM evento"), eventos_antes + 1)
        evento = self.con.execute("SELECT * FROM evento ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(evento["accion"], "MODIFICACION")
        self.assertEqual(evento["tabla"], "proveedor")
        self.assertEqual(json.loads(evento["clave"]), {"sap": "77170"})
        self.assertTrue(evento["usuario"])
        self.assertTrue(evento["pc"])
        self.assertEqual(json.loads(evento["antes"])["version"], 1)
        self.assertEqual(json.loads(evento["despues"])["email"], "a@b.com")
        # parámetros compartidos usan el mismo mecanismo
        db.guardar_parametro(self.con, "dias_gracia", 15, 1)
        self.assertEqual(db.leer_parametros(self.con)["dias_gracia"], 15)

    def test_conflicto_de_version_no_escribe_nada(self):
        self._alta_proveedor()
        with db.transaccion(self.con):
            db.actualizar_con_version(self.con, "proveedor", {"sap": "77170"}, 1, {"notas": "primera"})
        eventos_antes = _contar(self.con, "SELECT COUNT(*) FROM evento")
        with self.assertRaises(db.ConflictoVersion) as contexto:
            with db.transaccion(self.con):
                db.actualizar_con_version(self.con, "proveedor", {"sap": "77170"}, 1, {"notas": "vieja"})
        self.assertEqual(
            str(contexto.exception),
            "Otra persona guardó cambios en este registro. Recargá para ver la última versión.",
        )
        fila = db.leer_fila(self.con, "proveedor", {"sap": "77170"})
        self.assertEqual(fila["notas"], "primera")
        self.assertEqual(fila["version"], 2)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM evento"), eventos_antes)

    def test_evento_y_expediente_no_se_borran(self):
        self._alta_proveedor()
        ahora = db.ahora_utc()
        with db.transaccion(self.con):
            db.insertar(self.con, "oc", {"numero": "4500555861", "efector": "HBI", "sap": "77170"})
            id_exp = db.insertar(self.con, "expediente", {
                "tipo": "COMUN", "efector": "HBI", "oc": "4500555861", "estado": "BORRADOR",
                "creado": ahora, "actualizado": ahora, "usuario": "prueba",
            })
        eventos = _contar(self.con, "SELECT COUNT(*) FROM evento")
        self.assertGreaterEqual(eventos, 3)
        intentos = [
            ("DELETE FROM evento", ()),
            ("UPDATE evento SET usuario = 'otro'", ()),
            ("DELETE FROM expediente WHERE id = ?", (id_exp,)),
            ("DELETE FROM oc WHERE numero = ?", ("4500555861",)),
        ]
        for sql, parametros in intentos:
            with self.subTest(sql=sql):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.con.execute(sql, parametros)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM evento"), eventos)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM evento WHERE usuario = 'otro'"), 0)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM expediente WHERE id = ?", (id_exp,)), 1)
        self.assertEqual(_contar(self.con, "SELECT COUNT(*) FROM oc WHERE numero = '4500555861'"), 1)

    def test_backup_conserva_30(self):
        carpeta = self.entorno.dir / "datos" / "backups"
        inicio = datetime(2026, 1, 1, 8, 0, 0)
        for i in range(31):
            db.hacer_backup(self.ruta, carpeta, conservar=30, ahora=inicio + timedelta(minutes=i))
        archivos = sorted(p.name for p in carpeta.iterdir())
        self.assertEqual(len(archivos), 30)
        for nombre in archivos:
            self.assertRegex(nombre, r"^expedientes-\d{8}-\d{6}\.db$")
        self.assertNotIn("expedientes-20260101-080000.db", archivos)
        self.assertEqual(archivos[0], "expedientes-20260101-080100.db")
        self.assertEqual(archivos[-1], "expedientes-20260101-083000.db")
        self.assertEqual(db.ultimo_backup(carpeta).name, "expedientes-20260101-083000.db")


class PruebaBaseServidor(ayudas.CasoConServidor):

    def test_salud_informa_db_ok_y_estado_de_base(self):
        salud = self.servidor.get("/api/salud").json()
        self.assertEqual(salud["db"], "ok")
        resp = self.servidor.get("/api/base/estado")
        self.assertEqual(resp.estado, 200)
        datos = resp.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["datos"]["integridad"], "ok")
        self.assertIsNone(datos["datos"]["ultimo_backup"])

    def test_restaurar_ultimo_backup(self):
        ruta = self.entorno.ruta_base
        carpeta = self.entorno.dir / "datos" / "backups"
        sin_backups = self.servidor.post("/api/base/restaurar", {})
        self.assertEqual(sin_backups.estado, 422)
        self.assertEqual(sin_backups.json(), {
            "ok": False,
            "error": {"codigo": "negocio", "mensaje": "No hay copias de seguridad para restaurar."},
        })

        con = db.conectar(ruta)
        try:
            with db.transaccion(con):
                db.insertar(con, "proveedor", {"sap": "77170", "razon_social": "GRUPO EFIA S.R.L."})
        finally:
            con.close()
        backup = db.hacer_backup(ruta, carpeta, conservar=30)

        con = db.conectar(ruta)
        try:
            with db.transaccion(con):
                db.actualizar_con_version(con, "proveedor", {"sap": "77170"}, 1, {"razon_social": "CAMBIADO"})
        finally:
            con.close()

        resp = self.servidor.post("/api/base/restaurar", {})
        self.assertEqual(resp.estado, 200, resp.texto())
        self.assertEqual(resp.json(), {"ok": True, "datos": {"restaurado": backup.name}})

        con = db.conectar(ruta)
        try:
            fila = db.leer_fila(con, "proveedor", {"sap": "77170"})
            self.assertEqual(fila["razon_social"], "GRUPO EFIA S.R.L.")
            self.assertEqual(fila["version"], 1)
            evento = con.execute("SELECT * FROM evento WHERE accion = 'RESTAURACION'").fetchone()
            self.assertIsNotNone(evento)
            self.assertEqual(json.loads(evento["clave"]), {"backup": backup.name})
        finally:
            con.close()
        estado = self.servidor.get("/api/base/estado").json()["datos"]
        self.assertEqual(estado["ultimo_backup"], backup.name)
        self.assertEqual(estado["integridad"], "ok")


if __name__ == "__main__":
    unittest.main()
