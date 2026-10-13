// El servidor valida el precio de cada línea al registrar la venta (ADR-079; `libracommerce` ADR-049). Si el POS mandó un precio
// que ya no es el vigente (la lista cambió con la pantalla abierta, o el carrito se armó contra otra), `POST /api/ventas` contesta
// 409 y NO escribe nada: este módulo reconoce esa respuesta y arma el aviso al cajero. El `detail` es un objeto
// (`{mensaje, codigo, precios}`) y el `ApiError` del kit lo conserva en `detailData`.
//
// Desde libracommerce 0.59.0 (ADR-058 del motor; ADR-083 de este repo) el POS manda `sucursal_id` y el `detail` suma, **sólo cuando el
// servidor validó contra una sucursal**, ese mismo campo (la que usó él, que sale del depósito de la venta y no del pedido). Sin
// sucursal el cuerpo es el de siempre. El POS no lo necesita para corregir el carrito -- el `esperado` de cada línea ya es el precio
// de esa sucursal --, así que se lee con tolerancia (puede faltar, venir `null` o no ser un número) y nunca decide si el 409 se
// reconoce.
import { ApiError } from '../api'

/** Una línea cuyo precio no coincide: `indice` es su posición en el pedido (la misma que en el carrito). */
export type PrecioDistinto = {
  indice: number
  producto_id: number | null
  variante_id: number | null
  enviado: number
  esperado: number
}

export const CODIGO_PRECIOS_DISTINTOS = 'precios_distintos'

/** El `detail` del 409 completo. `sucursal_id` es opcional: sólo está si el servidor validó por sucursal (motor >= 0.59.0). */
export type DetallePreciosDistintos = {
  mensaje?: string
  codigo: typeof CODIGO_PRECIOS_DISTINTOS
  precios: PrecioDistinto[]
  sucursal_id?: number | null
}

/** La sucursal contra la que el servidor validó los precios de un 409 `precios_distintos`; `null` si no validó por sucursal (el
 *  campo falta, es `null` o no es un entero) o si el error es otro. */
export function sucursalDeLosPrecios(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const datos = err.detailData as Partial<DetallePreciosDistintos> | undefined
  return datos && datos.codigo === CODIGO_PRECIOS_DISTINTOS && Number.isInteger(datos.sucursal_id) ? (datos.sucursal_id as number) : null
}

/** Las líneas con precio distinto si el error es el 409 de la validación de precios; `null` si es cualquier otro error
 *  (otro 409 como «No hay un turno abierto» sigue siendo un error común). */
export function preciosDistintosDe(err: unknown): PrecioDistinto[] | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const datos = err.detailData as { codigo?: unknown; precios?: unknown } | undefined
  if (!datos || datos.codigo !== CODIGO_PRECIOS_DISTINTOS || !Array.isArray(datos.precios)) return null
  const validos = datos.precios.filter((p): p is PrecioDistinto => (
    !!p && typeof p === 'object'
    && Number.isInteger((p as PrecioDistinto).indice) && Number.isFinite((p as PrecioDistinto).esperado)
  ))
  return validos.length > 0 ? validos : null
}

/** El aviso del cajero: cuántos productos cambiaron y qué hacer. */
export function avisoDePreciosDistintos(distintos: PrecioDistinto[]): string {
  const n = distintos.length
  return n === 1
    ? 'Cambió el precio de 1 producto; revisá el total y volvé a cobrar.'
    : `Cambiaron los precios de ${n} productos; revisá el total y volvé a cobrar.`
}
