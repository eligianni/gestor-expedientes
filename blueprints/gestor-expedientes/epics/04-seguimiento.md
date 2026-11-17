# Epic 04: Seguimiento

> Existen el calendario anual accesible, la pantalla Inicio con alertas, las entregas con su CSV NUMERACIÓN, pendientes, la pantalla Configuración con apagado e `Iniciar.bat`, y los seis exportes en Excel, CSV e impresión.

| | |
|---|---|
| **Epic id** | `04-seguimiento` |
| **Tasks** | `E4-T1` … `E4-T5` (pasos 22–26 de `blueprint.md` §9) |
| **Depends on** | `03-salidas-y-prototipo` |
| **Unlocks** | `05-especiales-y-cierre` |
| **Parallel with** | ninguno (comparte `negocio.py`, `server.py` y `app.js`) |

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
Iniciar.bat               # NUEVO (paso 25)
gestor/
  negocio.py              # existe — calendario, alertas, entregas, pendientes
  exportes.py             # NUEVO (paso 24), editado (26)
  xlsx_escritor.py        # NUEVO (paso 26)
  server.py               # existe — /api/calendario, /api/inicio/alertas, /api/entregas/*, /api/pendientes, /api/config-local, /api/base/backup, /api/apagar, /api/exportes/*
web/app.js  web/style.css # existen — Calendario, Inicio, Entregas, Configuración, exportes
tests/
  test_calendario.py test_inicio.py test_entregas.py test_pendientes_config.py test_exportes.py   # NUEVOS
