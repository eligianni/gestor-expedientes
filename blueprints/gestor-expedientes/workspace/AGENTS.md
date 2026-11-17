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
