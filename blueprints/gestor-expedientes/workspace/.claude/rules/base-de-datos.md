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
