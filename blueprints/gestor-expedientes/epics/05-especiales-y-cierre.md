# Epic 05: Trámites especiales y cierre

> Existen las centralizadas, los correctivos, los pagos eventuales, los modelos AySA/Edenor del CASPH, la prueba de dos procesos concurrentes, el instructivo y la pantalla Ayuda, y pasa el gate final.

| | |
|---|---|
| **Epic id** | `05-especiales-y-cierre` |
| **Tasks** | `E5-T1` … `E5-T6` (pasos 27–32 de `blueprint.md` §9) |
| **Depends on** | `04-seguimiento` |
| **Unlocks** | nada — es el último |
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
docs/INSTRUCTIVO.md       # NUEVO (paso 32)
gestor/
  textos.py controles.py negocio.py server.py db.py   # existen — se editan
web/index.html web/app.js # existen — Centralizadas, Ayuda, correctivo, eventual, servicios CASPH
tests/
  test_centralizadas.py test_correctivo.py test_eventual.py test_casph_servicios.py
  test_concurrencia.py test_instructivo.py   # NUEVOS
```

Todo lo que está fuera de este árbol queda fuera de alcance. Si una tarea parece exigir editar otro archivo, parar y reportarlo.

## Data model touched here

| Entidad | Campos | Notas |
|---|---|---|
| `expediente.datos.centralizada` | `numero_cv`, `numero_nota`, `fecha_envio` | tabla por OC × período |
| `expediente.datos.checklist` | `{documento: true/false}` | documentos de `oc.doc_requerida_central` |
| `expediente.datos.correctivo` | `procedimiento`, `objeto_correctivo`, `presupuestos[]`, `informes[]`, `monto_convalidado` | |
| `expediente.datos.eventual` | campos de la solicitud de pago eventual | |
| `renglon.es_correctivo` | 0/1 | renglón contra el que se convalida |

## Contracts

**Consumed** — ya existe, no reconstruir:

| From | Interface | Guarantee |
|---|---|---|
| `03-salidas-y-prototipo` | `textos.*`, `docx_gen.generar_cv(observacion=...)`, `negocio.cambiar_estado` | |
| `04-seguimiento` | `negocio.calendario`, `exportes` | marca ◆ y exporte de centralizadas |
| `01-nucleo-y-oc` | `db.conectar`, `db.ConflictoVersion` | prueba de dos procesos |

**Produced** — los epics siguientes dependen de estas firmas exactas:

| Export | Signature | Used by |
|---|---|---|
| `gestor/textos.py` → `nota_central`, `informe_economico`, `referencia_correctivo`, `caratula_eventual`, `solicitud_pago_eventual`, `autorizacion_servicio_casph` | funciones puras | — |
| `docs/INSTRUCTIVO.md` | una página | usuarias |

## Conventions that bite in this area

- Los textos de pago eventual y AySA/Edenor son literales de §5 con `[CAMPOS]`; no se reescriben.
- La prueba de concurrencia usa procesos reales (`spawn`), no threads: así se prueba el bloqueo de archivo de SQLite.
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

### `E5-T1` — Centralizadas: CV con leyenda, nota a Central y checklist

**Depends on:** `E4-T5` · **Priority:** p2 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/textos.py` (editar): `nota_central(ctx) -> {"referencia", "cuerpo"}`:
   referencia `VALIDACIÓN DE BIENES Y SERVICIOS <razon> - <expediente_contratacion>, período <P>` y cuerpo
   `Se envían como archivos embebidos la validación del servicio y remito correspondientes al proveedor <razon>, del <expediente_contratacion>, con orden de compra <oc>, período <P>.`
   seguido de `\nDocumentación embebida:` y una línea `- <documento>` por cada elemento de `oc.doc_requerida_central`.
   `<P>` = `MM-AAAA` (`08-2026`) para mes calendario o `dd/mm/aaaa al dd/mm/aaaa` para período específico.
