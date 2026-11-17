# Epic 02: Expediente común con controles

> Existe el expediente común completo hasta los controles: alta con versión, remitos múltiples, período sugerido, parser de SII, consumo y saldo, motor de controles con notas aclaratorias y el asistente pasos 1–4.

| | |
|---|---|
| **Epic id** | `02-expediente-comun` |
| **Tasks** | `E2-T1` … `E2-T7` (pasos 9–15 de `blueprint.md` §9) |
| **Depends on** | `01-nucleo-y-oc` |
| **Unlocks** | `03-salidas-y-prototipo` |
| **Parallel with** | ninguno |

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
gestor/
  negocio.py        # existe — se agregan expedientes, remitos, período, consumo, notas
  server.py         # existe — rutas /api/expedientes/*, /api/comprobantes/analizar, /api/oc/<n>/consumo
  comprobantes.py   # NUEVO (paso 11) — parser SII
  util.py           # existe — se agrega normalizar_domicilio (paso 11)
  controles.py      # NUEVO (paso 13), editado (paso 14)
web/
  index.html  app.js  style.css   # existen — asistente pasos 1–4 (paso 15)
tests/
  datos_prueba.py   # existe — se agregan armar_expediente_efia/biofab/macatex (paso 13)
  test_expedientes_api.py test_periodo_remitos.py test_comprobantes.py test_consumo.py
  test_controles.py test_notas.py test_web_asistente.py   # NUEVOS
  fixtures/expedientes/*/0004_IF-*.txt   # provistos — textos SII reales
```

Todo lo que está fuera de este árbol queda fuera de alcance. Si una tarea parece exigir editar otro archivo, parar y reportarlo.

## Data model touched here

| Entidad | Campos | Notas |
|---|---|---|
| `expediente` | `tipo`, `efector`, `oc`, `sap`, `periodo`, `periodo_desde`, `periodo_hasta`, `periodo_manual`, `factura`, `estado`, `motivo_anulacion`, `datos`, `version` | ver esquema en el epic 01 |
| `expediente.datos` (JSON) | `remitos[]` (`numero`, `fecha`, `fecha_firma`, `es_equipo_comodato`, `aclara_periodo`, `items[]` con `pos`, `cantidad`, `codigo`), `factura` (`numero`, `fecha`, `centavos`, `cae`, `vto_cae`, `destinatario`, `domicilio`, `periodo_desde`, `periodo_hasta`, `menciona`), `sii` (salida de `comprobantes.analizar_texto_sii`), `gde`, `sap`, `notas_aclaratorias[]`, `checklist`, `correctivo`, `eventual`, `centralizada`, `historial[]` | claves de primer nivel se reemplazan enteras al editar |
| `renglon` | `consumo_previo`, `desglose_*` | se leen para consumo y saldo |

## Contracts

**Consumed** — ya existe, no reconstruir:

| From | Interface | Guarantee |
|---|---|---|
| `01-nucleo-y-oc` | `db.transaccion`, `db.actualizar_con_version`, `db.ConflictoVersion` | 409 con el mensaje fijo |
| `01-nucleo-y-oc` | `util.periodo_de_fecha`, `util.normalizar_factura`, `util.misma_factura` | puras |
| `01-nucleo-y-oc` | `negocio.crear_oc_manual`, `tests/datos_prueba.py` | OC EFIA manual y BIO FAB/MACATEX importadas |

**Produced** — los epics siguientes dependen de estas firmas exactas:

| Export | Signature | Used by |
|---|---|---|
| `gestor/negocio.py` → `crear_expediente`, `actualizar_expediente`, `anular_expediente`, `periodo_sugerido`, `consumo_por_renglon`, `guardar_nota` | ver pasos 9–14 | `03`–`05` |
| `gestor/comprobantes.py` → `analizar_texto_sii` | `analizar_texto_sii(texto) -> dict` | `03` |
| `gestor/controles.py` → `controlar`, `armar_contexto`, `CONTROLES`, `NOTAS` | `controlar(con, id) -> {"resultados", "resumen"}` | `03`–`05` |
| `tests/datos_prueba.py` → `armar_expediente_efia(con)`, `armar_expediente_biofab(con, con_equipo=True)`, `armar_expediente_macatex(con)` | cada una devuelve el `id` del expediente creado | `03`–`05` |

## Conventions that bite in this area

- El período sale del **remito** (fecha de firma si la hay), nunca de la factura.
- El remito del equipo en comodato no cuenta para cantidades ni para el control de período, y solo se exige en la primera validación.
- Un error de **importe** nunca es salvable.
- Los controles no leen la base: reciben `ctx` armado una vez por `armar_contexto`.
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

### `E2-T1` — API de expedientes: alta, versión, historial y anulación

**Depends on:** `E1-T8` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `crear_expediente(con, datos)`, `obtener_expediente(con, id)`,
   `listar_expedientes(con, estado=None, tipo=None, periodo=None, sap=None, entrega=None, efector=None)`,
   `actualizar_expediente(con, id, version, cambios)`, `anular_expediente(con, id, version, motivo)`.
   - Alta: `tipo` (`COMUN`, `CENTRALIZADA`, `CORRECTIVO`, `EVENTUAL`), `efector`, `oc` (obligatoria salvo `EVENTUAL`), `sap`
     copiado de la OC, `estado = "BORRADOR"`, `creado = actualizado = db.ahora_utc()`, `usuario = getpass.getuser()`,
     `datos` = estructura de la sección *expediente.datos* (§4) con listas vacías, y una entrada en `datos.historial`
     `{"fecha", "usuario", "accion": "ALTA", "estado": "BORRADOR"}`.
   - Edición: `cambios` puede traer columnas (`periodo`, `periodo_desde`, `periodo_hasta`, `periodo_manual`, `motivo_pendiente`,
     `fecha_seguimiento`) y `datos` (las claves de primer nivel de `datos` se reemplazan). Si viene `datos.factura.numero` se
     guarda también la columna `factura` normalizada (`util.normalizar_factura` → `"<pv:04d><letra><numero:08d>"`).
     Cada edición agrega una entrada a `datos.historial` y actualiza `actualizado`.
   - Anulación: motivo vacío → `ErrorValidacion("Indicá el motivo de la anulación.")`; si no, `estado = "ANULADO"`,
     `motivo_anulacion`, evento `ANULACION`. Un expediente `ANULADO` no se edita: `ErrorNegocio("El expediente está anulado.")`.
2. `gestor/server.py` (editar): `GET /api/expedientes` (filtros por query string), `POST /api/expedientes`,
   `GET /api/expedientes/<id>`, `PUT /api/expedientes/<id>` (`{"version", "cambios"}`), `POST /api/expedientes/<id>/anular`
   (`{"version", "motivo"}`). La respuesta de un expediente incluye `datos` ya decodificado.
3. `tests/test_expedientes_api.py` — `PruebaExpedientesApi(ayudas.CasoConServidor)`: `test_crear_expediente_borrador`,
   `test_editar_incrementa_version_y_audita`, `test_editar_con_version_vieja_da_409`, `test_anular_sin_motivo_da_400`,
   `test_anular_conserva_la_fila`, `test_listar_filtra_por_estado_y_periodo`, `test_editar_anulado_da_422`.

**Files**

- `gestor/negocio.py` — edit: expedientes
- `gestor/server.py` — edit: rutas /api/expedientes
- `tests/test_expedientes_api.py` — nuevo

**Acceptance**

1. **WHEN** `POST /api/expedientes` creates a `COMUN` file for OC 4500555861 **THE SYSTEM SHALL** store `estado` `BORRADOR`, `version` 1, `sap` `77170`, `usuario` equal to `getpass.getuser()` and one `datos.historial` entry with `accion` `ALTA`.
2. **WHEN** `PUT /api/expedientes/<id>` saves with the current `version` **THE SYSTEM SHALL** answer with `version` 2 and write one `evento` row with `accion` `MODIFICACION`; with a stale `version` it SHALL answer 409 with `mensaje` `Otra persona guardó cambios en este registro. Recargá para ver la última versión.`
3. **WHEN** `POST /api/expedientes/<id>/anular` arrives with an empty `motivo` **THE SYSTEM SHALL** answer 400 with `mensaje` `Indicá el motivo de la anulación.`
4. **WHEN** a file is annulled with a reason **THE SYSTEM SHALL** keep its row with `estado` `ANULADO` and the reason, and a later `PUT` on it SHALL answer 422 with `mensaje` `El expediente está anulado.`
5. **WHEN** `GET /api/expedientes?estado=BORRADOR&periodo=2026-08` runs **THE SYSTEM SHALL** return only files in that state and period.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_expedientes_api -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T1: API de expedientes: alta, versión, historial y anulación"
git tag step-09-expedientes-api
```

### `E2-T2` — Período sugerido y carga rápida de varios remitos

**Depends on:** `E2-T1` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar):
   - `parsear_remitos_pegados(texto) -> list[dict]`: una línea por remito `numero;fecha[;fecha_firma]` (fechas `dd/mm/aaaa`),
     líneas vacías ignoradas; línea mal formada → `ErrorValidacion('Línea <n>: se esperaba "numero;fecha[;fecha_firma]".')`.
     Cada remito queda `{"numero", "fecha", "fecha_firma", "es_equipo_comodato": false, "aclara_periodo": false, "items": []}`
     con fechas ISO. `items` = `[{"pos", "cantidad", "codigo"}]` (el código como figura en el remito; vacío = igual a la OC).
   - `fecha_base(remito)` = `fecha_firma` si existe, si no `fecha`.
   - `periodo_sugerido(oc, remitos) -> util.Periodo`: usa el remito NO de equipo con la fecha base más reciente y
     `util.periodo_de_fecha(fecha_base, oc["dia_inicio_periodo"])`.
   - `remitos_fuera_de_periodo(periodo, remitos) -> list[str]`: números de remito (no de equipo, sin `aclara_periodo`) cuya
     fecha base cae fuera de `periodo.desde`..`periodo.hasta`.
   - Al pegar remitos, si `periodo_manual == 0` el expediente toma el período sugerido (`periodo`, `periodo_desde`, `periodo_hasta`).
     Cambiar el período a mano pone `periodo_manual = 1` y agrega al historial `{"accion": "PERIODO_MANUAL", ...}`.
2. `gestor/server.py` (editar): `POST /api/expedientes/<id>/remitos/pegar` (`{"version", "texto", "es_equipo_comodato"}`) →
   expediente actualizado + `periodo_sugerido` + `fuera_de_periodo`.
3. `tests/test_periodo_remitos.py` — `PruebaPeriodoRemitos(ayudas.CasoConServidor)`: `test_pegar_tres_lineas_con_fecha_firma`,
   `test_linea_invalida_informa_numero`, `test_periodo_sugerido_usa_remito_mas_reciente`, `test_periodo_especifico_dia_17`,
   `test_esterisur_quince_mas_uno`, `test_periodo_manual_queda_registrado`. Para Esterisur el test arma una OC manual de servicio
   (día de inicio 1) y pega 15 remitos de agosto de 2026 y 1 de julio de 2026.

**Files**

- `gestor/negocio.py` — edit: remitos y período sugerido
- `gestor/server.py` — edit: ruta de pegado de remitos
- `tests/test_periodo_remitos.py` — nuevo

**Acceptance**

1. **WHEN** the text `0001-00000001;05/08/2026` + newline + `0001-00000002;28/08/2026;02/09/2026` is pasted into a file whose OC starts periods on day 1 **THE SYSTEM SHALL** store two remitos and suggest period `2026-09`, because the newest base date is the signature date 2026-09-02.
2. **WHEN** the second pasted line is `0001-00000003` without a date **THE SYSTEM SHALL** answer 400 with `mensaje` `Línea 2: se esperaba "numero;fecha[;fecha_firma]".` and store no remito.
3. **WHEN** the OC starts periods on day 17 and the only remito is dated 20/10/2026 **THE SYSTEM SHALL** set `periodo` `2026-11`, `periodo_desde` `2026-10-17` and `periodo_hasta` `2026-11-16`.
4. **WHEN** 15 remitos dated August 2026 and 1 dated July 2026 are pasted **THE SYSTEM SHALL** suggest `2026-08` and `remitos_fuera_de_periodo` SHALL return exactly the July remito.
5. **WHEN** the period is changed by hand **THE SYSTEM SHALL** store `periodo_manual` 1 and a `datos.historial` entry with `accion` `PERIODO_MANUAL`, and later pastes SHALL not overwrite that period.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_periodo_remitos -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T2: Período sugerido y carga rápida de varios remitos"
git tag step-10-periodo-y-remitos
```

### `E2-T3` — Parser del texto pegado de SII y normalización de factura

**Depends on:** `E1-T3` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/comprobantes.py` (nuevo, funciones puras):
   - `analizar_texto_sii(texto) -> dict` sobre el texto "Factura de Proveedor / Sistema de Autogestión de Comprobantes
     Electrónicos" (formato de `tests/fixtures/expedientes/*/0004_IF-*.txt`). Extrae por rótulo (`CAE:`, `Fecha de emisión:`,
     `Período:`, `Monto:`, `Tipo de Comprobante:`, `Nro Comprobante:`, `Razón Social:`, `CUIT:`, `Nro SAP:`, `Área:`,
     `Tipo de Servicio:`, `Concepto:`, `Orden de Compra:`, `Cod. Trámite:`) y devuelve
     `{"cae", "fecha_emision" (ISO), "periodo", "monto_centavos", "tipo_comprobante", "nro_comprobante" ("0003-00031812"),
     "letra" (la última letra de "FACTURA B"), "razon_social", "cuit", "sap", "area", "tipo_servicio", "concepto",
     "orden_compra", "cod_tramite", "faltantes": [rótulos no encontrados]}`.
   - `cae_valido(cae) -> bool` (14 dígitos). `vencimiento_cae_ok(fecha_emision, vto) -> bool | None` (`None` si no hay vto).
2. `gestor/util.py` (editar): `normalizar_domicilio(s) -> str`: mayúsculas, sin tildes, signos de puntuación quitados (cada uno
   de `.,;:-/` se borra), espacios colapsados: `"Perú 169, C.A.B.A."` → `"PERU 169 CABA"`, `"Perú 169 CABA"` → `"PERU 169 CABA"`.
   Va en `util` (no en `comprobantes`) porque la usan `comprobantes` y `controles`, y `controles` solo importa `util` y `letras`.
3. `gestor/server.py` (editar): `POST /api/comprobantes/analizar` (`{"texto"}`) → `{"ok": true, "datos": <dict>}`.
4. `tests/test_comprobantes.py` — `PruebaComprobantes(unittest.TestCase)`: `test_sii_efia`, `test_sii_biofab`, `test_sii_macatex`
   (leen el `0004_IF-*.txt` de cada carpeta con `ayudas.texto_fixture`), `test_texto_incompleto_lista_faltantes`,
   `test_normalizar_domicilio`, `test_factura_equivale_a_nro_sii`.

**Files**

- `gestor/comprobantes.py` — nuevo: parser SII, CAE y vencimiento
- `gestor/util.py` — edit: normalizar_domicilio
- `gestor/server.py` — edit: /api/comprobantes/analizar
- `tests/test_comprobantes.py` — nuevo

**Acceptance**

1. **WHEN** the EFIA fixture `EX-2026-89654857_EFIA/0004_IF-*.txt` is parsed **THE SYSTEM SHALL** return CAE `86372407008783`, `fecha_emision` `2026-09-10`, `periodo` `2026-08`, `monto_centavos` 122499000, `tipo_comprobante` `FACTURA B`, `nro_comprobante` `0003-00031812`, `sap` `77170`, `orden_compra` `4500555861`, `area` `GESP - MESA DE ENTRADAS Y SALIDAS - HOSPITAL DEL BICENTENARIO ITUZAINGO` and `cod_tramite` `HXW2037078`.
2. **WHEN** the BIO FAB fixture `EX-2026-94963848_BIOFAB/0004_IF-*.txt` is parsed **THE SYSTEM SHALL** return CAE `86372594419176`, `fecha_emision` `2026-09-11`, `periodo` `2026-08`, `monto_centavos` 2109500000, `nro_comprobante` `0002-00003908`, `orden_compra` `4500587121` and `cuit` `30-71172660-4`.
3. **WHEN** the MACATEX fixture `EX-2026-99349179_MACATEX/0004_IF-*.txt` is parsed **THE SYSTEM SHALL** return CAE `86416949757962`, `fecha_emision` `2026-10-09`, `periodo` `2026-09`, `monto_centavos` 3388160000, `nro_comprobante` `0002-00000160` and `orden_compra` `4500594643`.
4. **WHEN** the pasted text has no `CAE:` label **THE SYSTEM SHALL** return `cae` `None` and list `CAE` in `faltantes` instead of failing.
5. **WHEN** `util.misma_factura` compares the invoice `0003B00031812` with the SII number `0003-00031812` **THE SYSTEM SHALL** report them as the same invoice.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_comprobantes -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T3: Parser del texto pegado de SII y normalización de factura"
git tag step-11-comprobantes
```

