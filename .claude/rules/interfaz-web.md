---
description: Interfaz HTML/JS sin framework, accesibilidad y tokens visuales
paths:
  - "web/**"
  - "tests/test_web*.py"
---

# Interfaz web (sin framework)

- Archivos: `web/index.html`, `web/app.js`, `web/style.css` y la fuente `web/fuentes/inter.woff2` (servidos por la lista
  `server.ESTATICOS`). Sin CDN, sin build, sin dependencias: si hace falta algo de afuera, se guarda en `web/`.
- Una `<section id="pantalla-...">` por pantalla; el menu lateral muestra una y oculta las demas (`hidden`).
- Todo texto visible en espanol. Letra base 15 px (Inter). Botones minimo 44x44 px.
- Colores SOLO como variables CSS definidas en `:root` de `web/style.css` (ver CLAUDE.md, Sistema visual).
- Cada estado del calendario tiene color Y letra/icono (no solo color): V, C, P, A, M, -, y ◆ / ● para marcas.
- Foco visible: `outline: 3px solid var(--foco); outline-offset: 2px` en todo elemento interactivo.
- Toda llamada a la API pasa por `api(metodo, ruta, cuerpo)` en `app.js`, que muestra `error.mensaje`
  en la region `#avisos` (`aria-live="polite"`). Un 409 muestra el mensaje de version y un boton Recargar.
- Insertar texto de datos con `textContent`, nunca con `innerHTML` (los datos vienen de Excel y de pegados).
- Copiar con formato: `navigator.clipboard.write` con `text/html` (`<p style="text-align: justify">`) y `text/plain`.
