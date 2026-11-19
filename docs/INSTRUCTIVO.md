# Gestor de expedientes de pago — instructivo

Programa local para las OC, los consumos y los expedientes de pago del HBI y del CASPH. Corre en cada PC y las dos
usuarias comparten la misma base. No necesita internet.

## Instalar Python

1. Descargar Python 3.10 o superior (recomendado el último 3.x) desde https://www.python.org/downloads/windows/.
2. En el instalador, tildar **Add python.exe to PATH** y elegir **Install Now**.
3. No hay que instalar nada más: el programa usa solo lo que trae Python.

## Abrir el programa

1. Hacer doble clic en `Iniciar.bat` (en la carpeta del programa).
2. Se abre el navegador en `http://127.0.0.1:8765` (si ese puerto está ocupado, usa el siguiente libre hasta el 8775).
3. Si el programa ya estaba abierto, el doble clic solo vuelve a abrir la pestaña.
4. Para cerrarlo: Configuración → **Cerrar programa**. Cerrar la pestaña no lo apaga.
5. El selector de efector (HBI, CASPH o Ambos), arriba, filtra todas las pantallas.

## Dónde está la base

- La base es un único archivo SQLite. Por defecto `datos/expedientes.db`, dentro de la carpeta del programa.
- Para compartirla, las dos PCs apuntan al mismo archivo en la unidad de red (por ejemplo `Z:\Contable\gestor\expedientes.db`):
  Configuración → **Ubicación de la base de datos** → Guardar, y volver a abrir el programa.
- La ruta se guarda en `config.json` de cada PC. Los parámetros compartidos (siglas, destinatarios, límites) están en la base.
- Dos personas pueden trabajar a la vez. Si las dos editan lo mismo, la segunda ve el aviso de que el dato cambió y recarga
  antes de guardar: nunca se pisa el trabajo de la otra.
- Nada se borra: los expedientes se anulan con motivo y las OC se excluyen. Todo cambio queda registrado con usuaria y fecha.

## Copias de seguridad

- Cada vez que se abre el programa se hace una copia de la base en `datos/backups` (o en la carpeta configurada).
  Se conservan las últimas 30.
- Configuración → **Copia de seguridad ahora** hace una copia en el momento (recomendado antes de importar un reporte grande).
- Si al abrir aparece "la base tiene errores", usar **Restaurar última copia** en Inicio y avisar a la otra usuaria.
- Una vez por mes, copiar la carpeta de backups a otro lugar (pendrive o carpeta personal).

## Flujo de un expediente

1. **Importar** el reporte de OC (Excel de SAP) en Importar. Las OC nuevas aparecen en Órdenes de compra.
2. **PDF de la OC** (una vez por OC, antes de validar): en la ficha de la OC, o en el paso 1 del expediente, subir el PDF
   digital de la OC (el firmado en GDE) y tocar **Leer y comparar**. El programa toma de ahí el objeto de la contratación,
   el N° GDE del PDF, la CA, la vigencia y, por renglón, la cantidad, la unidad, el precio y los subrenglones (por ejemplo
   1 UP = 3 MES × $ 1.224.990,00), que el reporte de SAP suele traer mal. Muestra lo que cambia y solo se aplica lo
   tildado; el objeto se puede corregir antes de aplicar. Lo aplicado queda como cargado a mano: importar de nuevo el
   reporte de SAP no lo pisa. Si el PDF no se puede leer (por ejemplo, un escaneo), copiar el texto desde el visor de
   PDF y pegarlo en «¿El PDF no se puede leer? Pegá su texto».
3. En **Expedientes → Nuevo expediente**: elegir tipo (común, centralizada, correctivo o pago eventual) y OC.
4. **Remitos**: pegar una línea por remito (`numero;fecha[;fecha de firma]`). El período sale del remito, nunca de la factura.
5. **Factura y SII**: cargar la factura y pegar el texto del SII. Los controles marcan errores (rojo), salvables con nota
   (violeta), avisos y cosas a verificar a mano.
6. **Textos**: copiar carátula, referencias GDE, autorización y textos SAP; descargar el certificado de validación (Word).
7. **Números GDE**: pegar los números de cada documento subido.
8. **Estado**: Borrador → Controlado → En firma → Firmado. El paso a Enviado se hace en **Entregas** (con su CSV de numeración).
   Después: Contabilizado → Cerrado. Si falta algo, Pendiente con motivo y fecha de seguimiento.
- Correctivo: Recibido de Mantenimiento → Informe económico → Devuelto → Para facturar → Controlado (sigue el flujo común).
- Pago eventual: Armado → En Dto. Económico Contable → Devuelto → Contabilizado → Finalizado. Uno por proveedor y año.
- Centralizadas: cargar N° de CV, N° de nota y fecha de envío en la pantalla Centralizadas, y tildar la documentación auditada.
- Servicios del CASPH (AySA y Edenor): panel "Servicios CASPH" en Expedientes.
- **Tablas**: expedientes, órdenes de compra y renglones de OC como planillas. Tocar un encabezado ordena; la fila de
  abajo de los encabezados filtra cada columna (texto que contiene, o `>`, `<`, `>=`, `<=`, `=` y rangos `desde..hasta`
  en montos, cantidades y fechas, como `>=01/08/2026` o `100000..500000`). En **Columnas** se eligen las que se ven;
  **Guardar vista…** guarda columnas, orden y filtros con un nombre (en esta PC). **Exportar a Excel** descarga las
  columnas visibles y todas las filas filtradas, en el mismo orden.
- El **Calendario** muestra cada OC por mes: `V` validado, `C` en curso, `P` pendiente en plazo, `A` atrasado,
  `M` pendiente con motivo, `·` sin iniciar, `-` fuera de vigencia. Inicio junta las alertas del día.

## Revisión manual por pantalla

Recorrer cada pantalla solo con el teclado (Tab, Mayús+Tab, Enter, Espacio) y mirar: el foco siempre visible (recuadro
azul), que se llegue a todos los botones y campos, que no haya textos en inglés y que los estados digan una letra o
palabra además del color.

- [ ] Inicio: alertas ordenadas por urgencia, cada una con su marca (▲ ■ ●) y enlace al expediente u OC.
- [ ] Calendario: filtros por año, efector, tipo y SAP; cada celda se lee con su letra y abre el expediente con Enter.
- [ ] Órdenes de compra: búsqueda, ficha con renglones y consumo, edición de objeto, prórroga y marcas; PDF de la OC
  (leer, revisar con las casillas Tomar y aplicar). Tablas: ordenar, filtrar por columna, elegir columnas, guardar una
  vista y exportar a Excel.
- [ ] Expedientes: los 7 pasos del asistente, pendientes arriba, Copiar en cada texto y avisos legibles.
- [ ] Centralizadas: tabla por OC y período, N° de CV y de nota, fecha de envío, checklist y marca ◆ cuando se envió.
- [ ] Entregas: crear, asignar firmados, enviar y descargar el CSV de numeración.
- [ ] Importar: elegir el Excel, ver el resumen (nuevas, modificadas, sin cambios) y el historial de importaciones.
- [ ] Configuración: parámetros compartidos, ruta de la base, copia manual y Cerrar programa.