### `E2-T4` — Consumo, saldo y grilla renglón × período

**Depends on:** `E2-T2` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar):
   - `cantidades_del_expediente(exp) -> dict[int, Decimal]`: suma por `pos` de `items` de los remitos que NO son de equipo.
   - `consumo_por_renglon(con, oc) -> list[dict]` por renglón: `cantidad_oc` (desglose si existe, si no `cantidad`), `unidad`,
     `consumo_previo`, `validado` (suma de expedientes no `ANULADO` de la OC), `saldo = cantidad_oc − consumo_previo − validado`,
     `ideal_mes = cantidad_oc / meses de vigencia del renglón` (1 si el desglose es `MES`), `pct_consumido` (entero, redondeo
     half-up), `por_agotarse` (`saldo < ideal_mes` o `pct_consumido >= umbral_por_agotarse_pct`), `por_periodo` {`AAAA-MM`: cantidad}.
   - `grilla(con, oc) -> {"periodos": [...], "filas": [...]}`: una columna por período de la vigencia (OC sin fin de vigencia →
     una sola columna `unica`).
2. `gestor/server.py` (editar): `GET /api/oc/<numero>/consumo` → `{"renglones": [...], "grilla": {...}}`.
3. `tests/test_consumo.py` — `PruebaConsumo(ayudas.CasoConServidor)`: `test_efia_un_mes_validado`, `test_anulado_no_cuenta`,
   `test_consumo_previo_reduce_saldo`, `test_grilla_doce_periodos_de_vigencia`, `test_por_agotarse`.

