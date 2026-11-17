# Epic 01: Núcleo y órdenes de compra

> Existe el programa que arranca con doble función (servidor + `--check`), la base SQLite auditada con backups, el importador de z_compras2 y la gestión de OC.

| | |
|---|---|
| **Epic id** | `01-nucleo-y-oc` |
| **Tasks** | `E1-T1` … `E1-T8` (pasos 1–8 de `blueprint.md` §9) |
| **Depends on** | nada — empezar acá |
| **Unlocks** | `02-expediente-comun` |
| **Parallel with** | ninguno (es la base de todo) |

No necesitás ningún otro archivo para completar este epic. Todo lo de abajo se repite acá a propósito.

---

## Stack

Python ≥ 3.10 (probado en 3.14) · **solo biblioteca estándar** · servidor `http.server.ThreadingHTTPServer` en 127.0.0.1 ·
SQLite (`sqlite3`) en `datos/expedientes.db` o en la ruta de `config.json` · interfaz HTML/CSS/JS sin framework en `web/` ·
Excel y Word con `zipfile` + `xml.etree.ElementTree` · tests con `unittest`. No hay gestor de paquetes ni archivo de
dependencias: **nunca** `pip install`. Los comandos se corren en Git Bash desde la raíz del proyecto.

| Tarea | Comando |
|---|---|
| Arrancar | `python app.py` · sin navegador: `python app.py --no-browser --port 8765` |
| Prueba de humo del entry point | `python app.py --check` (imprime el JSON de `/api/salud` y sale 0) |
| Test de un módulo | `python -W error::DeprecationWarning -m unittest tests.test_<modulo> -v` |
| Todos los tests | `python -W error::DeprecationWarning -m unittest discover -s tests -t .` |
| Formato/lint | `python -m compileall -q app.py gestor tests` |

**Gate:** `python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`
salen 0 antes de marcar cualquier tarea como hecha. No hay servicios externos: la base es un archivo y los tests usan una base
temporal (`tests/ayudas.py` apunta `GESTOR_CONFIG` a un directorio temporal).

## Directory subtree

Solo lo que toca este epic:

```
app.py                      # NUEVO (paso 1) — entry point: --check, --no-browser, --port
config.json                 # existe (workspace) — solo lectura en este epic
gestor/
  __init__.py               # NUEVO — APP_ID, __version__
  config.py                 # NUEVO — carga config.json / GESTOR_CONFIG
  server.py                 # NUEVO, luego editado — rutas HTTP
  db.py                     # NUEVO (paso 2) — esquema, transacciones, versión, auditoría, backups
  util.py                   # NUEVO (paso 3) — fechas, períodos, montos, GDE, factura
  letras.py                 # NUEVO (paso 3) — importe en letras
  xlsx.py                   # NUEVO (paso 4) — lector .xlsx
  importar.py               # NUEVO (paso 5), editado (paso 6)
  negocio.py                # NUEVO (paso 8) — reglas de OC
web/
  index.html  app.js  style.css   # NUEVOS (paso 7), app.js editado (paso 8)
tests/
  __init__.py  ayudas.py    # existen (workspace) — no se editan
  datos_prueba.py           # NUEVO (paso 8) — datos reales reutilizables
  test_servidor.py test_db.py test_util.py test_letras.py test_xlsx.py
  test_importar.py test_desglose.py test_web_importar.py test_oc.py   # NUEVOS
  fixtures/xlsx/*.xlsx      # provistos — solo lectura
```

Todo lo que está fuera de este árbol queda fuera de alcance. Si una tarea parece exigir editar otro archivo, parar y reportarlo.

## Data model touched here

Este epic crea el esquema completo (paso 2, `gestor/db.py` → `ESQUEMA`). DDL literal:

```sql
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
```

## Contracts

**Consumed** — ya existe, no reconstruir:

| From | Interface | Guarantee |
|---|---|---|
| Bootstrap (§10) | `config.json`, `tests/ayudas.py` | `ayudas.EntornoTemporal` crea config y base temporales; `ayudas.ServidorDePrueba` llama `gestor.server.crear_servidor(0, gestor.config.cargar_config())` |

**Produced** — los epics siguientes dependen de estas firmas exactas:

| Export | Signature | Used by |
|---|---|---|
| `gestor/config.py` → `cargar_config`, `ruta` | `cargar_config() -> dict`; `ruta(cfg, clave) -> Path` | todos |
| `gestor/server.py` → `crear_servidor` | `crear_servidor(puerto: int, cfg: dict) -> ThreadingHTTPServer` | todos los tests HTTP |
| `gestor/db.py` → `conectar`, `transaccion`, `insertar`, `actualizar_con_version`, `ConflictoVersion`, `registrar_evento`, `leer_parametros` | ver paso 2 | `02`–`05` |
| `gestor/util.py` → `periodo_de_fecha`, `a_centavos`, `formato_pesos`, `normalizar_factura`, `misma_factura`, `normalizar_gde`, `validar_gde`, `mm_aa` | ver paso 3 | `02`–`05` |
| `gestor/letras.py` → `importe_en_letras`, `letras_con_centavos`, `numero_a_letras` | ver paso 3 | `03`, `05` |
| `gestor/xlsx.py` → `leer_filas`, `leer_tabla` | ver paso 4 | `04` (roundtrip) |
| `gestor/negocio.py` → `ficha_oc`, `crear_oc_manual`, `actualizar_oc`, `ErrorValidacion`, `ErrorNegocio` | ver paso 8 | `02`–`05` |
| `tests/datos_prueba.py` → `OC_EFIA_MANUAL`, `cargar_efia`, `importar_hbi_2026`, `preparar_biofab`, `preparar_macatex` | ver paso 8 | `02`–`05` |

## Conventions that bite in this area

- El importador busca columnas por **nombre normalizado** (`util.clave_encabezado`), nunca por posición: los dos reportes reales tienen columnas en distinto orden.
- `N° O/C` usa el signo de grado (U+00B0); `clave_encabezado` lo deja como `n o c`.
- El lector xlsx devuelve texto: los números de OC y SAP nunca pasan por `float` (perderían ceros o dígitos).
- Cada pedido HTTP abre y cierra su propia conexión: `ThreadingHTTPServer` atiende en varios threads.
- Montos en centavos `int` (y `Decimal` para cantidades); nunca `float`. Formato `1.224.990,00` solo con `util.formato_pesos`.
- `sqlite3.connect` solo en `gestor/db.py`, con keywords; toda escritura en `with db.transaccion(con):` con versión y evento.
- Fechas en la base como `AAAA-MM-DD` (texto). Nada de `datetime.utcnow()` ni `datetime.UTC`: `datetime.now(timezone.utc)`.
- Compatibilidad 3.10: sin `ExceptionGroup`/`except*`, sin `typing.Self`, sin `tomllib`, sin `cgi`, sin `sqlite3.connect(autocommit=...)`.
- Los tests corren con `-W error::DeprecationWarning`: una API deprecada rompe el gate.
- No tocar `plantillas/*.docx`, `tests/fixtures/**`, `tests/ayudas.py`, `config.json` (salvo que la tarea lo diga), ni nada bajo `blueprints/`.

Reglas completas: `CLAUDE.md`. Reglas por área: `.claude/rules/base-de-datos.md`, `.claude/rules/textos-y-documentos.md`, `.claude/rules/interfaz-web.md`. Están en la raíz del proyecto: Bootstrap (§10 de `blueprint.md`) las copió desde `workspace/` antes de la primera tarea.

