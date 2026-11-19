"""Capa de datos SQLite: esquema, conexión, transacciones, versión optimista, auditoría y backups.

Único módulo que llama a sqlite3.connect. Ver .claude/rules/base-de-datos.md.
"""
import getpass
import json
import re
import socket
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Copia literal del bloque "Schema" de blueprint.md §4 (no cambiar una letra).
ESQUEMA = """\
-- gestor/db.py :: ESQUEMA  (PRAGMA user_version = 1)
-- Montos: INTEGER en centavos. Cantidades: TEXT con str(Decimal). Fechas: TEXT 'AAAA-MM-DD'.
-- JSON: TEXT con json.dumps(..., ensure_ascii=False, sort_keys=True).

CREATE TABLE IF NOT EXISTS config (
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS proveedor (
  sap TEXT PRIMARY KEY,
  razon_social TEXT NOT NULL,
  cuit TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  notas TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS oc (
  numero TEXT PRIMARY KEY,
  efector TEXT NOT NULL CHECK (efector IN ('HBI', 'CASPH')),
  sap TEXT NOT NULL REFERENCES proveedor (sap),
  clase TEXT NOT NULL DEFAULT '',
  org_compras TEXT NOT NULL DEFAULT '',
  centro TEXT NOT NULL DEFAULT '',
  ca TEXT NOT NULL DEFAULT '',
  expediente_contratacion TEXT NOT NULL DEFAULT '',
  fecha_oc TEXT,
  vig_desde TEXT,
  vig_hasta TEXT,
  prorroga TEXT,
  tipo TEXT NOT NULL DEFAULT 'SERVICIO' CHECK (tipo IN ('SERVICIO', 'BIEN', 'PROVISION')),
  comodato INTEGER NOT NULL DEFAULT 0 CHECK (comodato IN (0, 1)),
  centralizada INTEGER NOT NULL DEFAULT 0 CHECK (centralizada IN (0, 1)),
  objeto TEXT NOT NULL DEFAULT '',
  objeto_articulo TEXT NOT NULL DEFAULT 'al' CHECK (objeto_articulo IN ('al', 'a la', 'a los', 'a las')),
  concepto_corto TEXT NOT NULL DEFAULT '',
  dia_inicio_periodo INTEGER NOT NULL DEFAULT 1 CHECK (dia_inicio_periodo BETWEEN 1 AND 28),
  gde_pdf_oc TEXT NOT NULL DEFAULT '',
  leyenda_cv TEXT NOT NULL DEFAULT '',
  extras_cv TEXT NOT NULL DEFAULT '{}',
  doc_requerida_central TEXT NOT NULL DEFAULT '[]',
  origen TEXT NOT NULL DEFAULT 'SAP' CHECK (origen IN ('SAP', 'MANUAL')),
  cerrada_sap INTEGER NOT NULL DEFAULT 0 CHECK (cerrada_sap IN (0, 1)),
  excluida INTEGER NOT NULL DEFAULT 0 CHECK (excluida IN (0, 1)),
  motivo_exclusion TEXT NOT NULL DEFAULT '',
  campos_manuales TEXT NOT NULL DEFAULT '[]',
  ultima_importacion TEXT,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS renglon (
  oc TEXT NOT NULL REFERENCES oc (numero),
  pos INTEGER NOT NULL,
  codigo TEXT NOT NULL DEFAULT '',
  descripcion TEXT NOT NULL DEFAULT '',
  cantidad TEXT NOT NULL DEFAULT '0',
  unidad TEXT NOT NULL DEFAULT '',
  precio_centavos INTEGER NOT NULL DEFAULT 0,
  importe_centavos INTEGER NOT NULL DEFAULT 0,
  partida TEXT NOT NULL DEFAULT '',
  sap_entregado TEXT NOT NULL DEFAULT '0',
  sap_facturado TEXT NOT NULL DEFAULT '0',
  sap_por_entregar TEXT NOT NULL DEFAULT '0',
  consumo_previo TEXT NOT NULL DEFAULT '0',
  desglose_cantidad TEXT,
  desglose_unidad TEXT,
  desglose_precio_centavos INTEGER,
  revisar_desglose INTEGER NOT NULL DEFAULT 0 CHECK (revisar_desglose IN (0, 1)),
  exceso_sap INTEGER NOT NULL DEFAULT 0 CHECK (exceso_sap IN (0, 1)),
  revisar_importe INTEGER NOT NULL DEFAULT 0 CHECK (revisar_importe IN (0, 1)),
  es_correctivo INTEGER NOT NULL DEFAULT 0 CHECK (es_correctivo IN (0, 1)),
  campos_manuales TEXT NOT NULL DEFAULT '[]',
  crudo TEXT NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (oc, pos)
);

CREATE TABLE IF NOT EXISTS entrega (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  efector TEXT NOT NULL CHECK (efector IN ('HBI', 'CASPH')),
  numero INTEGER NOT NULL,
  nombre TEXT NOT NULL DEFAULT '',
  fecha_envio TEXT,
  estado TEXT NOT NULL DEFAULT 'ABIERTA' CHECK (estado IN ('ABIERTA', 'ENVIADA')),
  observaciones TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (efector, numero)
);

CREATE TABLE IF NOT EXISTS expediente (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL CHECK (tipo IN ('COMUN', 'CENTRALIZADA', 'CORRECTIVO', 'EVENTUAL')),
  efector TEXT NOT NULL CHECK (efector IN ('HBI', 'CASPH')),
  oc TEXT REFERENCES oc (numero),
  sap TEXT NOT NULL DEFAULT '',
  periodo TEXT,
  periodo_desde TEXT,
  periodo_hasta TEXT,
  periodo_manual INTEGER NOT NULL DEFAULT 0 CHECK (periodo_manual IN (0, 1)),
  factura TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL,
  motivo_pendiente TEXT NOT NULL DEFAULT '',
  fecha_seguimiento TEXT,
  motivo_anulacion TEXT NOT NULL DEFAULT '',
  entrega_id INTEGER REFERENCES entrega (id),
  datos TEXT NOT NULL DEFAULT '{}',
  creado TEXT NOT NULL,
  actualizado TEXT NOT NULL,
  usuario TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS evento (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL,
  usuario TEXT NOT NULL,
  pc TEXT NOT NULL,
  accion TEXT NOT NULL CHECK (accion IN ('ALTA', 'MODIFICACION', 'ANULACION', 'IMPORTACION', 'RESTAURACION')),
  tabla TEXT NOT NULL,
  clave TEXT NOT NULL,
  antes TEXT,
  despues TEXT
);

CREATE TABLE IF NOT EXISTS importacion (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL,
  archivo TEXT NOT NULL,
  efector TEXT NOT NULL CHECK (efector IN ('HBI', 'CASPH')),
  usuario TEXT NOT NULL,
  informe TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_oc_efector ON oc (efector, excluida);
CREATE INDEX IF NOT EXISTS ix_oc_sap ON oc (sap);
CREATE INDEX IF NOT EXISTS ix_expediente_oc_periodo ON expediente (oc, periodo);
CREATE INDEX IF NOT EXISTS ix_expediente_estado ON expediente (estado, fecha_seguimiento);
CREATE INDEX IF NOT EXISTS ix_expediente_entrega ON expediente (entrega_id);
CREATE INDEX IF NOT EXISTS ix_expediente_factura ON expediente (factura);
CREATE INDEX IF NOT EXISTS ix_evento_tabla_clave ON evento (tabla, clave);

CREATE TRIGGER IF NOT EXISTS evento_sin_update BEFORE UPDATE ON evento
BEGIN SELECT RAISE(ABORT, 'evento es de solo agregado'); END;
CREATE TRIGGER IF NOT EXISTS evento_sin_delete BEFORE DELETE ON evento
BEGIN SELECT RAISE(ABORT, 'evento es de solo agregado'); END;
CREATE TRIGGER IF NOT EXISTS expediente_sin_delete BEFORE DELETE ON expediente
BEGIN SELECT RAISE(ABORT, 'los expedientes se anulan, no se borran'); END;
CREATE TRIGGER IF NOT EXISTS oc_sin_delete BEFORE DELETE ON oc
BEGIN SELECT RAISE(ABORT, 'las OC se excluyen, no se borran'); END;
"""


