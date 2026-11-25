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

Python stdlib · `http.server.ThreadingHTTPServer` en 127.0.0.1 · SQLite (`sqlite3`) · HTML/CSS/JS sin framework en `web/` (fuente Inter local) ·
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
| `gestor/pdf_texto.py` | stdlib | base, archivos, otros módulos de `gestor` |
| `gestor/oc_pdf.py`, `gestor/factura_pdf.py` | `util` | base, archivos, `negocio` |
| `gestor/tablas.py` | `db`, `negocio` (solo lectura), `util`, `xlsx_escritor` | escribir la base, `server` |
| `gestor/migracion.py` | `db`, `util`, `xlsx`, `negocio` | `server` |
| `gestor/textos.py`, `gestor/letras.py`, `gestor/util.py` | stdlib, `util`, `letras` | base, archivos, `negocio` |
| `gestor/db.py` | stdlib | cualquier otro módulo de `gestor` salvo `config` |
| `web/*` | nada externo (sin CDN); archivos propios en `web/` (la fuente en `web/fuentes/`) | llamar `fetch` fuera de `api()` |
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
| Texto de un PDF digital | `gestor/pdf_texto.py` → `texto_de_pdf` (sin OCR) |
| Datos de la factura desde su PDF | `gestor/factura_pdf.py` → `leer_factura` (varios formatos; sin descripción de ítems) |
| Datos de la OC desde su PDF | `gestor/oc_pdf.py` → `leer_oc`; comparar/aplicar en `negocio.comparar_oc_pdf` / `aplicar_oc_pdf` |
| Migración del seguimiento en Excel | `gestor/migracion.py` (NUMERACIÓN + solapa HBI 20252026 → expedientes, entregas) |
| Pantalla Tablas y su Excel | `gestor/tablas.py` (columnas por tabla) + `web/app.js` (filtros, orden, vistas) |
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

Estilo limpio de panel (inspirado en Stripe) con el azul institucional. Tokens definidos una vez en `:root` de
`web/style.css`; el CSS usa solo `var(--...)`. Sin modo oscuro.

| Token | Valor | Uso |
|---|---|---|
| `--primario` / `--primario-hover` | `#1F4E8C` / `#173D6E` | botones, enlaces, foco |
| `--primario-suave` / `--primario-borde` | `#EBF2FB` / `#B9CDE8` | ítem activo del menú, botones dentro de tablas |
| `--primario-texto` | `#FFFFFF` | texto sobre primario |
| `--fondo` / `--superficie` / `--superficie-hundida` | `#F6F8FB` / `#FFFFFF` / `#F9FAFC` | página / paneles / encabezados de tabla |
| `--borde` / `--borde-fuerte` / `--borde-control` | `#E3E8EF` / `#D5DCE5` / `#8792A2` | divisores / botones secundarios / inputs |
| `--texto` / `--texto-suave` | `#1A1F36` / `#5E6A7D` | cuerpo / secundario |
| `--error` / `--error-fondo` | `#B3261E` / `#FDF0EF` | errores, atrasado |
| `--exito` / `--exito-fondo` | `#217A3C` / `#EAF6EE` | validado, confirmaciones |
| `--aviso` / `--aviso-fondo` | `#8A5300` / `#FFF6E5` | avisos |
| `--info` / `--info-fondo` | `#1565C0` / `#EAF2FD` | verificar, en curso |
| `--violeta` / `--violeta-fondo` | `#6A3FA0` / `#F3EEFA` | salvable, pendiente con motivo |
| `--pendiente-plazo` | `#FFE08A` | celda pendiente en plazo |
| `--neutro-fondo` | `#EEF1F5` | fuera de vigencia, hover, pastilla neutra |
| `--naranja` | `#C2410C` | borde OC por vencer |
| `--foco` | `#1F4E8C` | `outline: 3px solid var(--foco); outline-offset: 2px` |