---

## Tasks

En el mismo orden que `tasks.json`. Ese orden es el orden de construcción: de arriba hacia abajo, sin reordenar por prioridad.

### `E1-T1` — Entry point app.py, servidor y /api/salud con --check

**Depends on:** nada · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

Crear el entry point ejecutable y el servidor HTTP mínimo. Bootstrap (§10) ya dejó en la raíz
`config.json`, `.gitignore`, `tests/__init__.py`, `tests/ayudas.py`, `plantillas/` y `tests/fixtures/`:
no se reescriben. `tests/ayudas.py` define el contrato que este paso implementa
(`gestor.config.cargar_config()` y `gestor.server.crear_servidor(puerto, cfg)`).

1. `gestor/__init__.py` — exactamente:
   ```python
   """Gestor de expedientes de pago (HBI / CASPH)."""
   APP_ID = "gestor-expedientes"
   __version__ = "0.1.0"
   ```
2. `gestor/config.py`:
   - `RAIZ = Path(__file__).resolve().parent.parent`
   - `class ConfigError(Exception)`
   - `ruta_config() -> Path`: `Path(os.environ["GESTOR_CONFIG"])` si la variable existe y no está vacía; si no `RAIZ / "config.json"`.
   - `cargar_config() -> dict`: lee el JSON (UTF-8); si no existe lanza `ConfigError("No se encontró el archivo de configuración: <ruta>")`; agrega `cfg["_ruta"] = str(ruta)` y `cfg["_dir"] = str(ruta.parent)`.
   - `ruta(cfg, clave) -> Path`: `Path(cfg[clave])` si es absoluta; si no, `Path(cfg["_dir"]) / cfg[clave]` (sirve para `base_datos`, `carpeta_backups`, `carpeta_salidas`).
   - `guardar_config(cfg) -> None`: escribe sin las claves que empiezan con `_`, con `json.dump(..., ensure_ascii=False, indent=2)` y `"\n"` final.
3. `gestor/server.py`:
   - `class Manejador(http.server.BaseHTTPRequestHandler)` con `do_GET`, `do_POST`, `do_PUT`; despacha con la lista
     `RUTAS = [(metodo, re.compile(patron), funcion), ...]`; cada `funcion(h, m, cuerpo)` devuelve `(estado_http, dict)`.
   - `responder_json(h, estado, dic)`: `Content-Type: application/json; charset=utf-8`, cuerpo
     `json.dumps(dic, ensure_ascii=False).encode("utf-8")` (separadores por defecto: `", "` y `": "`).
   - `log_message` no escribe nada (con `pythonw` no hay consola).
   - `GET /api/salud` → 200 con, en este orden de claves:
     `{"app": "gestor-expedientes", "version": "0.1.0", "db": <"ok"|"sin_base">, "usuario": getpass.getuser()}`.
     En este paso `db` = `"ok"` si el archivo `config.ruta(cfg, "base_datos")` existe, si no `"sin_base"`.
   - Ruta inexistente → 404 `{"ok": false, "error": {"codigo": "no_encontrado", "mensaje": "Ruta no encontrada: <ruta>"}}`.
     Excepción no prevista → 500 `{"ok": false, "error": {"codigo": "interno", "mensaje": "Error interno: <NombreDeLaExcepcion>"}}`.
   - `crear_servidor(puerto: int, cfg: dict) -> http.server.ThreadingHTTPServer`: enlaza `("127.0.0.1", puerto)`,
     `daemon_threads = True`, guarda `httpd.cfg = cfg`. Puerto 0 = el sistema elige.
   - `consultar_salud(puerto, timeout=0.5) -> dict | None`: GET `http://127.0.0.1:<puerto>/api/salud` con `urllib`; `None` ante cualquier error.
   - `class SinPuertoLibre(Exception)`; `elegir_puerto(preferido, maximo) -> tuple[int, bool]`: para cada puerto del rango,
     si `consultar_salud` devuelve `app == "gestor-expedientes"` → `(puerto, True)`; si no, intenta `socket.bind(("127.0.0.1", puerto))`
     y si lo logra lo cierra y devuelve `(puerto, False)`; si nada sirve lanza `SinPuertoLibre`.
4. `app.py` — `main(argv=None) -> int` con `argparse`: `--no-browser`, `--port N` (int), `--check`.
   - `--check`: `crear_servidor(0, cfg)` en un thread, GET `/api/salud`, imprime **una línea** `json.dumps(salud)`
     (ASCII, para no romper consolas cp1252), `shutdown()`, devuelve 0 si `salud["app"] == "gestor-expedientes"`, si no 1.
     No abre navegador ni hace backup.
   - Normal: `(p, ya) = elegir_puerto(args.port or cfg["puerto_preferido"], args.port or cfg["puerto_maximo"])`;
     si `ya` abre `http://127.0.0.1:<p>/` con `webbrowser` y devuelve 0; si no crea el servidor, abre el navegador
     con `threading.Timer(0.5, ...)` salvo `--no-browser`, y `serve_forever()` hasta `KeyboardInterrupt`. En modo normal no imprime nada.
   - `if __name__ == "__main__": sys.exit(main())`.
5. `tests/test_servidor.py` — clases y métodos exactos:
   - `PruebaServidor(ayudas.CasoConServidor)`: `test_salud_devuelve_json_del_gestor` (200; `list(json.keys()) == ["app", "version", "db", "usuario"]`;
     `app`, `version`, `db in ("ok", "sin_base")`, `usuario == getpass.getuser()`), `test_servidor_escucha_solo_en_localhost`,
     `test_ruta_inexistente_devuelve_404_con_sobre_de_error`.
   - `PruebaPuertos(ayudas.CasoConEntorno)`: `test_elegir_puerto_saltea_puerto_ocupado_por_otra_app` (ocupa un puerto con un
     socket en `listen()` y afirma que `elegir_puerto(p, p + 5)` devuelve otro puerto y `False`),
     `test_elegir_puerto_detecta_gestor_ya_corriendo` (con `ayudas.ServidorDePrueba()` levantado, `elegir_puerto(p, p) == (p, True)`).
   - `PruebaCheck(ayudas.CasoConEntorno)`: `test_check_imprime_salud_y_sale_0` (`subprocess.run([sys.executable, str(ayudas.RAIZ / "app.py"), "--check"], capture_output=True, text=True, timeout=60)`
     → `returncode == 0` y `json.loads(stdout.strip())["app"] == "gestor-expedientes"`).

**Files**

- `app.py` — nuevo: entry point con --check, --no-browser, --port
- `gestor/__init__.py` — nuevo: APP_ID y __version__
- `gestor/config.py` — nuevo: carga de config.json / GESTOR_CONFIG
- `gestor/server.py` — nuevo: ThreadingHTTPServer, /api/salud, elegir_puerto
- `tests/test_servidor.py` — nuevo: 6 pruebas del servidor y del entry point

**Acceptance**

