# Gestor de expedientes de pago (HBI / CASPH) — Blueprint

> Generado por The Architect el 2026-11-16
> Shape: internal-tool · `knowledge/shapes/internal-tool.md`
> Runtime track: Python, **solo biblioteca estándar** (desvío del track `python` por restricción dura: sin pip ni internet en el trabajo) · `knowledge/runtime-tracks/python.md` solo como contexto
> Modo de emisión: bundle (`blueprint.md`, `tasks.json`, `epics/`, `workspace/`)
> Versión del blueprint: 1
> Versiones verificadas por última vez: 2026-11-16 — ver §11 para la procedencia de cada pin

**Cómo usar este bundle.** El builder trabaja en la carpeta del proyecto (`C:\Users\Cami Personal\Documents\gestor-expedientes`),
con este bundle en `blueprints/gestor-expedientes/`. Primero corre el bloque *Bootstrap* de §10 (copia **una sola carpeta**,
`workspace/`, a la raíz del proyecto, crea el repositorio y el primer commit). Después ejecuta las 32 tareas de `tasks.json` en
orden; cada una está explicada también en su epic (`epics/0N-*.md`) y en §9. Termina cuando §20.1 está en verde.

---

## 1. Project Overview & Non-Goals

### Vision

Un programa local, de doble clic, que concentra en un solo lugar las órdenes de compra (OC), los consumos por período y los
expedientes de pago del área contable del Hospital del Bicentenario de Ituzaingó (HBI) y del Centro Ambulatorio de Salud PAMI
Hurlingham (CASPH). Hoy cada dato de un expediente (proveedor, OC, remitos, factura, comprobante SII, período) se tipea varias
veces en Word, en SAP, en GDE y en planillas de seguimiento; los errores aparecen recién cuando Contaduría devuelve el expediente.

Con el gestor, cada dato se carga **una vez**: la OC llega importada del reporte z_compras2 de SAP, la factura y el SII se pegan
como texto, y el programa genera todos los textos (carátula, referencias GDE, autorización de pago, constancia de comodato, CV en
Word, textos SAP) y corre los controles que hoy se hacen a ojo (importe exacto al centavo, período del remito, código de renglón,
remito del equipo en comodato, vigencia y saldo de la OC) **antes** de que el expediente avance. La base vive en la carpeta
compartida para que las dos personas del área vean lo mismo.

### Users

| Persona | Qué viene a hacer | Frecuencia |
|---|---|---|
| Responsable contable HBI (usa la PC con el programa abierto todo el día) | Importar el z_compras2, armar y controlar expedientes, generar textos y CV, armar entregas | Diaria |
| Segunda persona del área (prefiere una interfaz simple, sin consola) | Cargar remitos y facturas, copiar textos a GDE, mirar el calendario y los pendientes | Diaria |

### Goals — v1 scope

1. El programa arranca con doble clic (`Iniciar.bat`) sin consola visible, abre el navegador en `http://127.0.0.1:8765` y guarda todo en una base SQLite en la carpeta configurada.
2. Importa los reportes z_compras2 por nombre de encabezado, con limpieza, descartes por motivo, upsert que respeta lo cargado a mano y desglose de servicios mensuales.
3. Arma un expediente común en un asistente de 7 pasos: OC, remitos (pegados), factura y SII (pegados), controles con cuatro niveles, documentos, números GDE y estado.
4. Genera con el texto exacto de los modelos reales: carátula, referencias GDE, nombres de archivo, autorización de pago (texto y Word), constancia de comodato, CV en Word sobre la plantilla del efector, textos SAP/MIGO/ML81N.
5. Sigue el trabajo: calendario OC × mes con estados accesibles, pantalla Inicio con alertas, entregas con CSV NUMERACIÓN, pendientes y seis exportes (Excel, CSV, impresión).
6. Cubre los trámites especiales: centralizadas, mantenimiento correctivo, pago eventual y autorizaciones AySA/Edenor del CASPH.
7. Dos personas pueden trabajar a la vez sobre la misma base sin perder datos: versión por registro, 409 con mensaje claro, auditoría append-only y backups automáticos.

### Non-Goals — explicitly out of scope for v1

| No se construye | Por qué no ahora | Revisar cuando |
|---|---|---|
| Conexión a SAP, SII o GDE (APIs o scripting de SAP GUI) | No hay acceso a APIs; el scripting de SAP GUI suele estar bloqueado y rompe con cada cambio de pantalla | El área de sistemas habilite una API o un usuario técnico |
| Lectura de PDFs o escaneos (OCR) | Requiere bibliotecas fuera de la stdlib; los datos se pegan como texto desde el SII | Se permita instalar paquetes de PyPI |
| Reportes FBL1N, ZEJECUC, ZFI_INF_PRESUP | El circuito diario no los necesita; se pueden sumar como importadores aparte | La usuaria los pida para conciliación |
| Importar las planillas existentes (SEGUIMIENTO REMITOS 2026.xlsx, SEGUIMIENTO CENTRALIZADAS.xlsx) como histórico | Formatos manuales irregulares; el gestor arranca en limpio | Se necesite el historial de 2026 dentro del programa |
| Login y contraseñas | Son 2 personas en una red interna; la identidad es el usuario de Windows | Se sume gente de otras áreas o se exponga fuera de la PC |
| Servidor central multiusuario | SQLite en la carpeta compartida alcanza para 2 personas (riesgo aceptado en §20.2) | Haya 3+ usuarias o corrupción repetida de la base |
| Modo oscuro | Pedido explícito: fondo claro, sobrio | Una usuaria lo pida por accesibilidad |
| Instalador | El programa es una carpeta y un `Iniciar.bat`; Python se instala aparte | Se distribuya a otros efectores |

**El builder no implementa nada de esta tabla**, aunque parezca un agregado chico en un paso vecino. Si un paso parece
requerir un no-objetivo, es un defecto del blueprint: parar y reportarlo.

### Success metrics

| Métrica | Objetivo | Cómo se mide |
|---|---|---|
| Expedientes reales reproducidos | Los 3 (EFIA, BIO FAB, MACATEX) de punta a punta al terminar el epic 03 | `python -W error::DeprecationWarning -m unittest tests.test_prototipo -v` sale 0 |
| Textos idénticos a los modelos | Autorización EFIA y BIO FAB, carátulas y constancia iguales a los goldens de §5 | Tests de goldens de los pasos 16, 17 y 21 |
| Datos perdidos por concurrencia | 0 filas perdidas con 2 procesos escribiendo | `python -W error::DeprecationWarning -m unittest tests.test_concurrencia -v` sale 0 |
| Tiempo de armado de un expediente común | Menos de 10 minutos con remitos y SII pegados (hoy ~30) | Cronometraje de la usuaria durante el primer mes; fuera del gate automático |

---

## 2. Tech Stack

**Runtime track: Python, solo biblioteca estándar.** Esta tabla nombra *elecciones*, no versiones: los pines están en §11.

| Capa | Elección | Por qué esta, en lugar de cuál |
|---|---|---|
| Lenguaje / runtime | CPython ≥ 3.10 (objetivo 3.14) | En las PCs del trabajo pip puede estar bloqueado y no hay internet: solo la stdlib es instalable en todas. Se descartó Node/TypeScript (track por defecto) porque exige `npm install`. |
| Framework | Ninguno: `http.server.ThreadingHTTPServer` | Flask/FastAPI necesitan pip. Un servidor de threads alcanza para 2 usuarias locales. |
| Estilos | CSS propio en `web/style.css` con variables (§7) | Sin build ni CDN (sin internet). Tailwind requiere Node. |
| Capa de componentes | HTML + JS sin framework (`web/app.js`) | React/Vue exigirían un bundler o un CDN. 8 pantallas caben en un solo archivo JS. |
| Base de datos | SQLite (`sqlite3` de la stdlib) en un archivo de la carpeta compartida | No hay servidor de base disponible; SQLite viene con Python. Riesgo SMB aceptado y mitigado (§20.2). |
| ORM / acceso a datos | SQL a mano en `gestor/db.py` y `gestor/negocio.py` | SQLAlchemy necesita pip; el esquema es chico (8 tablas). |
| Auth | Ninguna: identidad = `getpass.getuser()` (usuario de Windows), registrada en auditoría | Sin login por decisión (§1 Non-Goals); la auditoría sí guarda quién hizo qué. |
| Trabajo en segundo plano | Ninguno; backup al iniciar dentro del arranque | No hay tareas periódicas que justifiquen un scheduler. |
| Pagos | NOT APPLICABLE — el programa no cobra ni paga: solo prepara expedientes | — |
| Archivos | Excel y Word con `zipfile` + `xml.etree.ElementTree`; subidas multipart con `email.parser.BytesParser` | `openpyxl`/`python-docx` necesitan pip; `cgi` fue eliminado en 3.13. |
| Email / notificaciones | NOT APPLICABLE — las alertas se muestran en la pantalla Inicio; no se envían correos | — |
| Hosting | Local: cada PC corre `app.py` contra la base compartida | No hay servidor central (§1 Non-Goals). |
| Gestor de paquetes | Ninguno: no hay archivo de dependencias | Stdlib only; el piso de versión lo verifica Bootstrap con un one-liner de Python. |
| Tests | `unittest` con `-W error::DeprecationWarning` | pytest necesita pip. |
| Formato/lint | `python -m compileall -q app.py gestor tests` | ruff/flake8 necesitan pip; `compileall` detecta errores de sintaxis en todo el código sin recorrer `blueprints/`. |

### Compatibility check

Revisado contra `knowledge/stack-compatibility.md`: no hay combinaciones conocidas como problemáticas, porque no hay paquetes de
terceros. Las incompatibilidades reales están **dentro** de la stdlib entre 3.10 y 3.14 y este blueprint las evita de forma
explícita: sin `cgi` (eliminado en 3.13), sin adaptadores de fecha por defecto de `sqlite3` (deprecados en 3.12), sin
`datetime.utcnow()` (deprecado en 3.12), sin `datetime.UTC`, `tomllib`, `ExceptionGroup`, `except*`, `typing.Self` ni
`sqlite3.connect(autocommit=...)` (no existen en 3.10), sin `RETURNING` (SQLite 3.35+) ni `ON CONFLICT DO UPDATE` (la versión de
SQLite que trae Python en Windows no fue verificada).

---

## 3. Directory Structure

```
gestor-expedientes/                 # raíz del repo = raíz del proyecto; todo Verify corre desde acá
  Iniciar.bat                       # paso 25 — doble clic: pythonw → pyw -3 → py -3, sin consola; mensaje si no hay Python
  app.py                            # paso 1 — entry point: --check, --no-browser, --port N; elige puerto 8765..8775
  config.json                       # workspace (Bootstrap) — config local: ruta de la base, puertos, parámetros iniciales
  .gitignore                        # workspace (Bootstrap) — datos/, salidas/, *.db, *.db-journal, __pycache__/, *.pyc
  CLAUDE.md                         # workspace (Bootstrap) — instrucciones del proyecto para el agente (§19.1)
  AGENTS.md                         # workspace (Bootstrap) — puente para otros agentes (§19.2)
  .claude/
    settings.json                   # workspace — allowlist de comandos (§19.3)
    skills/nuevo-texto-generado/SKILL.md   # workspace — procedimiento golden-test-first para un texto nuevo (§19.4)
    skills/agregar-control/SKILL.md        # workspace — procedimiento para sumar un control (§19.4)
    rules/base-de-datos.md          # workspace — reglas para gestor/db.py y negocio.py (§19.5)
    rules/textos-y-documentos.md    # workspace — reglas para textos.py, letras.py, docx_gen.py (§19.5)
    rules/interfaz-web.md           # workspace — reglas para web/ (§19.5)
  gestor/                           # paquete de la aplicación; se importa como `gestor.<modulo>` desde la raíz
    __init__.py                     # paso 1 — APP_ID = "gestor-expedientes", __version__ = "0.1.0"
    config.py                       # paso 1 — cargar_config(), ruta(), guardar_config(); respeta GESTOR_CONFIG
    server.py                       # paso 1, crece en casi todos los pasos — rutas HTTP, sobre JSON, estáticos de web/
    db.py                           # paso 2 — ESQUEMA (§4), conectar, transaccion, versión, auditoría, backups, integridad
    util.py                         # paso 3 — fechas, períodos, montos en centavos, formato $, factura, GDE
    letras.py                       # paso 3 — importe en letras
    xlsx.py                         # paso 4 — lector .xlsx (zipfile + ElementTree)
    importar.py                     # pasos 5–6 — importador z_compras2, limpieza, desglose
    negocio.py                      # paso 8 en adelante — reglas de OC, expedientes, estados, calendario, entregas
    comprobantes.py                 # paso 11 — parser del texto pegado del SII
    controles.py                    # pasos 13–14 — motor de controles y notas aclaratorias
    textos.py                       # pasos 16–19, 27–30 — todos los textos generados (§5 Textos canónicos)
    docx_gen.py                     # paso 18 — CV y autorización en Word
    exportes.py                     # pasos 24 y 26 — CSV, HTML imprimible, exportes por nombre
    xlsx_escritor.py                # paso 26 — escritor .xlsx mínimo
  web/                              # estáticos servidos por server.py; nada fuera de web/ se sirve
    index.html                      # paso 7 — 8 pantallas (+ Ayuda en el paso 32), región #avisos
    app.js                          # paso 7, crece — api(), navegación, pantallas
    style.css                       # paso 7 — tokens de §7
  plantillas/                       # PROVISTO (workspace) — no se edita
    cv_hbi.docx                     # plantilla del CV del HBI
    cv_casph.docx                   # plantilla del CV del CASPH (con footer2.xml RESOL-2023-926)
  docs/
    INSTRUCTIVO.md                  # paso 32 — instructivo de una página, servido en la pantalla Ayuda
  datos/                            # IGNORADO — se crea en runtime: expedientes.db y backups/
  salidas/                          # IGNORADO — .docx y exportes generados
  tests/
    __init__.py                     # workspace — vuelve a tests/ un paquete (unittest discover -t .)
    ayudas.py                       # workspace (§19.6) — EntornoTemporal, ServidorDePrueba, CasoConEntorno, CasoConServidor
    datos_prueba.py                 # paso 8, editado en 13 y 21 — datos reales reutilizables (OC EFIA, BIO FAB, MACATEX)
    test_*.py                       # 33 módulos; cada uno lo crea el paso que lo corre (lista en §9)
    fixtures/                       # PROVISTO (workspace) — datos reales; no se edita
      xlsx/z_compras2_hbi_2026.xlsx
      xlsx/z_compras2_por_partida.xlsx
      modelos/*.docx                # modelos de autorización, constancia, nota a Central, AySA, Edenor, pago eventual, correctivo
      expedientes/EX-2026-89654857_EFIA/*.txt      # 12 textos extraídos de los PDF reales
      expedientes/EX-2026-94963848_BIOFAB/*.txt    # 14 textos
      expedientes/EX-2026-99349179_MACATEX/*.txt   # 12 textos
  blueprints/gestor-expedientes/    # ESTE bundle — nunca se edita ni lo recorre ninguna herramienta del proyecto
```

**Origen de cada archivo.** Todo archivo del árbol tiene uno de dos orígenes: (1) un paso de §9 lo crea (aparece en su lista
*Files touched* y en `files` de `tasks.json`), o (2) llega por la copia de `workspace/` del Bootstrap (§10, §19). Los marcados
PROVISTO son datos reales que el arquitecto copió al bundle: se commitean y no se reescriben.

**Reglas de frontera**
- `gestor/db.py` es el **único** módulo que llama a `sqlite3.connect`. Todo lo demás recibe una conexión.
- `gestor/textos.py`, `gestor/letras.py` y `gestor/util.py` son puros: no leen la base ni archivos; reciben datos y devuelven strings.
- `gestor/controles.py` no lee la base: recibe el contexto armado por `armar_contexto`.
- `gestor/server.py` solo traduce HTTP ↔ funciones de `negocio`, `importar`, `controles`, `textos`, `docx_gen`, `exportes`; no tiene reglas de negocio.
- `web/` no importa nada externo (sin CDN) y habla con el servidor solo por `api()` de `app.js`.
- Los tests importan la app como `gestor.<modulo>` y usan `tests/ayudas.py` para la base temporal; nunca tocan `datos/`.
- La convención de importación (`import gestor.<modulo>` desde la raíz, sin `sys.path`) está reconciliada en §19.6, *Resolution convention matrix*.

**Quién autora el manifiesto de dependencias:** no aplica — stdlib only, no hay archivo de dependencias; el piso de versión lo
verifica Bootstrap con `python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)"`.

---

## 4. Data Model

Convenciones de almacenamiento (valen para toda la base): **montos en `INTEGER` de centavos** (nunca `REAL`; en Python `int`
y `Decimal`), **cantidades en `TEXT`** con `str(Decimal)` (hay cantidades fraccionarias como `3600.001`), **fechas en `TEXT`
`AAAA-MM-DD`** convertidas a mano (sin adaptadores de `sqlite3`), fechas-hora en ISO UTC (`db.ahora_utc()` =
`datetime.now(timezone.utc).isoformat(timespec="seconds")`), **JSON en `TEXT`** con `json.dumps(..., ensure_ascii=False,
sort_keys=True)`. Todas las tablas mutables tienen `version` (control optimista de concurrencia).

### Entities

**config** — parámetros compartidos por las dos PCs (efectores, partidas excluidas, exclusiones, días de gracia, textos fijos).
Se siembra desde `config.json` → `parametros_iniciales` la primera vez que se crea la base.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `clave` | TEXT | PK | nombre del parámetro (`efectores`, `partidas_excluidas`, `dias_gracia`, …) |
| `valor` | TEXT | NOT NULL | JSON del valor |
| `version` | INTEGER | NOT NULL DEFAULT 1 | control optimista |

**proveedor** — un proveedor SAP; se da de alta al importar o al cargar una OC manual.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `sap` | TEXT | PK | número SAP sin ceros a la izquierda (`0000077170` → `77170`) |
| `razon_social` | TEXT | NOT NULL | como figura en SAP o en la OC manual (`GRUPO EFIA S.R.L.`) |
| `cuit`, `email`, `notas` | TEXT | NOT NULL DEFAULT '' | datos de contacto cargados a mano |
| `version` | INTEGER | NOT NULL DEFAULT 1 | |

**oc** — una orden de compra de un efector; nunca se borra (trigger `oc_sin_delete`), se marca `excluida`.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `numero` | TEXT | PK | `4500555861` |
| `efector` | TEXT | NOT NULL, `HBI`/`CASPH` | elegido al importar |
| `sap` | TEXT | NOT NULL, FK → `proveedor.sap` | |
| `clase`, `org_compras`, `centro` | TEXT | DEFAULT '' | del reporte; `centro` decide el efector al importar |
| `ca` | TEXT | DEFAULT '' | `<Licitacion>-<Año Licit>` (`195-2025`) |
| `expediente_contratacion` | TEXT | DEFAULT '' | EX normalizado con `util.normalizar_gde`; es el "N° Expediente" del CV |
| `fecha_oc`, `vig_desde`, `vig_hasta`, `prorroga` | TEXT | fechas ISO o NULL | `vig_hasta` NULL = entrega única sin fin de vigencia |
| `tipo` | TEXT | `SERVICIO`/`BIEN`/`PROVISION` | inferido al importar (paso 6), editable |
| `comodato`, `centralizada` | INTEGER | 0/1 | `comodato` se infiere si la descripción dice `COMODATO`; si no, a mano |
| `objeto`, `objeto_articulo` | TEXT | artículo ∈ `al`, `a la`, `a los`, `a las` | objeto vacío bloquea la autorización |
| `concepto_corto` | TEXT | DEFAULT '' | concepto del Texto SAP (`SERV. FUMIGACIÓN`) |
| `dia_inicio_periodo` | INTEGER | 1..28 | 1 = mes calendario; otro = período específico |
| `gde_pdf_oc`, `leyenda_cv` | TEXT | DEFAULT '' | N° GDE del PDF de la OC; leyenda del CV (obligatoria en centralizadas) |
| `extras_cv`, `doc_requerida_central` | TEXT | JSON `{}` / `[]` | datos extra del CV; documentos que la centralizada exige tildar |
| `origen` | TEXT | `SAP`/`MANUAL` | `MANUAL` = cargada a mano (la OC EFIA 4500555861 de los tests) |
| `cerrada_sap`, `excluida`, `motivo_exclusion` | | 0/1, TEXT | `cerrada_sap` = entrega final o factura final marcada en SAP |
| `campos_manuales` | TEXT | JSON lista | campos editados a mano; la importación nunca los pisa |
| `ultima_importacion` | TEXT | fecha-hora ISO o NULL | |
| `version` | INTEGER | | |

**renglon** — una posición de una OC (PK compuesta `oc`, `pos`).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `oc`, `pos` | TEXT, INTEGER | PK, FK → `oc.numero` | |
| `codigo`, `descripcion` | TEXT | | código de material y texto del renglón |
| `cantidad`, `unidad` | TEXT | Decimal como texto | |
| `precio_centavos`, `importe_centavos` | INTEGER | | precio = columna `Precio unitario` o `Importe / Cant` |
| `partida` | TEXT | DEFAULT '' | partida presupuestaria (solo en reportes que la traen) |
| `sap_entregado`, `sap_facturado`, `sap_por_entregar` | TEXT | Decimal | según SAP; `sap_por_entregar` negativo se lleva a 0 y marca `exceso_sap` |
| `consumo_previo` | TEXT | Decimal | consumo anterior al gestor, cargado a mano |
| `desglose_cantidad`, `desglose_unidad`, `desglose_precio_centavos` | TEXT, TEXT, INTEGER | NULL si no aplica | servicio anual partido en meses (EFIA: 3 MES × 1.224.990) |
| `revisar_desglose`, `exceso_sap`, `revisar_importe`, `es_correctivo` | INTEGER | 0/1 | banderas para la ficha de la OC |
| `campos_manuales`, `crudo` | TEXT | JSON | `crudo` = fila original con claves = encabezados del Excel |
| `version` | INTEGER | | |