**Files**

- `gestor/negocio.py` — edit: consumo y saldo
- `gestor/server.py` — edit: /api/oc/<numero>/consumo
- `tests/test_consumo.py` — nuevo

**Acceptance**

1. **WHEN** OC 4500555861 (9 `MES`) has one non-annulled file for `2026-08` with quantity 1 **THE SYSTEM SHALL** report for position 1 `validado` 1, `saldo` 8, `ideal_mes` 1 and `pct_consumido` 11.
2. **WHEN** that file is annulled **THE SYSTEM SHALL** report `validado` 0 and `saldo` 9.
3. **WHEN** `consumo_previo` 5 is saved on position 1 **THE SYSTEM SHALL** report `saldo` 3 with the `2026-08` file still counted.
4. **WHEN** `GET /api/oc/4500555861/consumo` runs **THE SYSTEM SHALL** return a grid whose periods go from `2025-10` to `2026-09` (12 columns) with quantity 1 under `2026-08`.
5. **WHEN** validated quantity leaves a balance lower than `ideal_mes` **THE SYSTEM SHALL** set `por_agotarse` true for that row.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_consumo -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T4: Consumo, saldo y grilla renglón × período"
git tag step-12-consumo-y-saldo
```

### `E2-T5` — Motor de controles con cuatro niveles

**Depends on:** `E2-T3`, `E2-T4` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/controles.py` (nuevo):
   - `NIVELES = ("error", "salvable", "aviso", "verificar")`; `Resultado(codigo, nivel, ambito, mensaje, referencia=None)`
     (NamedTuple; `referencia` = número de remito o de renglón cuando aplica).
   - `armar_contexto(con, expediente_id) -> dict` (OC, proveedor, renglones, consumo del paso 12, expediente, parámetros,
     otros expedientes de la OC). Los controles NO leen la base: reciben `ctx`.
   - `CONTROLES`: lista de funciones `control_<codigo>(ctx) -> list[Resultado]`; `controlar(con, id) -> {"resultados": [...],
     "resumen": {"error": n, "salvable": n, "aviso": n, "verificar": n}}`.
   - Controles y niveles (tabla completa en §5 *Controles del expediente*): `importe_factura` (error, nunca salvable: importe ≠
     Σ cantidad × precio exacto al centavo), `destinatario_factura` (error si `datos.factura.destinatario` en mayúsculas ≠
     `parametros.destinatario_factura.nombre` = `INSSJP`), `domicilio_factura` (error si
     `util.normalizar_domicilio(datos.factura.domicilio)` NO empieza con `parametros.destinatario_factura.domicilio` = `PERU 169`),
     `periodo_factura` (salvable si `datos.factura.periodo_desde`/`periodo_hasta` existen y no caen en el período validado;
     **sin resultado** si la factura no trae período), `menciones_factura` (salvable por cada clave de `datos.factura.menciona`
     — `oc`, `expediente`, `remito` — cuyo valor difiere del real; **sin resultado** si `menciona` falta o está vacío), `formato_factura` (error: N°, CAE de 14 dígitos), `vencimiento_cae` (error si
     vence antes de la emisión; `verificar` si no hay vencimiento), `factura_repetida` (error), `sii_coincide` (error: OC, N°,
     CAE y monto), `sii_periodo` (error), `sii_destino` (error: área, tipo de servicio, concepto de `parametros.sii`),
     `remito_fuera_de_periodo` (error, uno por remito), `codigo_remito_distinto` (salvable, uno por renglón),
     `formato_remito` (aviso, `^\d{4,5}-\d{8}$`), `vigencia_oc` (error), `saldo_renglon` (error),
     `comodato_sin_remito_equipo` (error), `expediente_duplicado` (aviso), `renglon_por_agotarse` (aviso),
     `objeto_faltante` (error), `documentacion_centralizada` (error; se completa en el paso 27).
   - Mensajes exactos que los tests fijan: `Falta el objeto de la contratación en la OC 4500594643`;
     `Primera validación de OC con comodato sin remito del equipo.`;
     `El importe de la factura ($ 1.224.990,01) no coincide con cantidad × precio ($ 1.224.990,00).`;
     `El remito <numero> (<dd/mm/aaaa>) está fuera del período <AAAA-MM>.`;
     `El remito <numero> indica el código <codigo_remito> en el renglón <pos>; la OC tiene <codigo_oc>.`
   - Primera validación = no hay otro expediente no anulado de la misma OC en estado `CONTROLADO` o posterior.