- **Tipo:** Inter guardada en `web/fuentes/inter.woff2` (OFL, licencia al lado), con `"Segoe UI", system-ui` de respaldo;
  cuerpo 15px/1.55; títulos 26/19/16px peso 700/650; encabezados de tabla 12px en mayúsculas; mono `Consolas` 14px;
  números de tablas con `tabular-nums` (`.numero`).
- **Espaciado:** base 4px — 4, 8, 12, 16, 20, 24, 32. Margen de la app: `--margen` (34px) en encabezado, menú y contenido. Paneles con padding 20px 24px.
- **Radio:** 6px botones e inputs, 10px paneles, 999px pastillas. **Sombras:** `--sombra-panel` (anillo de 1px + sombra suave),
  sin bordes duros en paneles.
- **Botones:** alto mínimo 44px; primario azul lleno, secundario blanco con texto oscuro.
- **Estados:** pastillas (`.pastilla .pastilla-<tono>`) con la palabra siempre visible; calendario con letra (`-` `V` `C` `P`
  `A` `M` `·`) y marcas ● ◆. Nunca solo color.
- **Motion:** solo transiciones de color de 120ms `ease-out`; `transition: none` con `prefers-reduced-motion: reduce`.

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
- La carga del PDF de la OC no tiene columna propia: queda como `evento` `IMPORTACION` de la OC con `despues.fuente = "pdf_oc"`
  (`negocio.ultimo_pdf_oc`). Lo aplicado se marca en `campos_manuales`, así la importación del z_compras2 no lo pisa.
- La exportación de Tablas se envía con un `<form>` POST (no `fetch`) para que el navegador descargue el archivo.
- Copias de seguridad: una al arrancar (rotan, `backups_a_conservar`) y una por día en `<carpeta_backups>/diarios`
  (`db.backup_diario`, hilo en `app.py` cada 30 min, `backups_diarios_a_conservar`). Restaurar usa solo las de arranque.
- Importar z_compras2: si el reporte trae la columna «Centro Gestor», entra todo lo imputado al centro gestor del efector
  (`efectores.<X>.centros_gestores`, por defecto 4500 HBI y 4900 CASPH) aunque el renglón tenga otro centro; sin esa
  columna se filtra por `centros`. Centralizada (compra de Nivel Central, «UOC: Nivel Central BS» en el PDF) = algún
  renglón del centro 0010 (`parametros.centros_centrales`), o comprada por otra organización de compras (0100, 0110…)
  para entregar en un centro propio (1900 HBI, 1300 CASPH); otra organización para otro centro (1000, 1500, 1700) es
  «otro centro». Sin centro en el reporte alcanza con la organización distinta de la propia
  (`efectores.<X>.org_compras`, 1900 HBI y 1300 CASPH). El día de inicio del período sale del día de
  `vig_desde` (29 a 31 → 1), salvo que se haya editado a mano. La prórroga no se carga en la ficha: sale como otra OC.
- Renglón de «otro centro»: su centro (de la fila del z_compras2 en `renglon.crudo`) no es un centro propio del efector
  (`efectores.<X>.centros` o, si está vacío, 1900 HBI / 1300 CASPH) ni el de Nivel Central (0010, que se marca como
  «Centralizada»). Se marca en la ficha, el paso 2, la lista de OC y
  Tablas (`negocio.marcar_otro_centro`); no cambia controles ni calendario.
- «Nueva OC» (Órdenes de compra): acepta varios PDF; `POST /api/oc/pdf` lee cada uno sin guardar y la ventana
  `#dialogo-pdf-oc` (`colaPdf` en `app.js`) los recorre «Confirmar datos (i/n)»: OC nueva → formulario, OC existente →
  comparación (`/api/oc/<n>/pdf`), al final un resumen. La comparación desde la ficha o el paso 1 usa la misma ventana. Confirmar y `POST /api/oc/desde-pdf` → `negocio.crear_oc_desde_pdf` (origen MANUAL, todo
  lo del PDF como manual, evento `pdf_oc`). «Sin PDF (escaneada)» abre el alta a mano. El artículo va chiquito a la
  izquierda del objeto (`campoObjeto` en `app.js`).