1. **WHEN** `python app.py --check` runs from the project root **THE SYSTEM SHALL** start the server on a free port of 127.0.0.1, request `/api/salud`, print one JSON line containing `"app": "gestor-expedientes"` and `"version": "0.1.0"`, shut the server down and exit 0.
2. **WHEN** `GET /api/salud` is requested **THE SYSTEM SHALL** answer 200 with a JSON object whose keys are exactly `app`, `version`, `db`, `usuario` in that order, `db` being `ok` or `sin_base` and `usuario` equal to `getpass.getuser()`.
3. **WHEN** a route that does not exist is requested **THE SYSTEM SHALL** answer 404 with the body `{"ok": false, "error": {"codigo": "no_encontrado", "mensaje": "Ruta no encontrada: <ruta>"}}`.
4. **WHEN** the preferred port is already held by another program **THE SYSTEM SHALL** return the next bindable port of the range from `elegir_puerto` together with `False`.
5. **WHEN** the port being probed already answers `/api/salud` with `"app": "gestor-expedientes"` **THE SYSTEM SHALL** return that port together with `True` from `elegir_puerto` instead of binding it.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_servidor -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T1: Entry point app.py, servidor y /api/salud con --check"
git tag step-01-esqueleto
```

### `E1-T2` — Capa de datos SQLite: esquema, versión, auditoría y backups

**Depends on:** `E1-T1` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

Primer gate de datos. Crear `gestor/db.py`, conectar el servidor a la base y hacer el backup de arranque.

1. `gestor/db.py`:
   - `ESQUEMA`: string con el bloque SQL **completo** de la sección *Esquema* (blueprint §4; el mismo bloque está copiado en la
     sección *Modelo de datos* del epic 01), sin cambiar una letra. `VERSION_ESQUEMA = 1`. `SQLITE_MINIMA = (3, 8, 3)`.
   - `TABLAS = ("config", "proveedor", "oc", "renglon", "entrega", "expediente", "evento", "importacion")`;
     `COLUMNAS: dict[str, tuple[str, ...]]` se llena al inicializar con `PRAGMA table_info(<tabla>)` y es la lista blanca
     de nombres dinámicos.
   - `class ConflictoVersion(Exception)` (mensaje fijo: `Otra persona guardó cambios en este registro. Recargá para ver la última versión.`),
     `class BaseNoDisponible(Exception)`.
   - `conectar(ruta: Path) -> sqlite3.Connection`: `sqlite3.connect(database=str(ruta), timeout=10, isolation_level=None)`,
     `row_factory = sqlite3.Row`, `PRAGMA journal_mode=DELETE`, `PRAGMA busy_timeout=10000`, `PRAGMA foreign_keys=ON`.
     Si `sqlite3.sqlite_version_info < SQLITE_MINIMA` lanza `BaseNoDisponible`.
   - `inicializar(ruta: Path, parametros_iniciales: dict) -> None`: crea la carpeta, `executescript(ESQUEMA)`,
     `PRAGMA user_version = 1`, y por cada clave de `parametros_iniciales` que no esté en `config` inserta
     `(clave, json.dumps(valor, ensure_ascii=False, sort_keys=True))`. Idempotente.
   - `@contextmanager transaccion(con)`: `BEGIN IMMEDIATE` → `COMMIT`; ante excepción `ROLLBACK` y re-lanza.
   - `ahora_utc() -> str`: `datetime.now(timezone.utc).isoformat(timespec="seconds")` (nunca `utcnow()`).
   - `registrar_evento(con, accion, tabla, clave: dict, antes: dict | None, despues: dict | None) -> None`
     (usuario `getpass.getuser()`, pc `socket.gethostname()`; JSON con `sort_keys=True`). Se llama dentro de la transacción del cambio.
   - `insertar(con, tabla, fila: dict) -> int`: valida columnas contra `COLUMNAS`, inserta, registra evento `ALTA`, devuelve `lastrowid`.
   - `actualizar_con_version(con, tabla, clave: dict, version_esperada: int, cambios: dict) -> dict`:
     lee la fila (`antes`), `UPDATE <tabla> SET <cambios>, version = version + 1 WHERE <clave> AND version = ?`;
     `rowcount == 0` → `ConflictoVersion` sin escribir evento; si no, evento `MODIFICACION` y devuelve la fila nueva.
     El llamador envuelve todo en `transaccion`.
   - `leer_parametros(con) -> dict` y `guardar_parametro(con, clave, valor, version_esperada) -> None` (usa `actualizar_con_version` sobre `config`).
   - `verificar_integridad(con) -> bool`: `PRAGMA integrity_check` devuelve `ok`.
   - `hacer_backup(ruta_base, carpeta, conservar=30, ahora=None) -> Path`: `ahora` (datetime local) por defecto `datetime.now()`;
     nombre `expedientes-AAAAMMDD-HHMMSS.db`; copia con `origen.backup(destino)` de `sqlite3`; después borra los backups más viejos
     (orden por nombre) hasta dejar `conservar`.
   - `ultimo_backup(carpeta) -> Path | None`; `restaurar_backup(ruta_backup, ruta_base) -> None`: copia el backup sobre la base con
     la API `backup` y después registra en la base restaurada un evento `RESTAURACION` (tabla `config`, clave `{"backup": "<nombre>"}`).
2. `gestor/server.py` (editar): `crear_servidor` llama `db.inicializar(config.ruta(cfg, "base_datos"), cfg["parametros_iniciales"])`
   dentro de `try`; si falla (`sqlite3.Error`, `OSError`, `db.BaseNoDisponible`) guarda `httpd.estado_db = "sin_base"`, si no
   `"ok"` y `httpd.integridad = db.verificar_integridad(...)`. Cada pedido abre su propia conexión con `db.conectar` y la cierra
   en `finally` (los threads no comparten conexiones). `/api/salud` informa `httpd.estado_db`. Rutas nuevas:
   `GET /api/base/estado` → `{"ok": true, "datos": {"integridad": "ok"|"falla", "ultimo_backup": <nombre o null>}}`;
   `POST /api/base/restaurar` (cuerpo `{}`) → restaura `ultimo_backup` y responde `{"ok": true, "datos": {"restaurado": <nombre>}}`;
   sin backups → 422 `{"ok": false, "error": {"codigo": "negocio", "mensaje": "No hay copias de seguridad para restaurar."}}`.
   Errores mapeados: `db.ConflictoVersion` → 409 con `codigo` `conflicto_version` y el mensaje fijo de la clase.
3. `app.py` (editar): en modo normal, después de elegir puerto y antes de servir, `db.hacer_backup(...)` con
   `cfg["backups_a_conservar"]`; un fallo de backup no impide arrancar (queda en `/api/base/estado`). `--check` no hace backup.
4. `tests/test_db.py` — `PruebaBase(ayudas.CasoConEntorno)` con:
   `test_inicializar_crea_todas_las_tablas`, `test_inicializar_es_idempotente`, `test_parametros_iniciales_sembrados`,
   `test_actualizar_con_version_incrementa_y_audita`, `test_conflicto_de_version_no_escribe_nada`,
   `test_evento_y_expediente_no_se_borran`, `test_backup_conserva_30` (7 pruebas);
   y `PruebaBaseServidor(ayudas.CasoConServidor)` con `test_salud_informa_db_ok_y_estado_de_base` y `test_restaurar_ultimo_backup`
   (2 pruebas: la restauración se prueba por `POST /api/base/restaurar`).

**Files**

- `gestor/db.py` — nuevo: esquema, conexión, transacciones, versión, auditoría, backups
- `gestor/server.py` — edit: inicializa la base, conexión por pedido, /api/base/*
- `app.py` — edit: backup al arrancar en modo normal
- `tests/test_db.py` — nuevo: 9 pruebas de la capa de datos

**Acceptance**

1. **WHEN** `gestor.db.inicializar` runs on a database path that does not exist **THE SYSTEM SHALL** create every table of the schema (`config`, `proveedor`, `oc`, `renglon`, `entrega`, `expediente`, `evento`, `importacion`) with `PRAGMA user_version` 1 and `PRAGMA journal_mode` `delete`, and a second run SHALL leave exactly one `config` row per key of `parametros_iniciales`.
2. **WHEN** `db.actualizar_con_version` saves a row with its current `version` **THE SYSTEM SHALL** store `version + 1` and insert exactly one `evento` row (accion `MODIFICACION`, usuario, pc, antes, despues) in the same transaction.
3. **WHEN** `db.actualizar_con_version` saves a row with a stale `version` **THE SYSTEM SHALL** raise `db.ConflictoVersion`, leave the row unchanged and insert no `evento` row.
4. **WHEN** a `DELETE` or `UPDATE` is attempted on `evento`, or a `DELETE` on `expediente` or `oc`, **THE SYSTEM SHALL** raise `sqlite3.IntegrityError` and keep the row.
5. **WHEN** `db.hacer_backup` runs 31 times with distinct timestamps and `conservar=30` **THE SYSTEM SHALL** leave exactly 30 files named `expedientes-AAAAMMDD-HHMMSS.db`, the oldest one removed, and `POST /api/base/restaurar` SHALL bring back the content of the newest backup.
6. **WHEN** the server starts with a temporary `GESTOR_CONFIG` **THE SYSTEM SHALL** answer `/api/salud` with `"db": "ok"` and `GET /api/base/estado` with `"ok": true` and `datos.integridad` equal to `"ok"`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_db -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T2: Capa de datos SQLite: esquema, versión, auditoría y backups"
git tag step-02-base-de-datos
```