2. `gestor/server.py` (editar): `GET /api/expedientes/<id>/controles`.
3. `tests/datos_prueba.py` (editar): `armar_expediente_efia(con)` (OC manual EFIA, remito `00001-00029461` del 31/08/2026 con
   cantidad 1 en el renglón 1, factura `0003B00031812` del 10/09/2026 por 122499000 centavos, destinatario `INSSJP`, domicilio
   `Perú 169 CABA`, CAE `86372407008783` sin vencimiento, SII del fixture EFIA), `armar_expediente_biofab(con, con_equipo=True)`
   (remito `0001-00003354` del 25/08/2026 con 1000/400/200/150 y código `5002383` en el renglón 2; remito de equipo
   `0001-00003281`; factura `00002B00003908` del 11/09/2026 por 2109500000 centavos, destinatario `INSSJP`, domicilio
   `Perú 169 CABA`, CAE `86372594419176`, vto CAE 21/09/2026; SII BIO FAB),
   `armar_expediente_macatex(con)` (remito `0001-00004409` del 07/09/2026 con las cantidades totales de los 6 renglones;
   factura `0002B00000160` del 09/10/2026 por 3388160000 centavos, destinatario `INSSJP`, domicilio `Perú 169 CABA`,
   CAE `86416949757962`, vto CAE 19/10/2026; SII MACATEX). Ninguna de las tres facturas trae `periodo_desde`/`periodo_hasta`
   ni `menciona`, así que `periodo_factura` y `menciones_factura` no dan resultado; EFIA sin vto CAE da `vencimiento_cae`
   en nivel `verificar` (no `error`). Con esas reglas literales: EFIA 0 error y 0 salvable; BIO FAB 0 error y 1 salvable;
   MACATEX exactamente 1 error (`objeto_faltante`) y 0 salvable.