VERSION_ESQUEMA = 1
SQLITE_MINIMA = (3, 8, 3)

TABLAS = ("config", "proveedor", "oc", "renglon", "entrega", "expediente", "evento", "importacion")

# Lista blanca de nombres dinámicos: se llena al inicializar con PRAGMA table_info.
COLUMNAS = {}
_CLAVES_PRIMARIAS = {}

_PATRON_BACKUP = re.compile(r"expedientes-\d{8}-\d{6}\.db")


class ConflictoVersion(Exception):
    """La fila cambió desde que se leyó (control optimista de concurrencia)."""

    MENSAJE = "Otra persona guardó cambios en este registro. Recargá para ver la última versión."

    def __init__(self, mensaje=None):
        super().__init__(mensaje or self.MENSAJE)


class BaseNoDisponible(Exception):
    """No se puede abrir la base (SQLite demasiado viejo, archivo inaccesible, etc.)."""


# --- Conexión y esquema ----------------------------------------------------

def conectar(ruta):
    """Abre una conexión nueva (una por pedido HTTP; nunca se comparte entre threads)."""
    if sqlite3.sqlite_version_info < SQLITE_MINIMA:
        raise BaseNoDisponible(
            "La versión de SQLite (%s) es anterior a la mínima %s." % (sqlite3.sqlite_version, ".".join(map(str, SQLITE_MINIMA)))
        )
    con = sqlite3.connect(database=str(ruta), timeout=10, isolation_level=None)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA foreign_keys=ON")
    except Exception:
        con.close()
        raise
    return con