- PDF de la OC: artículo («a la» si dice adquisición/provisión, «al» si dice servicio; manda el primero), día de inicio y
  N° GDE (también de los campos de formulario del PDF) vienen tildados solos; el objeto se corta antes de «con destino».
  En los bienes no se muestran ni se toman vigencia, prórroga ni día de inicio.
- La migración crea expedientes ya tramitados directo en su estado (CERRADO, ENVIADO, PENDIENTE, BORRADOR) con
  `periodo_manual = 1` e historial `MIGRACION`; reconoce lo ya migrado por factura + SAP (o OC + período si no hay
  factura). Las hojas "ENTREGA (n)" con paréntesis son copias y se ignoran.
- Tablas: todo centrado salvo las columnas de texto largo (proveedor, objeto, descripción…), que llevan `.izq`
  (`claseColumna` en `app.js` por el título; en Tablas, `COLUMNAS_A_LA_IZQUIERDA`). La lista de OC muestra las marcas
  (centralizada, comodato, otro centro, manual, excluida) como etiquetas en «Observaciones», no en «Tipo». Tablas tiene
  «Ver más grande» (`body.vista-amplia`, sin menú ni encabezado; Esc sale) y la tabla de Entregas (`tablas.tabla_entregas`).
- OC «Acciones pendientes» (`faltantesOC` en `app.js`): falta el PDF (`negocio.ocs_con_pdf`, `listar_oc.pdf_cargado`) o el
  concepto corto; ambos llevan (*) en la ventana de edición (que también tiene la carga del PDF) y sin ellos «Nuevo
  expediente» de la ficha está deshabilitado. La ficha no muestra GDE del PDF, concepto corto ni día de inicio (solo al editar).
- Paso 2 (remitos): formulario fila por fila (N°, fecha, fecha de firma, casilla de equipo en comodato por remito), hasta
  `negocio.MAX_REMITOS` (20) por expediente; va por `POST .../remitos/pegar` con `remitos: [...]` (el texto pegado sigue
  aceptado). Un número repetido actualiza fechas y conserva cantidades. Las cantidades se cargan después, por remito y renglón.
  Los remitos ya cargados (también los migrados, que vienen sin fecha ni cantidades) se editan en el mismo paso: número,
  fechas, comodato y cantidades, y se guardan juntos con `PUT /api/expedientes/<id>` (`datos.remitos`).
- Paso 3: «Leer y controlar» sube el PDF de la factura (`POST /api/comprobantes/factura-pdf`) y/o el del SII
  (`/api/comprobantes/sii-pdf`, mismo parser que el texto pegado) y controla enseguida con
  `POST /api/expedientes/<id>/comprobantes/revisar` → `negocio.revisar_comprobantes`: los controles de ámbito factura/sii
  del paso 4 sobre lo leído, más CUIT de factura y SII contra el proveedor, SAP y letra del SII. No guarda nada.
  La pantalla es una sola tabla «Corroborar los datos» (`FILAS_COMPROBANTES` en `app.js`: factura editable | SII | debe
  ser, con «Coincide / No coincide»); el resumen «N errores · N para verificar» abre la ventana `#dialogo-revision`.
  Un SII sin datos no se controla. En el SII va el mes en que termina el período validado
  (`controles.periodo_sii_esperado`). El N° de factura se guarda como figura (punto de venta de 4 o 5 dígitos); el SII
  lo muestra con 4 y se comparan por valor (`util.misma_factura`).
- Certificado de validación: «Fecha de Entrega» = fin del período en servicios (octubre → 31/10; 9/10 al 8/11 → 8/11);
  en bienes, la fecha de firma del remito si la tiene, si no la del remito. Lleva todos los renglones (0 si no hubo entrega), cantidad de la OC sin unidad, objeto con
  mayúscula inicial y la celda de la fecha ensanchada (`docx_gen._ensanchar_fecha`, sin tocar la plantilla). No necesita factura ni SII (`textos.referencia_cv`, solo razón y período). Botón en el paso 2
  y en el 5 (`botonCertificado`): primero `GET .../cv/verificar` (422 con lo que falta) y después baja `cv.docx`.