2. `gestor/controles.py` (editar): `documentacion_centralizada` (error si algún documento de `oc.doc_requerida_central` no está
   tildado en `datos.checklist`: `Falta tildar como auditada la documentación: <doc1>, <doc2>.`) y `leyenda_cv_faltante`
   (error si la OC es centralizada y `oc.leyenda_cv` está vacía: `Falta la leyenda del CV en la OC <oc>.`). Solo para tipo `CENTRALIZADA`.
3. `gestor/negocio.py` (editar): para `CENTRALIZADA`, `textos_del_expediente` agrega `nota_central` y el CV recibe
   `observacion = oc.leyenda_cv`; `datos.centralizada = {"numero_cv", "numero_nota", "fecha_envio"}` (GDE validados);
   `centralizadas_por_periodo(con, anio)`; el calendario marca `centralizada_enviada` (◆) cuando hay `numero_nota` y `fecha_envio`.
4. `gestor/server.py` (editar): `GET /api/centralizadas?anio=` y `PUT /api/expedientes/<id>/centralizada` (`{"version", "centralizada"}`).
5. `tests/test_centralizadas.py` — `PruebaCentralizadas(ayudas.CasoConServidor)`: `test_nota_central_golden`,
   `test_checklist_incompleto_es_error`, `test_leyenda_faltante_es_error`, `test_cv_lleva_la_leyenda`, `test_rombo_en_calendario`.
   Datos del test: OC `4500000001` centralizada de `PROVEEDOR CENTRAL S.A.`, expediente `EX-2025-11111111- -INSSJP-GESP#INSSJP`,
   documentos `Remito` y `Factura`, período `2026-08`.
   La interfaz de Centralizadas (pantalla `pantalla-centralizadas`) se completa en el paso 32 junto con Ayuda.

**Files**

- `gestor/textos.py` — edit: nota a Central
- `gestor/controles.py` — edit: controles de centralizadas
- `gestor/negocio.py` — edit: centralizadas por período y marca de calendario
- `gestor/server.py` — edit: rutas de centralizadas
- `tests/test_centralizadas.py` — nuevo

**Acceptance**