```

Todo lo que está fuera de este árbol queda fuera de alcance. Si una tarea parece exigir editar otro archivo, parar y reportarlo.

## Data model touched here

| Entidad | Campos | Notas |
|---|---|---|
| `entrega` | `efector`, `numero` (correlativo por efector), `nombre`, `fecha_envio`, `estado` (`ABIERTA`/`ENVIADA`) | `UNIQUE (efector, numero)` |
| `expediente` | `entrega_id`, `estado`, `motivo_pendiente`, `fecha_seguimiento` | `ENVIADO` solo al enviar la entrega |
| `config` | `dias_gracia`, `dias_aviso_vencimiento_oc`, `umbral_por_agotarse_pct` | se leen para colores y alertas |

## Contracts

**Consumed** — ya existe, no reconstruir:

| From | Interface | Guarantee |
|---|---|---|
| `03-salidas-y-prototipo` | `textos.textos_sap`, `negocio.cambiar_estado`, `negocio.contexto_textos` | para NUMERACIÓN y estados |
| `02-expediente-comun` | `negocio.consumo_por_renglon` | para alertas y exportes |
| `01-nucleo-y-oc` | `xlsx.leer_filas`, `config.guardar_config`, `db.hacer_backup` | roundtrip, config local, backup manual |

**Produced** — los epics siguientes dependen de estas firmas exactas:

| Export | Signature | Used by |
|---|---|---|
| `gestor/negocio.py` → `calendario`, `alertas`, `crear_entrega`, `asignar_a_entrega`, `enviar_entrega`, `pendientes` | ver pasos 22–25 | `05` |
| `gestor/exportes.py` → `a_csv`, `a_html`, exportes por nombre | ver pasos 24 y 26 | `05` |
| `gestor/xlsx_escritor.py` → `escribir_xlsx` | ver paso 26 | `05` |

## Conventions that bite in this area

- Cada estado del calendario lleva color **y** letra (accesibilidad): `-`, `V`, `C`, `M`, `P`, `A`, `·`.
- `hoy` se puede pasar por query string para que los tests sean deterministas; por defecto es `date.today()`.
- CSV: UTF-8 con BOM, `;`, CRLF.
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

### `E4-T1` — Calendario anual OC × meses con estados accesibles

**Depends on:** `E3-T6` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `calendario(con, anio, efector=None, tipo=None, sap=None, hoy=None) -> dict` — una fila
   por OC no excluida con vigencia, 12 celdas (una por mes del año; el período de cada mes respeta `dia_inicio_periodo`):
   | estado | cuándo | color (token) | letra |
   |---|---|---|---|
   | `fuera` | el período no se superpone con la vigencia | `--gris-fuera` | `-` |
   | `validado` | hay expediente no anulado en `FIRMADO`, `ENVIADO`, `CONTABILIZADO` o `CERRADO` | `--exito` | `V` |
   | `en_curso` | hay expediente en `BORRADOR`, `CONTROLADO` o `EN_FIRMA` | `--info` | `C` |
   | `pendiente_motivo` | hay expediente en `PENDIENTE` | `--violeta` | `M` |
   | `pendiente_en_plazo` | sin expediente, el período ya empezó y `hoy <= hasta + dias_gracia` | fondo `--pendiente-plazo`, texto `--texto` | `P` |
   | `atrasado` | sin expediente y `hoy > hasta + dias_gracia` | `--error` | `A` |
   | `sin_iniciar` | el período todavía no empezó | `--superficie` | `·` |
   Marcas de fila/celda: `vence_pronto` (borde `--naranja` si `vig_hasta - hoy <= dias_aviso_vencimiento_oc`), `entrega_enviada`
   (`●`, expediente con entrega `ENVIADA`), `centralizada_enviada` (`◆`, se llena en el paso 27). Cada celda trae `expediente_id` o `null`.
2. `gestor/server.py` (editar): `GET /api/calendario?anio=&efector=&tipo=&sap=&hoy=` (`hoy` opcional, `AAAA-MM-DD`).
3. `web/app.js` (editar): tabla con encabezado de meses, celdas con color + letra + `aria-label` ("agosto 2026: validado"),
   filtros, y `<div id="leyenda-calendario">` con los siete estados y las tres marcas (color, letra y nombre). Clic o Enter en una
   celda abre el expediente o crea uno con OC y período.
4. `web/style.css` (editar): clases `.cal-fuera`, `.cal-validado`, `.cal-en_curso`, `.cal-pendiente_motivo`,
   `.cal-pendiente_en_plazo`, `.cal-atrasado`, `.cal-sin_iniciar`, `.cal-vence_pronto` con los tokens de §7.
5. `tests/test_calendario.py` — `PruebaCalendario(ayudas.CasoConServidor)`: `test_estados_efia_2026`, `test_vence_pronto`,
   `test_letras_por_estado`, `test_leyenda_en_app_js`, `test_atrasado_respeta_dias_gracia`.

**Files**

- `gestor/negocio.py` — edit: calendario
- `gestor/server.py` — edit: /api/calendario
- `web/app.js` — edit: pantalla Calendario
- `web/style.css` — edit: clases del calendario
- `tests/test_calendario.py` — nuevo

**Acceptance**

1. **WHEN** `GET /api/calendario?anio=2026&hoy=2026-09-20` runs with the EFIA manual OC (validity 2025-10-01 to 2026-09-30) and one FIRMADO file for `2026-08` **THE SYSTEM SHALL** return `validado` for August, `atrasado` for July, `pendiente_en_plazo` for September and `fuera` for October to December.
2. **WHEN** the OC validity ends 10 days after `hoy` and `dias_aviso_vencimiento_oc` is 60 **THE SYSTEM SHALL** set `vence_pronto` true on that row.
3. **WHEN** the calendar is returned **THE SYSTEM SHALL** give every cell a `letra` among `-`, `V`, `C`, `M`, `P`, `A` and `·` matching its state, so no state is conveyed by color alone.
4. **WHEN** a period without file ended 9 days before `hoy` and `dias_gracia` is 10 **THE SYSTEM SHALL** return `pendiente_en_plazo`, and 11 days before it SHALL return `atrasado`.
5. **WHEN** `GET /app.js` is requested **THE SYSTEM SHALL** serve an `app.js` whose text contains `leyenda-calendario` and each of the seven state names.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_calendario -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E4-T1: Calendario anual OC × meses con estados accesibles"
git tag step-22-calendario
```

### `E4-T2` — Pantalla Inicio con alertas ordenadas por urgencia

