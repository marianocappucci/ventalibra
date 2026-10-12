// El servidor valida el precio de cada línea al registrar la venta (ADR-079; `libracommerce` ADR-049). Si el POS mandó un precio
// que ya no es el vigente (la lista cambió con la pantalla abierta, o el carrito se armó contra otra), `POST /api/ventas` contesta
// 409 y NO escribe nada: este módulo reconoce esa respuesta y arma el aviso al cajero. El `detail` es un objeto
// (`{mensaje, codigo, precios}`) y el `ApiError` del kit lo conserva en `detailData`.
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