1. **WHEN** `textos.nota_central` runs for OC 4500000001 of `PROVEEDOR CENTRAL S.A.`, expediente `EX-2025-11111111- -INSSJP-GESP#INSSJP`, period `2026-08` **THE SYSTEM SHALL** return the reference `VALIDACIÓN DE BIENES Y SERVICIOS PROVEEDOR CENTRAL S.A. - EX-2025-11111111- -INSSJP-GESP#INSSJP, período 08-2026` and a body starting `Se envían como archivos embebidos la validación del servicio y remito correspondientes al proveedor PROVEEDOR CENTRAL S.A., del EX-2025-11111111- -INSSJP-GESP#INSSJP, con orden de compra 4500000001, período 08-2026.` followed by `Documentación embebida:` and the lines `- Remito` and `- Factura`.
2. **WHEN** a CENTRALIZADA file has `Factura` unchecked in `datos.checklist` **THE SYSTEM SHALL** report the error `documentacion_centralizada` with `mensaje` `Falta tildar como auditada la documentación: Factura.`
3. **WHEN** the centralized OC has an empty `leyenda_cv` **THE SYSTEM SHALL** report the error `leyenda_cv_faltante` with `mensaje` `Falta la leyenda del CV en la OC 4500000001.`
4. **WHEN** the CV of a CENTRALIZADA file is generated **THE SYSTEM SHALL** write the OC `leyenda_cv` in the `Observaciones:` paragraph.
5. **WHEN** a CENTRALIZADA file has `numero_nota` and `fecha_envio` **THE SYSTEM SHALL** mark that calendar cell with `centralizada_enviada` true.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_centralizadas -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T1: Centralizadas: CV con leyenda, nota a Central y checklist"
git tag step-27-centralizadas
```

### `E5-T2` — Correctivo: estados, informe económico e informe mensual

**Depends on:** `E4-T5` · **Priority:** p2 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `TRANSICIONES_CORRECTIVO = {"RECIBIDO_MANTENIMIENTO": ["INFORME_ECONOMICO"],
   "INFORME_ECONOMICO": ["DEVUELTO"], "DEVUELTO": ["PARA_FACTURAR"], "PARA_FACTURAR": ["CONTROLADO"]}` y desde `CONTROLADO`
   sigue `TRANSICIONES_COMUN`. Un `CORRECTIVO` nace en `RECIBIDO_MANTENIMIENTO`. `datos.correctivo = {"procedimiento"
   (ej. `CAM 12/2026`), "objeto_correctivo", "presupuestos": [{"proveedor", "centavos"}], "informes": [GDE], "monto_convalidado"}`.
   `porcentaje_convalidado = monto_convalidado / importe del renglón con es_correctivo` (entero, half-up).
   `informe_mensual_correctivos(con, mes)` → filas `{"expediente", "oc", "procedimiento", "adjudicatario", "detalle", "monto"}`
   de los correctivos con período `mes`.
2. `gestor/textos.py` (editar): `referencia_correctivo(ctx)` →
   `<sap> <razon> - OC <oc> - <procedimiento> - <objeto> - MANTENIMIENTO CORRECTIVO - <objeto_correctivo>`;
   `informe_economico(ctx)` → líneas, en este orden:
   `INFORME ECONÓMICO - MANTENIMIENTO CORRECTIVO` /
   `Orden de Compra N° <oc> - <razon> (SAP <sap>) - <objeto_correctivo>` /
   `Presupuesto menor: $ <menor>` / `Presupuesto mayor: $ <mayor>` /
   `Diferencia entre presupuestos: $ <mayor − menor> (<pct> %).` con `pct = (mayor − menor) / menor × 100` redondeado a entero /
   `Monto a convalidar frente al renglón de correctivo: $ <monto> de $ <importe_renglon> (<pct_conv> %).`
3. `gestor/server.py` (editar): `GET /api/correctivos/informe-mensual?mes=AAAA-MM` y `PUT /api/expedientes/<id>/correctivo`.
4. `web/app.js` (editar): en el asistente, para `CORRECTIVO`, sección de presupuestos, informe económico con Copiar y la lista mensual.
5. `tests/test_correctivo.py` — `PruebaCorrectivo(ayudas.CasoConServidor)`: `test_estados_del_correctivo`,
   `test_informe_economico_ascensor`, `test_porcentaje_convalidado`, `test_referencia_correctivo`, `test_informe_mensual`.
   Datos: OC 4500587755 del reporte 2026 (renglón 2 `MANT. CORRECTIVO` 5.000.000 marcado `es_correctivo`), expediente
   `EX-2026-75399232- -INSSJP-GESP#INSSJP`, presupuestos 5.000.000 y 8.700.000.

**Files**

- `gestor/negocio.py` — edit: estados y datos del correctivo, informe mensual
- `gestor/textos.py` — edit: referencia e informe económico
- `gestor/server.py` — edit: rutas de correctivos
- `web/app.js` — edit: sección de correctivo
- `tests/test_correctivo.py` — nuevo

**Acceptance**

