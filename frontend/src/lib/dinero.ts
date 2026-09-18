/**
 * Formateo de montos en pesos. `money()` reemplaza los locales de
 * `CierreDiario.tsx`, `CuentasCorrientes.tsx`, `Reportes.tsx` y `Pos.tsx`
 * (mismo formato), y `pesos()` se usa donde el valor puede ser NEGATIVO
 * (diferencia, saldo). Los que sólo formatean importes que nunca bajan de
 * cero en otras pantallas (precios en `Productos.tsx`, costos en Compras) se
 * dejaron como estaban.
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