- Subrenglones (1-10, 1-20…): sin columna propia, en `renglon.crudo["_subrenglones"]` (`negocio.subrenglones_de`); se
  guardan al crear/aplicar desde el PDF (`subrenglones: {pos: [...]}`; al reaplicar se conserva la descripción editada),
  se editan en «Editar» del renglón (`PUT /api/oc/<n>/renglones/<pos>/subrenglones`) y la importación los conserva
  (`importar._con_subrenglones_guardados`). En el CV va una fila por subrenglón y lo entregado se asigna en orden según
  lo consumido antes (`negocio._consumido_antes`). Consumo: `agotado` cuando el saldo llega a 0. La ficha no muestra
  «Consumo previo».
- Centralizadas: no son expedientes de pago (la factura y el SII los hace Nivel Central). Cada «validación» es un
  expediente tipo CENTRALIZADA por OC + efector + período (se crea desde el tablero o la ficha; `crear_expediente` acepta
  otro efector y el período fijo), con 4 pasos en el asistente (`PASOS_CENTRALIZADA`): remitos y CV → N° de IF del CV
  firmado → Nota a Central (`GET .../nota-central`) + N° de nota y fecha de envío. `guardar_centralizada` mueve el estado:
  IF → FIRMADO («CV firmado»), nota + fecha → ENVIADO («Validado»). No aparecen en «Expedientes» (`listar_expedientes`
  sin `tipo`). Reparto por efector en `renglon.crudo["_por_efector"]` (`guardar_por_efector`, `PUT .../renglones/<pos>/
  efectores`): consumo (`consumo_oc(efector=)`), CV y lo consumido antes van por efector; la OC aparece en la lista de cada
  efector que la valida (`efectores_de_oc`). Tablero: `GET /api/centralizadas/tablero` (`negocio.tablero_centralizadas`).
  Se validan por mes calendario recortado a la vigencia (`negocio.limites_centralizada`); en el tablero un mes está
  «pendiente» hasta `dias_gracia` (10) días después de terminar. El SEGUIMIENTO_CENTRALIZADAS en Excel se carga desde la
  pantalla («NOTAS ENVIADAS» y «ENTREGAS ÚNICAS», HUR = CASPH): `migracion.planificar_centralizadas` / `migrar_centralizadas`
  (`/api/importar/centralizadas/{vista-previa,confirmar}`), idempotente por OC + efector + mes; marca las OC como centralizadas.
- Los expedientes no se borran: «Anular expediente» (arriba del asistente, `abrirDialogoAnular`) pide un motivo y llama a
  `POST /api/expedientes/<id>/anular`; queda ANULADO y deja de contar para consumo y controles.
- Consumo a mano: meses ya facturados sin remitos → `datos.consumo_manual` del expediente
  (`negocio.guardar_consumo_manual`, `PUT /api/expedientes/<id>/consumo-manual`); `cantidades_del_expediente` lo usa solo
  si los remitos no tienen cantidades. La ficha de la OC muestra el consumo como tabla (renglón × período).
- Editar una OC: lápiz (`botonLapiz`) en la lista y en la ficha → ventana `abrirDialogoEditarOC` (campos de
  `CAMPOS_OC_FORM`, `PUT /api/oc/<n>`); la confirmación se muestra dentro de la ventana y la ficha queda en lectura
  (`resumenDatosOC`). Buscar cierra la ficha abierta. La leyenda del CV solo se muestra en centralizadas.
- Todo archivo nuevo de `web/` se sirve solo si está en `server.ESTATICOS` (lista blanca); nunca desde internet.
- Programa viejo abierto después de un `git pull`: los archivos de `web/` se leen en cada pedido pero el Python no. El
  servidor guarda `huella_codigo()` al arrancar y, si cambió en el disco, responde con `X-Gestor-Desactualizado: 1`;
  `api()` muestra un aviso fijo para reiniciar (también ante «Ruta no encontrada»).
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