1. **WHEN** a CORRECTIVO file is created **THE SYSTEM SHALL** start it in `RECIBIDO_MANTENIMIENTO` and accept, in order, `INFORME_ECONOMICO`, `DEVUELTO`, `PARA_FACTURAR` and `CONTROLADO`, rejecting `PARA_FACTURAR` straight from `RECIBIDO_MANTENIMIENTO` with `mensaje` `No se puede pasar de RECIBIDO_MANTENIMIENTO a PARA_FACTURAR.`
2. **WHEN** the budgets are 500000000 and 870000000 centavos **THE SYSTEM SHALL** include in the economic report the line `Diferencia entre presupuestos: $ 3.700.000,00 (74 %).`
3. **WHEN** `monto_convalidado` is 500000000 centavos against the corrective row of 500000000 centavos **THE SYSTEM SHALL** return `porcentaje_convalidado` 100.
4. **WHEN** `GET /api/correctivos/informe-mensual?mes=2026-08` runs with one corrective of period `2026-08` **THE SYSTEM SHALL** return one row with `expediente`, `oc` `4500587755`, `procedimiento`, `adjudicatario`, `detalle` and `monto`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_correctivo -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T2: Correctivo: estados, informe económico e informe mensual"
git tag step-28-correctivos
```

### `E5-T3` — Pago eventual: estados, solicitud y uno por proveedor y año

**Depends on:** `E4-T5` · **Priority:** p2 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar): `TRANSICIONES_EVENTUAL = {"ARMADO": ["EN_DTO_ECONOMICO_CONTABLE"],
   "EN_DTO_ECONOMICO_CONTABLE": ["DEVUELTO"], "DEVUELTO": ["CONTABILIZADO"], "CONTABILIZADO": ["FINALIZADO"]}`; un `EVENTUAL`
   nace en `ARMADO` (la OC puede estar vencida o faltar). `datos.eventual` guarda los campos de la solicitud (§5 *Solicitud de pago eventual*).
2. `gestor/controles.py` (editar): `eventual_repetido` (error): otro `EVENTUAL` no anulado del mismo SAP con factura del mismo año →
   `Ya hay un pago eventual para el proveedor SAP <sap> en <año> (expediente <id>).`
3. `gestor/textos.py` (editar): `caratula_eventual(ctx)` → `<SIGLA> - PAGO EVENTUAL - <razon> - FC N° <factura>`;
   `solicitud_pago_eventual(ctx) -> {"referencia", "parrafos": [8 strings]}` con la referencia
   `SOLICITUD PAGO EVENTUAL - <N° EXPEDIENTE PRINCIPAL> - <ESTABLECIMIENTO> - <PROVEEDOR>` y los párrafos P1–P8 literales de §5,
   reemplazando cada `[CAMPO]` por su dato; el monto de P1 es `$ <formato_pesos>.- (PESOS <letras_con_centavos> CENTAVOS)`.
   Campo faltante → `TextoIncompleto("Falta <CAMPO> en la solicitud de pago eventual.")`.
4. `web/app.js` (editar): formulario de pago eventual (campos de la solicitud) con Copiar por párrafo.
5. `tests/test_eventual.py` — `PruebaEventual(ayudas.CasoConServidor)`: `test_estados_del_eventual`, `test_monto_philips_con_centavos`,
   `test_solicitud_tiene_ocho_parrafos_sin_corchetes`, `test_un_eventual_por_proveedor_por_anio`, `test_caratula_eventual`.
   Datos: expediente `EX-2026-23468433- -INSSJP-GESP#INSSJP`, factura `1000-00006268` por 2210187213 centavos.

**Files**

- `gestor/negocio.py` — edit: estados del pago eventual
- `gestor/controles.py` — edit: un eventual por proveedor por año
- `gestor/textos.py` — edit: carátula y solicitud de pago eventual
- `web/app.js` — edit: formulario de pago eventual
- `tests/test_eventual.py` — nuevo

**Acceptance**

