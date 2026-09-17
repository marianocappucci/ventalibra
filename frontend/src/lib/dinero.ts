/**
 * Formateo de montos en pesos. Consolida los `function money(...)` locales
 * que había repetidos en `CierreDiario.tsx`, `CuentasCorrientes.tsx`,
 * `Reportes.tsx`, `Catalogo.tsx` y `Pos.tsx` -- acá sólo el que puede recibir
 * un valor NEGATIVO (diferencia, saldo): los que sólo formatean importes que
 * nunca bajan de cero (precios, totales de venta) se dejan como estaban, sin
 * tocar su formato.
 *
 * Encontrado en la prueba en pantalla del 2026-09-17: con un negativo, un
 * `$` antepuesto a mano en el JSX + `money(v)` da `$-500,00` en vez de
 * `-$500,00` -- el signo queda pegado al número, no a la moneda. La forma
 * correcta separa el signo del `$` (ya la tenía bien, antes de esto,
 * `CuentasCorrientes.tsx::conSigno`, sólo que no la reusaba nadie más).
 */
export function money(value: string | number): string {
  return Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

/** `-500` -> `"-$500,00"`; `1500.5` -> `"$1.500,50"`. Mismos separadores que
 *  `money()`; el signo va ANTES del `$`, nunca pegado al número. */
export function pesos(value: string | number): string {
  const n = Number(value)
  return `${n < 0 ? '-' : ''}$${money(Math.abs(n))}`
}
