"""Copia de seguridad diaria: una por día en backups/diarios, aparte de las de cada arranque."""
from datetime import datetime, timedelta

import app
from gestor import db
from tests import ayudas


class PruebaBackupDiario(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.ruta = self.entorno.ruta_base
        db.inicializar(self.ruta, {})
        self.carpeta = self.entorno.dir / "datos" / "backups"

    def test_una_por_dia(self):
        manana = datetime(2026, 11, 19, 8, 0, 0)
        primera = db.backup_diario(self.ruta, self.carpeta, ahora=manana)
        self.assertEqual(primera.name, "expedientes-20261119-080000.db")
        self.assertEqual(primera.parent.name, "diarios")
        self.assertIsNone(db.backup_diario(self.ruta, self.carpeta, ahora=manana + timedelta(hours=10)))
        siguiente = db.backup_diario(self.ruta, self.carpeta, ahora=manana + timedelta(days=1, minutes=1))
        self.assertEqual(siguiente.name, "expedientes-20261120-080100.db")
        self.assertEqual(db.ultimo_backup_diario(self.carpeta).name, "expedientes-20261120-080100.db")

    def test_conserva_los_ultimos_dias_y_no_se_mezcla_con_las_de_arranque(self):
        inicio = datetime(2026, 1, 1, 9, 0, 0)
        for dia in range(5):
            db.backup_diario(self.ruta, self.carpeta, conservar=3, ahora=inicio + timedelta(days=dia))
        diarios = sorted(p.name for p in (self.carpeta / "diarios").iterdir())
        self.assertEqual(diarios, ["expedientes-20260103-090000.db", "expedientes-20260104-090000.db",
                                   "expedientes-20260105-090000.db"])
        # Restaurar usa solo las copias de arranque: las diarias no cuentan como "última copia".
        self.assertIsNone(db.ultimo_backup(self.carpeta))
        for minuto in range(4):
            db.hacer_backup(self.ruta, self.carpeta, conservar=2, ahora=inicio + timedelta(minutes=minuto))
        self.assertEqual(len(list((self.carpeta / "diarios").iterdir())), 3)

    def test_app_hace_la_copia_del_dia_con_la_config(self):
        cfg = dict(self.entorno.config, _dir=str(self.entorno.dir), backups_diarios_a_conservar=10)
        primera = app._backup_diario(cfg)
        self.assertIsNotNone(primera)
        self.assertTrue(primera.is_file())
        self.assertIsNone(app._backup_diario(cfg))

    def test_estado_de_la_base_informa_la_copia_diaria(self):
        servidor = ayudas.ServidorDePrueba()
        self.addCleanup(servidor.cerrar)
        self.assertIsNone(servidor.get("/api/base/estado").json()["datos"]["ultimo_backup_diario"])
        db.backup_diario(self.ruta, self.carpeta, ahora=datetime(2026, 11, 19, 8, 0, 0))
        self.assertEqual(servidor.get("/api/base/estado").json()["datos"]["ultimo_backup_diario"],
                         "expedientes-20261119-080000.db")
