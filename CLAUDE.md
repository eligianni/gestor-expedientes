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
| `gestor/oc_pdf.py` | `util` | base, archivos, `negocio` |
| `gestor/tablas.py` | `util`, `xlsx_escritor` | escribir la base, `server` |
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
| Datos de la OC desde su PDF | `gestor/oc_pdf.py` → `leer_oc`; comparar/aplicar en `negocio.comparar_oc_pdf` / `aplicar_oc_pdf` |
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
- **Espaciado:** base 4px — 4, 8, 12, 16, 20, 24, 32. Paneles con padding 20px 24px.
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
- Todo archivo nuevo de `web/` se sirve solo si está en `server.ESTATICOS` (lista blanca); nunca desde internet.
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