**Depends on:** `E4-T1` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `alertas(con, hoy, integridad_ok=True) -> list[dict]` con `{"tipo", "urgencia" (1 alta … 3
   baja), "mensaje", "oc", "expediente_id"}`, ordenadas por urgencia y fecha. Tipos: `base_con_errores` (urgencia 1, si
   `integridad_ok` es falso: `La base de datos tiene errores de integridad. Restaurá la última copia de seguridad desde Configuración.`),
   `periodo_atrasado` (1), `pendiente_vencido` (1, `fecha_seguimiento < hoy`), `oc_por_vencer` (2, ≤ `dias_aviso_vencimiento_oc`),
   `renglon_por_agotarse` (2), `comodato_sin_equipo` (2, OC con comodato sin ningún expediente con remito de equipo),
   `esperando_devolucion` (2, `CORRECTIVO` en `INFORME_ECONOMICO` o `EVENTUAL` en `EN_DTO_ECONOMICO_CONTABLE`),
   `listo_sin_entrega` (3, `FIRMADO` sin entrega), `informe_correctivos` (2, entre el 1.º y el 5.º día hábil del mes, lunes a
   viernes: `Enviar a GESP el informe mensual de correctivos del mes anterior.`).
2. `gestor/server.py` (editar): `GET /api/inicio/alertas?hoy=` (usa `httpd.integridad`).
3. `web/app.js` (editar): pantalla Inicio con la lista de alertas (ícono y palabra por urgencia: `Urgente`, `Atención`, `Para mirar`)
   y enlace a la OC o al expediente; si hay `base_con_errores`, banner rojo con botón "Restaurar última copia" (`POST /api/base/restaurar`).
4. `tests/test_inicio.py` — `PruebaInicio(ayudas.CasoConServidor)`: `test_orden_por_urgencia`, `test_pendiente_vencido`,
   `test_listo_sin_entrega`, `test_informe_correctivos_dias_habiles`, `test_base_con_errores_primero`.

**Files**

- `gestor/negocio.py` — edit: alertas
- `gestor/server.py` — edit: /api/inicio/alertas
- `web/app.js` — edit: pantalla Inicio
- `tests/test_inicio.py` — nuevo

**Acceptance**