1. **WHEN** an EVENTUAL file is created **THE SYSTEM SHALL** start it in `ARMADO` and accept, in order, `EN_DTO_ECONOMICO_CONTABLE`, `DEVUELTO`, `CONTABILIZADO` and `FINALIZADO`.
2. **WHEN** the invoice `1000-00006268` is for 2210187213 centavos **THE SYSTEM SHALL** write in paragraph 1 `$ 22.101.872,13.- (PESOS VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100 CENTAVOS)`.
3. **WHEN** every field of the request is loaded **THE SYSTEM SHALL** return exactly 8 paragraphs and none of them SHALL contain `[` or `]`.
4. **WHEN** a second non-annulled EVENTUAL file for the same SAP and year is controlled **THE SYSTEM SHALL** report the error `eventual_repetido` with `mensaje` `Ya hay un pago eventual para el proveedor SAP <sap> en 2026 (expediente <id>).` naming the first file.
5. **WHEN** `textos.caratula_eventual` runs for HBI, razón `PROVEEDOR DE PRUEBA S.A.` and invoice `1000-00006268` **THE SYSTEM SHALL** return `HBI - PAGO EVENTUAL - PROVEEDOR DE PRUEBA S.A. - FC N° 1000-00006268`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_eventual -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T3: Pago eventual: estados, solicitud y uno por proveedor y año"
git tag step-29-pago-eventual
```

### `E5-T4` — Modelos de autorización AySA y Edenor del CASPH

**Depends on:** `E3-T2` · **Priority:** p2 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/textos.py` (editar): `autorizacion_servicio_casph(empresa, factura, centavos, mes, anio, expediente) -> list[str]`
   (dos párrafos) con los textos literales de §5 *AySA y Edenor (CASPH)*. `mes` en MAYÚSCULAS (`AGOSTO`). AySA escribe
   `PESOS <letras> con <cc>/100 CENTAVOS ($ <monto>-)` (con `con` en minúscula, como el modelo); Edenor
   `PESOS <letras> CON <cc>/100 CENTAVOS ($ <monto>-),`. `<letras>` = `letras.numero_a_letras(centavos // 100)`.
   Empresa distinta de `AYSA`/`EDENOR` → `ValueError`.
2. `gestor/server.py` (editar): `POST /api/textos/servicio-casph` (`{"empresa", "factura", "centavos", "mes", "anio", "expediente"}`).
3. `web/app.js` (editar): panel "Servicios CASPH (AySA / Edenor)" en Expedientes con Copiar con formato.
4. `tests/test_casph_servicios.py` — `PruebaServiciosCasph(unittest.TestCase)`: `test_aysa_golden`, `test_edenor_golden`,
   `test_parrafo_resol_identico_en_ambos`, `test_empresa_desconocida`.
   Datos: factura `0001-00012345`, 4512300 centavos, `AGOSTO` 2026, expediente `EX-2026-11111111- -INSSJP-GESP#INSSJP`.

**Files**

- `gestor/textos.py` — edit: AySA y Edenor
- `gestor/server.py` — edit: /api/textos/servicio-casph
- `web/app.js` — edit: panel de servicios CASPH
- `tests/test_casph_servicios.py` — nuevo

**Acceptance**

