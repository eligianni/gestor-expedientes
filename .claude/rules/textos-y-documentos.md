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
