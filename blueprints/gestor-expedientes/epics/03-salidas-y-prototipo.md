# Epic 03: Salidas y prototipo usable

> El programa genera todos los textos (carátula, referencias, autorización, constancia, SAP), el CV y la autorización en Word, maneja estados y números GDE, y pasa el gate del prototipo con los tres expedientes reales.

| | |
|---|---|
| **Epic id** | `03-salidas-y-prototipo` |
| **Tasks** | `E3-T1` … `E3-T6` (pasos 16–21 de `blueprint.md` §9) |
| **Depends on** | `02-expediente-comun` |
| **Unlocks** | `04-seguimiento`, `05-especiales-y-cierre` |
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
  textos.py         # NUEVO (paso 16), editado (17, 19)
  docx_gen.py       # NUEVO (paso 18)
  negocio.py        # existe — contexto_textos, textos_del_expediente, estados, GDE
  server.py         # existe — /textos, descargas .docx, /estado, /reanudar, /gde
web/app.js          # existe — copiar con formato, pasos 5–7
plantillas/cv_hbi.docx cv_casph.docx   # provistas — solo lectura
tests/
  datos_prueba.py   # existe — flujo_por_api (paso 21)
  test_textos_referencias.py test_autorizacion.py test_docx.py test_sap.py test_estados.py test_prototipo.py   # NUEVOS
  fixtures/expedientes/**   # provistos — originales para comparar
```

Todo lo que está fuera de este árbol queda fuera de alcance. Si una tarea parece exigir editar otro archivo, parar y reportarlo.

## Data model touched here

| Entidad | Campos | Notas |
|---|---|---|
| `expediente.datos.gde` | `expediente`, `caratula`, `factura`, `sii`, `oc_pdf`, `remitos{}`, `remito_equipo`, `orden_remito_equipo`, `cv`, `vale_hoja`, `autorizacion`, `constancia`, `contabilizacion` | normalizados con `util.normalizar_gde` |
| `expediente.estado` | `BORRADOR` → `CONTROLADO` → `EN_FIRMA` → `FIRMADO` → `ENVIADO` → `CONTABILIZADO` → `CERRADO`; `PENDIENTE`; `ANULADO` | `ENVIADO` solo vía entrega (epic 04) |
| `oc` | `objeto`, `objeto_articulo`, `concepto_corto`, `gde_pdf_oc`, `expediente_contratacion`, `ca` | se leen para los textos |

## Contracts

**Consumed** — ya existe, no reconstruir:

| From | Interface | Guarantee |
|---|---|---|
| `02-expediente-comun` | `controles.controlar`, `negocio.obtener_expediente` | resumen por nivel |
| `01-nucleo-y-oc` | `letras.importe_en_letras`, `util.formato_pesos`, `util.mm_aa` | formatos exactos |

**Produced** — los epics siguientes dependen de estas firmas exactas:

| Export | Signature | Used by |
|---|---|---|
| `gestor/textos.py` → `caratula`, `referencias`, `nombre_archivo`, `autorizacion`, `constancia_comodato`, `textos_sap`, `TextoIncompleto` | funciones puras sobre `ctx` | `04`, `05` |
| `gestor/docx_gen.py` → `generar_cv`, `generar_autorizacion_docx` | `(...) -> bytes` | `05` |
| `gestor/negocio.py` → `contexto_textos`, `textos_del_expediente`, `cambiar_estado`, `guardar_gde` | ver pasos 16–20 | `04`, `05` |

## Conventions that bite in this area

- Los goldens de §5 se copian literales en los tests; un texto, una función.
- `MM-AA` es el período validado (`08-26`), nunca la fecha de la factura.
- El CV se edita EN SU LUGAR: solo cambia `word/document.xml`; header, footer y media se copian byte a byte.
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

### `E3-T1` — Carátula, referencias GDE y nombres de archivo

**Depends on:** `E2-T5` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/textos.py` (nuevo): `class TextoIncompleto(Exception)`; funciones puras sobre un `ctx` (dict):
   - `caratula(ctx)` → `PAGO SAP <sap> <razon> - FC <factura> - <oc>`.
   - `referencias(ctx) -> list[dict]` con `{"clave", "referencia", "archivo"}`, en este orden (`MM-AA` = `util.mm_aa(periodo)`;
     CASPH antepone `CASPH - ` a TODAS): `MM-AA - FC <factura> - <razon>`, `MM-AA - CARGA EN SII - <razon>`,
     un remito → `MM-AA - RTO <numero> - <razon>` / dos o más → un solo `MM-AA - REMITOS - <razon>`,
     si hay remito de equipo en primera validación → `MM-AA - REMITO POR EQUIPO EN COMODATO - <razon>`,
     `MM-AA - CERTIFICADO DE VALIDACIÓN - <razon>`, `MM-AA - VALE DE ENTRADA - <razon>` (OC `BIEN`/`PROVISION`) o
     `MM-AA - HOJA DE ENTRADA - <razon>` (OC `SERVICIO`), `AUTORIZACIÓN DE PAGO FC N° <factura>, <razon> - MM-AA`,
     `MM-AA - CONSTANCIA DE CONTABILIZACIÓN - <razon>`.
   - `nombre_archivo(referencia) -> str`: reemplaza cada uno de `\ / : * ? " < > |` por `-` y agrega `.pdf`.
2. `gestor/negocio.py` (editar): `contexto_textos(con, id) -> dict` (efector y sus parámetros, `sap`, `razon` = razón social de la
   OC, `oc`, `factura` = `datos.factura.numero` tal cual, `centavos`, `periodo`, `periodo_desde`, `periodo_hasta`, `dia_inicio`,
   `remitos` (números no de equipo, en orden de carga), `remito_equipo`, `primera_validacion`, `tipo_oc`, `objeto`, `articulo`,
   `concepto_corto`, `expediente` = `datos.gde.expediente`, `expediente_contratacion`, `ca`) y
   `textos_del_expediente(con, id) -> dict` (`caratula`, `referencias`; los pasos 17 y 19 agregan claves).
3. `gestor/server.py` (editar): `GET /api/expedientes/<id>/textos` → `{"ok": true, "datos": textos_del_expediente(...)}`.
4. `tests/test_textos_referencias.py` — `PruebaReferencias(unittest.TestCase)`: `test_caratulas_de_los_tres_expedientes`,
   `test_referencias_efia`, `test_varios_remitos_un_solo_documento`, `test_remito_de_equipo_en_comodato`, `test_prefijo_casph`,
   `test_nombre_archivo_reemplaza_invalidos`; y `PruebaTextosApi(ayudas.CasoConServidor)` con `test_textos_efia_por_api`.

**Files**

- `gestor/textos.py` — nuevo: carátula, referencias, nombres de archivo
- `gestor/negocio.py` — edit: contexto_textos y textos_del_expediente
- `gestor/server.py` — edit: /api/expedientes/<id>/textos
- `tests/test_textos_referencias.py` — nuevo

**Acceptance**

1. **WHEN** `textos.caratula` runs for the three real files **THE SYSTEM SHALL** return exactly `PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861`, `PAGO SAP 116467 BIO FAB S.R.L - FC 00002B00003908 - 4500587121` and `PAGO SAP 118896 MACATEX S.A - FC 0002B00000160 - 4500594643`.
2. **WHEN** `textos.referencias` runs for the EFIA file (service, one remito, period `2026-08`) **THE SYSTEM SHALL** return in order `08-26 - FC 0003B00031812 - GRUPO EFIA S.R.L.`, `08-26 - CARGA EN SII - GRUPO EFIA S.R.L.`, `08-26 - RTO 00001-00029461 - GRUPO EFIA S.R.L.`, `08-26 - CERTIFICADO DE VALIDACIÓN - GRUPO EFIA S.R.L.`, `08-26 - HOJA DE ENTRADA - GRUPO EFIA S.R.L.`, `AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26` and `08-26 - CONSTANCIA DE CONTABILIZACIÓN - GRUPO EFIA S.R.L.`
3. **WHEN** a file has two or more remitos **THE SYSTEM SHALL** emit one reference `MM-AA - REMITOS - <razon>` instead of one per remito, and WHEN it has an equipment remito in a first validation **THE SYSTEM SHALL** add `08-26 - REMITO POR EQUIPO EN COMODATO - BIO FAB S.R.L` for BIO FAB.
4. **WHEN** the efector is CASPH **THE SYSTEM SHALL** prefix every reference with `CASPH - `, giving `CASPH - AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26` for the authorization.
5. **WHEN** `textos.nombre_archivo` receives `08-26 - RTO 1/2 - X:Y` **THE SYSTEM SHALL** return `08-26 - RTO 1-2 - X-Y.pdf`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_textos_referencias -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T1: Carátula, referencias GDE y nombres de archivo"
git tag step-16-caratula-y-referencias
```

### `E3-T2` — Autorización, constancia de comodato y copiar con formato

**Depends on:** `E3-T1` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/textos.py` (editar):
   - `frase_remitos(numeros)`: 1 → `conforme al remito N° A`; 2 → `conforme a los remitos N° A y B`; 3+ → `conforme a los remitos N° A, B y C`.
   - `frase_periodo(ctx)`: día de inicio 1 → `en el mes de <mes en minúsculas> del <AAAA>`; si no →
     `en el período del <dd/mm/aaaa desde> al <dd/mm/aaaa hasta>`.
   - `autorizacion(ctx) -> {"referencia", "cuerpo"}` con el texto canónico de §5 (*Autorización de pago*), en una sola línea:
     `Por medio del expediente <EX> AUTORIZO se abone la factura N° <fc> por la suma de <letras.importe_en_letras(centavos)> del proveedor <razon> correspondiente <articulo> <objeto>, <frase_remitos><frase_comodato>, con destino <destino>, <frase_periodo> de acuerdo a la Orden de compra N° <oc>.`
     `<frase_comodato>` = `, y el remito n° <X>, correspondiente al equipo entregado en calidad de comodato` solo si la OC es de
     comodato, es la primera validación y hay remito de equipo. Referencia: `AUTORIZACIÓN DE PAGO FC N° <fc>, <razon> - MM-AA`
     (CASPH: `CASPH - ` delante). Objeto vacío → `TextoIncompleto("Falta el objeto de la contratación en la OC <oc>")`;
     sin remitos, sin factura o sin `EX` → `TextoIncompleto` con el dato faltante.
   - `constancia_comodato(ctx) -> {"referencia", "cuerpo"}`: referencia `CONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC <oc>, <razon>`;
     cuerpo de dos párrafos separados por `\n` (texto en §5 *Constancia de recepción de comodato*), con `<orden>` =
     `datos.gde.orden_remito_equipo` y `nota_comodato` de los parámetros.
2. `gestor/negocio.py` (editar): `textos_del_expediente` agrega `autorizacion` (o `autorizacion_error` con el mensaje de
   `TextoIncompleto`) y `constancia_comodato` cuando corresponde.
3. `web/app.js` (editar): botón "Copiar con formato" que usa `navigator.clipboard.write([new ClipboardItem({"text/html": ..., "text/plain": ...})])`
   con `<p style="text-align: justify">` y botón "Copiar" de texto plano.
4. `tests/test_autorizacion.py` — `PruebaAutorizacion(unittest.TestCase)`: `test_golden_efia`, `test_efia_coincide_con_original_salvo_diferencias_aceptadas`
   (toma el párrafo de `EX-2026-89654857_EFIA/0009_IF-2026-91157933*.txt` desde `Por medio del expediente` hasta `4500555861.`,
   normaliza espacios con `ayudas.normalizar_espacios`, y lo compara con el generado tras quitar `, con destino al Hospital del Bicentenario de Ituzaingó,`
   y reemplazar `del 2026` por `2026`), `test_golden_biofab_con_comodato`, `test_macatex_sin_objeto_no_genera`,
   `test_frase_remitos_uno_dos_tres`, `test_periodo_especifico`, `test_referencia_casph`, `test_constancia_biofab_coincide_con_original`
   (contra el cuerpo de `EX-2026-94963848_BIOFAB/0008_PV-2026-96851161*.txt` normalizando espacios y reemplazando en el fixture
   `BIO FAB S.R.L.` por `BIO FAB S.R.L` — única diferencia aceptada: el original escribió la razón con punto final); y
   `PruebaCopiarConFormato(ayudas.CasoConServidor)` con `test_app_js_copia_html_justificado` (el `/app.js` servido contiene
   `ClipboardItem` y `text-align: justify`).

**Files**

- `gestor/textos.py` — edit: autorización y constancia de comodato
- `gestor/negocio.py` — edit: textos_del_expediente agrega autorización y constancia
- `web/app.js` — edit: copiar con formato
- `tests/test_autorizacion.py` — nuevo: goldens y comparación con los originales

**Acceptance**

1. **WHEN** `textos.autorizacion` runs for the EFIA file **THE SYSTEM SHALL** return the reference `AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26` and the body, as one line, `Por medio del expediente EX-2026-89654857- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 0003B00031812 por la suma de PESOS UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100 CENTAVOS ($ 1.224.990,00-) del proveedor GRUPO EFIA S.R.L. correspondiente al servicio de control integral de plagas, fumigación, desinsectación y desratización, conforme al remito N° 00001-00029461, con destino al Hospital del Bicentenario de Ituzaingó, en el mes de agosto del 2026 de acuerdo a la Orden de compra N° 4500555861.`
2. **WHEN** the EFIA body has `, con destino al Hospital del Bicentenario de Ituzaingó,` removed and `del 2026` replaced by `2026` **THE SYSTEM SHALL** match word for word the paragraph of the fixture `0009_IF-2026-91157933` with whitespace normalized.
3. **WHEN** `textos.autorizacion` runs for the BIO FAB first validation with equipment remito **THE SYSTEM SHALL** return exactly `Por medio del expediente EX-2026-94963848- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 00002B00003908 por la suma de PESOS VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100 CENTAVOS ($ 21.095.000,00-) del proveedor BIO FAB S.R.L correspondiente a la provisión de inmunoensayo por fluorescencia, conforme al remito N° 0001-00003354, y el remito n° 0001-00003281, correspondiente al equipo entregado en calidad de comodato, con destino al Hospital del Bicentenario de Ituzaingó, en el mes de agosto del 2026 de acuerdo a la Orden de compra N° 4500587121.`
4. **WHEN** the OC has an empty `objeto` (MACATEX 4500594643) **THE SYSTEM SHALL** raise `textos.TextoIncompleto` with `Falta el objeto de la contratación en la OC 4500594643` and never return a text containing `correspondiente al , conforme`.
5. **WHEN** `textos.frase_remitos` receives one, two and three numbers and `textos.frase_periodo` a day-17 period **THE SYSTEM SHALL** return `conforme al remito N° A`, `conforme a los remitos N° A y B`, `conforme a los remitos N° A, B y C` and `en el período del 17/10/2026 al 16/11/2026`.
6. **WHEN** `textos.constancia_comodato` runs for BIO FAB (razón `BIO FAB S.R.L` as stored in `proveedor.razon_social`, SAP 116467, remito `0001-00003281`, orden 7) **THE SYSTEM SHALL** return the reference `CONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC 4500587121, BIO FAB S.R.L` and a body equal to the body of fixture `0008_PV-2026-96851161` after normalizing whitespace and replacing `BIO FAB S.R.L.` with `BIO FAB S.R.L` in the fixture.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_autorizacion -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T2: Autorización, constancia de comodato y copiar con formato"
git tag step-17-autorizacion
```

### `E3-T3` — Certificado de validación y autorización en Word

**Depends on:** `E3-T2` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/docx_gen.py` (nuevo, `zipfile` + `xml.etree.ElementTree`):
   - Registra los prefijos de los namespaces de `word/document.xml` (`w`, `r`, `wp`, `a`, `pic`, `mc`, `w14`, `wps`, … leídos del
     propio XML con `ET.iterparse(..., events=("start-ns",))`) antes de serializar.
   - `texto_parrafo(p)` une los `w:t` de todos los runs; `poner_texto(p, texto)` deja el texto en el primer run y vacía los demás
     (conserva el formato del primer run).
   - `celda_derecha_de(tabla, rotulo)` ubica la celda siguiente a la que contiene el rótulo (normalizado con `util.normalizar_texto`).
   - `generar_cv(ruta_plantilla, datos) -> bytes`: completa EN SU LUGAR — fecha (`Buenos Aires,` | `dd de <mes> del aaaa`, con el
     año correcto), `Proveedor:`, `N° SAP:`, `N° Expediente:` (= expediente de contratación de la OC), `N° C.A. :`,
     `Orden de Compra:`, `Vigencia de la OC :` (`dd/mm/aaaa` a `dd/mm/aaaa`), `Rubro:` (`Bienes` o `Servicios`), `Entrega:`
     (`Única`, `Parcial` o `Mensual`) y `Período:`; reemplaza `Objeto de Contratación: _____________` por el objeto; la tabla de
     renglones (`Renglón`, `Descripción`, `Cantidad OC`, `Cantidad Entregada`, `Fecha de Entrega`) agrega o quita filas copiando
     la primera fila vacía como modelo; `Observaciones:` recibe `datos["observacion"]` (vacío salvo centralizadas, paso 27); y la
     frase final: 1 remito → `Se valida con remito A correspondiente al período P.`, varios →
     `Se valida con remitos A, B y C correspondientes al período P.` (P = `agosto 2026` o `17/10/2026 al 16/11/2026`).
     Solo reescribe `word/document.xml`; cualquier otro part se copia byte a byte (`ZipFile.read` → `writestr` con el mismo `ZipInfo`).
   - `generar_autorizacion_docx(referencia, cuerpo) -> bytes`: .docx mínimo nuevo (`[Content_Types].xml`, `_rels/.rels`,
     `word/document.xml`) con la referencia en negrita y el cuerpo en un párrafo `<w:jc w:val="both"/>`.
2. `gestor/server.py` (editar): `GET /api/expedientes/<id>/cv.docx` y `GET /api/expedientes/<id>/autorizacion.docx` con
   `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document` y
   `Content-Disposition: attachment; filename*=UTF-8''<nombre de archivo de la referencia con .docx>`; plantilla según
   `parametros.efectores[efector].plantilla_cv` (relativa a la raíz del proyecto). `TextoIncompleto` → 422.
3. `tests/test_docx.py` — `PruebaDocx(ayudas.CasoConServidor)`: `test_cv_efia_contenido`, `test_cv_conserva_partes_no_tocadas`,
   `test_cv_casph_conserva_footer2`, `test_cv_varios_remitos_y_filas`, `test_cv_anio_correcto`, `test_autorizacion_docx_justificada`.

**Files**

- `gestor/docx_gen.py` — nuevo: CV desde plantilla y autorización .docx
- `gestor/server.py` — edit: descargas .docx
- `tests/test_docx.py` — nuevo

**Acceptance**

1. **WHEN** `GET /api/expedientes/<id>/cv.docx` runs for the EFIA file **THE SYSTEM SHALL** return a valid zip whose `word/document.xml` parses and contains `GRUPO EFIA S.R.L.`, `4500555861` and `Se valida con remito 00001-00029461 correspondiente al período agosto 2026.`
2. **WHEN** the HBI CV is generated **THE SYSTEM SHALL** keep `word/media/image1.jpeg` and `word/header1.xml` byte for byte identical to `plantillas/cv_hbi.docx`, and every part other than `word/document.xml` identical too.
3. **WHEN** the CASPH CV is generated **THE SYSTEM SHALL** keep `word/footer2.xml` byte for byte identical to `plantillas/cv_casph.docx`.
4. **WHEN** the file has three remitos and five OC rows **THE SYSTEM SHALL** write `Se valida con remitos A, B y C correspondientes al período agosto 2026.` and a rows table with exactly five data rows.
5. **WHEN** the CV is generated for a 2027 period **THE SYSTEM SHALL** write the year 2027 in the date line instead of the template's fixed `2026`.
6. **WHEN** `GET /api/expedientes/<id>/autorizacion.docx` runs **THE SYSTEM SHALL** return a .docx whose body paragraph has `w:jc` `both` and contains the EFIA authorization text.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_docx -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T3: Certificado de validación y autorización en Word"
git tag step-18-word
```

### `E3-T4` — Textos para SAP: ingreso, contabilización, MIGO y ML81N

**Depends on:** `E3-T1` · **Priority:** p1 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/textos.py` (editar): `textos_sap(ctx, limite) -> dict`:
   - `ingreso`: `fecha_documento` `01.MM.AAAA` (primer día del mes del período), `importe` (`util.formato_pesos`),
     `texto` = `<SIGLA> - OC <oc> - <concepto_corto> - MM/AA`, `largo_texto`, `aviso_largo` (`None` o
     `El Texto tiene <n> caracteres; el límite configurado es <limite>.` cuando `n > limite`), `asignacion` = `OC <oc>`,
     `txt_cabecera` = `0000-0000-0000000-0`, `clase` = `KE`.
   - `contabilizada`: `txt_cabecera` = `MM/AA <SIGLA> OC <oc>`.
   - `entrada`: `transaccion` `MIGO` (OC `BIEN`/`PROVISION`) o `ML81N` (`SERVICIO`), `fecha_documento` `01.MM.AAAA`,
     `fecha_contabilizacion` = fecha base del remito más reciente en `dd.mm.aaaa`, `renglones` `[{"pos", "cantidad"}]`,
     `periodo` (`MM/AAAA` o `dd.mm.aaaa - dd.mm.aaaa`) y `texto_breve` = `<concepto_corto> - MM/AA`.
   `<SIGLA>` = `parametros.efectores[efector].sigla` (`HBI` / `CASPH`).
2. `gestor/negocio.py` (editar): `textos_del_expediente` agrega `sap` con `limite = parametros["limite_texto_sap"]`.
3. `tests/test_sap.py` — `PruebaSap(unittest.TestCase)`: `test_texto_ingreso_efia`, `test_txt_cabecera_contabilizada_efia`,
   `test_casph_reemplaza_hbi`, `test_aviso_de_largo`, `test_ml81n_y_migo`.

**Files**

- `gestor/textos.py` — edit: textos SAP
- `gestor/negocio.py` — edit: textos_del_expediente agrega sap
- `tests/test_sap.py` — nuevo

**Acceptance**

1. **WHEN** `textos.textos_sap` runs for the EFIA file (concepto corto `SERV. FUMIGACIÓN`, period `2026-08`) **THE SYSTEM SHALL** return `ingreso.texto` `HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26`, `ingreso.fecha_documento` `01.08.2026`, `ingreso.asignacion` `OC 4500555861`, `ingreso.txt_cabecera` `0000-0000-0000000-0` and `ingreso.clase` `KE`.
2. **WHEN** the same file is booked **THE SYSTEM SHALL** return `contabilizada.txt_cabecera` `08/26 HBI OC 4500555861`, and for efector CASPH `08/26 CASPH OC 4500555861`.
3. **WHEN** `ingreso.texto` is longer than the configured limit **THE SYSTEM SHALL** return `aviso_largo` `El Texto tiene <n> caracteres; el límite configurado es <limite>.` with the real length, and `None` when it fits.
4. **WHEN** the OC is a service **THE SYSTEM SHALL** return `entrada.transaccion` `ML81N` with `fecha_contabilizacion` `31.08.2026` for the EFIA remito, and `MIGO` for a `BIEN` OC.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_sap -v  # expect: exit 0; el resumen final dice OK
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T4: Textos para SAP: ingreso, contabilización, MIGO y ML81N"
git tag step-19-textos-sap
```

### `E3-T5` — Asistente pasos 5 a 7: documentos, GDE y estados

**Depends on:** `E2-T6`, `E2-T7`, `E3-T2`, `E3-T3`, `E3-T4` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

1. `gestor/negocio.py` (editar):
   - `TRANSICIONES_COMUN = {"BORRADOR": ["CONTROLADO"], "CONTROLADO": ["EN_FIRMA", "BORRADOR"], "EN_FIRMA": ["FIRMADO", "CONTROLADO"],
     "FIRMADO": ["ENVIADO"], "ENVIADO": ["CONTABILIZADO"], "CONTABILIZADO": ["CERRADO"]}`; `PENDIENTE` desde cualquier estado
     no final (exige `motivo` y `fecha_seguimiento`, guarda `estado_previo` en el historial) y `reanudar` vuelve al `estado_previo`.
   - `cambiar_estado(con, id, version, estado, motivo="", fecha_seguimiento=None)`: transición inválida →
     `ErrorNegocio("No se puede pasar de <A> a <B>.")`; a `CONTROLADO` exige 0 errores y todos los salvables con nota, si no
     `ErrorNegocio("No se puede pasar a CONTROLADO: hay <n> errores y <m> salvables sin nota.")`; a `ENVIADO` solo desde una
     entrega (paso 24): por esta vía → `ErrorNegocio("Asigná el expediente a una entrega para marcarlo como enviado.")`.
   - `guardar_gde(con, id, version, gde: dict)`: claves `expediente`, `caratula`, `factura`, `sii`, `oc_pdf`, `remitos` (dict
     número → GDE), `remito_equipo`, `orden_remito_equipo` (entero), `cv`, `vale_hoja`, `autorizacion`, `constancia`,
     `contabilizacion`. Cada número pasa por `util.normalizar_gde`; inválido → `ErrorValidacion('El número GDE "<x>" no tiene un formato válido.')`.
     `oc_pdf` se completa solo desde `oc.gde_pdf_oc` si viene vacío.
2. `gestor/server.py` (editar): `POST /api/expedientes/<id>/estado` (`{"version", "estado", "motivo", "fecha_seguimiento"}`),
   `POST /api/expedientes/<id>/reanudar` (`{"version"}`), `PUT /api/expedientes/<id>/gde` (`{"version", "gde"}`).
3. `web/app.js` (editar): pasos 5) documentos (carátula, referencias con nombre de archivo, autorización, constancia, textos SAP,
   botones Copiar y descargas .docx); 6) números de GDE con validación al escribir; 7) estado, pendiente con motivo y fecha de seguimiento.
4. `tests/test_estados.py` — `PruebaEstados(ayudas.CasoConServidor)`: `test_efia_recorre_hasta_firmado`,
   `test_controlado_bloqueado_por_errores`, `test_transicion_invalida`, `test_pendiente_y_reanudar`,
   `test_enviado_solo_por_entrega`, `test_gde_normaliza_y_valida`, `test_gde_oc_pdf_desde_la_oc`.

**Files**

- `gestor/negocio.py` — edit: estados, pendiente, GDE
- `gestor/server.py` — edit: rutas de estado, reanudar y GDE
- `web/app.js` — edit: pasos 5 a 7
- `tests/test_estados.py` — nuevo

**Acceptance**

1. **WHEN** the EFIA file is moved BORRADOR → CONTROLADO → EN_FIRMA → FIRMADO **THE SYSTEM SHALL** accept every transition and append one `datos.historial` entry per change.
2. **WHEN** the MACATEX file (error `objeto_faltante`) is moved to CONTROLADO **THE SYSTEM SHALL** answer 422 with `mensaje` `No se puede pasar a CONTROLADO: hay 1 errores y 0 salvables sin nota.`
3. **WHEN** a file in BORRADOR is moved to FIRMADO **THE SYSTEM SHALL** answer 422 with `mensaje` `No se puede pasar de BORRADOR a FIRMADO.`
4. **WHEN** a file is set to PENDIENTE with a reason and a follow-up date and later resumed **THE SYSTEM SHALL** return it to the state it had before PENDIENTE.
5. **WHEN** `POST /api/expedientes/<id>/estado` asks for ENVIADO **THE SYSTEM SHALL** answer 422 with `mensaje` `Asigná el expediente a una entrega para marcarlo como enviado.`
6. **WHEN** `PUT /api/expedientes/<id>/gde` receives `IF-2026-90061259-INSSJP-GESP%INSSJP` **THE SYSTEM SHALL** store `IF-2026-90061259-INSSJP-GESP#INSSJP`, and for `IF-2026-12` it SHALL answer 400 with `mensaje` `El número GDE "IF-2026-12" no tiene un formato válido.`

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_estados -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T5: Asistente pasos 5 a 7: documentos, GDE y estados"
git tag step-20-asistente-5-7-y-estados
```

### `E3-T6` — Gate del prototipo: tres expedientes reales de punta a punta

**Depends on:** `E3-T5` · **Priority:** p0 — metadato para recortes de alcance, no un orden de ejecución

Hito "prototipo usable". Un test de integración recorre por HTTP, con datos reales, el circuito completo de los tres
expedientes. Si el gate falla, el defecto se corrige en el módulo responsable (`gestor/*.py`) y se informa en el commit.

1. `tests/datos_prueba.py` (editar): `flujo_por_api(servidor, caso)` que, para `efia`, `biofab` y `macatex`, prepara la OC
   (manual para EFIA; importación de `z_compras2_hbi_2026.xlsx` + campos manuales para BIO FAB y MACATEX), crea el expediente,
   pega remitos, analiza el texto SII del fixture `0004_IF-*.txt` con `POST /api/comprobantes/analizar`, guarda en `datos.factura`
   el mismo dict `factura` que arma `datos_prueba.armar_expediente_<prov>` (`numero`, `fecha`, `centavos`, `destinatario`,
   `domicilio`, `cae`, `vto_cae`; sin `periodo_desde`/`periodo_hasta` ni `menciona`, igual que allí) y en `datos.sii` el resultado del análisis, carga los GDE del expediente
   (`EX-2026-89654857- -INSSJP-GESP#INSSJP`, `EX-2026-94963848- -INSSJP-GESP#INSSJP`, `EX-2026-99349179- -INSSJP-GESP#INSSJP`)
   y devuelve el id.
2. `tests/test_prototipo.py` — `PruebaPrototipo(ayudas.CasoConServidor)`: `test_efia_de_punta_a_punta` (controles 0/0, textos y
   autorización iguales a los goldens, CV con `Se valida con remito 00001-00029461 correspondiente al período agosto 2026.`,
   estado final FIRMADO), `test_biofab_de_punta_a_punta` (guarda la nota sugerida, pasa a CONTROLADO, autorización golden BIO FAB),
   `test_macatex_bloqueado_hasta_cargar_objeto` (`autorizacion_error` = `Falta el objeto de la contratación en la OC 4500594643`,
   CONTROLADO rechazado; después de `PUT /api/oc/4500594643` con objeto `provisión de insumos textiles` y artículo `a la`
   pasa a CONTROLADO y la autorización contiene `correspondiente a la provisión de insumos textiles, conforme al remito N° 0001-00004409`).

**Files**

- `tests/datos_prueba.py` — edit: flujo completo por API
- `tests/test_prototipo.py` — nuevo: gate del prototipo

**Acceptance**

1. **WHEN** the EFIA case runs end to end over HTTP **THE SYSTEM SHALL** report 0 `error` and 0 `salvable`, return the golden carátula and authorization, serve a CV containing `Se valida con remito 00001-00029461 correspondiente al período agosto 2026.` and reach `FIRMADO`.
2. **WHEN** the BIO FAB case runs end to end over HTTP and the suggested note is saved **THE SYSTEM SHALL** accept CONTROLADO and return the golden BIO FAB authorization.
3. **WHEN** the MACATEX case runs end to end over HTTP **THE SYSTEM SHALL** return `autorizacion_error` `Falta el objeto de la contratación en la OC 4500594643` and refuse CONTROLADO, and after the OC gets the object `provisión de insumos textiles` with article `a la` it SHALL accept CONTROLADO and generate an authorization containing `correspondiente a la provisión de insumos textiles, conforme al remito N° 0001-00004409`.

**Verify** — cada comando, en orden, desde la raíz del proyecto; cada uno sale 0 cuando la tarea está bien.

```bash
python -W error::DeprecationWarning -m unittest tests.test_prototipo -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

**Checkpoint** — después de que el último Verify salga 0:

```bash
git add -A && git commit -m "E3-T6: Gate del prototipo: tres expedientes reales de punta a punta"
git tag step-21-gate-prototipo
```

---

## Epic acceptance

El epic está terminado cuando todas sus tareas están `done` **y**:

1. **WHEN** `python -W error::DeprecationWarning -m unittest tests.test_prototipo -v` runs **THE SYSTEM SHALL** pass the EFIA, BIO FAB and MACATEX end-to-end cases.
2. **WHEN** a text cannot be completed **THE SYSTEM SHALL** return the missing-data message instead of a text with gaps.

```bash
python -W error::DeprecationWarning -m unittest tests.test_prototipo -v  # expect: exit 0; el resumen final dice OK
python app.py --check | grep -q '"app": "gestor-expedientes"'  # expect: exit 0 — el entry point arranca y /api/salud responde
python -m compileall -q app.py gestor tests  # expect: exit 0, sin salida (formato/lint del proyecto)
python -W error::DeprecationWarning -m unittest discover -s tests -t .  # expect: exit 0, OK — los gates de los pasos anteriores siguen en verde
```

## Pitfalls

- **Runs partidos en el XML de Word** — el rótulo `Proveedor:` puede estar en dos `w:r`; unir el texto del párrafo antes de buscar.
- **Namespaces perdidos al serializar** — `ET` renombra prefijos (`ns0:`) si no se registran; Word no abre el archivo.
- **"del 2026" fijo en la plantilla** — el generador escribe el año del período.

## Before moving on

- [ ] Cada tarea de este epic está `done` en `tasks.json`; ninguna quedó `in_progress`.
- [ ] Pasaron **todos** los comandos `verify` de cada tarea, no solo el primero.
- [ ] Ningún comando `verify` fue editado ni salteado.
- [ ] Cada tarea tiene su tag de checkpoint: `git tag -l 'step-*'` lista `step-16-caratula-y-referencias`, `step-17-autorizacion`, `step-18-word`, `step-19-textos-sap`, `step-20-asistente-5-7-y-estados`, `step-21-gate-prototipo`.
- [ ] El gate (`python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -m compileall -q app.py gestor tests`) sale 0 desde la raíz.
- [ ] Cada contrato "Produced" existe con la firma indicada.
- [ ] Ningún archivo fuera del árbol fue modificado; `plantillas/`, `tests/fixtures/` y `tests/ayudas.py` siguen intactos.
- [ ] Este proyecto no tiene `.env` ni `.env.example`: la única variable de entorno es `GESTOR_CONFIG` (§10), opcional.
- [ ] Un commit por tarea, con el id de la tarea como prefijo, seguido de su tag.
