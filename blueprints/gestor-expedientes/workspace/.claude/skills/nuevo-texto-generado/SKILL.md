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