### `E1-T3` — Utilidades de fechas, períodos, montos y letras

**Depends on:** `E1-T1` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

Funciones puras, sin base ni servidor.

1. `gestor/util.py`:
   - `normalizar_texto(s) -> str`: NFKD sin marcas combinantes, minúsculas, espacios colapsados.
   - `clave_encabezado(s) -> str`: reemplaza `º` por `°`, aplica `normalizar_texto` y luego `re.sub(r"[^a-z0-9]+", " ", s).strip()`
     (`"N° O/C"` → `"n o c"`, `"Año Licit"` → `"ano licit"`).
   - `a_decimal(valor) -> Decimal` y `a_centavos(valor) -> int`: aceptan `int`, `Decimal`, `"1224990.01"` y formato argentino
     `"1.224.990,01"` (si hay coma, los puntos son de miles). Redondeo `ROUND_HALF_UP` a 2 decimales. Nunca `float`.
   - `formato_pesos(centavos) -> str`: `122499001` → `"1.224.990,01"`.
   - `fecha_desde_texto(s) -> date` (`dd/mm/aaaa`, `aaaa-mm-dd`, `dd.mm.aaaa`), `fecha_desde_serial_excel(n) -> date`
     (base 1899-12-30), `iso(d)`, `ddmmaaaa(d)` (`31/08/2026`), `fecha_sap(d)` (`31.08.2026`).
   - `MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")`; `class Periodo(NamedTuple): periodo: str; desde: date; hasta: date`.
   - `periodo_de_fecha(fecha, dia_inicio=1) -> Periodo`: día 1 = mes calendario. Si no: si `fecha.day >= dia_inicio` el período va
     del `dia_inicio` de ese mes al `dia_inicio - 1` del mes siguiente y se nombra por el mes siguiente; si no, del `dia_inicio` del mes
     anterior al `dia_inicio - 1` del mes actual y se nombra por el mes actual.
   - `mm_aa("2026-08") -> "08-26"`, `mm_barra_aa("2026-08") -> "08/26"`, `mm_aaaa("2026-08") -> "08-2026"`.
   - `normalizar_factura(s) -> tuple[int, str | None, int]`: `"0003B00031812"` → `(3, "B", 31812)`; `"0002 - 00003908"` → `(2, None, 3908)`.
     `misma_factura(a, b) -> bool` compara punto de venta y número (y la letra cuando ambas la tienen).
   - `sap_sin_ceros("0000077170") -> "77170"`.
   - `RE_GDE = re.compile(r"^(EX|IF|PV|RM|DOCFI|NO|ME|PROSA|IFGRA|ITFCO)-\d{4}-\d{6,9}-( -)?INSSJP-[A-Z0-9]+#INSSJP$")`;
     `normalizar_gde(s)`: mayúsculas, `%` → `#`, `-\s+-` → `- -`, quita el resto de los espacios; `validar_gde(s) -> bool` aplica `RE_GDE` a la forma normalizada.
2. `gestor/letras.py`:
   - `numero_a_letras(n: int) -> str` en MAYÚSCULAS sin tildes salvo `MILLÓN`: `UNO` → `UN` delante de `MIL`/`MILLÓN`/`MILLONES` y al final;
     21 `VEINTIUN`, 22 `VEINTIDOS`, 23 `VEINTITRES`, 26 `VEINTISEIS`; 100 `CIEN`, 101–199 `CIENTO …`; 500 `QUINIENTOS`,
     700 `SETECIENTOS`, 900 `NOVECIENTOS`; 1.000 `MIL` (nunca `UN MIL`); 1.000.000 `UN MILLÓN`; ≥ 2.000.000 `… MILLONES`.
   - `letras_con_centavos(centavos) -> str`: `"<letras> CON <cc>/100"`.
   - `importe_en_letras(centavos) -> str`: `"PESOS <letras> CON <cc>/100 CENTAVOS ($ <formato_pesos>-)"` (espacio después de `$`).
3. `tests/test_util.py` — `PruebaUtil(unittest.TestCase)`: `test_periodo_mes_calendario`, `test_periodo_especifico_dia_17`,
   `test_a_centavos_y_formato_pesos`, `test_normalizar_factura`, `test_normalizar_y_validar_gde`, `test_clave_encabezado`,
   `test_fecha_serial_excel` (45971 → 2025-11-10).
4. `tests/test_letras.py` — `PruebaLetras(unittest.TestCase)`: `test_importe_efia_completo`, `test_casos_del_blueprint`
   (los seis montos de los criterios), `test_veinti_y_cientos` (21, 22, 23, 26, 101, 500, 700, 900).

**Files**

- `gestor/util.py` — nuevo: textos, montos, fechas, períodos, factura, GDE
- `gestor/letras.py` — nuevo: importe en letras
- `tests/test_util.py` — nuevo
- `tests/test_letras.py` — nuevo

**Acceptance**