**entrega** — lote de expedientes FIRMADO que se envía junto a Contaduría; numerado por efector.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK autoinc | |
| `efector`, `numero` | TEXT, INTEGER | UNIQUE (`efector`, `numero`) | correlativo por efector (HBI 1, 2…; CASPH 1…) |
| `nombre`, `observaciones` | TEXT | | |
| `fecha_envio` | TEXT | fecha ISO o NULL | se completa al enviar |
| `estado` | TEXT | `ABIERTA`/`ENVIADA` | |
| `version` | INTEGER | | |

**expediente** — un expediente de pago; nunca se borra (trigger `expediente_sin_delete`), se ANULA.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK autoinc | |
| `tipo` | TEXT | `COMUN`/`CENTRALIZADA`/`CORRECTIVO`/`EVENTUAL` | |
| `efector` | TEXT | `HBI`/`CASPH` | |
| `oc` | TEXT | FK → `oc.numero`, NULL solo en `EVENTUAL` | |
| `sap` | TEXT | | copiado de la OC (o cargado en `EVENTUAL`) |
| `periodo`, `periodo_desde`, `periodo_hasta` | TEXT | `AAAA-MM`, fechas ISO | sugerido desde los remitos (paso 10) |
| `periodo_manual` | INTEGER | 0/1 | 1 = la usuaria lo fijó; los pegados no lo pisan |
| `factura` | TEXT | DEFAULT '' | N° normalizado `"<pv:04d><letra><numero:08d>"` para buscar repetidas |
| `estado` | TEXT | NOT NULL | ver *Estados* abajo |
| `motivo_pendiente`, `fecha_seguimiento` | TEXT | | estado `PENDIENTE` |
| `motivo_anulacion` | TEXT | | estado `ANULADO` |
| `entrega_id` | INTEGER | FK → `entrega.id` | |
| `datos` | TEXT | JSON | ver *expediente.datos* abajo |
| `creado`, `actualizado`, `usuario` | TEXT | NOT NULL | fecha-hora UTC y usuario de Windows |
| `version` | INTEGER | | |

**evento** — auditoría append-only (triggers `evento_sin_update` y `evento_sin_delete`); se escribe en la **misma transacción**
que la mutación que registra.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK autoinc | |
| `fecha` | TEXT | NOT NULL | ISO UTC |
| `usuario`, `pc` | TEXT | NOT NULL | `getpass.getuser()`, `socket.gethostname()` |
| `accion` | TEXT | `ALTA`/`MODIFICACION`/`ANULACION`/`IMPORTACION`/`RESTAURACION` | |
| `tabla`, `clave` | TEXT | NOT NULL | registro afectado (`clave` en JSON para PK compuestas) |
| `antes`, `despues` | TEXT | JSON o NULL | |

**importacion** — una corrida del importador con su informe.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK autoinc | |
| `fecha`, `archivo`, `efector`, `usuario` | TEXT | NOT NULL | |
| `informe` | TEXT | JSON | filas, descartes por motivo, quedan, OC distintas, duplicados, altas, cambios, avisos, errores |

#### Estados del expediente

| Tipo | Flujo |
|---|---|
| `COMUN`, `CENTRALIZADA` | `BORRADOR` → `CONTROLADO` → `EN_FIRMA` → `FIRMADO` → `ENVIADO` (solo al enviar su entrega) → `CONTABILIZADO` → `CERRADO` |
| `CORRECTIVO` | `RECIBIDO_MANTENIMIENTO` → `INFORME_ECONOMICO` → `DEVUELTO` → `PARA_FACTURAR` → `CONTROLADO` → sigue como `COMUN` |
| `EVENTUAL` | `ARMADO` → `EN_DTO_ECONOMICO_CONTABLE` → `DEVUELTO` → `CONTABILIZADO` → `FINALIZADO` |
| Todos | `PENDIENTE` (con motivo y fecha de seguimiento) desde cualquier estado no final, y `reanudar` vuelve al anterior; `ANULADO` con motivo |

`CONTROLADO` solo se acepta con 0 resultados `error` y cada `salvable` con su nota aclaratoria guardada.

#### expediente.datos

Estructura con la que nace todo expediente (paso 9). Al editar, cada clave de primer nivel que llega reemplaza entera a la
guardada.

```json
{
  "remitos": [],
  "factura": {},
  "sii": {},
  "gde": {},
  "sap": {},
  "notas_aclaratorias": [],
  "checklist": {},
  "correctivo": {},
  "eventual": {},
  "centralizada": {},
  "historial": []
}
```

| Clave | Contenido |
|---|---|
| `remitos[]` | `{"numero", "fecha", "fecha_firma", "es_equipo_comodato", "aclara_periodo", "items": [{"pos", "cantidad", "codigo"}]}` — fechas ISO; `codigo` vacío = igual al de la OC |
| `factura` | `{"numero", "fecha", "centavos", "cae", "vto_cae", "destinatario", "domicilio", "periodo_desde", "periodo_hasta", "menciona"}` — `numero` tal cual figura (`0003B00031812`) |
| `sii` | salida de `comprobantes.analizar_texto_sii` (CAE, fecha, período, monto, tipo, N°, razón social, CUIT, SAP, área, tipo de servicio, concepto, OC, código de trámite) |
| `gde` | `expediente`, `caratula`, `factura`, `sii`, `oc_pdf`, `remitos{}`, `remito_equipo`, `orden_remito_equipo`, `cv`, `vale_hoja`, `autorizacion`, `constancia`, `contabilizacion` — normalizados con `util.normalizar_gde` |
| `sap` | datos de contabilización cargados (número de documento, fecha) |
| `notas_aclaratorias[]` | `{"codigo", "referencia", "texto", "usuario", "fecha"}` |
| `checklist` | `{documento: true/false}` para `oc.doc_requerida_central` (centralizadas) |
| `correctivo` | `procedimiento`, `objeto_correctivo`, `presupuestos[]`, `informes[]`, `monto_convalidado` |
| `eventual` | los campos de la solicitud de pago eventual (§5) |
| `centralizada` | `numero_cv`, `numero_nota`, `fecha_envio` |
| `historial[]` | `{"fecha", "usuario", "accion", "estado"}` — una entrada por alta, edición, cambio de estado o período manual |

#### Limpieza

Reglas del importador (paso 5, `gestor/importar.py`), en este orden. Los números esperados con los reportes reales están en el
paso 5.

1. Las columnas se buscan por **nombre normalizado** (`util.clave_encabezado`: minúsculas, sin tildes, signos → espacio, espacios colapsados; `N° O/C` → `n o c`), nunca por posición.
2. Columnas obligatorias: `N° O/C`, `Posición.`, `Elemento`, `Cant`, `Importe`, `Centro`, `Proveedor`, `Razón Social Proveed`. Falta una → `Falta la columna obligatoria "<nombre>" en el reporte.` y no se escribe nada.
3. Descarte `sin_oc`: fila sin N° O/C (vacía o subtotal).
4. Descarte `partida`: partida en `partidas_excluidas` (default `["3490000"]`, honorarios). `ZGRH` **no** se descarta por clase. Sin columna de partida → aviso `Este reporte no tiene la partida presupuestaria; no se pueden descartar honorarios (3490000). Agregá la columna al layout del z_compras2.` y se importa igual.
5. Descarte `centro`: centro fuera de los del efector elegido (HBI `["1900"]`; CASPH configurable, inicialmente vacío → la pantalla lo pide).
6. Descarte `exclusion_manual`: SAP en `exclusiones.sap` u OC en `exclusiones.oc`.
7. OC, posición y SAP a texto sin ceros a la izquierda; cantidades e importes a `Decimal` redondeados a 2 decimales con tolerancia 0,01.
8. Fechas desde serial de Excel (45971 = 2025-11-10); `vig_hasta < vig_desde` → la fila va a `errores` y no entra.
9. Expediente con `util.normalizar_gde` (espacios colapsados, `%` → `#`); `ca = "<Licitacion>-<Año Licit>"`.
10. Precio = `Precio unitario` o, si falta la columna, `Importe / Cant` redondeado a 2 decimales; `revisar_importe = 1` si `|cantidad × precio − importe| > 1 centavo`.
11. Upsert por (OC, posición) con SELECT + INSERT/UPDATE: nunca pisa un campo de `campos_manuales`; una posición repetida en el mismo reporte deja la última y suma a `duplicados`; `Entrega final`/`Factura final` con `X` → `oc.cerrada_sap = 1`; la fila original va a `renglon.crudo`.

### Relationships

- `proveedor` —(1:N)→ `oc` por `oc.sap`. Sin cascada: los proveedores no se borran.
- `oc` —(1:N)→ `renglon` por `renglon.oc`. Las OC no se borran (trigger), así que no hay cascada.
- `oc` —(1:N)→ `expediente` por `expediente.oc` (NULL en `EVENTUAL`). Los expedientes no se borran (trigger).
- `entrega` —(1:N)→ `expediente` por `expediente.entrega_id`. Las entregas no se borran.
- `evento` referencia cualquier tabla por (`tabla`, `clave`) sin FK: es un registro histórico, append-only.
- Nada se borra físicamente; `PRAGMA foreign_keys = ON` en cada conexión.

### Indexes

| Table | Index | Why |
|---|---|---|
| `oc` | `ix_oc_efector (efector, excluida)` | lista de OC por efector sin las excluidas |
| `oc` | `ix_oc_sap (sap)` | búsqueda por proveedor y control de pago eventual por SAP |
| `expediente` | `ix_expediente_oc_periodo (oc, periodo)` | calendario, consumo por período y expediente duplicado |
| `expediente` | `ix_expediente_estado (estado, fecha_seguimiento)` | pendientes y alertas de Inicio |
| `expediente` | `ix_expediente_entrega (entrega_id)` | armado del CSV NUMERACIÓN |
| `expediente` | `ix_expediente_factura (factura)` | control `factura_repetida` |
| `evento` | `ix_evento_tabla_clave (tabla, clave)` | historial de un registro |

### Schema

`gestor/db.py` → `ESQUEMA` contiene **exactamente** este bloque (paso 2); `db.inicializar` lo ejecuta con `executescript` y
fija `PRAGMA user_version = 1`. Tiene 8 tablas (`config`, `proveedor`, `oc`, `renglon`, `entrega`, `expediente`, `evento`,
`importacion`).

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

### Migrations

Sin herramienta de migraciones (stdlib). `PRAGMA user_version` guarda la versión del esquema (`VERSION_ESQUEMA = 1` en v1).
v1 no implementa migraciones: `db.inicializar` es idempotente gracias a `CREATE ... IF NOT EXISTS`. Regla para una versión
futura (no se construye ahora): cambios solo aditivos (`ALTER TABLE ... ADD COLUMN` con default) aplicados en una transacción
según `user_version`, con backup previo; nunca se borra una columna con datos.

### Seed data

Una base nueva recibe solo la tabla `config` sembrada desde `config.json` → `parametros_iniciales` (efectores HBI y CASPH,
partida `3490000` excluida, días de gracia 10, aviso de vencimiento 60 días, umbral 85 %, límite de Texto SAP 50, email de
carátula, datos SII, destinatario de factura, nota de comodato). No hay datos de demo: la primera acción real es importar el
z_compras2. Los tests usan los datos reales de `tests/fixtures/` a través de `tests/datos_prueba.py` (paso 8) sobre una base
temporal.

---

## 5. API Design

### Conventions

- Base path: `/api/` en `http://127.0.0.1:<puerto>`; los estáticos de `web/` se sirven en `/`, `/app.js`, `/style.css`. Nada fuera de `web/` se sirve (`GET /config.json` → 404).
- Sobre de respuesta, una sola forma: éxito `{"ok": true, "datos": <valor>}`; error `{"ok": false, "error": {"codigo": "<codigo>", "mensaje": "<texto para la usuaria>"}}`. JSON UTF-8 con `ensure_ascii=False`. **Única excepción:** `GET /api/salud` devuelve el objeto plano `{"app": "gestor-expedientes", "version": "0.1.0", "db": "ok"|"sin_base", "usuario": "<usuario de Windows>"}`, en ese orden de claves, porque lo leen `--check` y la detección de "ya está corriendo".
- Códigos de error: `validacion` 400 · `no_encontrado` 404 · `conflicto_version` 409 · `demasiado_grande` 413 · `negocio` 422 · `interno` 500 (`Error interno: <NombreDeLaExcepcion>`, sin traza al cliente).
- Validación: a mano en `gestor/negocio.py` (`ErrorValidacion` → 400, `ErrorNegocio` → 422); los mensajes son frases en español que la UI muestra tal cual.
- Concurrencia: toda escritura de un registro existente lleva `version` en el cuerpo; si no coincide → 409 con `Otra persona guardó cambios en este registro. Recargá para ver la última versión.`
- Subidas: `multipart/form-data` con el campo `archivo`, parseado con `email.parser.BytesParser(policy=email.policy.default)`; `Content-Length` mayor que `tamano_maximo_subida_mb` (25 MB) → 413 sin leer el cuerpo.
- Paginación: NOT APPLICABLE — los volúmenes (cientos de OC, decenas de expedientes por mes) se devuelven completos y se filtran con query string (`efector`, `q`, `estado`).
- Idempotencia: reimportar el mismo reporte no crea nada nuevo (upsert); no hay claves de idempotencia.
- Rate limits: NOT APPLICABLE — servidor ligado a 127.0.0.1, una usuaria por PC.

### Routes

| Method | Path | Description | Auth | Rate limit |
|---|---|---|---|---|
| GET | `/api/salud` | identidad del servidor (plano, sin sobre) | local | — |
| GET | `/api/base/estado` | integridad y último backup | local | — |
| POST | `/api/base/restaurar` | restaura el último backup | local | — |
| POST | `/api/base/backup` | backup manual | local | — |
| POST | `/api/apagar` | apaga el servidor (botón "Cerrar programa") | local | — |
| GET/PUT | `/api/parametros` | parámetros compartidos (tabla `config`) | local | — |
| GET/PUT | `/api/config-local` | `config.json` de esta PC (ruta de la base, puertos) | local | — |
| POST | `/api/importar/vista-previa` | analiza un z_compras2 sin escribir | local | — |
| POST | `/api/importar/confirmar` | importa (upsert) y guarda el informe | local | — |
| GET | `/api/importaciones` | historial de importaciones | local | — |
| GET/POST | `/api/oc` | lista con filtros / alta manual | local | — |
| GET/PUT | `/api/oc/<numero>` | ficha / edición (marca `campos_manuales`) | local | — |
| POST | `/api/oc/<numero>/renglones` | agrega renglón a una OC manual | local | — |
| PUT | `/api/oc/<numero>/renglones/<pos>` | edita renglón (desglose, consumo previo) | local | — |
| GET | `/api/oc/<numero>/consumo` | consumo y saldo por renglón × período | local | — |
| GET/POST | `/api/expedientes` | lista / alta | local | — |
| GET/PUT | `/api/expedientes/<id>` | detalle / edición con versión | local | — |
| POST | `/api/expedientes/<id>/anular` | anula con motivo | local | — |
| POST | `/api/expedientes/<id>/remitos/pegar` | carga rápida de remitos `numero;fecha[;fecha_firma]` | local | — |
| POST | `/api/comprobantes/analizar` | parsea el texto pegado del SII | local | — |
| GET | `/api/expedientes/<id>/controles` | resultados por nivel + notas sugeridas | local | — |
| POST | `/api/expedientes/<id>/notas` | guarda una nota aclaratoria | local | — |
| GET | `/api/expedientes/<id>/textos` | carátula, referencias, autorización, constancia, SAP | local | — |
| GET | `/api/expedientes/<id>/cv.docx` | CV en Word | local | — |
| GET | `/api/expedientes/<id>/autorizacion.docx` | autorización en Word | local | — |
| POST | `/api/expedientes/<id>/estado` | cambia de estado (valida transición) | local | — |
| POST | `/api/expedientes/<id>/reanudar` | sale de `PENDIENTE` | local | — |
| PUT | `/api/expedientes/<id>/gde` | números GDE (validados y normalizados) | local | — |
| PUT | `/api/expedientes/<id>/centralizada` | N° CV, N° nota y fecha de envío | local | — |
| PUT | `/api/expedientes/<id>/correctivo` | datos del correctivo | local | — |
| GET | `/api/calendario` | OC × 12 meses con estado por celda | local | — |
| GET | `/api/inicio/alertas` | alertas de la pantalla Inicio | local | — |
| GET | `/api/pendientes` | expedientes `PENDIENTE` con seguimiento | local | — |
| GET/POST | `/api/entregas` | lista / alta (numeración por efector) | local | — |
| GET | `/api/entregas/<id>` | detalle | local | — |
| POST | `/api/entregas/<id>/asignar` | asigna expedientes FIRMADO | local | — |
| POST | `/api/entregas/<id>/enviar` | envía: entrega `ENVIADA`, expedientes `ENVIADO` | local | — |
| GET | `/api/entregas/<id>/numeracion.csv` | CSV NUMERACIÓN | local | — |
| GET | `/api/exportes/<nombre>.<xlsx\|csv\|html>` | seis exportes | local | — |
| GET | `/api/centralizadas` | tabla de centralizadas por OC × período | local | — |
| GET | `/api/correctivos/informe-mensual` | informe mensual a GESP | local | — |
| POST | `/api/textos/servicio-casph` | autorización AySA/Edenor | local | — |
| GET | `/api/ayuda` | contenido de `docs/INSTRUCTIVO.md` | local | — |

"local" = cualquier proceso de la misma PC; no hay login (§8). El servidor escucha solo en `127.0.0.1`.

### Critical endpoints — full detail

**`GET /api/salud`** (paso 1) — sin cuerpo. 200 `{"app": "gestor-expedientes", "version": "0.1.0", "db": "ok", "usuario": "<usuario>"}`;
`db` = `"sin_base"` si la base no se pudo abrir o crear. Sin efectos. `python app.py --check` levanta el servidor en un puerto
libre, hace este GET, imprime el JSON en una línea y sale 0.

**`POST /api/importar/confirmar`** (paso 7) — multipart: `archivo` (.xlsx), `efector` (`HBI`/`CASPH`). 200 `{"ok": true, "datos":
<informe>}` con `filas`, `descartes` (`sin_oc`, `partida`, `centro`, `exclusion_manual`), `quedan`, `oc_distintas`,
`duplicados`, `altas`, `actualizadas`, `sin_cambios`, `cambios`, `avisos`, `errores`. Errores: falta `efector` o es inválido → 400;
CASPH sin centros configurados → 422 `Configurá los centros SAP de CASPH antes de importar.`; falta una columna obligatoria → 400
`Falta la columna obligatoria "<nombre>" en el reporte.`; archivo > 25 MB → 413. Efectos: upsert en `proveedor`, `oc`, `renglon`,
una fila en `importacion` y un evento `IMPORTACION`, todo en una transacción.

**`PUT /api/expedientes/<id>`** (paso 9) — `{"version": n, ...campos editables..., "datos": {...claves a reemplazar...}}`. 200 con
el expediente nuevo (`version` n+1). Errores: id inexistente → 404; `version` vieja → 409 (mensaje fijo); expediente `ANULADO` →
422 `El expediente está anulado.`; valor inválido → 400. Efectos: `UPDATE ... WHERE id = ? AND version = ?`,
entrada en `datos.historial`, evento `MODIFICACION`, columna `factura` normalizada si llega `datos.factura.numero`.

**`GET /api/expedientes/<id>/controles`** (pasos 13–14) — 200 `{"ok": true, "datos": {"resultados": [{"codigo", "nivel", "ambito",
"mensaje", "referencia", "nota_sugerida", "nota_guardada"}], "resumen": {"error": n, "salvable": n, "aviso": n, "verificar": n}}}`.
Sin efectos (lectura). 404 si no existe.

**`POST /api/expedientes/<id>/estado`** (paso 20) — `{"version": n, "estado": "<nuevo>", "motivo": "...", "fecha_seguimiento": "..."}`.
Transición no permitida → 422 `No se puede pasar de <A> a <B>.`; `CONTROLADO` con errores o salvables sin nota → 422 `No se puede pasar a CONTROLADO: hay <n> errores y <m> salvables sin nota.`; `ENVIADO`
solo vía `/api/entregas/<id>/enviar`. Efectos: estado, historial, evento.

### Controles del expediente

Implementados en `gestor/controles.py` (pasos 13, 14, 27, 29). Niveles: **error** (bloquea `CONTROLADO`), **salvable** (se acepta
con nota aclaratoria guardada), **aviso** (informativo), **verificar** (la usuaria confirma a ojo).