1. **WHEN** `textos.autorizacion_servicio_casph("AYSA", "0001-00012345", 4512300, "AGOSTO", 2026, "EX-2026-11111111- -INSSJP-GESP#INSSJP")` runs **THE SYSTEM SHALL** return as first paragraph exactly `Por medio de la presente se autoriza el pago de la factura N° 0001-00012345 de la empresa AySA (AGUA Y SANEAMIENTOS ARGENTINOS S.A.), SAP 70262, por un monto de PESOS CUARENTA Y CINCO MIL CIENTO VEINTITRES con 00/100 CENTAVOS ($ 45.123,00-) correspondiente al mes de AGOSTO 2026, por el servicio de CLOACA del Centro Ambulatorio de Salud PAMI Hurlingham de acuerdo a la factura vinculada al EX-2026-11111111- -INSSJP-GESP#INSSJP.`
2. **WHEN** the same data runs for `EDENOR` **THE SYSTEM SHALL** return as first paragraph exactly `Por medio de la presente se autoriza el pago de la factura N° 0001-00012345 de la EMPRESA DISTRIBUIDORA Y COMERCIALIZADORA NORTE S.A. por un monto de PESOS CUARENTA Y CINCO MIL CIENTO VEINTITRES CON 00/100 CENTAVOS ($ 45.123,00-), correspondiente al mes de AGOSTO 2026, por el servicio de provisión de energía eléctrica del Centro Ambulatorio de Salud PAMI Hurlingham, de acuerdo a la factura vinculada al expediente EX-2026-11111111- -INSSJP-GESP#INSSJP.`
3. **WHEN** either text is generated **THE SYSTEM SHALL** return as second paragraph the same RESOL paragraph, containing `RESOL-2023-926-INSSJP-DE#INSSJP` and ending `Sin más, se eleva para su intervención.`
4. **WHEN** the company is not `AYSA` or `EDENOR` **THE SYSTEM SHALL** raise `ValueError`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_casph_servicios -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T4: Modelos de autorización AySA y Edenor del CASPH"
git tag step-30-aysa-edenor-casph
```

### `E5-T5` — Prueba de dos procesos escribiendo la misma base

**Depends on:** `E2-T1` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

Prueba TX.3 del riesgo principal (SQLite en unidad de red con dos usuarias).

1. `tests/test_concurrencia.py` (nuevo): funciones de nivel de módulo `escribir_proveedores(ruta, prefijo, n, cola)` y
   `actualizar_misma_oc(ruta, version, barrera, cola)` (cada una abre su propia conexión con `gestor.db.conectar`);
   `PruebaConcurrencia(ayudas.CasoConEntorno)`: `test_dos_procesos_sin_perdidas` (dos procesos
   `multiprocessing.get_context("spawn").Process` insertan 50 proveedores cada uno, con claves distintas, en transacciones
   cortas `BEGIN IMMEDIATE` → al final hay 100 proveedores y 100 eventos `ALTA`) y `test_dos_procesos_un_conflicto` (los dos
   procesos esperan una `Barrier` y actualizan la misma OC con `version` 1 → exactamente uno informa `ConflictoVersion`, la OC
   queda en `version` 2 y con un solo evento `MODIFICACION`). Los procesos devuelven su resultado por una `Queue`; `join(timeout=60)`.
2. `gestor/db.py` (editar solo si la prueba encuentra un defecto: por ejemplo reintento ante `sqlite3.OperationalError: database is locked`
   dentro del `timeout`).

**Files**

- `tests/test_concurrencia.py` — nuevo: dos procesos sobre una base temporal
- `gestor/db.py` — edit solo si la prueba encuentra un defecto

**Acceptance**

1. **WHEN** two Python processes insert 50 suppliers each into the same temporary database at the same time **THE SYSTEM SHALL** end with 100 rows in `proveedor` and 100 `evento` rows with `accion` `ALTA`.
2. **WHEN** two Python processes update the same OC with `version` 1 at the same time **THE SYSTEM SHALL** let exactly one succeed, report `ConflictoVersion` in the other, and leave the OC with `version` 2 and one `MODIFICACION` event.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_concurrencia -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T5: Prueba de dos procesos escribiendo la misma base"
git tag step-31-concurrencia
```

### `E5-T6` — Instructivo, pantallas Ayuda y Centralizadas, gate final

**Depends on:** `E4-T1`, `E4-T2`, `E4-T3`, `E4-T4`, `E4-T5`, `E5-T1`, `E5-T2`, `E5-T3`, `E5-T4`, `E5-T5` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `docs/INSTRUCTIVO.md` (nuevo, una página, como máximo 120 líneas) con exactamente estas secciones:
   `## Instalar Python`, `## Abrir el programa`, `## Dónde está la base`, `## Copias de seguridad`,
   `## Flujo de un expediente`, `## Revisión manual por pantalla` (una casilla `- [ ]` por cada una de las 8 pantallas,
   con lo que hay que mirar a mano: foco visible, navegación por teclado, textos en español).