4. `tests/test_controles.py` — `PruebaControles(ayudas.CasoConEntorno)`: `test_efia_sin_errores_ni_salvables`,
   `test_biofab_codigo_distinto_es_salvable`, `test_biofab_sin_remito_de_equipo_es_error`, `test_macatex_objeto_faltante`,
   `test_un_centavo_de_diferencia_es_error_no_salvable`, `test_esterisur_un_remito_fuera_de_periodo`.

**Files**

- `gestor/controles.py` — nuevo: motor y controles
- `gestor/server.py` — edit: /api/expedientes/<id>/controles
- `tests/datos_prueba.py` — edit: expedientes reales EFIA, BIO FAB y MACATEX
- `tests/test_controles.py` — nuevo

**Acceptance**

1. **WHEN** the EFIA file (manual OC 4500555861, remito `00001-00029461` of 31/08/2026 with quantity 1, invoice `0003B00031812` for 122499000 centavos, EFIA SII) is controlled **THE SYSTEM SHALL** use period `2026-08` and report 0 `error` and 0 `salvable` results.
2. **WHEN** the BIO FAB file (OC 4500587121 with `comodato` 1, remito `0001-00003354` whose position 2 carries code `5002383`, equipment remito `0001-00003281`) is controlled **THE SYSTEM SHALL** report exactly one `salvable` result with `codigo` `codigo_remito_distinto` and 0 `error` results.
3. **WHEN** the same BIO FAB file has no equipment remito **THE SYSTEM SHALL** report an `error` with `codigo` `comodato_sin_remito_equipo` and `mensaje` `Primera validación de OC con comodato sin remito del equipo.`
4. **WHEN** the MACATEX file (OC 4500594643 with empty `objeto`, remito `0001-00004409` of 07/09/2026) is controlled **THE SYSTEM SHALL** use period `2026-09` and report the `error` `objeto_faltante` with `mensaje` `Falta el objeto de la contratación en la OC 4500594643`.
5. **WHEN** the EFIA invoice amount is 122499001 centavos **THE SYSTEM SHALL** report the `error` `importe_factura` with `mensaje` `El importe de la factura ($ 1.224.990,01) no coincide con cantidad × precio ($ 1.224.990,00).` and no `salvable` result for the amount.
6. **WHEN** a file has 15 remitos of August 2026 and 1 of July 2026 **THE SYSTEM SHALL** report exactly one `remito_fuera_de_periodo` error, referencing the July remito.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_controles -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T5: Motor de controles con cuatro niveles"
git tag step-13-controles
```

### `E2-T6` — Notas aclaratorias redactadas para controles salvables

**Depends on:** `E2-T5` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/controles.py` (editar): `NOTAS: dict[codigo, funcion(resultado, ctx) -> str]` para cada control `salvable`;
   `controlar` agrega a cada resultado salvable `nota_sugerida` y `nota_guardada` (de `datos.notas_aclaratorias`), y el resumen
   suma `salvable_con_nota`. Un resultado `error` nunca tiene `nota_sugerida`.
   Texto exacto para `codigo_remito_distinto`:
   `Se deja constancia de que en el remito N° <remito> el renglón <pos> figura con el código <codigo_remito>, cuando el código correcto según la Orden de Compra N° <oc> es <codigo_oc>. Se trata de un error de tipeo que no afecta lo entregado.`
   Texto exacto para `periodo_factura` (`<periodo_factura>` = `periodo_desde[:7]` en forma `AAAA-MM` si `periodo_desde` y
   `periodo_hasta` caen en el mismo mes; si no, `dd/mm/aaaa al dd/mm/aaaa`; `test_nota_periodo_factura_exacta` carga en la factura EFIA
   `periodo_desde` 2026-07-01 y `periodo_hasta` 2026-07-31, así que la nota dice `2026-07`):
   `Se deja constancia de que la factura N° <factura> indica el período <periodo_factura>, cuando el período validado según remito es <periodo_validado>.`
   Texto exacto para `menciones_factura`:
   `Se deja constancia de que la factura N° <factura> menciona <dato> <valor_factura>, cuando corresponde <valor_real>.`
   (`<dato>` ∈ `la Orden de Compra N°`, `el expediente`, `el remito N°`).