| Código | Nivel | Qué controla | Mensaje fijo (los tests lo comparan) |
|---|---|---|---|
| `importe_factura` | error, nunca salvable | importe de la factura = Σ cantidad × precio, exacto al centavo | `El importe de la factura ($ 1.224.990,01) no coincide con cantidad × precio ($ 1.224.990,00).` (con los montos del caso) |
| `destinatario_factura` | error | `datos.factura.destinatario` en mayúsculas = `parametros.destinatario_factura.nombre` (`INSSJP`) | — |
| `domicilio_factura` | error | `util.normalizar_domicilio(datos.factura.domicilio)` (mayúsculas, sin tildes, sin `.,;:-/`, espacios colapsados: `Perú 169, C.A.B.A.` → `PERU 169 CABA`) empieza con `parametros.destinatario_factura.domicilio` (`PERU 169`) | — |
| `periodo_factura` | salvable | `datos.factura.periodo_desde`/`periodo_hasta` dentro del período validado; **sin resultado** si la factura no trae período. En la nota, el período de la factura se escribe `AAAA-MM` (= `periodo_desde[:7]`) si desde y hasta caen en el mismo mes, si no `dd/mm/aaaa al dd/mm/aaaa` | ver paso 14 |
| `menciones_factura` | salvable | cada valor de `datos.factura.menciona` (`oc`, `expediente`, `remito`) = valor real; **sin resultado** si `menciona` falta o está vacío | ver paso 14 |
| `formato_factura` | error | N° de factura válido y CAE de 14 dígitos | — |
| `vencimiento_cae` | error / verificar | vto CAE ≥ fecha de emisión (error si no); sin vencimiento → `verificar`, nunca `error` | — |
| `factura_repetida` | error | otra factura igual (`util.misma_factura`) en un expediente no anulado | — |
| `sii_coincide` | error | OC, N°, CAE y monto del SII = factura y OC | — |
| `sii_periodo` | error | período del SII = período validado | — |
| `sii_destino` | error | área, tipo de servicio y concepto = `parametros.sii` | — |
| `remito_fuera_de_periodo` | error, uno por remito | remito (no de equipo, sin `aclara_periodo`) fuera del período | `El remito <numero> (<dd/mm/aaaa>) está fuera del período <AAAA-MM>.` |
| `codigo_remito_distinto` | salvable, uno por renglón | código en el remito ≠ código de la OC | `El remito <numero> indica el código <codigo_remito> en el renglón <pos>; la OC tiene <codigo_oc>.` |
| `formato_remito` | aviso | número con forma `^\d{4,5}-\d{8}$` | — |
| `vigencia_oc` | error | período dentro de la vigencia (o prórroga) | — |
| `saldo_renglon` | error | cantidades del expediente ≤ saldo del renglón | — |
| `comodato_sin_remito_equipo` | error | OC con comodato, primera validación, sin remito de equipo | `Primera validación de OC con comodato sin remito del equipo.` |
| `expediente_duplicado` | aviso | otro expediente no anulado de la misma OC y período | — |
| `renglon_por_agotarse` | aviso | consumo ≥ `umbral_por_agotarse_pct` (85 %) | — |
| `objeto_faltante` | error | la OC tiene objeto | `Falta el objeto de la contratación en la OC 4500594643` (con el N° de OC) |
| `documentacion_centralizada` | error | cada documento de `doc_requerida_central` tildado | `Falta tildar como auditada la documentación: Factura.` |
| `leyenda_cv_faltante` | error | centralizada con `leyenda_cv` | `Falta la leyenda del CV en la OC 4500000001.` |
| `eventual_repetido` | error | un solo pago eventual por SAP y año | `Ya hay un pago eventual para el proveedor SAP <sap> en <año> (expediente <id>).` |

"Primera validación" = no hay otro expediente no anulado de la misma OC en `CONTROLADO` o posterior. Los mensajes marcados "—"
los redacta el paso que crea el control; los tests de esos controles comparan el `codigo` y el `nivel`, no el texto.

### Textos canónicos

Cada texto sale de **una** función de `gestor/textos.py`. `<razon>` es siempre `proveedor.razon_social` tal cual está guardada (una sola fuente para carátula, referencias, autorización y constancia). `<campo>` es un dato; todo lo demás es literal. `MM-AA` y `MM/AA` son
el **período validado** (`08-26`), nunca la fecha de la factura. CASPH antepone `CASPH - ` a carátulas y referencias.

#### Carátula y referencias GDE

- Carátula: `PAGO SAP <sap> <razon> - FC <factura> - <oc>`. Goldens: `PAGO SAP 77170 GRUPO EFIA S.R.L. - FC 0003B00031812 - 4500555861` · `PAGO SAP 116467 BIO FAB S.R.L - FC 00002B00003908 - 4500587121` · `PAGO SAP 118896 MACATEX S.A - FC 0002B00000160 - 4500594643`.
- Pago eventual: `<SIGLA> - PAGO EVENTUAL - <razon> - FC N° <factura>`. Email de carátula configurable (`contablehbi@pami.org.ar`; pago eventual `hbicontable@gmail.com`, tel 1161757182).
- Referencias, en orden: `MM-AA - FC <factura> - <razon>` · `MM-AA - CARGA EN SII - <razon>` · un remito `MM-AA - RTO <n> - <razon>` / dos o más **un solo** `MM-AA - REMITOS - <razon>` · `MM-AA - REMITO POR EQUIPO EN COMODATO - <razon>` (primera validación con remito de equipo) · `MM-AA - CERTIFICADO DE VALIDACIÓN - <razon>` · `MM-AA - VALE DE ENTRADA - <razon>` (bien/provisión) o `MM-AA - HOJA DE ENTRADA - <razon>` (servicio) · `AUTORIZACIÓN DE PAGO FC N° <factura>, <razon> - MM-AA` · `MM-AA - CONSTANCIA DE CONTABILIZACIÓN - <razon>`.
- Nombre de archivo = referencia con cada uno de `\ / : * ? " < > |` reemplazado por `-`, más `.pdf`.

#### Autorización de pago

Referencia: `AUTORIZACIÓN DE PAGO FC N° <factura>, <razon> - MM-AA` (CASPH: `CASPH - ` delante). Cuerpo, en una sola línea:

`Por medio del expediente <EX> AUTORIZO se abone la factura N° <factura> por la suma de <importe_en_letras> del proveedor <razon> correspondiente <articulo> <objeto>, <frase_remitos><frase_comodato>, con destino <destino>, <frase_periodo> de acuerdo a la Orden de compra N° <oc>.`

- `<importe_en_letras>` = `PESOS <LETRAS> CON <cc>/100 CENTAVOS ($ <n.nnn,cc>-)` (espacio después de `$`).
- `<frase_remitos>`: 1 → `conforme al remito N° A`; 2 → `conforme a los remitos N° A y B`; 3+ → `conforme a los remitos N° A, B y C` (sin el remito del equipo).
- `<frase_comodato>` (OC con comodato, primera validación y remito de equipo): `, y el remito n° <X>, correspondiente al equipo entregado en calidad de comodato`.
- `<destino>`: HBI `al Hospital del Bicentenario de Ituzaingó`; CASPH `al Centro Ambulatorio de Salud PAMI Hurlingham`.
- `<frase_periodo>`: día de inicio 1 → `en el mes de <mes en minúsculas> del <AAAA>`; otro → `en el período del <dd/mm/aaaa> al <dd/mm/aaaa>`.
- Objeto vacío → `TextoIncompleto("Falta el objeto de la contratación en la OC <oc>")`; nunca se devuelve un texto con huecos.

Golden EFIA (EX-2026-89654857):

```text
Por medio del expediente EX-2026-89654857- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 0003B00031812 por la suma de PESOS UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100 CENTAVOS ($ 1.224.990,00-) del proveedor GRUPO EFIA S.R.L. correspondiente al servicio de control integral de plagas, fumigación, desinsectación y desratización, conforme al remito N° 00001-00029461, con destino al Hospital del Bicentenario de Ituzaingó, en el mes de agosto del 2026 de acuerdo a la Orden de compra N° 4500555861.
```

Referencia EFIA: `AUTORIZACIÓN DE PAGO FC N° 0003B00031812, GRUPO EFIA S.R.L. - 08-26`. Diferencias aceptadas contra el original
`0009_IF-2026-91157933`: agrega `, con destino al Hospital del Bicentenario de Ituzaingó,` y `del` antes del año; quitándolas,
coincide palabra por palabra con el párrafo del fixture (espacios normalizados).

Golden BIO FAB (EX-2026-94963848, primera validación con comodato):

```text
Por medio del expediente EX-2026-94963848- -INSSJP-GESP#INSSJP AUTORIZO se abone la factura N° 00002B00003908 por la suma de PESOS VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100 CENTAVOS ($ 21.095.000,00-) del proveedor BIO FAB S.R.L correspondiente a la provisión de inmunoensayo por fluorescencia, conforme al remito N° 0001-00003354, y el remito n° 0001-00003281, correspondiente al equipo entregado en calidad de comodato, con destino al Hospital del Bicentenario de Ituzaingó, en el mes de agosto del 2026 de acuerdo a la Orden de compra N° 4500587121.
```

#### Importe en letras

Mayúsculas sin tildes salvo `MILLÓN`; `UN` ante MIL/MILLÓN/MILLONES y al final; 21 `VEINTIUN`, 22 `VEINTIDOS`, 23 `VEINTITRES`,
26 `VEINTISEIS`; 100 `CIEN`, 101–199 `CIENTO …`; 500 `QUINIENTOS`, 700 `SETECIENTOS`, 900 `NOVECIENTOS`; 1.000 `MIL`;
1.000.000 `UN MILLÓN`; ≥ 2 M `… MILLONES`. Casos: 1224990 → `UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100` ·
21095000 → `VEINTIUN MILLONES NOVENTA Y CINCO MIL CON 00/100` · 33881600 → `TREINTA Y TRES MILLONES OCHOCIENTOS OCHENTA Y UN MIL SEISCIENTOS CON 00/100` ·
22101872,13 → `VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100` · 1000 → `MIL CON 00/100` · 100 → `CIEN CON 00/100` ·
3700000 → `TRES MILLONES SETECIENTOS MIL CON 00/100`.

#### Constancia de recepción de comodato

Referencia: `CONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC <oc>, <razon>`. Cuerpo, dos párrafos:

```text
Por medio de la presente, y de conformidad con lo solicitado en la NO-2026-38484415-INSSJP-GESP#INSSJP, se deja constancia de la recepción del equipamiento cedido en comodato por el proveedor <razon> (SAP <sap>), correspondiente a la Orden de Compra N° <oc>.
Dicha entrega se encuentra debidamente respaldada mediante el remito N° <rto_equipo>, el cual consta vinculado en orden <orden> del <EX> y embebido al presente documento para su validación.
```

Golden BIO FAB: razón `BIO FAB S.R.L` (la de `proveedor.razon_social`, igual que en la carátula y la autorización), SAP 116467, OC 4500587121, remito `0001-00003281`, orden 7, EX
`EX-2026-94963848- -INSSJP-GESP#INSSJP`; coincide con el cuerpo del fixture `0008_PV-2026-96851161` normalizando espacios. Diferencia
aceptada y documentada: el original escribe `BIO FAB S.R.L.` (con punto final); la comparación reemplaza esa forma por `BIO FAB S.R.L`.

#### Nota a Central (centralizadas)

Referencia: `VALIDACIÓN DE BIENES Y SERVICIOS <razon> - <expediente_contratacion>, período <MM-AAAA o período específico>`. Cuerpo:
`Se envían como archivos embebidos la validación del servicio y remito correspondientes al proveedor <razon>, del <expediente_contratacion>, con orden de compra <oc>, período <periodo>.`
seguido de `Documentación embebida:` y una línea `- <documento>` por documento de la checklist.

#### Frase final del CV

1 remito: `Se valida con remito <A> correspondiente al período <P>.` · varios: `Se valida con remitos <A>, <B> y <C> correspondientes al período <P>.`
(`<P>` = `agosto 2026` o `17/10/2026 al 16/11/2026`). Centralizadas: la `leyenda_cv` de la OC en el párrafo `Observaciones:`.

#### Textos SAP

Ingreso: fecha de documento `01.MM.AAAA`; Texto `<SIGLA> - OC <oc> - <concepto_corto> - MM/AA` (golden `HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26`);
asignación `OC <oc>`; TXT cabecera `0000-0000-0000000-0`; clase `KE`. Contabilizada: TXT cabecera `MM/AA <SIGLA> OC <oc>`
(golden `08/26 HBI OC 4500555861`). Texto más largo que `limite_texto_sap` (50) → aviso `El Texto tiene <n> caracteres; el límite configurado es <limite>.`
Entrada: `ML81N` (servicio) o `MIGO` (bien/provisión), fecha de documento `01.MM.AAAA`, fecha de contabilización = fecha del remito
`dd.mm.aaaa`, texto breve `<concepto_corto> - MM/AA`.

#### Solicitud de pago eventual

Referencia: `SOLICITUD PAGO EVENTUAL - [N° EXPEDIENTE PRINCIPAL] - [ESTABLECIMIENTO/HOSPITAL] - [NOMBRE DEL PROVEEDOR]`. Ocho
párrafos literales (cada `[CAMPO]` se reemplaza por su dato; si falta uno → `Falta <CAMPO> en la solicitud de pago eventual.`):

```text
P1: Por la presente se solicita el pago eventual de la Factura tipo "[B/C]" N° [NÚMERO DE FACTURA], de fecha [FECHA DE EMISIÓN DE FACTURA], por la suma total de $ [MONTO EN NÚMEROS].- (PESOS [MONTO EN LETRAS] CON [XX]/100 CENTAVOS), correspondiente al período del [FECHA INICIO] al [FECHA FIN], del proveedor [RAZÓN SOCIAL DEL PROVEEDOR] (SAP [N SAP]), vinculada al expediente [N° EXPEDIENTE], a través del [N° DOCUMENTO FINANCIERO/DOCFI], vinculado en orden [N° DE ORDEN].
P2: La citada factura corresponde al [TIPO DE SERVICIO, EJ: MANTENIMIENTO PREVENTIVO DE LOS ASCENSORES] pertenecientes al [NOMBRE DEL ESTABLECIMIENTO DETALLADO], tal como se describe en el remito N° [NÚMERO DE REMITO] perteneciente al periodo [FECHA INICIO] al [FECHA FIN] tal cual lo describe la factura, vinculado mediante [N° DOCUMENTO REMITO] en orden [N° DE ORDEN].
P3: Las tareas específicas de [TIPO DE SERVICIO] se encuentran detalladas en el informe técnico brindado por [NOMBRE DEL PROVEEDOR], el cual se encuentra embebido en la [N° PROVIDENCIA INFORME], orden [N° DE ORDEN]. La mencionada providencia fue confeccionada y firmada por el [CARGO DEL RESPONSABLE TÉCNICO], [NOMBRE Y APELLIDO DEL RESPONSABLE], quien da conformidad e informa sobre el correcto funcionamiento de los equipos al día de la fecha.
P4: De la consulta efectuada en el CUP - Padrón de Prestadores y Proveedores del Instituto, se verifica que la firma [RAZÓN SOCIAL DEL PROVEEDOR] (SAP [CÓDIGO SAP]), titular de la CUIT N° [NÚMERO DE CUIT], no registra suspensión ni inhabilitación para contratar, resultando su estado válido.
P5: La Orden de Compra N° [NÚMERO DE ORDEN DE COMPRA] se encontraba vencida el día [FECHA DE VENCIMIENTO], habiendo sido tramitada por el expediente [N° EXPEDIENTE ANTERIOR]. No obstante, el proveedor siguió prestando el servicio, manteniéndose el precio y las bases y condiciones de la contratación. Asimismo, se solicitó la prórroga de dicha Orden de Compra mediante la [N° PROVIDENCIA PRÓRROGA], en orden [N° DE ORDEN] del citado expediente.
P6: Asimismo, se deja constancia de que la presente tramitación cuenta con la correspondiente autorización de la [NOMBRE DE LA GERENCIA COMPETENTE], conforme a lo establecido en la [N° NOTA AUTORIZACIÓN], orden [N° DE ORDEN], mediante la cual se habilita la continuidad del servicio bajo la modalidad de pago eventual, en función de las razones expuestas en las actuaciones.
P7: Finalmente, se deja constancia de que este Efector no ha cursado durante el corriente año ningún pedido de pago eventual a la firma mencionada.
P8: Con el Visto Bueno de esta Dirección, y atento a la urgencia y necesidad del caso, por no encontrarse la prestación bajo marco contractual, se giran las presentes actuaciones para su consideración y prosecución del trámite.
```

Los prefijos `P1:` … `P8:` numeran los párrafos en este documento y **no** forman parte del texto generado. El monto de P1 queda
`$ <formato_pesos>.- (PESOS <letras> CON <cc>/100 CENTAVOS)`; con 2210187213 centavos:
`$ 22.101.872,13.- (PESOS VEINTIDOS MILLONES CIENTO UN MIL OCHOCIENTOS SETENTA Y DOS CON 13/100 CENTAVOS)`.

#### AySA y Edenor (CASPH)

Dos párrafos cada uno. `<MES>` en mayúsculas; `<letras>` = `numero_a_letras(centavos // 100)`. AySA escribe `con` en minúscula
y Edenor `CON`, como los modelos.

```text
AySA: Por medio de la presente se autoriza el pago de la factura N° <fc> de la empresa AySA (AGUA Y SANEAMIENTOS ARGENTINOS S.A.), SAP 70262, por un monto de PESOS <letras> con <cc>/100 CENTAVOS ($ <monto>-) correspondiente al mes de <MES> <AÑO>, por el servicio de CLOACA del Centro Ambulatorio de Salud PAMI Hurlingham de acuerdo a la factura vinculada al <EX>.
Edenor: Por medio de la presente se autoriza el pago de la factura N° <fc> de la EMPRESA DISTRIBUIDORA Y COMERCIALIZADORA NORTE S.A. por un monto de PESOS <letras> CON <cc>/100 CENTAVOS ($ <monto>-), correspondiente al mes de <MES> <AÑO>, por el servicio de provisión de energía eléctrica del Centro Ambulatorio de Salud PAMI Hurlingham, de acuerdo a la factura vinculada al expediente <EX>.
Segundo párrafo (ambos): Atento a que por el artículo 5 de la RESOL-2023-926-INSSJP-DE#INSSJP se estableció que el Centro Ambulatorio de Salud PAMI Hurlingham, funcionará transitoriamente como una unidad orgánica anexa del Hospital de Alta complejidad del Bicentenario Ituzaingó dependiente de la Gerencia de Efectores Sanitarios Propios, exclusivamente para proveer los bienes y servicios esenciales necesarios que permitan su efectivo y habitual funcionamiento. Sin más, se eleva para su intervención.
```

Los rótulos `AySA:`, `Edenor:` y `Segundo párrafo (ambos):` no forman parte del texto generado.

#### Correctivo y otros

- Informe económico: `Diferencia entre presupuestos: $ <dif> (<pct> %).` con `pct = round((mayor − menor) / menor × 100)` (5.000.000 y 8.700.000 → `$ 3.700.000,00 (74 %)`).
- Referencia de correctivo (circuito PAMI00058): `<SAP> <razon> - OC <oc> - <procedimiento> - <objeto> - MANTENIMIENTO CORRECTIVO - <objeto_correctivo>`.
- Números GDE: se normalizan (`%` → `#`, espacios colapsados, `EX-2026-89654857- -INSSJP-GESP#INSSJP` es la forma canónica) y la forma normalizada se valida con `util.RE_GDE` = `^(EX|IF|PV|RM|DOCFI|NO|ME|PROSA|IFGRA|ITFCO)-\d{4}-\d{6,9}-( -)?INSSJP-[A-Z0-9]+#INSSJP$`.

---

## 6. Frontend Architecture

Una sola página (`web/index.html`) con 8 pantallas (más Ayuda desde el paso 32), servida por el mismo `server.py`. Sin
framework, sin build y sin CDN: la PC del trabajo puede no tener internet.

### Routes

| Route | Page | Data source | Auth |
|---|---|---|---|
| `/` → `#pantalla-inicio` | Inicio: alertas (atrasados, OC por vencer, renglones por agotarse, pendientes vencidos, integridad de la base) | `GET /api/inicio/alertas`, `GET /api/base/estado` | local |
| `#pantalla-calendario` | Calendario OC × 12 meses | `GET /api/calendario` | local |
| `#pantalla-oc` | Lista y ficha de OC, alta manual, renglones, consumo | `/api/oc*` | local |
| `#pantalla-expedientes` | Lista, pendientes y asistente de 7 pasos | `/api/expedientes*`, `/api/pendientes`, `/api/comprobantes/analizar` | local |
| `#pantalla-centralizadas` | Tabla de centralizadas por OC × período | `GET /api/centralizadas` | local |
| `#pantalla-entregas` | Entregas, asignación, envío, CSV NUMERACIÓN | `/api/entregas*` | local |
| `#pantalla-importar` | Vista previa e importación del z_compras2 | `/api/importar/*`, `/api/importaciones` | local |
| `#pantalla-configuracion` | Parámetros compartidos, config local, backup, cerrar programa | `/api/parametros`, `/api/config-local`, `/api/base/backup`, `/api/apagar` | local |
| `#pantalla-ayuda` (paso 32) | Instructivo | `GET /api/ayuda` | local |

Asistente de expediente (pantalla Expedientes): 1 OC y período · 2 remitos (pegado) · 3 factura y SII (pegado) · 4 controles y
notas aclaratorias · 5 documentos (textos, CV, autorización, copiar con formato) · 6 números GDE · 7 estado, entrega y
seguimiento.

### Rendering strategy

Todo se renderiza en el cliente: `index.html` es estático y `app.js` pide JSON y arma el DOM con `document.createElement` y
`textContent` (nunca `innerHTML` con datos: vienen de Excel y de texto pegado). Los estáticos se sirven con `Cache-Control:
no-store` para que una actualización del programa se vea sin limpiar el navegador.

### Component hierarchy

```
index.html
  header: título + <select id="selector-efector"> (HBI / CASPH / Ambos)
  nav: 8 botones (uno por pantalla) — el activo con aria-current="page"
  main#contenido
    section#pantalla-expedientes
      tabla de expedientes (filtros: estado, período) + lista de pendientes
      asistente: <ol> de 7 pasos; cada paso es un <form> con su botón Guardar (envía version)
        paso 4: lista de resultados por nivel (palabra + color) + nota sugerida editable
        paso 5: bloques de texto con botones "Copiar" y "Copiar con formato", enlaces .docx
  div#avisos (aria-live="polite") — mensajes de la API y el botón Recargar ante un 409
```

### State management