2. `gestor/server.py` (editar): `GET /api/ayuda` → `{"ok": true, "datos": {"markdown": <contenido de docs/INSTRUCTIVO.md>}}`.
3. `web/index.html` (editar): botón de menú "Ayuda" y `<section id="pantalla-ayuda">`.
4. `web/app.js` (editar): pantalla Ayuda (muestra el instructivo como texto preformateado) y pantalla Centralizadas
   (tabla OC × período con N° de CV, N° de nota y fecha de envío usando `GET /api/centralizadas`, y checklist editable).
5. `tests/test_instructivo.py` — `PruebaInstructivo(ayudas.CasoConServidor)`: `test_instructivo_tiene_las_secciones`,
   `test_instructivo_entra_en_una_pagina`, `test_api_ayuda_devuelve_el_instructivo`, `test_index_tiene_pantalla_ayuda`,
   `test_app_js_usa_api_centralizadas`.

**Files**

- `docs/INSTRUCTIVO.md` — nuevo: instructivo de una página
- `gestor/server.py` — edit: /api/ayuda
- `web/index.html` — edit: pantalla Ayuda
- `web/app.js` — edit: pantallas Ayuda y Centralizadas
- `tests/test_instructivo.py` — nuevo

**Acceptance**

1. **WHEN** `docs/INSTRUCTIVO.md` is read **THE SYSTEM SHALL** contain the headings `## Instalar Python`, `## Abrir el programa`, `## Dónde está la base`, `## Copias de seguridad`, `## Flujo de un expediente` and `## Revisión manual por pantalla`, in at most 120 lines.
2. **WHEN** `GET /api/ayuda` is requested **THE SYSTEM SHALL** return the exact content of `docs/INSTRUCTIVO.md` in `datos.markdown`.
3. **WHEN** `GET /` is requested **THE SYSTEM SHALL** return HTML containing `id="pantalla-ayuda"` in addition to the eight screens.
4. **WHEN** `GET /app.js` is requested **THE SYSTEM SHALL** serve an `app.js` whose text contains `/api/centralizadas` and `/api/ayuda`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_instructivo -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E5-T6: Instructivo, pantallas Ayuda y Centralizadas, gate final"
git tag step-32-instructivo-y-cierre
```

---

## Epic acceptance

El epic está terminado cuando todas sus tareas están `done` **y**:

1. **WHEN** the global gate of §20.1 runs **THE SYSTEM SHALL** exit 0 on every line.
2. **WHEN** two processes write the same database concurrently **THE SYSTEM SHALL** lose no row and report exactly one version conflict.

```bash
python -W error::DeprecationWarning -m unittest tests.test_concurrencia -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

## Pitfalls

- **Funciones de `multiprocessing` definidas dentro del test** — con `spawn` no se pueden importar; van a nivel de módulo.
- **AySA usa `con` en minúscula** y Edenor `CON`: así son los modelos.

## Before moving on

- [ ] Cada tarea de este epic está `done` en `tasks.json`; ninguna quedó `in_progress`.
- [ ] Pasaron **todos** los comandos `verify` de cada tarea, no solo el primero.
- [ ] Ningún comando `verify` fue editado ni salteado.
- [ ] Cada tarea tiene su tag de checkpoint: `git tag -l 'step-*'` lista `step-27-centralizadas`, `step-28-correctivos`, `step-29-pago-eventual`, `step-30-aysa-edenor-casph`, `step-31-concurrencia`, `step-32-instructivo-y-cierre`.
- [ ] El gate (`python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`) sale 0 desde la raíz.
- [ ] Cada contrato "Produced" existe con la firma indicada.
- [ ] Ningún archivo fuera del árbol fue modificado; `plantillas/`, `tests/fixtures/` y `tests/ayudas.py` siguen intactos.
- [ ] Este proyecto no tiene `.env` ni `.env.example`: la única variable de entorno es `GESTOR_CONFIG` (§10), opcional.
- [ ] Un commit por tarea, con el id de la tarea como prefijo, seguido de su tag.