2. `gestor/negocio.py` (editar): `guardar_nota(con, id, version, codigo, referencia, texto)` → agrega o reemplaza en
   `datos.notas_aclaratorias` `{"codigo", "referencia", "texto", "usuario", "fecha"}`. Si `codigo` no es de un control
   `salvable` (por ejemplo `importe_factura`) → `ErrorNegocio("Un error de importe no se salva con nota aclaratoria.")` cuando
   es `importe_factura`, y `ErrorNegocio("Ese control no admite nota aclaratoria.")` para los demás.
3. `gestor/server.py` (editar): `POST /api/expedientes/<id>/notas` (`{"version", "codigo", "referencia", "texto"}`).
4. `tests/test_notas.py` — `PruebaNotas(ayudas.CasoConServidor)`: `test_nota_biofab_codigo_exacta`,
   `test_nota_guardada_cuenta_como_resuelta`, `test_error_de_importe_no_tiene_nota`, `test_nota_periodo_factura_exacta`.

**Files**

- `gestor/controles.py` — edit: redactores de notas
- `gestor/negocio.py` — edit: guardar nota
- `gestor/server.py` — edit: /api/expedientes/<id>/notas
- `tests/test_notas.py` — nuevo

**Acceptance**

1. **WHEN** the BIO FAB file is controlled **THE SYSTEM SHALL** offer for `codigo_remito_distinto` exactly the note `Se deja constancia de que en el remito N° 0001-00003354 el renglón 2 figura con el código 5002383, cuando el código correcto según la Orden de Compra N° 4500587121 es 5003283. Se trata de un error de tipeo que no afecta lo entregado.`
2. **WHEN** that note is saved through `POST /api/expedientes/<id>/notas` **THE SYSTEM SHALL** return the result with `nota_guardada` filled and `resumen.salvable_con_nota` 1.
3. **WHEN** the result is the `error` `importe_factura` **THE SYSTEM SHALL** return it without `nota_sugerida` and SHALL not accept a note for it (answer 422 with `mensaje` `Un error de importe no se salva con nota aclaratoria.`).
4. **WHEN** the EFIA invoice carries `periodo_desde` 2026-07-01 and `periodo_hasta` 2026-07-31 (rendered `2026-07` because both fall in the same month) while the validated period is `2026-08` **THE SYSTEM SHALL** offer exactly `Se deja constancia de que la factura N° 0003B00031812 indica el período 2026-07, cuando el período validado según remito es 2026-08.`

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_notas -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T6: Notas aclaratorias redactadas para controles salvables"
git tag step-14-notas-aclaratorias
```

### `E2-T7` — Asistente del expediente, pasos 1 a 4 en la interfaz

**Depends on:** `E2-T6` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `web/index.html` (editar): dentro de `pantalla-expedientes`, la lista filtrable y el asistente con siete contenedores
   `asistente-paso-1` … `asistente-paso-7` (los pasos 5–7 quedan con el texto "Disponible en la próxima etapa" hasta el paso 20).
2. `web/app.js` (editar): pasos 1) tipo, OC y período (con el período sugerido y botón para corregirlo); 2) remitos (textarea de
   pegado `numero;fecha[;fecha_firma]`, casilla "remito del equipo en comodato", cantidades por renglón y código del remito);
   3) factura y SII (formulario + textarea "Pegar texto de SII" que llama `POST /api/comprobantes/analizar` y completa los campos);
   4) controles con semáforo (error rojo, salvable violeta, aviso amarillo, verificar azul — cada uno con su palabra además del
   color), nota sugerida editable y botón "Guardar nota". Toda llamada pasa por `api()`.
3. `web/style.css` (editar): clases `.nivel-error`, `.nivel-salvable`, `.nivel-aviso`, `.nivel-verificar` con los tokens de §7.
4. `tests/test_web_asistente.py` — `PruebaWebAsistente(ayudas.CasoConServidor)`: `test_index_tiene_los_7_pasos`,
   `test_app_js_usa_las_rutas_del_asistente` (el archivo servido en `/app.js` contiene `/remitos/pegar`,
   `/api/comprobantes/analizar`, `/controles` y `/notas`), `test_flujo_pasos_1_a_4_por_api_efia` (alta → pegado del remito →
   análisis del texto SII del fixture → `PUT` de factura y SII → controles con `resumen.error` 0 y `resumen.salvable` 0).

**Files**

- `web/index.html` — edit: lista y asistente de 7 pasos
- `web/app.js` — edit: pasos 1 a 4
- `web/style.css` — edit: clases de nivel
- `tests/test_web_asistente.py` — nuevo

**Acceptance**

1. **WHEN** `GET /` is requested **THE SYSTEM SHALL** return HTML containing the ids `asistente-paso-1` through `asistente-paso-7`.
2. **WHEN** `GET /app.js` is requested **THE SYSTEM SHALL** return a script that contains the API paths `/remitos/pegar`, `/api/comprobantes/analizar`, `/controles` and `/notas`.
3. **WHEN** the EFIA case is run through the HTTP API in the wizard order (create, paste remito, analyze SII text, save invoice and SII, control) **THE SYSTEM SHALL** end with `resumen.error` 0 and `resumen.salvable` 0.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_web_asistente -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E2-T7: Asistente del expediente, pasos 1 a 4 en la interfaz"
git tag step-15-asistente-1-4
```