Estado del servidor = la base; el cliente no cachea más que la pantalla abierta. `app.js` guarda en memoria solo: pantalla
activa, efector elegido (también en `localStorage`, envuelto en `try/catch`) y el registro abierto con su `version`. Toda llamada
pasa por `api(metodo, ruta, cuerpo)`, que devuelve `datos` o muestra `error.mensaje` en `#avisos`; un 409 muestra el mensaje fijo
y un botón "Recargar" que vuelve a pedir el registro. No hay actualizaciones optimistas: se pinta lo que devuelve el servidor.

### Loading, empty, and error states

- Carga: cada pantalla muestra `Cargando…` en su contenedor hasta que llega la respuesta.
- Vacío: OC → `Todavía no hay OC. Importá un z_compras2 desde la pantalla Importar.`; Expedientes → `No hay expedientes con estos filtros.`; Calendario → `No hay OC vigentes para este efector.`; Entregas → `No hay entregas abiertas.`; Pendientes → `No hay pendientes.`
- Error: el `mensaje` de la API en `#avisos` con estilo de error; `db: "sin_base"` en `/api/salud` → banner rojo `No se pudo abrir la base de datos. Revisá la ubicación en Configuración.`; integridad `falla` → banner rojo con botón `Restaurar la última copia`.

---

## 7. Design System

Fondo claro, azul institucional sobrio, botones grandes, tablas compactas, todo en español. **Sin modo oscuro** (§1 Non-Goals):
la columna *Dark* repite el valor claro porque la app fija `color-scheme: light`.

### Colors

Tokens como variables CSS en `:root` de `web/style.css`:

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--primario` | `#1F4E8C` | `#1F4E8C` | botones principales, enlaces, botón de nav activo |
| `--primario-hover` | `#173D6E` | `#173D6E` | hover/activo de botones principales |
| `--primario-texto` | `#FFFFFF` | `#FFFFFF` | texto sobre `--primario` |
| `--fondo` | `#F6F8FA` | `#F6F8FA` | página |
| `--superficie` | `#FFFFFF` | `#FFFFFF` | paneles, tablas, formularios |
| `--borde` | `#D0D7DE` | `#D0D7DE` | divisores y bordes de tablas (decorativos) |
| `--borde-control` | `#8C959F` | `#8C959F` | borde de inputs y selects (límite de componente) |
| `--texto` | `#1B2430` | `#1B2430` | texto de cuerpo |
| `--texto-suave` | `#57606A` | `#57606A` | texto secundario |
| `--error` | `#B3261E` | `#B3261E` | errores, nivel `error`, estado atrasado |
| `--error-fondo` | `#FDECEA` | `#FDECEA` | fondo de mensajes de error |
| `--exito` | `#2E7D32` | `#2E7D32` | confirmaciones, estado validado |
| `--aviso` | `#8A5300` | `#8A5300` | texto de nivel `aviso` |
| `--aviso-fondo` | `#FFF4E0` | `#FFF4E0` | fondo de avisos |
| `--pendiente-plazo` | `#FFE08A` | `#FFE08A` | celda amarilla "pendiente en plazo" (con texto `--texto`) |
| `--info` | `#1565C0` | `#1565C0` | nivel `verificar`, estado en curso |
| `--violeta` | `#6A3FA0` | `#6A3FA0` | nivel `salvable`, pendiente con motivo |
| `--gris-fuera` | `#C9CED6` | `#C9CED6` | celda fuera de vigencia (con texto `--texto`) |
| `--naranja` | `#C2410C` | `#C2410C` | borde "OC vence en ≤ 60 días" |
| `--foco` | `#1F4E8C` | `#1F4E8C` | anillo de foco (`outline: 3px solid var(--foco); outline-offset: 2px`) |

**Contraste** (WCAG 2.2 AA, medido): `--texto` sobre `--fondo` 14,7:1 · blanco sobre `--primario` 8,31:1 · `--aviso` sobre
`--aviso-fondo` 5,81:1 · `--error` sobre `--error-fondo` 5,72:1 · blanco sobre `--violeta` 7,42:1 · blanco sobre `--exito`
5,13:1 · blanco sobre `--info` 5,75:1 · `--texto` sobre `--gris-fuera` 9,9:1 · `--texto` sobre `--pendiente-plazo` 12,14:1 ·
`--borde-control` sobre blanco 3,04:1 (límite de componente, mínimo 3:1). El ámbar sugerido originalmente (`#B26A00`) daba 3,89:1
sobre su fondo y se oscureció a `#8A5300`.

### Typography

| Role | Family | Size / line-height | Weight | Tracking |
|---|---|---|---|---|
| Display (título de pantalla) | `"Segoe UI", system-ui, sans-serif` | 24px / 1.3 | 600 | 0 |
| Heading | `"Segoe UI", system-ui, sans-serif` | 20px / 1.3 y 18px / 1.35 | 600 | 0 |
| Body | `"Segoe UI", system-ui, sans-serif` | 16px / 1.5 | 400 | 0 |
| Mono (números GDE, textos SAP) | `Consolas, "Cascadia Mono", monospace` | 15px / 1.4 | 400 | 0 |

Importes y cantidades con `font-variant-numeric: tabular-nums` y alineados a la derecha. **Carga de fuentes:** ninguna; fuentes
del sistema (sin internet).

### Spacing, radius, elevation

- Espaciado: base 4px; escala 4, 8, 12, 16, 24, 32, 48.
- Radio: 4px en botones e inputs, 6px en paneles; celdas del calendario 2px.
- Sombras: paneles `0 1px 2px rgba(27, 36, 48, 0.08)`; diálogos `0 4px 16px rgba(27, 36, 48, 0.16)`.
- Botones: alto mínimo 44px, padding 10px 16px. Tablas compactas: celdas con padding 6px 8px.
- Ancho máximo del contenido: 1280px · Puntos de quiebre: 900px (el menú lateral pasa arriba).

### Motion

Sin animaciones salvo transiciones de color de 120ms `ease-out` en hover. Con `prefers-reduced-motion: reduce` se desactivan
(`transition: none`).

### Component style

Herramienta de oficina sobria: superficies blancas sobre gris claro, un solo color de acción (azul), estados siempre con
**palabra o letra además del color** (calendario: `-` fuera de vigencia, `V` validado, `C` en curso, `P` pendiente en plazo, `A`
atrasado, `M` pendiente con motivo, `·` sin iniciar; ● entrega enviada, ◆ CV/nota de centralizada enviada). Un componente nuevo
pertenece si es denso, legible a 16px y no usa color como única señal.

---

## 8. Authentication & Authorization

NOT APPLICABLE — no hay cuentas ni login por decisión de la entrevista (§1 Non-Goals): son 2 personas de la misma área en una red
interna y el servidor escucha solo en `127.0.0.1`, así que nadie fuera de la propia PC llega a la API. La identidad es el usuario
de Windows (`getpass.getuser()`) y la PC (`socket.gethostname()`), que se registran en cada evento de auditoría (§4, tabla
`evento`) y en `datos.historial`. No hay roles: las dos usuarias pueden hacer todo.

---

## 9. BUILD ORDER

Este es el conjunto de instrucciones. Un builder que sigue esta sección al pie de la letra y para cuando cada gate queda en
verde entrega el proyecto.

### The rules of a step

1. **Una sentada por paso.** Máximo 5 archivos y 2–6 criterios de aceptación por paso.
2. **Cada paso tiene los cuatro campos:** `Do` (con *Files touched*), `Done when` (EARS), `Verify` (comandos POSIX, desde la
   raíz del proyecto, en Git Bash) y `Checkpoint` (commit + tag `step-NN-<slug>`). El orden es siempre Do → Done when → Verify →
   Checkpoint; ningún Verify depende de un commit o un tag de su propio paso.
3. **Cada comando de Verify sale 0 cuando el paso está bien.** El comentario `# expect:` dice qué se espera. Ninguno exige una
   salida no cero.
4. **Un paso no está terminado hasta que pasan sus Verify *y* la suite completa** (`python -W error::DeprecationWarning -m unittest discover -s tests -t .`),
   que es el último comando de cada Verify: ningún paso puede romper el gate de un paso anterior.
5. **Cada paso escribe sus propios tests.** El archivo `tests/test_<x>.py` que corre un Verify está en *Files touched* de ese
   paso o de uno anterior; `tests/ayudas.py` y los fixtures llegan por `workspace/` (§19.6). No se edita ningún Verify.
6. **Los nombres de las clases y métodos de test de cada paso son obligatorios:** son el contrato de la prueba. Se pueden
   agregar más tests, nunca quitar los nombrados.
7. **Fail fast:** el paso 1 crea el entry point y su Verify lo **ejecuta** (`python app.py --check`); desde el paso 1 casi todos
   los Verify vuelven a correrlo.
8. **Nada de dependencias externas:** si un paso parece necesitar `pip install`, es un defecto del blueprint — parar y reportar.
9. **No editar** `plantillas/`, `tests/fixtures/`, `tests/ayudas.py` ni `blueprints/`. `config.json` solo lo edita la app en
   runtime (`PUT /api/config-local`).
10. **Si algo falla después de un Checkpoint**, volver al tag del paso anterior (`git reset --hard step-NN-<slug>`) en lugar de
    depurar hacia adelante.

### One step, one unit — the counting rule

Un paso = una tarea de `tasks.json` = un bloque de tarea en un epic, con el mismo id, el mismo tag y los mismos criterios.
Son **32 pasos en 5 epics** (8 + 7 + 6 + 5 + 6). Es más que el rango habitual de 10–18 porque el alcance de v1 es amplio (≈30
pasos pedidos en la entrevista); el hito "prototipo usable" es el paso 21 (fin del epic 03) y los epics 04–05 se pueden
posponer sin romper nada (§20.2).

### Step map

Columnas: *Depends on* = números de paso; *Touches* = archivos del paso. El gate de cada paso es su bloque Verify (abajo); todos
terminan con `python -m compileall -q app.py gestor tests` y la suite completa.

| Paso | Tarea | Epic | Título (Goal) | Depends on | Touches |
|---|---|---|---|---|---|
| 1 | `E1-T1` | `01-nucleo-y-oc` | Entry point app.py, servidor y /api/salud con --check | — | `app.py`<br>`gestor/__init__.py`<br>`gestor/config.py`<br>`gestor/server.py`<br>`tests/test_servidor.py` |
| 2 | `E1-T2` | `01-nucleo-y-oc` | Capa de datos SQLite: esquema, versión, auditoría y backups | 1 | `gestor/db.py`<br>`gestor/server.py`<br>`app.py`<br>`tests/test_db.py` |
| 3 | `E1-T3` | `01-nucleo-y-oc` | Utilidades de fechas, períodos, montos y letras | 1 | `gestor/util.py`<br>`gestor/letras.py`<br>`tests/test_util.py`<br>`tests/test_letras.py` |
| 4 | `E1-T4` | `01-nucleo-y-oc` | Lector de .xlsx con zipfile y ElementTree | 1 | `gestor/xlsx.py`<br>`tests/test_xlsx.py` |
| 5 | `E1-T5` | `01-nucleo-y-oc` | Importador z_compras2: limpieza, exclusiones y upsert | 2, 3, 4 | `gestor/importar.py`<br>`tests/test_importar.py` |
| 6 | `E1-T6` | `01-nucleo-y-oc` | Desglose mensual de servicios e inferencias al importar | 5 | `gestor/importar.py`<br>`tests/test_desglose.py` |
| 7 | `E1-T7` | `01-nucleo-y-oc` | Interfaz base (8 pantallas) y pantalla Importar | 5 | `web/index.html`<br>`web/app.js`<br>`web/style.css`<br>`gestor/server.py`<br>`tests/test_web_importar.py` |
| 8 | `E1-T8` | `01-nucleo-y-oc` | Órdenes de compra: lista, ficha, campos manuales y alta | 6, 7 | `gestor/negocio.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/datos_prueba.py`<br>`tests/test_oc.py` |
| 9 | `E2-T1` | `02-expediente-comun` | API de expedientes: alta, versión, historial y anulación | 8 | `gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_expedientes_api.py` |
| 10 | `E2-T2` | `02-expediente-comun` | Período sugerido y carga rápida de varios remitos | 9 | `gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_periodo_remitos.py` |
| 11 | `E2-T3` | `02-expediente-comun` | Parser del texto pegado de SII y normalización de factura | 3 | `gestor/comprobantes.py`<br>`gestor/util.py`<br>`gestor/server.py`<br>`tests/test_comprobantes.py` |
| 12 | `E2-T4` | `02-expediente-comun` | Consumo, saldo y grilla renglón × período | 10 | `gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_consumo.py` |
| 13 | `E2-T5` | `02-expediente-comun` | Motor de controles con cuatro niveles | 11, 12 | `gestor/controles.py`<br>`gestor/server.py`<br>`tests/datos_prueba.py`<br>`tests/test_controles.py` |
| 14 | `E2-T6` | `02-expediente-comun` | Notas aclaratorias redactadas para controles salvables | 13 | `gestor/controles.py`<br>`gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_notas.py` |
| 15 | `E2-T7` | `02-expediente-comun` | Asistente del expediente, pasos 1 a 4 en la interfaz | 14 | `web/index.html`<br>`web/app.js`<br>`web/style.css`<br>`tests/test_web_asistente.py` |
| 16 | `E3-T1` | `03-salidas-y-prototipo` | Carátula, referencias GDE y nombres de archivo | 13 | `gestor/textos.py`<br>`gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_textos_referencias.py` |
| 17 | `E3-T2` | `03-salidas-y-prototipo` | Autorización, constancia de comodato y copiar con formato | 16 | `gestor/textos.py`<br>`gestor/negocio.py`<br>`web/app.js`<br>`tests/test_autorizacion.py` |
| 18 | `E3-T3` | `03-salidas-y-prototipo` | Certificado de validación y autorización en Word | 17 | `gestor/docx_gen.py`<br>`gestor/server.py`<br>`tests/test_docx.py` |
| 19 | `E3-T4` | `03-salidas-y-prototipo` | Textos para SAP: ingreso, contabilización, MIGO y ML81N | 16 | `gestor/textos.py`<br>`gestor/negocio.py`<br>`tests/test_sap.py` |
| 20 | `E3-T5` | `03-salidas-y-prototipo` | Asistente pasos 5 a 7: documentos, GDE y estados | 14, 15, 17, 18, 19 | `gestor/negocio.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_estados.py` |
| 21 | `E3-T6` | `03-salidas-y-prototipo` | Gate del prototipo: tres expedientes reales de punta a punta | 20 | `tests/datos_prueba.py`<br>`tests/test_prototipo.py` |
| 22 | `E4-T1` | `04-seguimiento` | Calendario anual OC × meses con estados accesibles | 21 | `gestor/negocio.py`<br>`gestor/server.py`<br>`web/app.js`<br>`web/style.css`<br>`tests/test_calendario.py` |
| 23 | `E4-T2` | `04-seguimiento` | Pantalla Inicio con alertas ordenadas por urgencia | 22 | `gestor/negocio.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_inicio.py` |
| 24 | `E4-T3` | `04-seguimiento` | Entregas y CSV con formato NUMERACIÓN | 21 | `gestor/negocio.py`<br>`gestor/exportes.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_entregas.py` |
| 25 | `E4-T4` | `04-seguimiento` | Pendientes, pantalla Configuración, apagado e Iniciar.bat | 23, 24 | `gestor/negocio.py`<br>`gestor/server.py`<br>`web/app.js`<br>`Iniciar.bat`<br>`tests/test_pendientes_config.py` |
| 26 | `E4-T5` | `04-seguimiento` | Escritor .xlsx propio, vista imprimible y seis exportes | 25 | `gestor/xlsx_escritor.py`<br>`gestor/exportes.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_exportes.py` |
| 27 | `E5-T1` | `05-especiales-y-cierre` | Centralizadas: CV con leyenda, nota a Central y checklist | 26 | `gestor/textos.py`<br>`gestor/controles.py`<br>`gestor/negocio.py`<br>`gestor/server.py`<br>`tests/test_centralizadas.py` |
| 28 | `E5-T2` | `05-especiales-y-cierre` | Correctivo: estados, informe económico e informe mensual | 26 | `gestor/negocio.py`<br>`gestor/textos.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_correctivo.py` |
| 29 | `E5-T3` | `05-especiales-y-cierre` | Pago eventual: estados, solicitud y uno por proveedor y año | 26 | `gestor/negocio.py`<br>`gestor/controles.py`<br>`gestor/textos.py`<br>`web/app.js`<br>`tests/test_eventual.py` |
| 30 | `E5-T4` | `05-especiales-y-cierre` | Modelos de autorización AySA y Edenor del CASPH | 17 | `gestor/textos.py`<br>`gestor/server.py`<br>`web/app.js`<br>`tests/test_casph_servicios.py` |
| 31 | `E5-T5` | `05-especiales-y-cierre` | Prueba de dos procesos escribiendo la misma base | 9 | `tests/test_concurrencia.py`<br>`gestor/db.py` |
| 32 | `E5-T6` | `05-especiales-y-cierre` | Instructivo, pantallas Ayuda y Centralizadas, gate final | 22, 23, 24, 25, 26, 27, 28, 29, 30, 31 | `docs/INSTRUCTIVO.md`<br>`gestor/server.py`<br>`web/index.html`<br>`web/app.js`<br>`tests/test_instructivo.py` |

### Steps

### Epic 01 — Núcleo y órdenes de compra (`01-nucleo-y-oc`)

#### Step 1 — Entry point app.py, servidor y /api/salud con --check

**Tarea:** `E1-T1` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-01-esqueleto` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `app.py` — nuevo: entry point con --check, --no-browser, --port
- `gestor/__init__.py` — nuevo: APP_ID y __version__
- `gestor/config.py` — nuevo: carga de config.json / GESTOR_CONFIG
- `gestor/server.py` — nuevo: ThreadingHTTPServer, /api/salud, elegir_puerto
- `tests/test_servidor.py` — nuevo: 6 pruebas del servidor y del entry point

**Done when**

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

#### Step 2 — Capa de datos SQLite: esquema, versión, auditoría y backups

**Tarea:** `E1-T2` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-02-base-de-datos` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/db.py` — nuevo: esquema, conexión, transacciones, versión, auditoría, backups
- `gestor/server.py` — edit: inicializa la base, conexión por pedido, /api/base/*
- `app.py` — edit: backup al arrancar en modo normal
- `tests/test_db.py` — nuevo: 9 pruebas de la capa de datos

**Done when**

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

#### Step 3 — Utilidades de fechas, períodos, montos y letras

**Tarea:** `E1-T3` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-03-util-y-letras` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/util.py` — nuevo: textos, montos, fechas, períodos, factura, GDE
- `gestor/letras.py` — nuevo: importe en letras
- `tests/test_util.py` — nuevo
- `tests/test_letras.py` — nuevo

**Done when**

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

#### Step 4 — Lector de .xlsx con zipfile y ElementTree

**Tarea:** `E1-T4` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-04-lector-xlsx` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/xlsx.py` — nuevo: lector .xlsx
- `tests/test_xlsx.py` — nuevo: pruebas con los dos reportes reales

**Done when**

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

#### Step 5 — Importador z_compras2: limpieza, exclusiones y upsert

**Tarea:** `E1-T5` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-05-importar` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/importar.py` — nuevo: mapeo por encabezado, limpieza, descartes, upsert, informe
- `tests/test_importar.py` — nuevo: conteos con los dos reportes reales

**Done when**

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

#### Step 6 — Desglose mensual de servicios e inferencias al importar

**Tarea:** `E1-T6` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-06-desglose` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/importar.py` — edit: desglose, por entregar, inferencias de OC
- `tests/test_desglose.py` — nuevo

**Done when**

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

#### Step 7 — Interfaz base (8 pantallas) y pantalla Importar

**Tarea:** `E1-T7` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-07-ui-e-importar` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `web/index.html` — nuevo: estructura de 8 pantallas
- `web/app.js` — nuevo: api(), navegación, pantalla Importar
- `web/style.css` — nuevo: tokens visuales de §7
- `gestor/server.py` — edit: estáticos, sobre de respuesta, parámetros, importación multipart
- `tests/test_web_importar.py` — nuevo

**Done when**

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

#### Step 8 — Órdenes de compra: lista, ficha, campos manuales y alta

**Tarea:** `E1-T8` · **Epic:** `01-nucleo-y-oc` · **Checkpoint:** `step-08-oc` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — nuevo: reglas de OC
- `gestor/server.py` — edit: rutas /api/oc
- `web/app.js` — edit: pantalla Órdenes de compra
- `tests/datos_prueba.py` — nuevo: datos reales reutilizables (EFIA manual, BIO FAB, MACATEX)
- `tests/test_oc.py` — nuevo

**Done when**

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

### Epic 02 — Expediente común con controles (`02-expediente-comun`)

#### Step 9 — API de expedientes: alta, versión, historial y anulación

**Tarea:** `E2-T1` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-09-expedientes-api` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: expedientes
- `gestor/server.py` — edit: rutas /api/expedientes
- `tests/test_expedientes_api.py` — nuevo

**Done when**

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

#### Step 10 — Período sugerido y carga rápida de varios remitos

**Tarea:** `E2-T2` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-10-periodo-y-remitos` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: remitos y período sugerido
- `gestor/server.py` — edit: ruta de pegado de remitos
- `tests/test_periodo_remitos.py` — nuevo

**Done when**

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

#### Step 11 — Parser del texto pegado de SII y normalización de factura

**Tarea:** `E2-T3` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-11-comprobantes` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/comprobantes.py` — nuevo: parser SII, CAE y vencimiento
- `gestor/util.py` — edit: normalizar_domicilio
- `gestor/server.py` — edit: /api/comprobantes/analizar
- `tests/test_comprobantes.py` — nuevo

**Done when**

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

#### Step 12 — Consumo, saldo y grilla renglón × período