def _cargar_columnas(con):
    for tabla in TABLAS:
        info = con.execute("PRAGMA table_info(%s)" % tabla).fetchall()
        COLUMNAS[tabla] = tuple(fila["name"] for fila in info)
        pk = sorted((fila["pk"], fila["name"]) for fila in info if fila["pk"])
        _CLAVES_PRIMARIAS[tabla] = tuple(nombre for _, nombre in pk)


def _columnas(con, tabla):
    if tabla not in TABLAS:
        raise ValueError("Tabla desconocida: %s" % tabla)
    if tabla not in COLUMNAS:
        _cargar_columnas(con)
    return COLUMNAS[tabla]


def _validar_columnas(con, tabla, nombres):
    validas = _columnas(con, tabla)
    for nombre in nombres:
        if nombre not in validas:
            raise ValueError("Columna desconocida %s.%s" % (tabla, nombre))


def inicializar(ruta, parametros_iniciales):
    """Crea la base si falta (esquema, user_version, config sembrada). Idempotente."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = conectar(ruta)
    try:
        con.executescript(ESQUEMA)
        con.execute("PRAGMA user_version = %d" % VERSION_ESQUEMA)
        _cargar_columnas(con)
        with transaccion(con):
            existentes = {fila["clave"] for fila in con.execute("SELECT clave FROM config")}
            for clave, valor in (parametros_iniciales or {}).items():
                if clave not in existentes:
                    con.execute(
                        "INSERT INTO config (clave, valor) VALUES (?, ?)",
                        (clave, _json(valor)),
                    )
    finally:
        con.close()


@contextmanager
def transaccion(con):
    """BEGIN IMMEDIATE … COMMIT; ROLLBACK y re-lanza ante cualquier excepción.

    Si la conexión ya está dentro de una transacción, no abre otra: la externa decide.
    """
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


# --- Utilidades ------------------------------------------------------------

def ahora_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def _valor_columna(valor):
    """dict y list van a columnas JSON; el resto se guarda tal cual."""
    if isinstance(valor, (dict, list)):
        return _json(valor)
    return valor


def _fila_a_dict(fila):
    return None if fila is None else {clave: fila[clave] for clave in fila.keys()}


def _where(con, tabla, clave):
    if not clave:
        raise ValueError("Falta la clave del registro.")
    _validar_columnas(con, tabla, clave.keys())
    return " AND ".join("%s = ?" % nombre for nombre in clave), list(clave.values())


def leer_fila(con, tabla, clave):
    """Fila como dict (o None) buscando por las columnas de `clave`."""
    where, valores = _where(con, tabla, clave)
    return _fila_a_dict(con.execute("SELECT * FROM %s WHERE %s" % (tabla, where), valores).fetchone())


# --- Auditoría y escritura -------------------------------------------------

def registrar_evento(con, accion, tabla, clave, antes, despues):
    """Agrega una fila a `evento`; se llama dentro de la transacción del cambio."""
    con.execute(
        "INSERT INTO evento (fecha, usuario, pc, accion, tabla, clave, antes, despues) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ahora_utc(),
            getpass.getuser(),
            socket.gethostname(),
            accion,
            tabla,
            _json(clave),
            None if antes is None else _json(antes),
            None if despues is None else _json(despues),
        ),
    )


def insertar(con, tabla, fila):
    """INSERT validado contra COLUMNAS + evento ALTA; devuelve lastrowid."""
    if tabla == "evento":
        raise ValueError("evento se escribe solo con registrar_evento.")
    _validar_columnas(con, tabla, fila.keys())
    nombres = list(fila.keys())
    cursor = con.execute(
        "INSERT INTO %s (%s) VALUES (%s)" % (tabla, ", ".join(nombres), ", ".join("?" for _ in nombres)),
        [_valor_columna(fila[n]) for n in nombres],
    )
    rowid = cursor.lastrowid
    pk = _CLAVES_PRIMARIAS.get(tabla) or ()
    if pk and all(nombre in fila for nombre in pk):
        clave = {nombre: fila[nombre] for nombre in pk}
    elif len(pk) == 1:
        clave = {pk[0]: rowid}
    else:
        clave = {"rowid": rowid}
    if "rowid" in clave:
        despues = _fila_a_dict(con.execute("SELECT * FROM %s WHERE rowid = ?" % tabla, (rowid,)).fetchone())
    else:
        despues = leer_fila(con, tabla, clave)
    registrar_evento(con, "ALTA", tabla, clave, None, despues)
    return rowid


def actualizar_con_version(con, tabla, clave, version_esperada, cambios, accion="MODIFICACION"):
    """UPDATE … SET cambios, version = version + 1 WHERE clave AND version = ?; evento `accion` (MODIFICACION por defecto).

    rowcount 0 → ConflictoVersion sin escribir nada. El llamador envuelve todo en `transaccion`.
    """
    if not cambios:
        raise ValueError("No hay cambios para guardar.")
    if "version" in cambios:
        raise ValueError("La versión no se cambia a mano.")
    _validar_columnas(con, tabla, cambios.keys())
    where, valores_where = _where(con, tabla, clave)
    antes = leer_fila(con, tabla, clave)
    nombres = list(cambios.keys())
    cursor = con.execute(
        "UPDATE %s SET %s, version = version + 1 WHERE %s AND version = ?"
        % (tabla, ", ".join("%s = ?" % n for n in nombres), where),
        [_valor_columna(cambios[n]) for n in nombres] + valores_where + [version_esperada],
    )
    if cursor.rowcount == 0:
        raise ConflictoVersion()
    despues = leer_fila(con, tabla, clave)
    registrar_evento(con, accion, tabla, clave, antes, despues)
    return despues


# --- Parámetros compartidos (tabla config) ---------------------------------

def leer_parametros(con):
    return {fila["clave"]: json.loads(fila["valor"]) for fila in con.execute("SELECT clave, valor FROM config ORDER BY clave")}


def versiones_parametros(con):
    """clave → version de cada parámetro compartido (para el control optimista desde la interfaz)."""
    return {fila["clave"]: fila["version"] for fila in con.execute("SELECT clave, version FROM config ORDER BY clave")}


def listar_importaciones(con):
    """Historial de importaciones, la más nueva primero (sin el informe completo)."""
    filas = con.execute("SELECT id, fecha, archivo, efector, usuario FROM importacion ORDER BY id DESC")
    return [_fila_a_dict(fila) for fila in filas]


def guardar_parametro(con, clave, valor, version_esperada):
    with transaccion(con):
        actualizar_con_version(con, "config", {"clave": clave}, version_esperada, {"valor": _json(valor)})


def verificar_integridad(con):
    fila = con.execute("PRAGMA integrity_check").fetchone()
    return fila is not None and fila[0] == "ok"


# --- Copias de seguridad ---------------------------------------------------

def _copiar_base(origen, destino):
    """Copia `origen` sobre `destino` con la API backup de sqlite3."""
    con_origen = conectar(origen)
    try:
        con_destino = sqlite3.connect(database=str(destino), timeout=10, isolation_level=None)
        try:
            con_origen.backup(con_destino)
        finally:
            con_destino.close()
    finally:
        con_origen.close()


def _backups(carpeta):
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.iterdir() if p.is_file() and _PATRON_BACKUP.fullmatch(p.name))


def hacer_backup(ruta_base, carpeta, conservar=30, ahora=None):
    """Copia la base a expedientes-AAAAMMDD-HHMMSS.db y deja solo los `conservar` más nuevos."""
    ruta_base = Path(ruta_base)
    if not ruta_base.is_file():
        raise FileNotFoundError("No existe la base %s" % ruta_base)
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora = ahora or datetime.now()
    destino = carpeta / ("expedientes-%s.db" % ahora.strftime("%Y%m%d-%H%M%S"))
    _copiar_base(ruta_base, destino)
    existentes = _backups(carpeta)
    for viejo in existentes[: max(0, len(existentes) - conservar)]:
        viejo.unlink()
    return destino


CARPETA_DIARIOS = "diarios"


def backup_diario(ruta_base, carpeta, conservar=90, ahora=None):
    """Una copia por día en <carpeta>/diarios; si ya hay una de hoy no hace nada y devuelve None.

    Va aparte de las copias de cada arranque para que esas (que rotan rápido) no se lleven las diarias.
    """
    ahora = ahora or datetime.now()
    diarios = Path(carpeta) / CARPETA_DIARIOS
    prefijo = "expedientes-%s-" % ahora.strftime("%Y%m%d")
    if any(p.name.startswith(prefijo) for p in _backups(diarios)):
        return None
    return hacer_backup(ruta_base, diarios, conservar, ahora)


def ultimo_backup_diario(carpeta):
    return ultimo_backup(Path(carpeta) / CARPETA_DIARIOS)


def ultimo_backup(carpeta):
    existentes = _backups(carpeta)
    return existentes[-1] if existentes else None


def restaurar_backup(ruta_backup, ruta_base):
    """Copia el backup sobre la base y registra RESTAURACION en la base restaurada."""
    ruta_backup = Path(ruta_backup)
    _copiar_base(ruta_backup, ruta_base)
    con = conectar(ruta_base)
    try:
        with transaccion(con):
            registrar_evento(con, "RESTAURACION", "config", {"backup": ruta_backup.name}, None, None)
    finally:
        con.close()