1. **WHEN** alerts of urgencies 3, 1 and 2 exist **THE SYSTEM SHALL** return them from `GET /api/inicio/alertas` ordered 1, 2, 3.
2. **WHEN** a PENDIENTE file has `fecha_seguimiento` earlier than `hoy` **THE SYSTEM SHALL** return a `pendiente_vencido` alert with urgency 1 and its `expediente_id`.
3. **WHEN** a file is FIRMADO and has no delivery **THE SYSTEM SHALL** return a `listo_sin_entrega` alert.
4. **WHEN** `hoy` is 2026-09-07 (fifth business day of September 2026) **THE SYSTEM SHALL** include the `informe_correctivos` alert, and WHEN `hoy` is 2026-09-08 it SHALL not.
5. **WHEN** the server started with a failed integrity check **THE SYSTEM SHALL** return `base_con_errores` as the first alert with `mensaje` `La base de datos tiene errores de integridad. Restaurá la última copia de seguridad desde Configuración.`

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_inicio -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E4-T2: Pantalla Inicio con alertas ordenadas por urgencia"
git tag step-23-inicio-alertas
```

### `E4-T3` — Entregas y CSV con formato NUMERACIÓN

**Depends on:** `E3-T6` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `crear_entrega(con, efector, nombre)` (número correlativo por efector),
   `listar_entregas`, `asignar_a_entrega(con, entrega_id, version, ids)` (solo expedientes `FIRMADO` del mismo efector; si no →
   `ErrorNegocio("Solo se asignan expedientes FIRMADO del mismo efector.")`), `enviar_entrega(con, entrega_id, version, fecha)`
   (entrega `ENVIADA` + `fecha_envio`; cada expediente asignado pasa a `ENVIADO` con historial). Es la única vía a `ENVIADO`.
2. `gestor/exportes.py` (nuevo): `ENCABEZADOS_NUMERACION` y `filas_numeracion(con, entrega_id)`; `a_csv(encabezados, filas) -> bytes`
   (UTF-8 con BOM, separador `;`, fin de línea `\r\n`, módulo `csv`). Encabezado exacto, en una línea:
   `REMITO;SII;PERIODO;SAP;OC;FACTURA;IMPORTE;TEXTO SAP;TXT CABECERA;EXPEDIENTE;GDE CARATULA;GDE FACTURA;GDE SII;GDE OC;GDE REMITOS;GDE CV;GDE VALE/HOJA;GDE AUTORIZACION;GDE CONTABILIZACION`.
   Valores: remitos unidos con ` / `, `PERIODO` `MM-AA`, `IMPORTE` con `util.formato_pesos`, `TEXTO SAP` y `TXT CABECERA` de `textos_sap`.
3. `gestor/server.py` (editar): `GET /api/entregas`, `POST /api/entregas`, `GET /api/entregas/<id>`,
   `POST /api/entregas/<id>/asignar` (`{"version", "expedientes"}`), `POST /api/entregas/<id>/enviar` (`{"version", "fecha"}`),
   `GET /api/entregas/<id>/numeracion.csv` (`text/csv; charset=utf-8`, descarga).
4. `web/app.js` (editar): pantalla Entregas (alta, asignación, envío, descarga CSV).
5. `tests/test_entregas.py` — `PruebaEntregas(ayudas.CasoConServidor)`: `test_numero_correlativo_por_efector`,
   `test_asignar_solo_firmados`, `test_enviar_pasa_a_enviado`, `test_csv_encabezado_y_bom`, `test_csv_fila_efia`.

**Files**

- `gestor/negocio.py` — edit: entregas
- `gestor/exportes.py` — nuevo: CSV NUMERACIÓN
- `gestor/server.py` — edit: rutas /api/entregas
- `web/app.js` — edit: pantalla Entregas
- `tests/test_entregas.py` — nuevo

**Acceptance**

1. **WHEN** two deliveries are created for HBI and one for CASPH **THE SYSTEM SHALL** number them 1 and 2 for HBI and 1 for CASPH.
2. **WHEN** a BORRADOR file is assigned to a delivery **THE SYSTEM SHALL** answer 422 with `mensaje` `Solo se asignan expedientes FIRMADO del mismo efector.`
3. **WHEN** a delivery with the FIRMADO EFIA file is sent **THE SYSTEM SHALL** set the delivery to `ENVIADA` with its `fecha_envio` and the file to `ENVIADO`.
4. **WHEN** `GET /api/entregas/<id>/numeracion.csv` runs **THE SYSTEM SHALL** return bytes starting with the UTF-8 BOM followed by the header line `REMITO;SII;PERIODO;SAP;OC;FACTURA;IMPORTE;TEXTO SAP;TXT CABECERA;EXPEDIENTE;GDE CARATULA;GDE FACTURA;GDE SII;GDE OC;GDE REMITOS;GDE CV;GDE VALE/HOJA;GDE AUTORIZACION;GDE CONTABILIZACION` and CRLF line endings.
5. **WHEN** the EFIA file is in the delivery **THE SYSTEM SHALL** write a row whose `REMITO` is `00001-00029461`, `PERIODO` `08-26`, `SAP` `77170`, `OC` `4500555861`, `FACTURA` `0003B00031812`, `IMPORTE` `1.224.990,00` and `TEXTO SAP` `HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_entregas -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E4-T3: Entregas y CSV con formato NUMERACIÓN"
git tag step-24-entregas
```

### `E4-T4` — Pendientes, pantalla Configuración, apagado e Iniciar.bat

**Depends on:** `E4-T2`, `E4-T3` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `pendientes(con, hoy) -> list[dict]` (`id`, `proveedor`, `oc`, `periodo`, `motivo`,
   `fecha_seguimiento`, `dias_demora` = días desde `fecha_seguimiento` si ya pasó, si no 0), ordenados por `dias_demora` descendente.
2. `gestor/server.py` (editar): `GET /api/pendientes?hoy=`; `GET /api/config-local` y `PUT /api/config-local`
   (`{"base_datos"}`: guarda `config.json` con `config.guardar_config`; rige al reiniciar); `POST /api/base/backup` (copia manual
   inmediata); `POST /api/apagar` → responde `{"ok": true, "datos": {"apagando": true}}` y luego, en otro thread, `httpd.shutdown()`.
3. `web/app.js` (editar): pantalla Configuración (ubicación de la base, centros por efector, partidas excluidas, exclusiones
   manuales, días de gracia, umbrales, límite del Texto SAP, emails, botones "Copia de seguridad ahora" y "Cerrar programa")
   y lista de pendientes dentro de Expedientes.
4. `Iniciar.bat` (nuevo, ASCII, fin de línea CRLF), exactamente:
   ```bat
   @echo off
   rem Gestor de expedientes de pago - doble clic para abrir
   cd /d "%~dp0"
   where pythonw >nul 2>nul && (start "" /b pythonw app.py & exit /b 0)
   where pyw >nul 2>nul && (start "" /b pyw -3 app.py & exit /b 0)
   where py >nul 2>nul && (start "" /b py -3 app.py & exit /b 0)
   echo No se encontro Python 3.10 o superior en esta PC.
   echo Instalarlo desde https://www.python.org/downloads/windows/ marcando "Add python.exe to PATH" y volver a hacer doble clic.
   pause
   exit /b 1
   ```
5. `tests/test_pendientes_config.py` — `PruebaPendientesConfig(ayudas.CasoConServidor)`: `test_pendientes_ordenados_por_demora`,
   `test_config_local_guarda_base_datos`, `test_backup_manual`, `test_apagar_detiene_el_servidor`,
   `test_iniciar_bat_prueba_los_tres_lanzadores_en_orden`.

**Files**

- `gestor/negocio.py` — edit: pendientes
- `gestor/server.py` — edit: pendientes, config local, backup manual, apagar
- `web/app.js` — edit: Configuración y Pendientes
- `Iniciar.bat` — nuevo: lanzador de doble clic
- `tests/test_pendientes_config.py` — nuevo

**Acceptance**

1. **WHEN** two PENDIENTE files have follow-up dates 5 and 2 days before `hoy` **THE SYSTEM SHALL** list them from `GET /api/pendientes` with `dias_demora` 5 first and 2 second.
2. **WHEN** `PUT /api/config-local` receives a new `base_datos` **THE SYSTEM SHALL** write it to the file named by `GESTOR_CONFIG` keeping every other key.
3. **WHEN** `POST /api/base/backup` runs **THE SYSTEM SHALL** create one more `expedientes-AAAAMMDD-HHMMSS.db` in the backup folder.
4. **WHEN** `POST /api/apagar` runs **THE SYSTEM SHALL** answer `{"ok": true, "datos": {"apagando": true}}` and stop accepting connections within 5 seconds.
5. **WHEN** `Iniciar.bat` is read **THE SYSTEM SHALL** contain `start "" /b pythonw app.py`, `start "" /b pyw -3 app.py` and `start "" /b py -3 app.py` in that order, followed by the message `No se encontro Python 3.10 o superior en esta PC.`

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_pendientes_config -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E4-T4: Pendientes, pantalla Configuración, apagado e Iniciar.bat"
git tag step-25-pendientes-y-configuracion
```