---

## Epic acceptance

El epic está terminado cuando todas sus tareas están `done` **y**:

1. **WHEN** the three real cases are controlled **THE SYSTEM SHALL** report EFIA with 0 errors and 0 salvables, BIO FAB with exactly one salvable `codigo_remito_distinto` and MACATEX with the error `objeto_faltante`.
2. **WHEN** two saves of the same file race with the same `version` **THE SYSTEM SHALL** accept one and answer 409 to the other.

```bash
python -W error::DeprecationWarning -m unittest tests.test_controles -v  # expect: exit 0; el resumen final dice OK
python -W error::DeprecationWarning -m unittest tests.test_expedientes_api -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

## Pitfalls

- **Tomar el período de la factura** — EFIA factura en septiembre un servicio de agosto.
- **Contar el remito del equipo como entrega** — duplicaría cantidades de BIO FAB.
- **Comparar N° de factura como texto** — `00002B00003908` y `0002 - 00003908` son la misma: usar `util.misma_factura`.

## Before moving on

- [ ] Cada tarea de este epic está `done` en `tasks.json`; ninguna quedó `in_progress`.
- [ ] Pasaron **todos** los comandos `verify` de cada tarea, no solo el primero.
- [ ] Ningún comando `verify` fue editado ni salteado.
- [ ] Cada tarea tiene su tag de checkpoint: `git tag -l 'step-*'` lista `step-09-expedientes-api`, `step-10-periodo-y-remitos`, `step-11-comprobantes`, `step-12-consumo-y-saldo`, `step-13-controles`, `step-14-notas-aclaratorias`, `step-15-asistente-1-4`.
- [ ] El gate (`python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`) sale 0 desde la raíz.
- [ ] Cada contrato "Produced" existe con la firma indicada.
- [ ] Ningún archivo fuera del árbol fue modificado; `plantillas/`, `tests/fixtures/` y `tests/ayudas.py` siguen intactos.
- [ ] Este proyecto no tiene `.env` ni `.env.example`: la única variable de entorno es `GESTOR_CONFIG` (§10), opcional.
- [ ] Un commit por tarea, con el id de la tarea como prefijo, seguido de su tag.