**Tarea:** `E2-T4` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-12-consumo-y-saldo` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: consumo y saldo
- `gestor/server.py` — edit: /api/oc/<numero>/consumo
- `tests/test_consumo.py` — nuevo

**Done when**

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

#### Step 13 — Motor de controles con cuatro niveles

**Tarea:** `E2-T5` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-13-controles` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/controles.py` — nuevo: motor y controles
- `gestor/server.py` — edit: /api/expedientes/<id>/controles
- `tests/datos_prueba.py` — edit: expedientes reales EFIA, BIO FAB y MACATEX
- `tests/test_controles.py` — nuevo

**Done when**

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

#### Step 14 — Notas aclaratorias redactadas para controles salvables

**Tarea:** `E2-T6` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-14-notas-aclaratorias` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/controles.py` — edit: redactores de notas
- `gestor/negocio.py` — edit: guardar nota
- `gestor/server.py` — edit: /api/expedientes/<id>/notas
- `tests/test_notas.py` — nuevo

**Done when**

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

#### Step 15 — Asistente del expediente, pasos 1 a 4 en la interfaz

**Tarea:** `E2-T7` · **Epic:** `02-expediente-comun` · **Checkpoint:** `step-15-asistente-1-4` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `web/index.html` — edit: lista y asistente de 7 pasos
- `web/app.js` — edit: pasos 1 a 4
- `web/style.css` — edit: clases de nivel
- `tests/test_web_asistente.py` — nuevo

**Done when**

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

### Epic 03 — Salidas y prototipo usable (`03-salidas-y-prototipo`)

#### Step 16 — Carátula, referencias GDE y nombres de archivo

**Tarea:** `E3-T1` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-16-caratula-y-referencias` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/textos.py` — nuevo: carátula, referencias, nombres de archivo
- `gestor/negocio.py` — edit: contexto_textos y textos_del_expediente
- `gestor/server.py` — edit: /api/expedientes/<id>/textos
- `tests/test_textos_referencias.py` — nuevo

**Done when**

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

#### Step 17 — Autorización, constancia de comodato y copiar con formato

**Tarea:** `E3-T2` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-17-autorizacion` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/textos.py` — edit: autorización y constancia de comodato
- `gestor/negocio.py` — edit: textos_del_expediente agrega autorización y constancia
- `web/app.js` — edit: copiar con formato
- `tests/test_autorizacion.py` — nuevo: goldens y comparación con los originales

**Done when**

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

#### Step 18 — Certificado de validación y autorización en Word

**Tarea:** `E3-T3` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-18-word` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/docx_gen.py` — nuevo: CV desde plantilla y autorización .docx
- `gestor/server.py` — edit: descargas .docx
- `tests/test_docx.py` — nuevo

**Done when**

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

#### Step 19 — Textos para SAP: ingreso, contabilización, MIGO y ML81N

**Tarea:** `E3-T4` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-19-textos-sap` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/textos.py` — edit: textos SAP
- `gestor/negocio.py` — edit: textos_del_expediente agrega sap
- `tests/test_sap.py` — nuevo

**Done when**

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

#### Step 20 — Asistente pasos 5 a 7: documentos, GDE y estados

**Tarea:** `E3-T5` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-20-asistente-5-7-y-estados` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: estados, pendiente, GDE
- `gestor/server.py` — edit: rutas de estado, reanudar y GDE
- `web/app.js` — edit: pasos 5 a 7
- `tests/test_estados.py` — nuevo

**Done when**

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

#### Step 21 — Gate del prototipo: tres expedientes reales de punta a punta

**Tarea:** `E3-T6` · **Epic:** `03-salidas-y-prototipo` · **Checkpoint:** `step-21-gate-prototipo` · **Prioridad:** p0

**Do**

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

Archivos tocados (Files touched):

- `tests/datos_prueba.py` — edit: flujo completo por API
- `tests/test_prototipo.py` — nuevo: gate del prototipo

**Done when**

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

### Epic 04 — Seguimiento (`04-seguimiento`)

#### Step 22 — Calendario anual OC × meses con estados accesibles

**Tarea:** `E4-T1` · **Epic:** `04-seguimiento` · **Checkpoint:** `step-22-calendario` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: calendario
- `gestor/server.py` — edit: /api/calendario
- `web/app.js` — edit: pantalla Calendario
- `web/style.css` — edit: clases del calendario
- `tests/test_calendario.py` — nuevo

**Done when**

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

#### Step 23 — Pantalla Inicio con alertas ordenadas por urgencia

**Tarea:** `E4-T2` · **Epic:** `04-seguimiento` · **Checkpoint:** `step-23-inicio-alertas` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: alertas
- `gestor/server.py` — edit: /api/inicio/alertas
- `web/app.js` — edit: pantalla Inicio
- `tests/test_inicio.py` — nuevo

**Done when**

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

#### Step 24 — Entregas y CSV con formato NUMERACIÓN

**Tarea:** `E4-T3` · **Epic:** `04-seguimiento` · **Checkpoint:** `step-24-entregas` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: entregas
- `gestor/exportes.py` — nuevo: CSV NUMERACIÓN
- `gestor/server.py` — edit: rutas /api/entregas
- `web/app.js` — edit: pantalla Entregas
- `tests/test_entregas.py` — nuevo

**Done when**

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

#### Step 25 — Pendientes, pantalla Configuración, apagado e Iniciar.bat

**Tarea:** `E4-T4` · **Epic:** `04-seguimiento` · **Checkpoint:** `step-25-pendientes-y-configuracion` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: pendientes
- `gestor/server.py` — edit: pendientes, config local, backup manual, apagar
- `web/app.js` — edit: Configuración y Pendientes
- `Iniciar.bat` — nuevo: lanzador de doble clic
- `tests/test_pendientes_config.py` — nuevo

**Done when**

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

#### Step 26 — Escritor .xlsx propio, vista imprimible y seis exportes

**Tarea:** `E4-T5` · **Epic:** `04-seguimiento` · **Checkpoint:** `step-26-exportes` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `gestor/xlsx_escritor.py` — nuevo: escritor .xlsx
- `gestor/exportes.py` — edit: seis exportes y HTML imprimible
- `gestor/server.py` — edit: /api/exportes
- `web/app.js` — edit: botones de exporte
- `tests/test_exportes.py` — nuevo

**Done when**

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

### Epic 05 — Trámites especiales y cierre (`05-especiales-y-cierre`)

#### Step 27 — Centralizadas: CV con leyenda, nota a Central y checklist

**Tarea:** `E5-T1` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-27-centralizadas` · **Prioridad:** p2

**Do**

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

Archivos tocados (Files touched):

- `gestor/textos.py` — edit: nota a Central
- `gestor/controles.py` — edit: controles de centralizadas
- `gestor/negocio.py` — edit: centralizadas por período y marca de calendario
- `gestor/server.py` — edit: rutas de centralizadas
- `tests/test_centralizadas.py` — nuevo

**Done when**

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

#### Step 28 — Correctivo: estados, informe económico e informe mensual

**Tarea:** `E5-T2` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-28-correctivos` · **Prioridad:** p2

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: estados y datos del correctivo, informe mensual
- `gestor/textos.py` — edit: referencia e informe económico
- `gestor/server.py` — edit: rutas de correctivos
- `web/app.js` — edit: sección de correctivo
- `tests/test_correctivo.py` — nuevo

**Done when**

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

#### Step 29 — Pago eventual: estados, solicitud y uno por proveedor y año

**Tarea:** `E5-T3` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-29-pago-eventual` · **Prioridad:** p2

**Do**

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

Archivos tocados (Files touched):

- `gestor/negocio.py` — edit: estados del pago eventual
- `gestor/controles.py` — edit: un eventual por proveedor por año
- `gestor/textos.py` — edit: carátula y solicitud de pago eventual
- `web/app.js` — edit: formulario de pago eventual
- `tests/test_eventual.py` — nuevo

**Done when**

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

#### Step 30 — Modelos de autorización AySA y Edenor del CASPH

**Tarea:** `E5-T4` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-30-aysa-edenor-casph` · **Prioridad:** p2

**Do**

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

Archivos tocados (Files touched):

- `gestor/textos.py` — edit: AySA y Edenor
- `gestor/server.py` — edit: /api/textos/servicio-casph
- `web/app.js` — edit: panel de servicios CASPH
- `tests/test_casph_servicios.py` — nuevo

**Done when**

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

#### Step 31 — Prueba de dos procesos escribiendo la misma base

**Tarea:** `E5-T5` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-31-concurrencia` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `tests/test_concurrencia.py` — nuevo: dos procesos sobre una base temporal
- `gestor/db.py` — edit solo si la prueba encuentra un defecto

**Done when**

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

#### Step 32 — Instructivo, pantallas Ayuda y Centralizadas, gate final

**Tarea:** `E5-T6` · **Epic:** `05-especiales-y-cierre` · **Checkpoint:** `step-32-instructivo-y-cierre` · **Prioridad:** p1

**Do**

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

Archivos tocados (Files touched):

- `docs/INSTRUCTIVO.md` — nuevo: instructivo de una página
- `gestor/server.py` — edit: /api/ayuda
- `web/index.html` — edit: pantalla Ayuda
- `web/app.js` — edit: pantallas Ayuda y Centralizadas
- `tests/test_instructivo.py` — nuevo

**Done when**

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

### 9.1 Parity and cutover

NOT APPLICABLE — greenfield build, no system is being replaced. Las planillas actuales siguen existiendo en paralelo; importarlas
es un no-objetivo (§1).

---

## 10. Environment Setup

### Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python (CPython) | ≥ 3.10; objetivo 3.14 (pin en §11). En esta PC: 3.14.0 en `PATH` como `python` | `python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)"` |
| Git | cualquiera reciente (Git for Windows trae Git Bash) | `git --version` |
| Identidad de git para los Checkpoints | la del usuario si existe; si no, el Bootstrap fija `builder` / `builder@localhost` en el repo (`git config` local) | `git config user.email` imprime un email después del Bootstrap |
| Shell | Git Bash (POSIX `sh`); todos los Verify están en sintaxis POSIX | `sh -c 'echo ok'` |

No hace falta instalar nada más: no hay `pip install`, ni Node, ni servicios.

### Accounts to create first

NOT APPLICABLE — el proyecto no usa servicios de terceros: no hay cuentas, claves ni internet.

### Environment variables

| Variable | Purpose | Where to get it | Required by step | Secret? |
|---|---|---|---|---|
| `GESTOR_CONFIG` | Ruta absoluta a un `config.json` alternativo. Si falta o está vacía, se usa `config.json` de la raíz del proyecto. `tests/ayudas.py` la apunta a un directorio temporal en cada test | No se obtiene: la fija `tests/ayudas.py` en los tests; en uso normal no se define | Opcional en todos los pasos (nunca requerida) | no |

No hay `.env` ni `.env.example`: la configuración vive en `config.json` (local, por PC) y en la tabla `config` (compartida). Nada
valida variables al arrancar, así que ningún paso puede romper el gate de otro por una variable. **Mecanismo de carga:** la única
herramienta que lee `GESTOR_CONFIG` es la propia app, en `gestor/config.py` → `ruta_config()` con `os.environ`; los tests la fijan
con `os.environ` dentro de `ayudas.EntornoTemporal` y la restauran en `cerrar()`. No hay CLIs externas que lean variables.

### Files that must be committed

`.gitignore` (llega por la copia de `workspace/` antes del primer commit) contiene solo `datos/`, `*.db`, `*.db-journal`,
`salidas/`, `__pycache__/` y `*.pyc`. Ningún archivo que el blueprint llama "commiteado" coincide con esos patrones:

| File | Why it is committed | Ignore-file exception line |
|---|---|---|
| `config.json` | config local por defecto; la app lo lee al arrancar | — not matched by any ignore pattern |
| `CLAUDE.md`, `AGENTS.md`, `.claude/settings.json`, `.claude/skills/**`, `.claude/rules/**` | workspace del agente (§19) | — not matched by any ignore pattern |
| `tests/__init__.py`, `tests/ayudas.py` | infraestructura de tests emitida (§19.6) | — not matched by any ignore pattern |
| `tests/fixtures/**` (`.xlsx`, `.docx`, `.txt`) | datos reales que los tests leen | — not matched by any ignore pattern |
| `plantillas/cv_hbi.docx`, `plantillas/cv_casph.docx` | plantillas del CV que la app completa | — not matched by any ignore pattern |
| `Iniciar.bat`, `docs/INSTRUCTIVO.md` | lanzador e instructivo (pasos 25 y 32) | — not matched by any ignore pattern |

`blueprints/gestor-expedientes/` también queda commiteado en el primer commit (Bootstrap usa `git add -A`): es la especificación
del proyecto y conviene versionarla. Ninguna herramienta del proyecto la recorre (§19.6).

### Bootstrap

Se corre desde la raíz del proyecto (`C:\Users\Cami Personal\Documents\gestor-expedientes`), en Git Bash, con este bundle en
`blueprints/gestor-expedientes/`. Cada línea es no interactiva, idempotente y sale 0 en su camino "ya hecho": el bloque se puede
correr dos veces seguidas.

```bash
# orden importa: piso de Python → copia de workspace (trae .gitignore) → repo → identidad local si falta → primer commit (ya con .gitignore)
python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)"
[ -f CLAUDE.md ] || cp -R blueprints/gestor-expedientes/workspace/. .
[ -d .git ] || git init -q
git config user.email >/dev/null || git config user.email builder@localhost
git config user.name >/dev/null || git config user.name builder
git add -A && (git rev-parse --verify -q HEAD >/dev/null || git -c user.name=builder -c user.email=builder@localhost commit -q -m "chore: bootstrap desde blueprint")
```

Qué hace cada línea en la segunda corrida:

1. Piso de versión: vuelve a imprimir la versión y sale 0 (sale 1 con `AssertionError` solo si Python < 3.10 — ahí hay que instalar Python, §10 Prerequisites).
2. Copia guardada por marcador: `CLAUDE.md` ya existe → `[` sale 0 y `cp` no corre. **Nunca se sobrescriben** archivos ya copiados (`config.json`, `tests/ayudas.py`, `.gitignore`, `.claude/**`); la copia es de una sola vez y `[ -f CLAUDE.md ]` es el marcador. No se usa `cp -Rn` porque en BSD/macOS sale 1 cuando saltea un archivo.
3. `.git` ya existe → no corre `git init`.
4. Identidad: `git config user.email` / `git config user.name` ya devuelven un valor (global o el local fijado en la primera corrida) → salen 0 y no se escribe nada. En la primera corrida, si no había identidad, `git config` sale 1 y la segunda mitad la fija **solo en este repo** (sale 0).
5. `git add -A` agrega lo que haya (sale 0); `HEAD` ya existe → no se hace otro commit. El primer commit usa además una identidad fija con `-c`; los Checkpoints usan la identidad configurada (global o la local del paso 4), así que `git commit` nunca falla por falta de identidad.

No se corre `unittest` en el Bootstrap: sin tests, `unittest discover` de Python ≥ 3.12 sale con código 5. El primer gate de
tests es el Verify del paso 1.

---

## 11. Dependencies

Procedencia: informe de `stack-researcher` de esta sesión (2026-11-16). No hay paquetes de terceros: toda la "dependencia" es
el intérprete y su biblioteca estándar, instalados por la usuaria (no por un paso) y verificados por la primera línea del
Bootstrap.

### Runtime

| Package | Version | Source (registry URL or track file) | Checked | Installed by | Purpose |
|---|---|---|---|---|---|
| CPython | 3.14.10 (2026-10-25), objetivo | https://endoflife.date/api/python.json ; https://www.python.org/downloads/windows/ | 2026-11-16 | §10 Prerequisites (instalación manual; Bootstrap verifica el piso) | intérprete objetivo; bugfix hasta 2027-10-01 |
| CPython (piso de compatibilidad) | 3.10 (3.10.22 final, EOL 2026-10-01) | https://endoflife.date/api/python.json | 2026-11-16 | §10 Bootstrap (verificación `sys.version_info >= (3, 10)`) | el código no usa nada posterior a 3.10. **Advertencia:** 3.10 ya no recibe parches de seguridad; 3.11 es la más vieja con parches |
| `http.server.ThreadingHTTPServer` (stdlib) | — | https://docs.python.org/3.14/library/http.server.html | 2026-11-16 | viene con CPython | servidor HTTP local |
| `sqlite3` (stdlib) | versión de SQLite: UNVERIFIED en builds Windows — verificar antes de confiar | https://docs.python.org/3.14/library/sqlite3.html | 2026-11-16 | viene con CPython | base; piso en runtime `SQLITE_MINIMA = (3, 8, 3)`; sin `RETURNING` ni `ON CONFLICT DO UPDATE` |
| `json` (stdlib) | — | https://docs.python.org/3.14/library/tomllib.html (confirma que `tomllib` es 3.11+, por eso JSON) | 2026-11-16 | viene con CPython | `config.json` y columnas JSON |
| `zipfile` + `xml.etree.ElementTree` (stdlib) | — | UNVERIFIED — verify before install (no consultado; módulos históricos de la stdlib) | 2026-11-16 | viene con CPython | lectura/escritura de `.xlsx` y `.docx` |
| `email.parser.BytesParser` (stdlib) | — | https://docs.python.org/3.14/library/email.parser.html | 2026-11-16 | viene con CPython | multipart de subidas (`cgi` fue eliminado en 3.13) |

### Development

| Package | Version | Source (registry URL or track file) | Checked | Installed by | Purpose |
|---|---|---|---|---|---|
| `unittest` (stdlib) | — | UNVERIFIED — verify before install (no consultado) | 2026-11-16 | viene con CPython | tests, siempre con `-W error::DeprecationWarning` |
| `compileall` (stdlib) | — | UNVERIFIED — verify before install (no consultado) | 2026-11-16 | viene con CPython | gate de formato/lint: `python -m compileall -q app.py gestor tests` |

### Deliberately not used

| Rejected | Instead | Why |
|---|---|---|
| `openpyxl`, `xlrd` | `gestor/xlsx.py` y `gestor/xlsx_escritor.py` (zipfile + XML) | requieren pip, que puede estar bloqueado |
| `python-docx` | `gestor/docx_gen.py` editando `word/document.xml` | requiere pip; además se necesita editar la plantilla en su lugar |
| Flask, FastAPI | `http.server` | requieren pip |
| `pytest` | `unittest` | requiere pip |
| `ruff`, `flake8`, `black` | `python -m compileall` | requieren pip |
| SQLAlchemy | SQL a mano en `gestor/db.py` | requiere pip; 8 tablas no lo justifican |
| `cgi` | `email.parser.BytesParser` | eliminado en Python 3.13 |
| `tomllib` | `json` | no existe en 3.10 |

---

## 12. Deployment Strategy

### Hosting

Local, en cada PC: la carpeta del proyecto (o una copia) y `Iniciar.bat`. `config.json` → `base_datos` apunta a la base
compartida (por ejemplo `Z:\Contable\gestor\expedientes.db`, editable en Configuración); por defecto `datos/expedientes.db`.
No hay build ni carpeta de salida. Nube: NOT APPLICABLE — no hay servidor central (§1 Non-Goals).

### Environments

| Entorno | Qué es |
|---|---|
| Desarrollo | la carpeta del repo; los tests usan una base temporal (`GESTOR_CONFIG`) |
| Uso | la misma carpeta en cada PC, con `base_datos` apuntando a la carpeta compartida |

### CI/CD

NOT APPLICABLE — no hay repositorio remoto ni CI. El gate es §20.1, corrido a mano o por el builder.

### Release and rollback

Actualizar = copiar la carpeta nueva del programa sobre la vieja (sin tocar la base). Volver atrás = volver a la carpeta anterior
o al tag de git anterior. La base tiene 30 backups automáticos (`expedientes-AAAAMMDD-HHMMSS.db`) y un botón "Restaurar la última
copia" cuando falla `PRAGMA integrity_check`.

### Domain, DNS, TLS

NOT APPLICABLE — el servidor escucha solo en `http://127.0.0.1:<puerto>`, sin red.

---

## 13. Testing Strategy

`unittest` de la stdlib, siempre con `python -W error::DeprecationWarning` (una API deprecada rompe el gate). Cada paso crea su
módulo `tests/test_<x>.py` con clases y métodos nombrados en el paso. Tres tipos:

- **Unitarios puros** (`unittest.TestCase`): letras, util, textos, parser SII, controles con contexto armado.
- **Con base temporal** (`ayudas.CasoConEntorno`): importador, db, negocio. `EntornoTemporal` crea un `config.json` en un directorio temporal con rutas absolutas y apunta `GESTOR_CONFIG` a él.
- **HTTP** (`ayudas.CasoConServidor`): `ServidorDePrueba` levanta `gestor.server.crear_servidor(0, ...)` en un thread y pide con `urllib`. Así se prueba la API y que `GET /` y `GET /app.js` sirven las pantallas y llaman las rutas correctas.

**No hay e2e de navegador** (Playwright/Selenium requieren pip o Node). La UI se verifica por HTTP (ids de pantallas y rutas usadas
por `app.js`) y con una checklist manual corta por pantalla en `docs/INSTRUCTIVO.md` (paso 32, sección *Revisión manual por
pantalla*), que forma parte de §20.1.

### Critical flows to cover E2E

Cubiertos de punta a punta **por HTTP** (no por navegador) en `tests/test_prototipo.py` (paso 21): EFIA (sin errores → textos →
CV → FIRMADO), BIO FAB (salvable con nota → autorización con comodato) y MACATEX (objeto faltante bloquea → se completa el objeto
→ se genera). La concurrencia real se cubre con dos procesos en `tests/test_concurrencia.py` (paso 31).

### Test data

Solo datos reales de `tests/fixtures/` (dos z_compras2, textos de los PDF de 3 expedientes, modelos Word) más la OC manual EFIA
4500555861, cargados por `tests/datos_prueba.py` (paso 8, ampliado en 13 y 21). Cada test usa su propia base temporal; nada toca
`datos/`.

### What is deliberately not tested

