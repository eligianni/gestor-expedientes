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
