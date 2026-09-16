/** Abre el PDF de un ticket en una ventana aparte y dispara la impresión.
 *
 *  El navegador no puede hablarle a la ticketeadora directamente: imprime a
 *  través del diálogo del sistema, que es el que conoce la impresora térmica.
 *  El PDF ya viene con el ancho de papel configurado, así que sale a la
 *  medida del rollo.
 *
 *  Extraído de `Pos.tsx::imprimirTicket` (F4, ADR-025) al sumar el ticket de
 *  cierre de turno y el de cierre diario (2026-09-16, cajas por sucursal):
 *  las tres rutas son PDFs del backend con el mismo contrato -- una sola
 *  función para abrirlas evita que una de las tres se quede sin el
 *  `addEventListener('load', ...)` que dispara la impresión sola.
 */
export function abrirTicket(url: string): void {
  const ventana = window.open(url, '_blank')
  if (!ventana) return  // bloqueador de popups: el ticket se puede pedir de nuevo
  ventana.addEventListener('load', () => ventana.print())
}