- Apariencia visual y el clipboard real del navegador (se revisan con la checklist manual).
- `Iniciar.bat` y `pythonw` (requieren doble clic en Windows; el test solo verifica el contenido del archivo).
- SQLite sobre una unidad de red real (se prueba con dos procesos sobre disco local; el riesgo SMB está en §20.2).

---

## 14. Security & Secrets

- No hay secretos: ni claves, ni tokens, ni contraseñas. Nada que rotar.
- El servidor se liga solo a `127.0.0.1`; no se abre ningún puerto a la red.
- Estáticos: solo archivos dentro de `web/` (ruta resuelta y verificada contra la carpeta; `GET /config.json` → 404).
- Subidas: tope de 25 MB por `Content-Length` (413 sin leer el cuerpo); solo se procesan `.xlsx` en memoria.
- SQL: siempre con parámetros `?`; los nombres de columna dinámicos se validan contra `db.COLUMNAS` (lista blanca).
- XML de Excel/Word: se parsea con `xml.etree.ElementTree` sobre archivos propios o elegidos por la usuaria; no se resuelven entidades externas.
- Datos con información de proveedores en `datos/` (ignorado por git); la auditoría no se puede borrar (triggers).
- `.claude/settings.json` niega `git push`, `rm -rf` y la lectura de `datos/**`.

---

## 15. Accessibility

### Baseline requirements

- `<html lang="es">`, enlace "Saltar al contenido", un `<h1>` por pantalla, `<nav>` y `<main>`.
- Todo usable con teclado (orden de tabulación natural, sin trampas); foco visible `outline: 3px solid var(--foco)`.
- Letra base 16px, botones de 44px de alto mínimo, contraste AA (§7).
- Cada `input` con `<label>`; errores de formulario asociados con `aria-describedby`.
- Mensajes de la API en `#avisos` con `aria-live="polite"`.
- Estados del calendario y niveles de control con letra o palabra además del color.

### WCAG 2.2 additions — the ones most often missed

- 2.4.11 Focus Not Obscured: el header no es fijo, así que el foco nunca queda tapado.
- 2.5.8 Target Size: objetivos de 44×44px (por encima de 24×24).
- 3.3.7 Redundant Entry: los datos se cargan una vez y se reutilizan (es el propósito del programa).
- 3.2.6 Consistent Help: la pantalla Ayuda está siempre en el mismo lugar del menú.

### Verification

Automático: los tests HTTP comprueban que `GET /` trae `lang="es"` e `id="avisos"` (paso 7) y que `app.js` arma la leyenda del
calendario con los siete estados (paso 22). El enlace de salto y el foco se revisan a mano. Manual (§20.1): una pasada solo con teclado por el asistente de expediente.

---

## 16. Observability & Cost

### Instrumentation

Sin servicios de logging. Toda mutación queda en la tabla `evento` (quién, desde qué PC, qué, antes y después). El historial
del expediente está en `datos.historial`. Los errores 500 devuelven `Error interno: <NombreDeLaExcepcion>`; el servidor no
escribe a consola (`log_message` vacío, `pythonw` no tiene consola).

### The metrics that matter for this project

| Métrica | Dónde se ve |
|---|---|
| Expedientes atrasados (pasaron `dias_gracia` del fin del período sin expediente) | Inicio y Calendario (celdas `A`) |
| OC que vencen en ≤ 60 días y renglones ≥ 85 % consumidos | Inicio |
| Pendientes con seguimiento vencido | Inicio y Expedientes |
| Integridad de la base y último backup | `GET /api/base/estado`, banner en Inicio |

### Health check

`GET /api/salud` → `{"app": "gestor-expedientes", "version": "0.1.0", "db": "ok"|"sin_base", "usuario": ...}`. `python app.py --check`
lo ejecuta de punta a punta y sale 0. `app.py` lo usa también para detectar que el gestor ya corre en el puerto y solo abrir el
navegador.

### Cost model

Costo de infraestructura: 0 (todo local, sin servicios pagos).

---

## 17. Model Routing

NOT APPLICABLE — el producto no usa modelos de lenguaje ni ninguna API de IA: todos los textos salen de plantillas fijas (§5).

---

## 18. Skills to Use During Build

Ningún skill es obligatorio: el diseño visual está fijado en §7 y los procedimientos del proyecto viven en
`.claude/skills/` (§19.4). Opcional:

| Skill | Build steps | Why | Install |
|---|---|---|---|
| frontend-design (se activa solo, sin `/`) | 7, 15, 22 | ayuda con el maquetado de las pantallas respetando los tokens de §7 | `/plugin marketplace add anthropics/skills` luego `/plugin install example-skills@anthropic-agent-skills` |

Si no está disponible, el builder sigue §6, §7 y `.claude/rules/interfaz-web.md`, anota la ausencia en una línea y continúa.

---

## 19. Agent Workspace

El bundle trae `workspace/`, que replica la raíz del proyecto. **El builder copia ese único directorio a la raíz del proyecto**
con la segunda línea del Bootstrap (§10):

```bash
[ -f CLAUDE.md ] || cp -R blueprints/gestor-expedientes/workspace/. .   # copia de una sola vez: CLAUDE.md es el marcador; una segunda corrida no pisa nada y sale 0
```

Archivos que esa copia deja y que **nunca se vuelven a sobrescribir**: `config.json`, `.gitignore`, `tests/ayudas.py`,
`tests/__init__.py`, `CLAUDE.md`, `AGENTS.md`, `.claude/**`, `plantillas/**`, `tests/fixtures/**`. No hay manifiesto de
paquetes ni lockfile que proteger (stdlib only). No se emite `.claude/commands/`: el builder es autónomo y no tipea comandos.

```
workspace/
  CLAUDE.md                                   # §19.1
  AGENTS.md                                   # §19.2
  .gitignore                                  # §19.6 (archivo que gobierna el primer commit)
  config.json                                 # §19.6
  tests/__init__.py                           # §19.6
  tests/ayudas.py                             # §19.6
  .claude/settings.json                       # §19.3
  .claude/skills/nuevo-texto-generado/SKILL.md  # §19.4
  .claude/skills/agregar-control/SKILL.md     # §19.4
  .claude/rules/base-de-datos.md              # §19.5
  .claude/rules/textos-y-documentos.md        # §19.5
  .claude/rules/interfaz-web.md               # §19.5
  plantillas/cv_hbi.docx, plantillas/cv_casph.docx   # PROVISTOS (no autorados por el blueprint)
  tests/fixtures/**                           # PROVISTOS (no autorados por el blueprint)
```

Los archivos emitidos pasan los gates del propio blueprint: el único gate de formato es `python -m compileall -q app.py gestor tests`,
que solo compila `.py`; `tests/__init__.py` y `tests/ayudas.py` compilan en Python ≥ 3.10 (verificado con `python -m compileall`
antes de emitir). Los `.md` y `.json` no tienen formateador que los revise.

### 19.1 `CLAUDE.md`

`workspace/CLAUDE.md` → `CLAUDE.md` en la raíz del proyecto:

````markdown
# Gestor de expedientes de pago (HBI / CASPH)

Programa local (Python stdlib + SQLite + HTML/JS) que concentra OC, consumos y expedientes de pago del área contable del HBI y
del CASPH, genera todos sus textos y controla requisitos. Lo usan 2 personas, cada una en su PC Windows, con la base compartida.

## Commands

Todo desde la raíz del proyecto, en Git Bash.

| Task | Command |
|---|---|
| Install | nada — solo biblioteca estándar; nunca `pip install` |
| Arrancar | `python app.py` — abre http://127.0.0.1:8765 (si está ocupado, 8766..8775) |
| Arrancar sin navegador | `python app.py --no-browser --port 8765` |
| Prueba de humo | `python app.py --check` — levanta, pide `/api/salud`, imprime el JSON y sale 0 |
| Formato / lint | `python -m compileall -q app.py gestor tests` |
| Test de un módulo | `python -W error::DeprecationWarning -m unittest tests.test_<modulo> -v` |
| Todos los tests | `python -W error::DeprecationWarning -m unittest discover -s tests -t .` |
| Base | no hay migraciones: `gestor/db.py` → `inicializar` crea el esquema al arrancar |

**Gate:** `python -m compileall -q app.py gestor tests` y `python -W error::DeprecationWarning -m unittest discover -s tests -t .`
salen 0 (y `python app.py --check` desde el paso 1) antes de marcar una tarea como hecha.

Orden de construcción: `blueprints/gestor-expedientes/tasks.json` y `blueprints/gestor-expedientes/epics/`. Cada tarea termina con
`git add -A && git commit -m "<id>: <título>"` y `git tag <checkpoint>`. No se edita nada bajo `blueprints/`.

Python ≥ 3.10 (objetivo 3.14). No hay archivo de dependencias porque no hay dependencias.

## Stack

Python stdlib · `http.server.ThreadingHTTPServer` en 127.0.0.1 · SQLite (`sqlite3`) · HTML/CSS/JS sin framework en `web/` ·
Excel/Word con `zipfile` + `xml.etree.ElementTree` · `unittest` · local, sin nube.

## Architecture

**Recorrido de un pedido.** navegador → `web/app.js` `api(metodo, ruta, cuerpo)` → `gestor/server.py` (`Manejador`, lista
`RUTAS`) → abre una conexión con `gestor/db.py` `conectar()` → `gestor/negocio.py` (reglas) dentro de `with db.transaccion(con):`
→ `db.actualizar_con_version` / `db.insertar` (versión + `evento`) → respuesta `{"ok": true, "datos": ...}` → la conexión se cierra
en `finally`. Textos: `negocio.contexto_textos` → `gestor/textos.py` (puro) → `server.py`. Word: `gestor/docx_gen.py` sobre
`plantillas/*.docx`.

**Fronteras.**

| Capa | Puede importar | Nunca |
|---|---|---|
| `app.py` | `gestor.config`, `gestor.server`, `gestor.db` | reglas de negocio |
| `gestor/server.py` | todos los módulos de `gestor` | reglas de negocio o SQL propio |
| `gestor/negocio.py`, `gestor/importar.py` | `db`, `util`, `letras`, `xlsx`, `controles`, `textos` | `server` |
| `gestor/controles.py` | `util`, `letras` | leer la base (recibe `ctx` de `armar_contexto`) |
| `gestor/textos.py`, `gestor/letras.py`, `gestor/util.py` | stdlib, `util`, `letras` | base, archivos, `negocio` |
| `gestor/db.py` | stdlib | cualquier otro módulo de `gestor` salvo `config` |
| `web/*` | nada externo (sin CDN) | llamar `fetch` fuera de `api()` |
| `tests/*` | `gestor.*`, `tests.ayudas`, `tests.datos_prueba` | tocar `datos/` |

**Dónde vive cada cosa.**

| Tema | Única fuente |
|---|---|
| Esquema SQL | `gestor/db.py` → `ESQUEMA` (copia literal del bloque de `blueprint.md` §4) |
| Config local | `config.json` (o el archivo de `GESTOR_CONFIG`) vía `gestor/config.py` → `cargar_config()` |
| Parámetros compartidos | tabla `config`, vía `db.leer_parametros` / `db.guardar_parametro` |
| Formato de montos | `gestor/util.py` → `a_centavos`, `formato_pesos` |
| Importe en letras | `gestor/letras.py` |
| Textos generados | `gestor/textos.py` — una función por texto |
| Controles | `gestor/controles.py` → `CONTROLES`, `NOTAS` |
| Tokens visuales | `:root` de `web/style.css` |
| Identidad de la app | `gestor/__init__.py` → `APP_ID = "gestor-expedientes"`, `__version__ = "0.1.0"` |

## Code rules

1. **Imports absolutos desde la raíz:** `from gestor import db`, `import gestor.textos`. Nada de `sys.path`, imports relativos con `..` ni `__main__` dentro de `gestor/`.
2. **Montos en centavos `int`; cantidades en `Decimal`.** Nunca `float` para dinero ni cantidades. Formatear solo con `util.formato_pesos`.
3. **Fechas en la base como texto `AAAA-MM-DD`**, convertidas a mano. Hora con `datetime.now(timezone.utc)`; nunca `utcnow()` ni `datetime.UTC`.
4. **`sqlite3.connect` solo en `gestor/db.py`**, con keywords (`database=`, `timeout=10`, `isolation_level=None`). Nada de `autocommit=`, adaptadores de fecha, `RETURNING` ni `ON CONFLICT DO UPDATE`: SELECT y después INSERT o UPDATE.
5. **Toda escritura** va en `with db.transaccion(con):` (`BEGIN IMMEDIATE`), compara `version` (`ConflictoVersion` → 409) y registra `evento` en la misma transacción.
6. **Una conexión por pedido HTTP**, cerrada en `finally`; los threads nunca comparten conexiones.
7. **Compatibilidad 3.10:** sin `ExceptionGroup`, `except*`, `typing.Self`, `tomllib`, `cgi`. Multipart con `email.parser.BytesParser(policy=email.policy.default)`.
8. **Errores con clases:** `ErrorValidacion` → 400, `ErrorNegocio` → 422, `TextoIncompleto` para textos con datos faltantes. Mensajes en español, para la usuaria.
9. **Un texto, una función, un golden.** Si cambia la redacción, primero cambia el test (ver `.claude/skills/nuevo-texto-generado/SKILL.md`).
10. **Los tests usan `tests/ayudas.py`** (`CasoConEntorno`, `CasoConServidor`): base temporal vía `GESTOR_CONFIG`, servidor en el puerto 0.

## Design system

Tokens definidos una vez en `:root` de `web/style.css`; el CSS usa solo `var(--...)`. Sin modo oscuro.

| Token | Valor | Uso |
|---|---|---|
| `--primario` / `--primario-hover` | `#1F4E8C` / `#173D6E` | botones, enlaces, nav activo |
| `--primario-texto` | `#FFFFFF` | texto sobre primario |
| `--fondo` | `#F6F8FA` | página |
| `--superficie` | `#FFFFFF` | paneles, tablas |
| `--borde` / `--borde-control` | `#D0D7DE` / `#8C959F` | divisores / bordes de inputs |
| `--texto` / `--texto-suave` | `#1B2430` / `#57606A` | cuerpo / secundario |
| `--error` / `--error-fondo` | `#B3261E` / `#FDECEA` | errores, atrasado |
| `--exito` | `#2E7D32` | validado, confirmaciones |
| `--aviso` / `--aviso-fondo` | `#8A5300` / `#FFF4E0` | avisos |
| `--pendiente-plazo` | `#FFE08A` | celda pendiente en plazo |
| `--info` | `#1565C0` | verificar, en curso |
| `--violeta` | `#6A3FA0` | salvable, pendiente con motivo |
| `--gris-fuera` | `#C9CED6` | fuera de vigencia |
| `--naranja` | `#C2410C` | borde OC por vencer |
| `--foco` | `#1F4E8C` | `outline: 3px solid var(--foco); outline-offset: 2px` |

- **Tipo:** `"Segoe UI", system-ui, sans-serif`; cuerpo 16px/1.5; títulos 24/20/18px peso 600; mono `Consolas, "Cascadia Mono", monospace` 15px; números `tabular-nums`.
- **Espaciado:** base 4px — 4, 8, 12, 16, 24, 32, 48.
- **Radio:** 4px botones e inputs, 6px paneles. **Sombras:** `0 1px 2px rgba(27, 36, 48, 0.08)`.
- **Botones:** alto mínimo 44px. **Tablas:** compactas (padding 6px 8px).
- **Motion:** solo transiciones de color de 120ms `ease-out`; `transition: none` con `prefers-reduced-motion: reduce`.
- **Estados siempre con letra o palabra además del color** (calendario `-` `V` `C` `P` `A` `M` `·`, marcas ● ◆).

## Environment

| Variable | Required | Used by | Source |
|---|---|---|---|
| `GESTOR_CONFIG` | no | `gestor/config.py` → `ruta_config()` | la fija `tests/ayudas.py`; en uso normal no existe |

No hay `.env` ni secretos. `config.json` es local de cada PC; los parámetros compartidos están en la tabla `config`.

## Rules

Leer el archivo correspondiente antes de editar esa área:

| File | Applies to |
|---|---|
| `.claude/rules/base-de-datos.md` | `gestor/db.py`, `gestor/negocio.py`, `gestor/importar.py` |
| `.claude/rules/textos-y-documentos.md` | `gestor/textos.py`, `gestor/letras.py`, `gestor/docx_gen.py` |
| `.claude/rules/interfaz-web.md` | `web/**` |

Procedimientos: `.claude/skills/nuevo-texto-generado/SKILL.md` (texto nuevo con golden) y
`.claude/skills/agregar-control/SKILL.md` (control nuevo).

## Gotchas

- `unittest discover` sin tests sale con código 5 en Python ≥ 3.12: el primer gate de tests es el paso 1.
- `N° O/C` en el Excel usa el signo de grado (U+00B0); los encabezados se comparan normalizados (`util.clave_encabezado`).
- El período sale del **remito** (fecha de firma si hay), nunca de la factura.
- En Word un rótulo puede estar partido en varios `w:r`: unir el texto del párrafo antes de buscar; registrar namespaces antes de serializar.
- ElementTree: comparar `elem is not None`, nunca `if elem:` (DeprecationWarning en ≥ 3.12, error con `-W error::DeprecationWarning`).
- `httpd.shutdown()` se llama desde otro thread (`POST /api/apagar`), nunca desde el que atiende.
- En la prueba de concurrencia las funciones de `multiprocessing` van a nivel de módulo (Windows usa `spawn`).

## Non-negotiable

1. Solo biblioteca estándar: nunca `pip install` ni un paquete de PyPI.
2. Nunca `float` para dinero; centavos `int` o `Decimal`.
3. Ninguna escritura sin `version` y sin `evento` en la misma transacción; nada se borra físicamente (se anula o se excluye).
4. No modificar `plantillas/`, `tests/fixtures/`, `tests/ayudas.py` ni `blueprints/`.
5. No cambiar un golden ni un Verify para que pase el código.
6. No commitear `datos/`, `salidas/` ni bases `.db`.
7. Nunca marcar una tarea como hecha con un gate fallando.
````

### 19.2 `AGENTS.md`

`workspace/AGENTS.md` → `AGENTS.md` en la raíz del proyecto:

````markdown
# Gestor de expedientes de pago (HBI / CASPH) — instrucciones para agentes

Programa local (Python, solo biblioteca estandar + SQLite) que concentra OC, consumos y expedientes
de pago del area contable del HBI y del CASPH y genera todos sus textos.

## Comandos (desde la raiz del proyecto, en Git Bash)

| Tarea | Comando |
|---|---|
| Arrancar | `python app.py` (abre el navegador) · `python app.py --no-browser --port 8765` |
| Prueba de humo | `python app.py --check` — arranca, consulta /api/salud, imprime el JSON y sale 0 |
| Tests (todos) | `python -W error::DeprecationWarning -m unittest discover -s tests -t .` |
| Tests (un modulo) | `python -W error::DeprecationWarning -m unittest tests.test_db -v` |
| Formato/lint | `python -m compileall -q app.py gestor tests` |

Gate: los tres ultimos comandos salen 0 antes de marcar una tarea como hecha.

## No negociable

1. Solo biblioteca estandar de Python (>= 3.10). Nunca `pip install`, nunca un paquete de PyPI.
2. Montos en centavos `int` (o `Decimal`), nunca `float`.
3. Toda escritura en SQLite: `BEGIN IMMEDIATE`, control de `version` (409) y fila en `evento` en la misma transaccion.
4. Los textos generados se comparan contra goldens exactos; no se cambia un golden para que pase el codigo.
5. No modificar `plantillas/*.docx` ni `tests/fixtures/**` (datos reales provistos).
6. Orden de construccion: `blueprints/gestor-expedientes/tasks.json` + `epics/`; no saltear pasos.

Arquitectura completa, convenciones y sistema visual: ver `CLAUDE.md` en este directorio.
````

### 19.3 `.claude/settings.json`

Cada comando de Verify (§9), del Bootstrap (§10) y del gate (§20.1) está cubierto, subcomando por subcomando: las tuberías
`python app.py --check | grep -q '"app": "gestor-expedientes"'` y `python -W error::DeprecationWarning -m unittest discover -s tests -t . 2>&1 | tail -n 1 | grep -qx OK` usan `Bash(python app.py --check:*)`,
`Bash(python -W error::DeprecationWarning -m unittest:*)`, `Bash(tail:*)` y `Bash(grep:*)`; los Checkpoints usan
`Bash(git add -A)`, `Bash(git commit:*)` y `Bash(git tag:*)`; el Bootstrap usa la entrada exacta del one-liner de Python,
`Bash([:*)`, la entrada exacta del `cp -R`, `Bash(git init -q)`, `Bash(git config user.email:*)`, `Bash(git config user.name:*)`, `Bash(git rev-parse:*)` y la del commit con `-c`. No hay
comodines de intérprete (`python:*`), de red ni `sh -c`.

`workspace/.claude/settings.json` → `.claude/settings.json` en la raíz del proyecto:

````json
{
  "permissions": {
    "allow": [
      "Bash(python -c \"import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)\")",
      "Bash(python -W error::DeprecationWarning -m unittest:*)",
      "Bash(python -m compileall -q app.py gestor tests:*)",
      "Bash(python app.py --check:*)",
      "Bash(cp -R blueprints/gestor-expedientes/workspace/. .)",
      "Bash(git init -q)",
      "Bash(git add -A)",
      "Bash(git rev-parse:*)",
      "Bash(git -c user.name=builder -c user.email=builder@localhost commit:*)",
      "Bash(git commit:*)",
      "Bash(git tag:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git ls-files:*)",
      "Bash(git check-ignore:*)",
      "Bash(git rev-list:*)",
      "Bash(git config user.email:*)",
      "Bash(git config user.name:*)",
      "Bash(test:*)",
      "Bash([:*)",
      "Bash(grep:*)",
      "Bash(ls:*)",
      "Bash(tail:*)"
    ],
    "deny": [
      "Bash(git push:*)",
      "Bash(rm -rf:*)",
      "Read(./datos/**)"
    ]
  }
}
````