### `E4-T5` — Escritor .xlsx propio, vista imprimible y seis exportes

**Depends on:** `E4-T4` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/xlsx_escritor.py` (nuevo): `escribir_xlsx(destino, nombre_hoja, titulo, encabezados, filas, columnas_moneda=())`
   — zip con `[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/styles.xml`,
   `xl/worksheets/sheet1.xml`; cadenas como `inlineStr`; fila 1 = `titulo` (incluye `Emitido el dd/mm/aaaa`), fila 2 =
   encabezados en negrita (estilo 1), montos como número con `numFmt` `#,##0.00` (estilo 2). Sin `sharedStrings`.
2. `gestor/exportes.py` (editar): seis exportes, cada uno `(titulo, encabezados, filas, columnas_moneda)`:
   `consumo-oc` (`?oc=`; encabezado de la OC y por renglón cantidad, precio, consumido por período, total, saldo, % y expedientes),
   `seguimiento-oc` (`?efector=&q=`; vigencia, estado, % consumido, renglones por agotarse, último período validado),
   `pendientes`, `entrega` (`?id=`; columnas NUMERACIÓN del paso 24), `calendario` (`?anio=`), `centralizadas` (`?periodo=`;
   OC, período, remito, N° de CV, N° de nota, fecha de envío). `a_html(...)`: página imprimible con `<table>` y
   `@media print` (sin menú). CSV con `a_csv`.
3. `gestor/server.py` (editar): `GET /api/exportes/<nombre>.<xlsx|csv|html>`; nombre desconocido → 404 `no_encontrado`.
4. `web/app.js` (editar): botones "Excel", "CSV" e "Imprimir" en OC, Expedientes, Entregas, Calendario y Centralizadas.
5. `tests/test_exportes.py` — `PruebaExportes(ayudas.CasoConServidor)`: `test_xlsx_roundtrip_consumo_efia` (relee con
   `gestor.xlsx.leer_filas` y obtiene los mismos valores), `test_xlsx_partes_minimas`, `test_csv_bom_y_punto_y_coma`,
   `test_html_imprimible`, `test_seis_exportes_responden`, `test_exporte_desconocido_404`.

**Files**

- `gestor/xlsx_escritor.py` — nuevo: escritor .xlsx
- `gestor/exportes.py` — edit: seis exportes y HTML imprimible
- `gestor/server.py` — edit: /api/exportes
- `web/app.js` — edit: botones de exporte
- `tests/test_exportes.py` — nuevo

**Acceptance**

1. **WHEN** `GET /api/exportes/consumo-oc.xlsx?oc=4500555861` runs **THE SYSTEM SHALL** return a zip containing `[Content_Types].xml`, `xl/workbook.xml` and `xl/worksheets/sheet1.xml`, and reading it back with `gestor.xlsx.leer_filas` SHALL return the same headers and cell values the export produced.
2. **WHEN** any of the six exports (`consumo-oc`, `seguimiento-oc`, `pendientes`, `entrega`, `calendario`, `centralizadas`) is requested as `.xlsx`, `.csv` and `.html` **THE SYSTEM SHALL** answer 200 for each.
3. **WHEN** a `.csv` export is requested **THE SYSTEM SHALL** return bytes that start with the UTF-8 BOM and use `;` as separator.
4. **WHEN** a `.html` export is requested **THE SYSTEM SHALL** return a page containing a `<table>` and an `@media print` rule.
5. **WHEN** `GET /api/exportes/inexistente.xlsx` runs **THE SYSTEM SHALL** answer 404 with `codigo` `no_encontrado`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_exportes -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E4-T5: Escritor .xlsx propio, vista imprimible y seis exportes"
git tag step-26-exportes
```

---

## Epic acceptance

El epic está terminado cuando todas sus tareas están `done` **y**:

1. **WHEN** the EFIA file is FIRMADO and its delivery is sent **THE SYSTEM SHALL** show August 2026 as `validado` with the `entrega_enviada` mark and include it in the NUMERACIÓN CSV.
2. **WHEN** every export is requested in its three formats **THE SYSTEM SHALL** answer 200 and the `.xlsx` files SHALL read back with the project's own reader.

```bash
python -W error::DeprecationWarning -m unittest tests.test_calendario -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_entregas -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_exportes -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

## Pitfalls

- **Fechas relativas a "hoy" en los tests** — siempre pasar `hoy` explícito.
- **`shutdown()` desde el mismo thread que atiende** — se cuelga; `POST /api/apagar` lo llama desde otro thread.
- **Excel que no abre** — falta `[Content_Types].xml` o un `rels`; el roundtrip lo detecta.

## Before moving on

- [ ] Cada tarea de este epic está `done` en `tasks.json`; ninguna quedó `in_progress`.
- [ ] Pasaron **todos** los comandos `verify` de cada tarea, no solo el primero.
- [ ] Ningún comando `verify` fue editado ni salteado.
- [ ] Cada tarea tiene su tag de checkpoint: `git tag -l 'step-*'` lista `step-22-calendario`, `step-23-inicio-alertas`, `step-24-entregas`, `step-25-pendientes-y-configuracion`, `step-26-exportes`.
- [ ] El gate (`python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`) sale 0 desde la raíz.
- [ ] Cada contrato "Produced" existe con la firma indicada.
- [ ] Ningún archivo fuera del árbol fue modificado; `plantillas/`, `tests/fixtures/` y `tests/ayudas.py` siguen intactos.
- [ ] Este proyecto no tiene `.env` ni `.env.example`: la única variable de entorno es `GESTOR_CONFIG` (§10), opcional.
- [ ] Un commit por tarea, con el id de la tarea como prefijo, seguido de su tag.