1. **WHEN** `letras.importe_en_letras(122499000)` runs **THE SYSTEM SHALL** return exactly `PESOS UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100 CENTAVOS ($ 1.224.990,00-)`.
2. **WHEN** `letras.letras_con_centavos` receives 2109500000, 3388160000, 2210187213, 100000, 10000 and 370000000 centavos **THE SYSTEM SHALL** return `VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100`, `TREINTA Y TRES MILLONES OCHOCIENTOS OCHENTA Y UN MIL SEISCIENTOS CON 00/100`, `VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100`, `MIL CON 00/100`, `CIEN CON 00/100` and `TRES MILLONES SETECIENTOS MIL CON 00/100` respectively.
3. **WHEN** `util.periodo_de_fecha` receives 2026-10-20, 2026-11-16 and 2026-11-17 with `dia_inicio=17` **THE SYSTEM SHALL** return `2026-11` (from 2026-10-17 to 2026-11-16), `2026-11` and `2026-12`, and with `dia_inicio=1` and 2026-08-31 it SHALL return `2026-08` from 2026-08-01 to 2026-08-31.
4. **WHEN** `util.normalizar_factura` receives `00002B00003908` and `0002 - 00003908` **THE SYSTEM SHALL** return `(2, "B", 3908)` and `(2, None, 3908)` and `util.misma_factura` SHALL report them as the same invoice.
5. **WHEN** `util.normalizar_gde` receives `EX-2025-18959064-   -INSSJP-GESP%INSSJP` **THE SYSTEM SHALL** return `EX-2025-18959064- -INSSJP-GESP#INSSJP`, which `util.validar_gde` SHALL accept while rejecting `EX-2026-12-INSSJP`.
6. **WHEN** `util.a_centavos` receives `1.224.990,01`, `1224990.01` and the integer 1224990 **THE SYSTEM SHALL** return 122499001, 122499001 and 122499000, and `util.formato_pesos(122499001)` SHALL return `1.224.990,01`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_util -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_letras -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T3: Utilidades de fechas, períodos, montos y letras"
git tag step-03-util-y-letras
```

### `E1-T4` — Lector de .xlsx con zipfile y ElementTree

**Depends on:** `E1-T1` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

`gestor/xlsx.py`, sin dependencias externas:

- `leer_filas(origen) -> list[list[str | None]]`: `origen` es una ruta o un archivo binario abierto. Abre el zip, lee
  `xl/workbook.xml` y `xl/_rels/workbook.xml.rels` para encontrar la PRIMERA hoja del libro que tenga al menos una `<row>`
  (en los reportes es `xl/worksheets/sheet1.xml`; `sheet2`/`sheet3` están vacías), carga `xl/sharedStrings.xml` si existe
  (concatenando todos los `<t>` de cada `<si>`), y resuelve celdas `t="s"`, `t="inlineStr"`, `t="str"`, `t="b"` y numéricas
  (el texto de `<v>` tal cual, sin convertir a `float`). Las columnas se ubican por la letra de la referencia `r` (`AB12` → 28),
  rellenando huecos con `None`.
- `leer_tabla(origen) -> tuple[list[str], list[dict[str, str | None]]]`: la primera fila son los encabezados (`str.strip()`);
  cada `<row>` siguiente es una fila de datos (también las vacías y los subtotales: la limpieza las descarta y las cuenta).
- Errores: zip inválido o sin hojas → `XlsxError("El archivo no es un Excel .xlsx válido.")`.

`tests/test_xlsx.py` — `PruebaXlsx(unittest.TestCase)`: `test_encabezados_hbi_2026`, `test_encabezados_por_partida`,
`test_cantidad_de_filas`, `test_valores_como_texto` (aparece el proveedor `0000115819` con sus ceros y el expediente
`EX-2025-18959064-   -INSSJP-GESP#INSSJP` con sus espacios), `test_archivo_invalido`. Las listas de encabezados esperadas se
escriben literales en el test, en este orden:

- `z_compras2_hbi_2026.xlsx` (27): `Número de Expediente GDE`, `Clase de Pedido`, `Licitacion`, `Precio unitario`, `Año Licit`,
  `Proveedor`, `Razón Social Proveed`, `N° O/C`, `F.O.Compra`, `In. Periodo Validez`, `Fin Periodo Validez`, `Posición.`, `Código`,
  `Elemento`, `Cant`, `Importe`, `Moneda`, `Org.Compras`, `Centro`, `Entrega final`, `Factura Final`, `Por entregar (cantid`,
  `Entregadas (cantidad`, `Por entregar (valor)`, `Entregadas (valor)`, `Por Facturar (cantid`, `Facturadas (cantidad`.
- `z_compras2_por_partida.xlsx` (30): `Partida Presupuestar` seguido de la lista anterior SIN `Precio unitario`, y al final
  `Tipo de Imputación`, `Expte`, `Número de Expediente`.

(`N° O/C` usa el signo de grado U+00B0.)

**Files**

- `gestor/xlsx.py` — nuevo: lector .xlsx
- `tests/test_xlsx.py` — nuevo: pruebas con los dos reportes reales

**Acceptance**

