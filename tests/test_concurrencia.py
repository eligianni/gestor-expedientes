"""Paso 31 (TX.3): dos procesos escribiendo la misma base SQLite, como dos usuarias sobre la unidad de red."""
import multiprocessing
import queue
import unittest

from gestor import db
from tests import ayudas, datos_prueba

OC = datos_prueba.OC_EFIA_MANUAL["numero"]
ESPERA = 60


# Las funciones que corren en los procesos hijos van a nivel de módulo: Windows usa "spawn".

def escribir_proveedores(ruta, prefijo, n, cola):
    """Inserta n proveedores (SAP <prefijo><i>), cada uno en su propia transacción corta BEGIN IMMEDIATE."""
    con = db.conectar(ruta)
    try:
        for i in range(n):
            with db.transaccion(con):
                db.insertar(con, "proveedor", {"sap": "%s%03d" % (prefijo, i), "razon_social": "PROVEEDOR %s %d" % (prefijo, i)})
        cola.put(("ok", prefijo))
    except Exception as error:  # el resultado vuelve al proceso de la prueba
        cola.put(("error", "%s: %s" % (type(error).__name__, error)))
    finally:
        con.close()


def actualizar_misma_oc(ruta, version, barrera, cola):
    """Espera al otro proceso y actualiza la misma OC con la misma versión esperada."""
    con = db.conectar(ruta)
    try:
        barrera.wait(timeout=ESPERA)
        with db.transaccion(con):
            db.actualizar_con_version(con, "oc", {"numero": OC}, version, {"objeto": "editada por %s" % multiprocessing.current_process().name})
        cola.put("ok")
    except db.ConflictoVersion:
        cola.put("ConflictoVersion")
    except Exception as error:
        cola.put("%s: %s" % (type(error).__name__, error))
    finally:
        con.close()


class PruebaConcurrencia(ayudas.CasoConEntorno):

    def setUp(self):
        super().setUp()
        self.ruta = str(self.entorno.ruta_base)
        db.inicializar(self.ruta, self.entorno.config["parametros_iniciales"])
        self.contexto = multiprocessing.get_context("spawn")

    def _correr(self, procesos, cola):
        for proceso in procesos:
            proceso.start()
        resultados = [cola.get(timeout=ESPERA) for _ in procesos]
        for proceso in procesos:
            proceso.join(timeout=ESPERA)
            self.assertFalse(proceso.is_alive(), "un proceso no terminó a tiempo")
            self.assertEqual(proceso.exitcode, 0)
        return resultados

    def _contar(self, sql, *valores):
        con = db.conectar(self.ruta)
        try:
            return con.execute(sql, valores).fetchone()[0]
        finally:
            con.close()

    def test_dos_procesos_sin_perdidas(self):
        cola = self.contexto.Queue()
        procesos = [self.contexto.Process(target=escribir_proveedores, args=(self.ruta, prefijo, 50, cola))
                    for prefijo in ("91", "92")]
        resultados = self._correr(procesos, cola)
        self.assertEqual(sorted(resultados), [("ok", "91"), ("ok", "92")])
        self.assertEqual(self._contar("SELECT COUNT(*) FROM proveedor"), 100)
        self.assertEqual(self._contar("SELECT COUNT(*) FROM evento WHERE accion = 'ALTA'"), 100)
        self.assertEqual(self._contar("SELECT COUNT(*) FROM evento WHERE accion = 'ALTA' AND tabla = 'proveedor'"), 100)

    def test_dos_procesos_un_conflicto(self):
        con = db.conectar(self.ruta)
        try:
            datos_prueba.cargar_efia(con)
            version = db.leer_fila(con, "oc", {"numero": OC})["version"]
        finally:
            con.close()
        self.assertEqual(version, 1)
        modificaciones_antes = self._contar(
            "SELECT COUNT(*) FROM evento WHERE accion = 'MODIFICACION' AND tabla = 'oc'")
        cola = self.contexto.Queue()
        barrera = self.contexto.Barrier(2)
        procesos = [self.contexto.Process(target=actualizar_misma_oc, args=(self.ruta, 1, barrera, cola), name="usuaria-%d" % i)
                    for i in (1, 2)]
        resultados = self._correr(procesos, cola)
        self.assertEqual(sorted(resultados), ["ConflictoVersion", "ok"])
        self.assertEqual(self._contar("SELECT version FROM oc WHERE numero = ?", OC), 2)
        self.assertEqual(self._contar("SELECT COUNT(*) FROM evento WHERE accion = 'MODIFICACION' AND tabla = 'oc'")
                         - modificaciones_antes, 1)
        self.assertEqual(modificaciones_antes, 0)


if __name__ == "__main__":
    unittest.main()
