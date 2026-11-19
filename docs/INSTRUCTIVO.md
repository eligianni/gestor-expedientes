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
2. En **Expedientes → Nuevo expediente**: elegir tipo (común, centralizada, correctivo o pago eventual) y OC.
3. **Remitos**: pegar una línea por remito (`numero;fecha[;fecha de firma]`). El período sale del remito, nunca de la factura.
4. **Factura y SII**: cargar la factura y pegar el texto del SII. Los controles marcan errores (rojo), salvables con nota
   (violeta), avisos y cosas a verificar a mano.
5. **Textos**: copiar carátula, referencias GDE, autorización y textos SAP; descargar el certificado de validación (Word).
6. **Números GDE**: pegar los números de cada documento subido.
7. **Estado**: Borrador → Controlado → En firma → Firmado. El paso a Enviado se hace en **Entregas** (con su CSV de numeración).
   Después: Contabilizado → Cerrado. Si falta algo, Pendiente con motivo y fecha de seguimiento.
- Correctivo: Recibido de Mantenimiento → Informe económico → Devuelto → Para facturar → Controlado (sigue el flujo común).
- Pago eventual: Armado → En Dto. Económico Contable → Devuelto → Contabilizado → Finalizado. Uno por proveedor y año.
- Centralizadas: cargar N° de CV, N° de nota y fecha de envío en la pantalla Centralizadas, y tildar la documentación auditada.
- Servicios del CASPH (AySA y Edenor): panel "Servicios CASPH" en Expedientes.
- El **Calendario** muestra cada OC por mes: `V` validado, `C` en curso, `P` pendiente en plazo, `A` atrasado,
  `M` pendiente con motivo, `·` sin iniciar, `-` fuera de vigencia. Inicio junta las alertas del día.

## Revisión manual por pantalla

Recorrer cada pantalla solo con el teclado (Tab, Mayús+Tab, Enter, Espacio) y mirar: el foco siempre visible (recuadro
azul), que se llegue a todos los botones y campos, que no haya textos en inglés y que los estados digan una letra o
palabra además del color.

- [ ] Inicio: alertas ordenadas por urgencia, cada una con su marca (▲ ■ ●) y enlace al expediente u OC.
- [ ] Calendario: filtros por año, efector, tipo y SAP; cada celda se lee con su letra y abre el expediente con Enter.
- [ ] Órdenes de compra: búsqueda, ficha con renglones y consumo, edición de objeto, prórroga y marcas.
- [ ] Expedientes: los 7 pasos del asistente, pendientes arriba, Copiar en cada texto y avisos legibles.
- [ ] Centralizadas: tabla por OC y período, N° de CV y de nota, fecha de envío, checklist y marca ◆ cuando se envió.
- [ ] Entregas: crear, asignar firmados, enviar y descargar el CSV de numeración.
- [ ] Importar: elegir el Excel, ver el resumen (nuevas, modificadas, sin cambios) y el historial de importaciones.
- [ ] Configuración: parámetros compartidos, ruta de la base, copia manual y Cerrar programa.