1. **WHEN** `xlsx.leer_tabla` reads `tests/fixtures/xlsx/z_compras2_hbi_2026.xlsx` **THE SYSTEM SHALL** return its 27 headers in file order, from `Número de Expediente GDE` to `Facturadas (cantidad`, and 3074 data rows.
2. **WHEN** `xlsx.leer_tabla` reads `tests/fixtures/xlsx/z_compras2_por_partida.xlsx` **THE SYSTEM SHALL** return its 30 headers starting with `Partida Presupuestar` and ending with `Número de Expediente`, without `Precio unitario`, and 5897 data rows.
3. **WHEN** a cell holds the supplier `0000115819` or the file `EX-2025-18959064-   -INSSJP-GESP#INSSJP` **THE SYSTEM SHALL** return the text exactly as stored, keeping leading zeros and inner spaces.
4. **WHEN** `xlsx.leer_tabla` receives bytes that are not a zip **THE SYSTEM SHALL** raise `xlsx.XlsxError` with the message `El archivo no es un Excel .xlsx válido.`

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_xlsx -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T4: Lector de .xlsx con zipfile y ElementTree"
git tag step-04-lector-xlsx
```

### `E1-T5` — Importador z_compras2: limpieza, exclusiones y upsert

**Depends on:** `E1-T2`, `E1-T3`, `E1-T4` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

`gestor/importar.py` — importa el reporte por NOMBRE de encabezado (`util.clave_encabezado`), nunca por posición.

- `MAPA` (clave normalizada → campo): `numero de expediente gde`→`expediente_contratacion`, `clase de pedido`→`clase`,
  `licitacion`→`licitacion`, `ano licit`→`anio_licit`, `precio unitario`→`precio`, `proveedor`→`sap`,
  `razon social proveed`→`razon_social`, `n o c`→`oc`, `f o compra`→`fecha_oc`, `in periodo validez`→`vig_desde`,
  `fin periodo validez`→`vig_hasta`, `posicion`→`pos`, `codigo`→`codigo`, `elemento`→`descripcion`, `cant`→`cantidad`,
  `importe`→`importe`, `org compras`→`org_compras`, `centro`→`centro`, `entrega final`→`entrega_final`,
  `factura final`→`factura_final`, `por entregar cantid`→`sap_por_entregar`, `entregadas cantidad`→`sap_entregado`,
  `facturadas cantidad`→`sap_facturado`, `partida presupuestar`→`partida`. Las demás columnas solo van a `crudo`.
- `OBLIGATORIAS = ("N° O/C", "Posición.", "Elemento", "Cant", "Importe", "Centro", "Proveedor", "Razón Social Proveed")`.
  Si falta una: `ErrorImportacion('Falta la columna obligatoria "<nombre>" en el reporte.')` antes de tocar la base.
- Descartes, en este orden, contados por motivo: `sin_oc` (fila sin N° O/C: vacía o subtotal), `partida` (partida en
  `parametros["partidas_excluidas"]`), `centro` (centro fuera de `parametros["efectores"][efector]["centros"]`),
  `exclusion_manual` (SAP en `exclusiones.sap` u OC en `exclusiones.oc`). La clase `ZGRH` NO se descarta por clase.
- Si el reporte no tiene `Partida Presupuestar`, `avisos` incluye exactamente:
  `Este reporte no tiene la partida presupuestaria; no se pueden descartar honorarios (3490000). Agregá la columna al layout del z_compras2.`
  y la importación sigue.
- Limpieza (reglas del §4 *Limpieza*): OC, posición y SAP a texto sin ceros a la izquierda; cantidades e importes a `Decimal`
  (restos `3600.001` redondeados a 2 decimales con tolerancia 0,01); fechas desde serial Excel; expediente con
  `util.normalizar_gde`; `ca = "<Licitacion>-<Año Licit>"` (`195-2025`); `precio` = columna `Precio unitario` o, si falta,
  `Importe / Cant` redondeado a 2 decimales; `revisar_importe = 1` si `|cantidad × precio − importe| > 1 centavo`;
  `vig_hasta < vig_desde` → la fila se informa en `errores` y no entra; `Entrega final` o `Factura final` con `X` → `oc.cerrada_sap = 1`;
  OC+posición repetida → queda la última y se cuenta en `duplicados`.
- `analizar(origen, efector, parametros, con=None) -> dict` (vista previa, no escribe) e
  `importar(con, origen, efector, parametros, archivo="") -> dict` (upsert en una sola `db.transaccion`): informe
  `{"filas", "descartes": {"sin_oc", "partida", "centro", "exclusion_manual"}, "quedan", "oc_distintas", "duplicados",
  "altas", "actualizadas", "sin_cambios", "cambios": [...], "avisos": [...], "errores": [...]}`. `cambios` lista los cambios de
  precio, cantidad y vigencia contra lo que ya hay en la base.
- Upsert: SELECT y luego INSERT o UPDATE (nada de `ON CONFLICT`); un campo listado en `oc.campos_manuales` o
  `renglon.campos_manuales` nunca se pisa. `renglon.crudo` guarda la fila original como JSON (claves = encabezados del Excel).
  `renglon.partida` guarda la partida. Proveedor nuevo → alta en `proveedor`. Al final inserta la fila de `importacion`
  y un evento `IMPORTACION`.

`tests/test_importar.py` — `PruebaImportar(ayudas.CasoConEntorno)` (base temporal con `db.inicializar`):
`test_analizar_hbi_2026_cuenta_descartes`, `test_analizar_por_partida_cuenta_descartes`, `test_aviso_sin_partida`,
`test_importar_ambos_y_reimportar`, `test_falta_columna_obligatoria`, `test_precio_derivado_cuando_falta_columna`,
`test_campos_manuales_no_se_pisan`, `test_exclusion_manual_por_oc`, `test_crudo_guarda_fila_original`.
Para el Excel sin columna `Importe` el test arma un .xlsx mínimo con `zipfile` (helper `crear_xlsx(ruta, encabezados, filas)` dentro del test).

**Files**

- `gestor/importar.py` — nuevo: mapeo por encabezado, limpieza, descartes, upsert, informe
- `tests/test_importar.py` — nuevo: conteos con los dos reportes reales

**Acceptance**

1. **WHEN** `importar.analizar` runs on `z_compras2_hbi_2026.xlsx` as efector HBI **THE SYSTEM SHALL** report 3074 rows, discards `sin_oc` 2, `partida` 0, `centro` 2639, `exclusion_manual` 0, 433 remaining rows, 107 distinct OC, 0 duplicates and the warning `Este reporte no tiene la partida presupuestaria; no se pueden descartar honorarios (3490000). Agregá la columna al layout del z_compras2.`
2. **WHEN** `importar.analizar` runs on `z_compras2_por_partida.xlsx` as efector HBI **THE SYSTEM SHALL** report 5897 rows, discards `sin_oc` 16, `partida` 5402, `centro` 192, `exclusion_manual` 0, 287 remaining rows, 108 distinct OC, 0 duplicates and no partida warning.
3. **WHEN** both reports are imported as HBI in either order **THE SYSTEM SHALL** hold 574 rows in `renglon`, and importing either report again SHALL report 0 `altas`.
4. **WHEN** a report lacks the column `Importe` **THE SYSTEM SHALL** raise `ErrorImportacion` with the message `Falta la columna obligatoria "Importe" en el reporte.` and write nothing.
5. **WHEN** a field of an OC listed in `campos_manuales` was edited by hand **THE SYSTEM SHALL** keep the hand-edited value after re-importing, and every imported `renglon.crudo` SHALL contain the original row keyed by the Excel headers.
6. **WHEN** the report has no `Precio unitario` column **THE SYSTEM SHALL** store `precio_centavos` equal to `Importe / Cant` rounded half-up to 2 decimals for every imported row with `Cant` different from 0.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_importar -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T5: Importador z_compras2: limpieza, exclusiones y upsert"
git tag step-05-importar
```

### `E1-T6` — Desglose mensual de servicios e inferencias al importar

**Depends on:** `E1-T5` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

Agregar a `gestor/importar.py` las inferencias que se aplican en el alta y en cada reimportación (salvo campos manuales):

- `RE_ANIO_FINAL = re.compile(r"[-\s]+(20\d\d)\s*$")`; `anio_final(descripcion) -> int | None` (acepta `… - 2027` y
  `SERV. ESTERIL. POR ETO 2026`, sin guion).
- `meses_entre(desde, hasta) -> Decimal | None`: meses enteros de `desde` a `hasta + 1 día` (2026-04-09..2026-08-08 → 4;
  2026-10-01..2026-12-31 → 3); `None` si no da un número entero de meses.
- `inferir_desglose(renglon, vig_desde, vig_hasta)`: si `cantidad == 1` y la descripción termina en un año, el tramo es la
  intersección de la vigencia con ese año; si `cantidad == 1` y `sap_entregado > 1` (por entregar negativo), el tramo es toda la
  vigencia. Resultado: `desglose_cantidad = meses`, `desglose_unidad = "MES"`, `desglose_precio_centavos = importe / meses`;
  si los meses no son enteros o el precio no es exacto al centavo → `revisar_desglose = 1` y sin desglose.
- Regla 5: `sap_por_entregar = max(0, cantidad − entregado)` medido en la unidad del desglose cuando lo hay; si lo entregado supera
  la cantidad → `exceso_sap = 1`. Ningún renglón queda con `sap_por_entregar` negativo.
- Inferencias de OC: `centralizada = 1` si `org_compras` no está en `parametros["org_compras_propias"]`; `tipo = "SERVICIO"` si el
  código está vacío o es de 7 dígitos que empieza con `1`, si no `"BIEN"`; si alguna descripción contiene `COMODATO` →
  `comodato = 1` y `tipo = "PROVISION"`. Sin fin de vigencia → la OC se trata como entrega única (no genera períodos).

`tests/test_desglose.py` — `PruebaDesglose(ayudas.CasoConEntorno)`: `test_anio_final_con_y_sin_guion`, `test_meses_entre`,
`test_efia_4500600299_tres_y_nueve_meses`, `test_esterisur_eto_sin_guion_se_desglosa`, `test_sin_por_entregar_negativo`,
`test_inferencia_tipo_y_comodato` (BIO FAB 4500587121 queda `BIEN` y `comodato = 0`; un renglón sintético
`EQUIPO EN COMODATO` da `PROVISION` y `comodato = 1`).

**Files**

- `gestor/importar.py` — edit: desglose, por entregar, inferencias de OC
- `tests/test_desglose.py` — nuevo

**Acceptance**