### 19.4 Project skills — `.claude/skills/<name>/SKILL.md`

`workspace/.claude/skills/nuevo-texto-generado/SKILL.md` → `.claude/skills/nuevo-texto-generado/SKILL.md` en la raíz del proyecto:

````markdown
---
name: nuevo-texto-generado
description: Usar al agregar o cambiar CUALQUIER texto que el programa genera (autorizacion, referencias GDE, caratula, textos SAP, CV, constancia, notas, solicitud de pago eventual, AySA/Edenor). Obliga a escribir primero el golden test con el texto exacto y despues el generador en gestor/textos.py.
---

# Nuevo texto generado (golden test primero)

## When to use
- "agregar un texto", "cambiar la redaccion de la autorizacion", "nuevo modelo", "otra referencia GDE".
- Cualquier cambio en `gestor/textos.py`, `gestor/letras.py` o `gestor/docx_gen.py` que altere bytes de salida.

## Steps
1. Copiar el texto modelo LITERAL (del blueprint §5 "Textos canonicos" o de un fixture en
   `tests/fixtures/expedientes/**` / `tests/fixtures/modelos/**`). No reescribirlo de memoria.
2. Escribir el test en `tests/test_<area>.py` con `self.assertEqual(generado, ESPERADO)` sobre el
   string completo (una sola linea si el modelo es una sola linea). Si el modelo viene de un PDF
   extraido, comparar con `ayudas.normalizar_espacios` sobre ambos lados.
3. Correr el test y verlo FALLAR.
4. Implementar el generador como UNA funcion pura en `gestor/textos.py` que recibe un dict de datos
   ya validados y devuelve `str`. Montos siempre en centavos `int`, nunca `float`.
5. Si falta un dato obligatorio (objeto, remito, factura), la funcion lanza `TextoIncompleto` con el
   mensaje del control; nunca devuelve un texto con huecos (ej. "correspondiente al , conforme").
6. Correr el test y verlo pasar; correr la suite completa.

## Verify
```bash
python -W error::DeprecationWarning -m unittest discover -s tests -t .   # expect: exit 0, OK
python -m compileall -q app.py gestor tests                              # expect: exit 0, sin salida
```

## Do not
- No cambiar un golden para que pase el codigo: el golden es el contrato con la usuaria.
- No usar `locale` ni `str.format` con separadores de miles: el formato `1.224.990,00` sale de `gestor.util.formato_pesos`.
- No duplicar un texto en dos funciones: un texto, un generador.
````

`workspace/.claude/skills/agregar-control/SKILL.md` → `.claude/skills/agregar-control/SKILL.md` en la raíz del proyecto:

````markdown
---
name: agregar-control
description: Usar al agregar o modificar un control del expediente (factura, SII, remito, OC, textos, centralizada). Define el nivel (error, salvable, aviso, verificar), el codigo estable y el test con un caso real antes de tocar gestor/controles.py.
---

# Agregar un control

## When to use
- "agregar un control", "validar que...", "marcar como salvable", "nuevo aviso en el expediente".
- Cualquier cambio en `gestor/controles.py`.

## Steps
1. Elegir el nivel: `error` (bloquea), `salvable` (sigue con nota aclaratoria redactada), `aviso`,
   `verificar` (lo confirma la persona). Un error de IMPORTE nunca es salvable.
2. Elegir un `codigo` estable en snake_case (ej. `remito_fuera_de_periodo`); la UI y las notas lo usan.
3. Escribir el test en `tests/test_controles.py` armando el expediente con los datos reales del caso
   (EFIA, BIO FAB, MACATEX, Esterisur) y afirmando `codigo`, `nivel` y el `mensaje` exacto.
4. Implementar la funcion `control_<codigo>(ctx) -> list[Resultado]` y registrarla en `CONTROLES`.
5. Si es `salvable`, implementar tambien su redactor de nota en `NOTAS[codigo]`.

## Verify
```bash
python -W error::DeprecationWarning -m unittest tests.test_controles -v   # expect: exit 0, OK
python -W error::DeprecationWarning -m unittest discover -s tests -t .   # expect: exit 0, OK
```

## Do not
- No leer la base dentro de un control: `ctx` ya trae OC, renglones, consumo y expediente.
- No devolver texto libre como nivel: solo los cuatro niveles definidos.
````

### 19.5 `.claude/rules/*.md`

`workspace/.claude/rules/base-de-datos.md` → `.claude/rules/base-de-datos.md` en la raíz del proyecto:

````markdown
---
description: Convenciones de SQLite, versionado optimista y auditoria
paths:
  - "gestor/db.py"
  - "gestor/negocio.py"
  - "gestor/importar.py"
  - "tests/test_db.py"
  - "tests/test_concurrencia.py"
---

# Base de datos (SQLite, stdlib)

- `gestor/db.py` es el UNICO lugar que llama a `sqlite3.connect`, y siempre con keywords:
  `sqlite3.connect(database=str(ruta), timeout=10, isolation_level=None)`. Nunca `autocommit=` (3.12+).
- Al abrir: `PRAGMA journal_mode=DELETE`, `PRAGMA busy_timeout=10000`, `PRAGMA foreign_keys=ON`.
  Nunca WAL: la base vive en una unidad de red (Z:) y WAL no funciona sobre SMB.
- Toda escritura va dentro de `with db.transaccion(con):` (`BEGIN IMMEDIATE` ... `COMMIT`). Transacciones cortas:
  nada de I/O de red ni lectura de archivos dentro.
- Toda mutacion escribe una fila en `evento` en la MISMA transaccion (`db.registrar_evento`).
- Actualizar = `UPDATE ... SET ..., version = version + 1 WHERE <clave> AND version = ?`.
  `rowcount == 0` -> `db.ConflictoVersion` -> HTTP 409.
- Nada se borra fisicamente: expedientes -> estado `ANULADO` + `motivo_anulacion`; OC -> `excluida = 1`.
- Montos: `INTEGER` en centavos. Cantidades: `TEXT` con `str(Decimal)`. Fechas: `TEXT` ISO `AAAA-MM-DD`
  convertidas a mano. Nunca registrar adaptadores de fecha de sqlite3 (deprecados en 3.12).
- No usar `RETURNING` ni `INSERT ... ON CONFLICT DO UPDATE`: SELECT y despues INSERT o UPDATE explicitos.
- Nombres de tabla/columna dinamicos solo si estan en `db.COLUMNAS[tabla]` (lista blanca del esquema).
- Columnas JSON (`datos`, `crudo`, `campos_manuales`, `extras_cv`, `doc_requerida_central`, `valor`, `informe`, `antes`, `despues`) se escriben con
  `json.dumps(valor, ensure_ascii=False, sort_keys=True)`.
````

`workspace/.claude/rules/textos-y-documentos.md` → `.claude/rules/textos-y-documentos.md` en la raíz del proyecto:

````markdown
---
description: Generadores de textos, importe en letras y documentos Word
paths:
  - "gestor/textos.py"
  - "gestor/letras.py"
  - "gestor/docx_gen.py"
  - "tests/test_textos*.py"
  - "tests/test_autorizacion.py"
  - "tests/test_letras.py"
  - "tests/test_docx.py"
---

# Textos y documentos

- Un texto = una funcion pura en `gestor/textos.py`. Recibe datos ya cargados, devuelve `str`.
- Los goldens del blueprint (§5, "Textos canonicos") son el contrato; un cambio de redaccion rompe un test a proposito.
- Importe en letras SOLO via `gestor.letras.importe_en_letras(centavos)`; formato numerico SOLO via
  `gestor.util.formato_pesos(centavos)` (`1.224.990,00`). Nunca `locale`, nunca `float`.
- Letras en MAYUSCULAS sin tildes, salvo `MILLÓN` (con tilde, como los originales).
- `MM-AA` = periodo validado del expediente (`08-26`), nunca la fecha de la factura.
- CASPH: prefijo `CASPH - ` en referencias; `CASPH` en lugar de `HBI` en textos SAP.
- Si falta un dato obligatorio se lanza `textos.TextoIncompleto(mensaje)`; nunca un texto con huecos.
- Word: se edita la plantilla del efector EN SU LUGAR con `zipfile` + `xml.etree.ElementTree`.
  Solo se reescribe `word/document.xml`; cualquier otro part se copia byte a byte.
- Registrar los namespaces de WordprocessingML con `ET.register_namespace` antes de serializar.
- Las celdas se localizan por el TEXTO del rotulo (normalizado), uniendo los runs `w:r` del parrafo; nunca por indice.
````

`workspace/.claude/rules/interfaz-web.md` → `.claude/rules/interfaz-web.md` en la raíz del proyecto:

````markdown
---
description: Interfaz HTML/JS sin framework, accesibilidad y tokens visuales
paths:
  - "web/**"
  - "tests/test_web*.py"
---

# Interfaz web (sin framework)

- Tres archivos: `web/index.html`, `web/app.js`, `web/style.css`. Sin CDN, sin build, sin dependencias.
- Una `<section id="pantalla-...">` por pantalla; el menu lateral muestra una y oculta las demas (`hidden`).
- Todo texto visible en espanol. Letra base 16 px. Botones minimo 44x44 px.
- Colores SOLO como variables CSS definidas en `:root` de `web/style.css` (ver CLAUDE.md, Sistema visual).
- Cada estado del calendario tiene color Y letra/icono (no solo color): V, C, P, A, M, -, y ◆ / ● para marcas.
- Foco visible: `outline: 3px solid var(--foco); outline-offset: 2px` en todo elemento interactivo.
- Toda llamada a la API pasa por `api(metodo, ruta, cuerpo)` en `app.js`, que muestra `error.mensaje`
  en la region `#avisos` (`aria-live="polite"`). Un 409 muestra el mensaje de version y un boton Recargar.
- Insertar texto de datos con `textContent`, nunca con `innerHTML` (los datos vienen de Excel y de pegados).
- Copiar con formato: `navigator.clipboard.write` con `text/html` (`<p style="text-align: justify">`) y `text/plain`.
````

### 19.6 Verify-critical config and local infrastructure

Los Verify de §9 invocan solo `python` (unittest, compileall, `app.py --check`) más `grep`/`tail`. No hay runner con archivo de
configuración propio, ni e2e, ni alias de rutas, ni servicios. Lo que los gates necesitan para correr:

| File | Path in the project | Which `Verify` commands need it | Resolution/env handling it carries | Bundle-path exclusion |
|---|---|---|---|---|
| Test setup / env-bootstrap | `tests/ayudas.py` | todo Verify con `unittest` desde el paso 1 (las clases `CasoConEntorno` / `CasoConServidor`) | `GESTOR_CONFIG` vía `os.environ` en `ayudas.EntornoTemporal` (se restaura en `cerrar()`); importa `gestor.config` y `gestor.server` dentro de funciones; solo stdlib | n/a — no recorre el árbol; arma rutas desde `RAIZ / "tests" / "fixtures"` |
| Paquete de tests | `tests/__init__.py` | todos los `python -W error::DeprecationWarning -m unittest ...` (pasos 1–32, §20.1) | none needed: hace de `tests` un paquete para `-t .` y `tests.test_<x>`; no lee variables | n/a — `unittest discover` arranca en `-s tests`, nunca en `blueprints/` |
| Config de la app | `config.json` | `python app.py --check` (pasos 1–32, §20.1) y todo test vía `ayudas.config_del_proyecto()` | none needed: JSON leído con `json` de la stdlib; `GESTOR_CONFIG` lo puede reemplazar (lo resuelve `gestor/config.py`) | n/a — no es una herramienta; solo lo lee la app |
| Ignore file (gobierna el primer commit) | `.gitignore` | §20.1 (`git ls-files`, `git check-ignore`, raíz del `.gitignore`) | none needed: no lee variables | `blueprints/` **no** se excluye a propósito: el bundle se versiona con el proyecto (§10) |
| Allowlist del agente | `.claude/settings.json` | todos: sin estas entradas un Verify queda esperando permiso | none needed: no lee variables | n/a — Claude Code lee solo el `.claude/settings.json` de la raíz; la copia bajo `blueprints/` no se usa |
| Test-runner config | NOT APPLICABLE — `unittest` se configura por línea de comando (`-s tests -t .`) | — | — | n/a — `compileall` recibe rutas explícitas (`app.py gestor tests`); `unittest` usa `-s tests`; ninguna herramienta recorre `blueprints/` |
| E2E-runner config | NOT APPLICABLE — no hay e2e de navegador (§13) | — | — | n/a |
| Path-alias config | NOT APPLICABLE — sin alias; `gestor` se importa desde la raíz (`-t .`) | — | — | n/a |
| Local service provisioning | NOT APPLICABLE — ningún Verify necesita un servicio; SQLite es un archivo | — | — | n/a |
| Archivos que un Verify nombra | cada `tests/test_<x>.py`, creado por su paso (§9, *Files touched*) | el paso que lo crea y todos los siguientes (suite completa) | los 33 módulos están en `files` de su paso o de uno anterior; no leen variables salvo por `tests/ayudas.py` | n/a — viven en `tests/` |

**Provistos, no autorados** (datos reales que el arquitecto copió al bundle; se commitean, ningún paso los reescribe):

| Archivo | Contenido | Lo usa |
|---|---|---|
| `plantillas/cv_hbi.docx` | plantilla del CV del HBI (logo en `word/header1.xml`, `word/media/image1.jpeg`) | paso 18 |
| `plantillas/cv_casph.docx` | plantilla del CV del CASPH (más `word/footer2.xml` con RESOL-2023-926) | paso 18 |
| `tests/fixtures/xlsx/z_compras2_hbi_2026.xlsx` | 3074 filas de datos, 27 columnas, sin partida | pasos 4–8 |
| `tests/fixtures/xlsx/z_compras2_por_partida.xlsx` | 5897 filas de datos, 30 columnas, con partida | pasos 4–6 |
| `tests/fixtures/modelos/*.docx` | modelos de autorización, constancia, nota a Central, AySA, Edenor, pago eventual, correctivo | referencia de §5 |
| `tests/fixtures/expedientes/EX-2026-89654857_EFIA/*.txt` | 12 textos de los PDF reales | pasos 11, 13, 17, 21 |
| `tests/fixtures/expedientes/EX-2026-94963848_BIOFAB/*.txt` | 14 textos | pasos 11, 13, 17, 21 |
| `tests/fixtures/expedientes/EX-2026-99349179_MACATEX/*.txt` | 12 textos | pasos 11, 13, 21 |

Contenido completo de los archivos emitidos:

`workspace/.gitignore` → `.gitignore` en la raíz del proyecto:

````text
# Gestor de expedientes de pago — archivos que NO se versionan.
# Llega a la raiz del proyecto con la copia de workspace/ de Bootstrap, ANTES del primer commit.
# Plantillas (plantillas/*.docx), fixtures (tests/fixtures/**), config.json y .claude/ SI se versionan:
# ninguna linea de abajo los alcanza.

# Base de datos y copias de seguridad (se crean en tiempo de ejecucion)
datos/
*.db
*.db-journal

# Documentos generados por el programa
salidas/

# Bytecode de Python
__pycache__/
*.pyc
````

`workspace/config.json` → `config.json` en la raíz del proyecto:

````json
{
  "version_config": 1,
  "base_datos": "datos/expedientes.db",
  "carpeta_backups": "datos/backups",
  "backups_a_conservar": 30,
  "carpeta_salidas": "salidas",
  "puerto_preferido": 8765,
  "puerto_maximo": 8775,
  "tamano_maximo_subida_mb": 25,
  "parametros_iniciales": {
    "efectores": {
      "HBI": {
        "nombre": "Hospital del Bicentenario de Ituzaingó",
        "destino": "al Hospital del Bicentenario de Ituzaingó",
        "centros": ["1900"],
        "prefijo_referencia": "",
        "sigla": "HBI",
        "plantilla_cv": "plantillas/cv_hbi.docx"
      },
      "CASPH": {
        "nombre": "Centro Ambulatorio de Salud PAMI Hurlingham",
        "destino": "al Centro Ambulatorio de Salud PAMI Hurlingham",
        "centros": [],
        "prefijo_referencia": "CASPH - ",
        "sigla": "CASPH",
        "plantilla_cv": "plantillas/cv_casph.docx"
      }
    },
    "partidas_excluidas": ["3490000"],
    "org_compras_propias": ["1900"],
    "exclusiones": {
      "sap": [],
      "oc": []
    },
    "dias_gracia": 10,
    "dias_aviso_vencimiento_oc": 60,
    "umbral_por_agotarse_pct": 85,
    "limite_texto_sap": 50,
    "email_caratula": "contablehbi@pami.org.ar",
    "pago_eventual": {
      "email_caratula": "hbicontable@gmail.com",
      "telefono": "1161757182"
    },
    "sii": {
      "area": "GESP - MESA DE ENTRADAS Y SALIDAS - HOSPITAL DEL BICENTENARIO ITUZAINGO",
      "tipo_servicio": "PROVEEDORES VARIOS",
      "concepto": "Todos los conceptos"
    },
    "destinatario_factura": {
      "nombre": "INSSJP",
      "domicilio": "PERU 169",
      "localidad": "CABA"
    },
    "nota_comodato": "NO-2026-38484415-INSSJP-GESP#INSSJP"
  }
}
````

`workspace/tests/__init__.py` → `tests/__init__.py` en la raíz del proyecto:

````python
# Paquete de tests del gestor de expedientes (unittest, solo biblioteca estandar).
# Se corre desde la raiz del proyecto:
#   python -W error::DeprecationWarning -m unittest discover -s tests -t .
````

`workspace/tests/ayudas.py` → `tests/ayudas.py` en la raíz del proyecto:

````python
"""Ayudas compartidas por todos los tests del gestor de expedientes.

Archivo emitido por el blueprint (seccion 19.6): no lo reescribe ningun paso.
Solo biblioteca estandar. Crea una configuracion y una base TEMPORALES y apunta
la variable de entorno GESTOR_CONFIG a ellas, para que ningun test toque
datos/expedientes.db del proyecto.

Contrato que deben cumplir los pasos (gestor/config.py y gestor/server.py):
  - gestor.config.cargar_config() lee el archivo que indica GESTOR_CONFIG.
  - gestor.server.crear_servidor(puerto, cfg) devuelve un ThreadingHTTPServer
    ya enlazado a 127.0.0.1 (puerto 0 = el sistema elige uno libre).
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
XLSX_HBI_2026 = FIXTURES / "xlsx" / "z_compras2_hbi_2026.xlsx"
XLSX_POR_PARTIDA = FIXTURES / "xlsx" / "z_compras2_por_partida.xlsx"
EXPEDIENTES = FIXTURES / "expedientes"
MODELOS = FIXTURES / "modelos"


def config_del_proyecto():
    """Devuelve el contenido de config.json de la raiz del proyecto."""
    with open(RAIZ / "config.json", encoding="utf-8") as archivo:
        return json.load(archivo)


def texto_fixture(carpeta, patron):
    """Lee (UTF-8) el unico .txt de tests/fixtures/expedientes/<carpeta> que coincide con patron."""
    encontrados = sorted((EXPEDIENTES / carpeta).glob(patron))
    if len(encontrados) != 1:
        raise FileNotFoundError("se esperaba 1 archivo para %s/%s y hay %d" % (carpeta, patron, len(encontrados)))
    return encontrados[0].read_text(encoding="utf-8")


def normalizar_espacios(texto):
    """Colapsa espacios, tabulaciones y saltos de linea en un solo espacio."""
    return " ".join(texto.split())


class EntornoTemporal:
    """Directorio temporal con su propio config.json; GESTOR_CONFIG apunta a el."""

    def __init__(self, **cambios):
        self.dir = Path(tempfile.mkdtemp(prefix="gestor-test-"))
        cfg = config_del_proyecto()
        cfg["base_datos"] = str(self.dir / "datos" / "expedientes.db")
        cfg["carpeta_backups"] = str(self.dir / "datos" / "backups")
        cfg["carpeta_salidas"] = str(self.dir / "salidas")
        cfg.update(cambios)
        self.config = cfg
        self.ruta_config = self.dir / "config.json"
        with open(self.ruta_config, "w", encoding="utf-8") as archivo:
            json.dump(cfg, archivo, ensure_ascii=False, indent=2)
        self._anterior = os.environ.get("GESTOR_CONFIG")
        os.environ["GESTOR_CONFIG"] = str(self.ruta_config)

    @property
    def ruta_base(self):
        return Path(self.config["base_datos"])

    def cerrar(self):
        if self._anterior is None:
            os.environ.pop("GESTOR_CONFIG", None)
        else:
            os.environ["GESTOR_CONFIG"] = self._anterior
        shutil.rmtree(self.dir, ignore_errors=True)


class Respuesta:
    """Respuesta HTTP de prueba: estado, cabeceras y cuerpo crudo."""

    def __init__(self, estado, cabeceras, cuerpo):
        self.estado = estado
        self.cabeceras = cabeceras
        self.cuerpo = cuerpo

    def json(self):
        return json.loads(self.cuerpo.decode("utf-8"))

    def texto(self):
        return self.cuerpo.decode("utf-8")


class ServidorDePrueba:
    """Levanta gestor.server en un thread, en un puerto libre de 127.0.0.1."""

    def __init__(self):
        from gestor import config, server

        self.httpd = server.crear_servidor(0, config.cargar_config())
        self.puerto = self.httpd.server_address[1]
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()

    def url(self, ruta):
        return "http://127.0.0.1:%d%s" % (self.puerto, ruta)

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        pedido = urllib.request.Request(self.url(ruta), data=cuerpo, method=metodo, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resp:
                return Respuesta(resp.status, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as error:
            return Respuesta(error.code, dict(error.headers), error.read())

    def get(self, ruta):
        return self.pedir("GET", ruta)

    def enviar_json(self, metodo, ruta, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        return self.pedir(metodo, ruta, cuerpo, {"Content-Type": "application/json; charset=utf-8"})

    def post(self, ruta, datos):
        return self.enviar_json("POST", ruta, datos)

    def put(self, ruta, datos):
        return self.enviar_json("PUT", ruta, datos)

    def subir(self, ruta, ruta_archivo, campos=None):
        """POST multipart/form-data con un campo 'archivo' y campos de texto extra."""
        limite = "----gestor" + uuid.uuid4().hex
        partes = []
        for nombre, valor in (campos or {}).items():
            partes.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (limite, nombre, valor)).encode("utf-8"))
        contenido = Path(ruta_archivo).read_bytes()
        cabecera = "--%s\r\nContent-Disposition: form-data; name=\"archivo\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % (limite, Path(ruta_archivo).name)
        partes.append(cabecera.encode("utf-8") + contenido + b"\r\n")
        partes.append(("--%s--\r\n" % limite).encode("utf-8"))
        return self.pedir("POST", ruta, b"".join(partes), {"Content-Type": "multipart/form-data; boundary=%s" % limite})

    def cerrar(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CasoConEntorno(unittest.TestCase):
    """TestCase con config y base temporales (sin servidor)."""

    def setUp(self):
        self.entorno = EntornoTemporal()
        self.addCleanup(self.entorno.cerrar)


class CasoConServidor(CasoConEntorno):
    """TestCase con config y base temporales y el servidor corriendo en un thread."""

    def setUp(self):
        super().setUp()
        self.servidor = ServidorDePrueba()
        self.addCleanup(self.servidor.cerrar)
````

#### A resolution convention is decided once and reconciled against every loader

La convención es una sola: **imports absolutos del paquete `gestor` desde la raíz del proyecto** (`from gestor import db`,
`import gestor.textos`), y `tests` como paquete (`from tests import ayudas`). Python resuelve con `sys.path[0]`, que es el
directorio del script (`app.py` en la raíz) o el directorio actual con `-m` (`unittest` corrido desde la raíz con `-t .`). Nadie
toca `sys.path`. Ver la matriz abajo.

#### An emitted config must be complete for the stack this blueprint chose

`tests/ayudas.py` importa solo stdlib e importa `gestor.config` y `gestor.server` **dentro** de las funciones que los usan, así
que el módulo carga aunque el paso que crea esos módulos todavía no haya corrido. `config.json` no requiere ningún paquete. No
hay paquetes con condiciones de export, binarios nativos ni codegen.

#### Every tool that reads env vars must be given a way to load them

La única variable es `GESTOR_CONFIG` y la única herramienta que la lee es la app (`gestor/config.py` → `ruta_config()` con
`os.environ`). Mecanismo de carga: los tests la fijan con `os.environ` en `ayudas.EntornoTemporal.__init__` y la restauran en
`cerrar()`; `python app.py --check` no la necesita (usa `config.json` de la raíz). No hay `.env`.

#### Services a gate depends on must be provisioned by the blueprint

NOT APPLICABLE — ningún Verify necesita un servicio: SQLite es un archivo que crea `db.inicializar`.

#### The bundle sits inside the project, so every emitted config must exclude it

Ninguna herramienta del proyecto recorre el árbol buscando configuración: `compileall` recibe la lista explícita
`app.py gestor tests` (nunca `.`), `unittest discover` arranca en `-s tests`, y no hay formateador, linter, type-checker ni
gestor de workspaces. Por eso `blueprints/` queda fuera **por construcción de los comandos**, no por una línea de exclusión.
`blueprints/gestor-expedientes/workspace/tests/ayudas.py` nunca se importa porque `blueprints` no es un paquete en `sys.path`
con ese nombre de módulo (`tests` resuelve a `./tests` por `-t .`). `.gitignore` no excluye `blueprints/` a propósito: el bundle
se versiona con el proyecto.

#### Resolution convention matrix

**La convención, una vez:** `import gestor.<modulo>` / `from gestor import <modulo>` y `from tests import ayudas`, resueltos desde
la raíz del proyecto; sin `sys.path`, sin imports relativos `..`.

| Context | Command that exercises it | Convention as it appears there | Config + literal setting that makes it work |
|---|---|---|---|
| Application source | `python app.py --check` | `app.py` hace `from gestor import config, server, db`; dentro de `gestor/`, `from gestor import util` | ninguna config: CPython pone el directorio del script (`app.py`, raíz) en `sys.path[0]` |
| Test files | `python -W error::DeprecationWarning -m unittest discover -s tests -t .` y `python -W error::DeprecationWarning -m unittest tests.test_<x> -v` | `from gestor import ...`, `from tests import ayudas` | flag `-t .` (raíz como top-level) y `tests/__init__.py`; con `-m`, el directorio actual (raíz) es `sys.path[0]` |
| Standalone scripts | NOT APPLICABLE — no hay scripts sueltos; la prueba de concurrencia (paso 31) lanza procesos con `multiprocessing` (`spawn`) que importan `tests.test_concurrencia` | funciones a nivel de módulo en `tests/test_concurrencia.py` | `spawn` reimporta el módulo por nombre desde el mismo `sys.path` (raíz), heredado del proceso padre |
| Build / bundle | `python -m compileall -q app.py gestor tests` | compila los mismos archivos sin importarlos | lista explícita de rutas en el comando |
| Lanzador | `Iniciar.bat` → `pythonw app.py` | igual que *Application source* | `cd /d "%~dp0"` deja la raíz como directorio actual |

#### Cross-artifact value reconciliation

| Shared value | Single source — the file that decides it | Literal value | Every other place it appears | Compared |
|---|---|---|---|---|
| Identidad de la app | `gestor/__init__.py` — `APP_ID` (paso 1) | `gestor-expedientes` | `/api/salud` (§5, §16); `python app.py --check \| grep -q '"app": "gestor-expedientes"'` en los Verify de §9, `tasks.json` y epics; detección de instancia en `app.py`; `CLAUDE.md` | yes |
| Versión | `gestor/__init__.py` — `__version__` (paso 1) | `0.1.0` | `/api/salud` (§5, §16); criterio del paso 1 | yes |
| Puertos | `config.json` — `puerto_preferido`, `puerto_maximo` | `8765`, `8775` | `app.py` (`elegir_puerto`, paso 1); `CLAUDE.md`; `AGENTS.md` (`--port 8765`); §1 | yes |
| Ruta de la base | `config.json` — `base_datos` | `datos/expedientes.db` | `.gitignore` (`datos/`, `*.db`); §3; §12; `tests/ayudas.py` (la reemplaza por una ruta temporal) | yes |
| Carpeta de backups y retención | `config.json` — `carpeta_backups`, `backups_a_conservar` | `datos/backups`, `30` | `.gitignore` (`datos/`); `db.hacer_backup(conservar=30)` (paso 2); §5 | yes |
| Carpeta de salidas | `config.json` — `carpeta_salidas` | `salidas` | `.gitignore` (`salidas/`); §3 | yes |
| Raíces de código | comando de lint (§9, §20.1) | `app.py gestor tests` | `.claude/settings.json` (`Bash(python -m compileall -q app.py gestor tests:*)`); `CLAUDE.md`; `AGENTS.md`; todos los Verify | yes |
| Raíz de tests | comando de tests (§9, §20.1) | `-s tests -t .` | `.claude/settings.json` (`Bash(python -W error::DeprecationWarning -m unittest:*)`); `CLAUDE.md`; `AGENTS.md`; todos los Verify | yes |
| Ruta del bundle | §10 Bootstrap | `blueprints/gestor-expedientes/workspace/.` | `.claude/settings.json` (`Bash(cp -R blueprints/gestor-expedientes/workspace/. .)`); §19 | yes |
| Variable de config | `gestor/config.py` — `ruta_config()` (paso 1) | `GESTOR_CONFIG` | `tests/ayudas.py`; §10; `CLAUDE.md` | yes |
| Plantillas del CV | `config.json` — `parametros_iniciales.efectores.<E>.plantilla_cv` | `plantillas/cv_hbi.docx`, `plantillas/cv_casph.docx` | archivos provistos en `workspace/plantillas/`; §3; paso 18 (ruta relativa a la raíz del proyecto) | yes |
| Fixtures Excel | `tests/ayudas.py` — `XLSX_HBI_2026`, `XLSX_POR_PARTIDA` | `tests/fixtures/xlsx/z_compras2_hbi_2026.xlsx`, `tests/fixtures/xlsx/z_compras2_por_partida.xlsx` | archivos provistos; §3; pasos 4–8 | yes |
| Contrato del servidor de prueba | `tests/ayudas.py` — `ServidorDePrueba` | `gestor.server.crear_servidor(puerto, cfg)` y `gestor.config.cargar_config()` | paso 1 (*Do*) los crea con esa firma; contratos del epic 01 | yes |

Todos los contratos de la tabla se ejercitan en el **paso 1** (el primero donde existen ambos lados): su Verify corre
`tests.test_servidor` (que usa `ayudas.ServidorDePrueba` → `crear_servidor` → `/api/salud`) y `python app.py --check`.

#### Byte-exact artifact reconciliation

Este blueprint dicta textos exactos (goldens de §5) **antes** de que exista el código que los produce. Ninguno es un mensaje del
runtime: son formato de strings propio, así que el runtime solo interviene en las filas marcadas.

| Byte-exact artifact | Authored by | First diffed at | Blueprint rules that constrain it | Runtime call that produces it, on the §11 pin | Both confirmed |
|---|---|---|---|---|---|
| Autorización EFIA (golden §5) | §5, copiado en `tests/test_autorizacion.py` (paso 17) | paso 17 | §5 *Autorización de pago* (plantilla del cuerpo, `<frase_periodo>` con `del`, destino HBI); §5 *Importe en letras*; §4 `oc.objeto_articulo` = `al`; EX con forma canónica `- -` (`util.normalizar_gde`) | ninguna: formato de strings propio. Contrastado con el fixture real `0009_IF-2026-91157933`: quitando las dos diferencias aceptadas coincide palabra por palabra | yes |
| Autorización BIO FAB (golden §5) | §5 → `tests/test_autorizacion.py` (paso 17) | paso 17 | §5 (frase de comodato solo en primera validación; razón `BIO FAB S.R.L` sin punto final, como en la carátula); artículo `a la` | ninguna (formato propio) | yes |
| Carátulas EFIA, BIO FAB, MACATEX | §5 → `tests/test_textos_referencias.py` (paso 16) | paso 16 | §5 *Carátula*: `<factura>` = `datos.factura.numero` tal cual (no la columna normalizada) | ninguna | yes |
| Constancia de comodato BIO FAB | §5 → `tests/test_autorizacion.py` (paso 17) | paso 17 | §5 *Constancia*; `<razon>` = `proveedor.razon_social` (`BIO FAB S.R.L`, igual que carátula y autorización); nota `NO-2026-38484415-INSSJP-GESP#INSSJP` de `config.json` | ninguna; contrastado con el fixture `0008_PV-2026-96851161` normalizando espacios y con la única diferencia aceptada `BIO FAB S.R.L.` → `BIO FAB S.R.L` | yes |
| Importe en letras (7 casos) | §5 → `tests/test_letras.py` (paso 3) | paso 3 | §5 *Importe en letras* | ninguna | yes |
| Textos SAP (`HBI - OC 4500555861 - SERV. FUMIGACIÓN - 08/26`, `08/26 HBI OC 4500555861`) | §5 → `tests/test_sap.py` (paso 19) | paso 19 | §5 *Textos SAP*; `MM/AA` = período validado `2026-08` | ninguna | yes |
| Valores del SII (CAE, montos, N°) | fixtures provistos `0004_IF-*.txt` | paso 11 | §4 montos en centavos; N° `0003-00031812` con guion y espacios quitados | ninguna: se extraen de texto real | yes |
| Salida de `--check` (`"app": "gestor-expedientes"`) | paso 1 | paso 1 | §5 `/api/salud`: orden de claves y `json.dumps` con separadores por defecto | `json.dumps({"app": "gestor-expedientes"})` → `{"app": "gestor-expedientes"}` (separador `": "` por defecto en toda versión ≥ 3.4) | yes |
| Serial de Excel `45971` → `2025-11-10` | paso 4 (criterio) | paso 4 | §4 *Limpieza* regla 8 | `date(1899, 12, 30) + timedelta(days=45971)` → `2025-11-10` (ejecutado en Python 3.14.0) | yes |
| CSV con BOM y encabezado NUMERACIÓN | paso 24 | paso 24 | §5 rutas de entregas; UTF-8 con BOM, `;`, CRLF | `"﻿".encode("utf-8")` → `b"\xef\xbb\xbf"` (estable en toda versión) | yes |

---

## 20. Acceptance Gate, Risks & Decision Log

### 20.1 Global acceptance gate

El proyecto está **terminado** cuando cada comando de abajo sale 0 desde la raíz del proyecto, con el bundle presente en
`blueprints/gestor-expedientes/`.

```bash
python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print(sys.version)"   # expect: exit 0, imprime la versión
python -m compileall -q app.py gestor tests   # expect: exit 0, sin salida
python -W error::DeprecationWarning -m unittest discover -s tests -t .   # expect: exit 0, última línea OK
python -W error::DeprecationWarning -m unittest discover -s tests -t . 2>&1 | tail -n 1 | grep -qx OK   # expect: exit 0 — la última línea es exactamente OK: 0 fallas y 0 skipped
python app.py --check | grep -q '"app": "gestor-expedientes"'   # expect: exit 0 — el entry point arranca y responde
python app.py --check | grep -q '"db": "ok"'   # expect: exit 0 — la base se abre o se crea
```

Cada línea sale 0 en un build correcto; ninguna usa una salida no cero como condición de éxito.

Gates manuales (lista previa al uso), cada uno una vez:

- [ ] Las 32 etiquetas de Checkpoint existen (32 = tareas de `tasks.json` = pasos de §9): `test "$(git tag -l 'step-*' | grep -c .)" -eq 32` sale 0. El repositorio lo crea el Bootstrap de §10.
- [ ] Los archivos que deben estar commiteados lo están, una ruta por invocación: `git ls-files --error-unmatch config.json`, `git ls-files --error-unmatch .gitignore`, `git ls-files --error-unmatch tests/ayudas.py`, `git ls-files --error-unmatch .claude/settings.json`, `git ls-files --error-unmatch plantillas/cv_hbi.docx`, `git ls-files --error-unmatch plantillas/cv_casph.docx`, `git ls-files --error-unmatch tests/fixtures/xlsx/z_compras2_hbi_2026.xlsx`, `git ls-files --error-unmatch Iniciar.bat`, `git ls-files --error-unmatch docs/INSTRUCTIVO.md` — cada uno sale 0.
- [ ] Ninguno está ignorado, una ruta por invocación y con el código afirmado: `status=0; git check-ignore -q config.json || status=$?; test "$status" -eq 1` (1 = no ignorado; 128 = error de uso, que ahora falla), y la misma línea para `tests/ayudas.py` y `plantillas/cv_hbi.docx`.
- [ ] `.gitignore` estaba antes del primer commit: `test "$(git log --diff-filter=A --format=%H -- .gitignore | tail -n 1)" = "$(git rev-list --max-parents=0 HEAD)"` sale 0.
- [ ] El Bootstrap de §10 se volvió a correr completo sobre el árbol terminado, **salió 0** en cada línea y después `test -z "$(git status --porcelain)"` sale 0 (no cambió nada versionado: `config.json` y `tests/ayudas.py` intactos).
- [ ] Cada fila de §19.6 *Byte-exact artifact reconciliation* dice `yes` y cada fila de *Cross-artifact value reconciliation* dice `yes`.
- [ ] Ningún no-objetivo de §1 fue construido (sin conexión a SAP/SII/GDE, sin OCR, sin login, sin modo oscuro, sin instalador).
- [ ] Revisión manual por pantalla de `docs/INSTRUCTIVO.md` (sección *Revisión manual por pantalla*) hecha en el navegador, incluida una pasada solo con teclado por el asistente de expediente (§15) y "Copiar con formato" pegado en GDE.
- [ ] `Iniciar.bat` probado con doble clic en una PC Windows: abre el navegador sin consola visible; con el gestor ya abierto, solo abre otra pestaña.
- [ ] Prueba real con la base en la unidad compartida desde las dos PCs, cada una editando un registro distinto y luego el mismo (el segundo guardado muestra el 409).
- [ ] Una restauración de backup hecha a propósito desde la pantalla Inicio/Configuración sobre una copia de la base.

### 20.2 Risk register

| Risk | Likelihood | Impact | Early signal | Mitigation |
|---|---|---|---|---|
| SQLite sobre unidad de red (SMB): corrupción o bloqueo si se corta la red durante una escritura | M | H | `PRAGMA integrity_check` falla al iniciar; errores `database is locked` | `journal_mode=DELETE`, `BEGIN IMMEDIATE` y transacciones cortas, backup al iniciar (30), restauración desde la UI, prueba de dos procesos (paso 31). Aceptado para 2 usuarias; si crece → servidor (§20.4) |
| Reportes sin columna de partida importan honorarios (3490000) | H | M | aviso `Este reporte no tiene la partida presupuestaria…` en la vista previa | aviso explícito + exclusión manual por SAP/OC; pedir a SAP el layout con partida |
| Python ausente o viejo en PCs del trabajo (3.10 EOL; el launcher `py` cambió en 3.14; instalar puede requerir admin) | M | H | `Iniciar.bat` muestra `No se encontro Python 3.10 o superior…` | `Iniciar.bat` prueba `pythonw`, `pyw -3`, `py -3`; código compatible con 3.10; el instructivo cubre la instalación |
| Textos "idénticos" frágiles ante variantes de los modelos reales | M | M | un golden falla tras un cambio de redacción | un generador por texto, goldens de los 3 expedientes reales; cambiar un texto exige cambiar primero el test (skill `nuevo-texto-generado`) |
| Alcance grande (32 pasos) para un builder autónomo | M | M | pasos que exceden una sentada o gates que tardan | hito "prototipo usable" en el paso 21 con su propio gate; epics 04–05 posponibles sin romper nada |
| XML de Word con rótulos partidos en varios `w:r` | H | M | el CV no encuentra `Proveedor:` en la plantilla real | trabajar a nivel de párrafo/celda uniendo runs; tests con las plantillas reales (paso 18) |
| Versión de SQLite en el Python de Windows no verificada | L | M | `BaseNoDisponible` al arrancar | piso en runtime `SQLITE_MINIMA = (3, 8, 3)`; sin `RETURNING` ni UPSERT |

### 20.3 Decision log

| # | Decision | Rejected alternative | Why | Would reverse if |
|---|---|---|---|---|
| 1 | Python solo stdlib | Node/TypeScript (track por defecto), Python + PyPI | pip puede estar bloqueado y no hay internet en el trabajo | se permite instalar paquetes en las PCs |
| 2 | SQLite en carpeta compartida | servidor de base (PostgreSQL) | no hay servidor disponible; 2 usuarias | 3+ usuarias o corrupción repetida |
| 3 | Sin login; identidad = usuario de Windows | usuarios y contraseñas propios | red interna, 2 personas; la auditoría registra quién | se suma gente de otras áreas |
| 4 | HTML/JS sin framework | React/Vue | sin build ni CDN; 8 pantallas | la UI crece mucho más allá de 8 pantallas |
| 5 | Montos en `INTEGER` de centavos | `TEXT` decimal | aritmética exacta y comparación simple en SQL | se necesitan más de 2 decimales |
| 6 | Control optimista con `version` + 409 | bloqueo pesimista por registro | sin servidor central no hay dónde mantener bloqueos | las colisiones se vuelven frecuentes |
| 7 | Importador por nombre de encabezado | por posición de columna | los dos reportes reales tienen columnas en distinto orden | SAP fija un layout único |
| 8 | 32 pasos en 5 epics (desvío del rango 10–18 y de los 6 epics sugeridos: centralizadas/correctivos/eventuales y transversales comparten epic 05) | 18 pasos más grandes | pasos de una sentada (≤ 5 archivos, ≤ 6 criterios); el epic 05 tiene 6 pasos | el builder demuestra pasos más grandes sin fallar |
| 9 | Allowlist con entradas exactas en `settings.json` | `Bash(python:*)`, `Bash(git:*)`, `Bash(cp:*)` | un comodín de intérprete permite cualquier código | nunca |
| 10 | `--aviso` = `#8A5300` | `#B26A00` sugerido | `#B26A00` da 3,89:1 sobre `#FFF4E0` (no pasa AA) | — |
| 11 | "N° Expediente" del CV = `oc.expediente_contratacion`; texto breve MIGO/ML81N = `<concepto_corto> - MM/AA`; días hábiles lunes a viernes sin feriados; formato del informe económico y de la referencia de correctivo definidos acá | preguntar cada uno | defaults técnicos razonables sin dato de la usuaria | la usuaria indica otro formato |
| 12 | Checkpoints con `git commit` y la identidad de la PC; si no hay, el Bootstrap fija `builder@localhost` solo en el repo | identidad fija en todos | los commits quedan a nombre de quien construye cuando hay identidad, y nunca fallan cuando no la hay | — |

### 20.4 What to build next

1. Servidor central (si hay 3+ usuarias o corrupción repetida de la base en la unidad compartida).
2. Importar las planillas SEGUIMIENTO REMITOS 2026 / SEGUIMIENTO CENTRALIZADAS como histórico (si se necesita el historial de 2026 adentro).
3. Importadores de FBL1N y ZEJECUC/ZFI_INF_PRESUP (si se pide conciliación).
4. Lectura de PDFs del SII y de facturas (si se permite instalar paquetes).
5. Instalador para otros efectores (si se distribuye fuera del HBI/CASPH).

---

*Fin del blueprint. El orden de construcción es §9. Parar cuando §20.1 esté en verde.*