1. **WHEN** `z_compras2_hbi_2026.xlsx` is imported as HBI **THE SYSTEM SHALL** store for OC 4500600299 position 1 `desglose_cantidad` 3, `desglose_unidad` `MES`, `desglose_precio_centavos` 122499000, and for position 2 `desglose_cantidad` 9 with the same unit and price.
2. **WHEN** `importar.anio_final` receives `SERV. ESTERIL. POR ETO 2026` and `SERV. ESTERIL. POR VAPOR HUMEDO - 2027` **THE SYSTEM SHALL** return 2026 and 2027, and for `DETERMINACIONES DE TROPONINA I` it SHALL return `None`.
3. **WHEN** `importar.meses_entre` receives 2026-04-09 to 2026-08-08 and 2026-10-01 to 2026-12-31 **THE SYSTEM SHALL** return 4 and 3.
4. **WHEN** `z_compras2_hbi_2026.xlsx` is imported as HBI **THE SYSTEM SHALL** leave no `renglon` with a negative `sap_por_entregar`.
5. **WHEN** OC 4500587121 is imported **THE SYSTEM SHALL** infer `tipo` `BIEN` and `comodato` 0, and WHEN a row description contains `COMODATO` **THE SYSTEM SHALL** infer `tipo` `PROVISION` and `comodato` 1.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_desglose -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_importar -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T6: Desglose mensual de servicios e inferencias al importar"
git tag step-06-desglose
```

### `E1-T7` — Interfaz base (8 pantallas) y pantalla Importar

**Depends on:** `E1-T5` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `web/index.html`: `<html lang="es">`, enlace "Saltar al contenido" (`href="#contenido"`), `<header>` con el título y
   `<select id="selector-efector">` (opciones `HBI`, `CASPH`, `Ambos`), `<nav>` lateral con 8 botones y `<main id="contenido">` con
   exactamente estas secciones: `pantalla-inicio`, `pantalla-calendario`, `pantalla-oc`, `pantalla-expedientes`,
   `pantalla-centralizadas`, `pantalla-entregas`, `pantalla-importar`, `pantalla-configuracion`; región
   `<div id="avisos" aria-live="polite">`. Carga `/style.css` y `/app.js`.
2. `web/style.css`: variables `:root` con los tokens de §7 (sin modo oscuro), `font-size: 16px`, botones de 44 px de alto
   mínimo, foco visible `outline: 3px solid var(--foco)`.
3. `web/app.js`: `api(metodo, ruta, cuerpo)` (fetch JSON; ante `ok: false` muestra `error.mensaje` en `#avisos`; ante 409 agrega
   botón Recargar), navegación por `hidden`, y la pantalla Importar: elegir archivo y efector, botón "Vista previa" (tabla de
   conteos por motivo, avisos, cambios), botón "Confirmar importación". Si el efector es CASPH sin centros muestra un campo para
   cargarlos (que guarda con `PUT /api/parametros`).
4. `gestor/server.py` (editar):
   - Estáticos: `GET /` → `web/index.html` (`text/html; charset=utf-8`), `GET /app.js` (`text/javascript; charset=utf-8`),
     `GET /style.css` (`text/css; charset=utf-8`). Solo esos tres nombres; cualquier otra ruta no-API → 404.
   - Sobre de respuesta de la API: `{"ok": true, "datos": ...}` / `{"ok": false, "error": {"codigo", "mensaje"}}`
     (códigos `validacion` 400, `no_encontrado` 404, `conflicto_version` 409, `demasiado_grande` 413, `negocio` 422, `interno` 500).
   - `GET /api/parametros` → `{"ok": true, "datos": {"parametros": {...}, "versiones": {"<clave>": <version>}}}`;
     `PUT /api/parametros` con `{"clave", "valor", "version"}` → guarda con `db.guardar_parametro` (409 si la versión es vieja).
   - `POST /api/importar/vista-previa` y `POST /api/importar/confirmar`: `multipart/form-data` con `archivo` y `efector`,
     parseado con `email.parser.BytesParser(policy=email.policy.default)` (nunca `cgi`). `Content-Length` mayor que
     `tamano_maximo_subida_mb` → 413 `{"codigo": "demasiado_grande", "mensaje": "El archivo supera el máximo de <n> MB."}`.
     Efector CASPH sin centros → 422 con `mensaje` `Configurá los centros SAP de CASPH antes de importar.`
     `ErrorImportacion`/`XlsxError` → 400 `validacion` con su mensaje. Responde el informe del importador.
   - `GET /api/importaciones` → lista de importaciones (id, fecha, archivo, efector, usuario).
5. `tests/test_web_importar.py` — `PruebaWebImportar(ayudas.CasoConServidor)`: `test_raiz_sirve_las_8_pantallas`,
   `test_estaticos_con_content_type`, `test_ruta_fuera_de_web_da_404` (`GET /config.json` → 404),
   `test_vista_previa_no_escribe_y_confirmar_importa`, `test_casph_sin_centros_pide_configurarlos`,
   `test_parametros_con_version_vieja_da_409`; y `PruebaSubidaGrande(unittest.TestCase)` con
   `test_subida_demasiado_grande_da_413` (arma su propio `ayudas.EntornoTemporal(tamano_maximo_subida_mb=0.01)` y servidor).

**Files**

- `web/index.html` — nuevo: estructura de 8 pantallas
- `web/app.js` — nuevo: api(), navegación, pantalla Importar
- `web/style.css` — nuevo: tokens visuales de §7
- `gestor/server.py` — edit: estáticos, sobre de respuesta, parámetros, importación multipart
- `tests/test_web_importar.py` — nuevo

**Acceptance**

1. **WHEN** `GET /` is requested **THE SYSTEM SHALL** serve `web/index.html` as `text/html; charset=utf-8` containing `lang="es"`, `id="selector-efector"`, `id="avisos"` and the eight section ids `pantalla-inicio`, `pantalla-calendario`, `pantalla-oc`, `pantalla-expedientes`, `pantalla-centralizadas`, `pantalla-entregas`, `pantalla-importar`, `pantalla-configuracion`.
2. **WHEN** `GET /config.json` is requested **THE SYSTEM SHALL** answer 404 and serve no file outside `web/`.
3. **WHEN** `z_compras2_hbi_2026.xlsx` is posted to `/api/importar/vista-previa` with efector HBI **THE SYSTEM SHALL** answer `quedan` 433 and leave `renglon` empty, and posting it to `/api/importar/confirmar` SHALL leave 433 rows in `renglon` and one row in `importacion`.
4. **WHEN** an import is posted with efector CASPH while CASPH has no configured centers **THE SYSTEM SHALL** answer 422 with `mensaje` `Configurá los centros SAP de CASPH antes de importar.`
5. **WHEN** `PUT /api/parametros` carries a stale `version` **THE SYSTEM SHALL** answer 409 with `mensaje` `Otra persona guardó cambios en este registro. Recargá para ver la última versión.`
6. **WHEN** an upload exceeds `tamano_maximo_subida_mb` **THE SYSTEM SHALL** answer 413 with `codigo` `demasiado_grande` without reading the file into the database.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_web_importar -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T7: Interfaz base (8 pantallas) y pantalla Importar"
git tag step-07-ui-e-importar
```

### `E1-T8` — Órdenes de compra: lista, ficha, campos manuales y alta

**Depends on:** `E1-T6`, `E1-T7` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (nuevo; capa de reglas que usa `db`): `listar_oc(con, efector=None, texto="", incluir_excluidas=False)`,
   `ficha_oc(con, numero)` (OC + proveedor + renglones + expedientes), `actualizar_oc(con, numero, version, cambios)`,
   `crear_oc_manual(con, datos)`, `actualizar_renglon(con, oc, pos, version, cambios)`, `agregar_renglon(con, oc, datos)`.
   `texto` busca (sin tildes ni mayúsculas) en número de OC, SAP, razón social y objeto.
   - Campos editables de la OC: `objeto`, `objeto_articulo`, `concepto_corto`, `dia_inicio_periodo`, `comodato`, `centralizada`,
     `tipo`, `ca`, `expediente_contratacion`, `gde_pdf_oc`, `leyenda_cv`, `extras_cv`, `doc_requerida_central`, `vig_desde`,
     `vig_hasta`, `prorroga`, `excluida`, `motivo_exclusion`. Cada campo editado se agrega a `oc.campos_manuales`.
     Campos editables del renglón: `desglose_cantidad`, `desglose_unidad`, `desglose_precio_centavos`, `consumo_previo`,
     `es_correctivo`, `revisar_desglose`, `revisar_importe` (y se agregan a `renglon.campos_manuales`).
   - Validaciones (`negocio.ErrorValidacion` → 400): `dia_inicio_periodo` fuera de 1..28 →
     `El día de inicio del período debe estar entre 1 y 28.`; `objeto_articulo` fuera de `al`, `a la`, `a los`, `a las`;
     GDE inválido (`util.validar_gde`). OC manual repetida → `negocio.ErrorNegocio` (422) `La OC <numero> ya existe.`
   - Toda escritura en `db.transaccion` con versión y evento.
2. `gestor/server.py` (editar): `GET /api/oc?efector=&q=&excluidas=0|1`, `GET /api/oc/<numero>`, `PUT /api/oc/<numero>`
   (`{"version", "cambios"}`), `POST /api/oc` (alta manual), `POST /api/oc/<numero>/renglones`,
   `PUT /api/oc/<numero>/renglones/<pos>`.
3. `web/app.js` (editar): pantalla Órdenes de compra (búsqueda, lista, ficha con formulario de campos manuales, renglones con
   desglose y consumo previo, alta manual).
4. `tests/datos_prueba.py` (nuevo, lo reutilizan los pasos siguientes): `OC_EFIA_MANUAL` (dict literal con SAP `77170`,
   razón social `GRUPO EFIA S.R.L.`, OC `4500555861`, efector HBI, fecha OC 2025-09-04, vigencia 2025-10-01 a 2026-09-30, CA
   `195-2025`, expediente `EX-2025-70356979- -INSSJP-GESP#INSSJP`, objeto `servicio de control integral de plagas, fumigación,
   desinsectación y desratización`, artículo `al`, concepto corto `SERV. FUMIGACIÓN`, día de inicio 1, renglón 1
   `SERV INTEGRAL CONTROL DE PLAGAS` con desglose 9 `MES` × 122499000 centavos), `cargar_efia(con)`,
   `importar_hbi_2026(con)`, `preparar_biofab(con)` (importa y marca 4500587121 `comodato = 1`, objeto `provisión de
   inmunoensayo por fluorescencia`, artículo `a la`), `preparar_macatex(con)` (importa; objeto vacío).
5. `tests/test_oc.py` — `PruebaOC(ayudas.CasoConServidor)`: `test_alta_manual_efia`, `test_editar_marca_campo_manual_y_reimportar_no_lo_pisa`,
   `test_editar_con_version_vieja_da_409`, `test_dia_inicio_fuera_de_rango_da_400`, `test_listar_filtra_por_efector_y_texto`,
   `test_excluir_oc_la_oculta`.

**Files**

- `gestor/negocio.py` — nuevo: reglas de OC
- `gestor/server.py` — edit: rutas /api/oc
- `web/app.js` — edit: pantalla Órdenes de compra
- `tests/datos_prueba.py` — nuevo: datos reales reutilizables (EFIA manual, BIO FAB, MACATEX)
- `tests/test_oc.py` — nuevo

**Acceptance**

1. **WHEN** `POST /api/oc` receives the manual OC 4500555861 of SAP 77170 `GRUPO EFIA S.R.L.` **THE SYSTEM SHALL** store it with `origen` `MANUAL`, CA `195-2025`, expediente `EX-2025-70356979- -INSSJP-GESP#INSSJP`, validity 2025-10-01 to 2026-09-30 and position 1 with `desglose_cantidad` 9, `desglose_unidad` `MES`, `desglose_precio_centavos` 122499000.
2. **WHEN** `PUT /api/oc/<numero>` changes `objeto` with the current `version` **THE SYSTEM SHALL** store it, add `objeto` to `campos_manuales`, and a later re-import of the same report SHALL keep the edited `objeto`.
3. **WHEN** `PUT /api/oc/<numero>` carries a stale `version` **THE SYSTEM SHALL** answer 409 with `mensaje` `Otra persona guardó cambios en este registro. Recargá para ver la última versión.`
4. **WHEN** `dia_inicio_periodo` 29 is saved **THE SYSTEM SHALL** answer 400 with `mensaje` `El día de inicio del período debe estar entre 1 y 28.`
5. **WHEN** `GET /api/oc?efector=HBI&q=EFIA` runs after importing `z_compras2_hbi_2026.xlsx` **THE SYSTEM SHALL** list OC 4500600299, and WHEN that OC is saved with `excluida` 1 **THE SYSTEM SHALL** leave it out of the default list.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_oc -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E1-T8: Órdenes de compra: lista, ficha, campos manuales y alta"
git tag step-08-oc
```

---

## Epic acceptance

El epic está terminado cuando todas sus tareas están `done` **y**:

1. **WHEN** `python app.py --check` runs after this epic **THE SYSTEM SHALL** print the `/api/salud` JSON with `"db": "ok"` and exit 0.
2. **WHEN** both z_compras2 reports are imported as HBI **THE SYSTEM SHALL** hold 574 rows in `renglon`, and the manual EFIA OC 4500555861 SHALL be listed by `GET /api/oc?efector=HBI` with `origen` `MANUAL`.

```bash
python -W error::DeprecationWarning -m unittest tests.test_importar -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_oc -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

## Pitfalls

- **Contar mal las filas del Excel** — cada `<row>` posterior al encabezado es una fila de datos, aunque esté vacía; los descartes `sin_oc` existen justamente para eso.
- **`ON CONFLICT DO UPDATE` / `RETURNING`** — no están garantizados en el SQLite de cualquier Python ≥ 3.10 para Windows; SELECT + INSERT/UPDATE.
- **Guardar fechas con adaptadores de sqlite3** — deprecados en 3.12 y con `-W error::DeprecationWarning` rompen todos los tests.

## Before moving on

- [ ] Cada tarea de este epic está `done` en `tasks.json`; ninguna quedó `in_progress`.
- [ ] Pasaron **todos** los comandos `verify` de cada tarea, no solo el primero.
- [ ] Ningún comando `verify` fue editado ni salteado.
- [ ] Cada tarea tiene su tag de checkpoint: `git tag -l 'step-*'` lista `step-01-esqueleto`, `step-02-base-de-datos`, `step-03-util-y-letras`, `step-04-lector-xlsx`, `step-05-importar`, `step-06-desglose`, `step-07-ui-e-importar`, `step-08-oc`.
- [ ] El gate (`python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`) sale 0 desde la raíz.
- [ ] Cada contrato "Produced" existe con la firma indicada.
- [ ] Ningún archivo fuera del árbol fue modificado; `plantillas/`, `tests/fixtures/` y `tests/ayudas.py` siguen intactos.
- [ ] Este proyecto no tiene `.env` ni `.env.example`: la única variable de entorno es `GESTOR_CONFIG` (§10), opcional.
- [ ] Un commit por tarea, con el id de la tarea como prefijo, seguido de su tag.
