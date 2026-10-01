// Los avisos de vencimiento del POS (vencimientos y lotes, ADR-053; `libracommerce` v0.30.0).
//
// Dos usos, los dos OPT-IN por lo que conteste el backend y ninguno puede frenar ni demorar una venta:
//
// 1. **Antes de cobrar** (`consultarAvisosDeSalida`): `POST /api/ventas/plan-salida` (lectura pura: de qué lote saldría cada línea del
//    carrito) y, si hay mercadería de un lote vencido o por vencer, el POS pregunta «¿Vender igual?». Si la consulta falla (404/405 de
//    un backend sin la opción, 403, 5xx, la red) o tarda más de `PLAN_SALIDA_TIMEOUT_MS`, no hay avisos y se cobra como siempre: esta
//    función NUNCA rechaza.
// 2. **Después de cobrar** (`Venta.avisos`): `POST /api/ventas` y `GET /api/ventas/{id}` traen `avisos` sólo si hay alguno; la
//    pantalla de la venta cobrada los muestra sin tocar el ticket ni el comprobante.
//
// Un producto vencido SE VENDE (decisión de producto 1, ADR-018 del motor): el aviso informa, no bloquea.
import { api } from '../api'
import { fecha } from './fechas'

/** Cuánto se espera al plan de salida antes de cobrar igual. El cajero no espera más que esto por una consulta opcional. */
export const PLAN_SALIDA_TIMEOUT_MS = 1500

export type AvisoDeVencimiento = {
  tipo: 'lote_vencido' | 'por_vencer' | 'faltante_sin_lote' | string
  producto_id: number
  nombre: string
  lote: string | null
  vence: string | null
  dias_para_vencer: number | null
  cantidad: number
  deposito_id?: number
  variante_id?: number | null
}

/** Los dos tipos por los que el POS pregunta antes de cobrar (`faltante_sin_lote` sólo se informa después). */
const TIPOS_QUE_PREGUNTAN = new Set(['lote_vencido', 'por_vencer'])

type Linea = { producto_id: number | null; qty: string; variante_id: number | null }

function esAviso(x: unknown): x is AvisoDeVencimiento {
  if (!x || typeof x !== 'object') return false
  const a = x as Record<string, unknown>
  return typeof a.tipo === 'string' && typeof a.nombre === 'string'
}

/** Los avisos que hay que confirmar antes de cobrar (`lote_vencido` y `por_vencer`) para estas líneas y este depósito, o `[]`.
 *  🔴 Nunca rechaza y nunca tarda más de `timeoutMs`: cualquier falla, una respuesta que no es la esperada o la demora cuentan como
 *  «sin avisos». Una respuesta tardía se descarta (no puede abrir un diálogo con la venta ya en camino). */
export async function consultarAvisosDeSalida(
  lineas: Linea[], depositoId: number | null, timeoutMs: number = PLAN_SALIDA_TIMEOUT_MS,
): Promise<AvisoDeVencimiento[]> {
  const items = lineas
    .map((l) => ({ producto_id: l.producto_id, qty: Number(l.qty), variante_id: l.variante_id }))
    .filter((l) => l.producto_id !== null && Number.isFinite(l.qty) && l.qty > 0)
  if (items.length === 0) return []
  let temporizador: ReturnType<typeof setTimeout> | undefined
  const espera = new Promise<null>((resolver) => { temporizador = setTimeout(() => resolver(null), timeoutMs) })
  try {
    const respuesta = await Promise.race([
      api.post<{ avisos?: unknown }>('/api/ventas/plan-salida', { items, deposito_id: depositoId }).catch(() => null),
      espera,
    ])
    const avisos = respuesta && typeof respuesta === 'object' ? (respuesta as { avisos?: unknown }).avisos : null
    if (!Array.isArray(avisos)) return []
    return avisos.filter(esAviso).filter((a) => TIPOS_QUE_PREGUNTAN.has(a.tipo))
  } catch {
    return []
  } finally {
    clearTimeout(temporizador)
  }
}

function dias(n: number): string {
  return `${n} ${n === 1 ? 'día' : 'días'}`
}

/** «vencido hace 3 días», «vence hoy», «vence mañana», «vence en 5 días». */
export function cuandoVence(d: number | null): string {
  if (d === null || d === undefined) return ''
  if (d < 0) return `vencido hace ${dias(-d)}`
  if (d === 0) return 'vence hoy'
  if (d === 1) return 'vence mañana'
  return `vence en ${dias(d)}`
}

function cantidadTexto(n: number): string {
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 3 }).format(n)
}

/** Una línea por aviso: «Yerba 500g, lote L1, vence 12-10-2026 (vencido hace 3 días)» (la fecha en dd-mm-aaaa). */
export function describirAviso(a: AvisoDeVencimiento): string {
  if (a.tipo === 'faltante_sin_lote') {
    return `${a.nombre}: ${cantidadTexto(a.cantidad)} salieron sin lote que las respaldara (no había stock con lote).`
  }
  const lote = a.lote ? `lote ${a.lote}` : 'lote sin código'
  const cuando = cuandoVence(a.dias_para_vencer)
  return `${a.nombre}, ${lote}, vence ${fecha(a.vence)}${cuando ? ` (${cuando})` : ''}`
}

/** «Hay 2 productos con lote vencido o por vencer» (singular con uno; «vencido» o «por vencer» si son todos de un tipo). */
export function tituloDeAvisos(avisos: AvisoDeVencimiento[]): string {
  const productos = new Set(avisos.map((a) => a.producto_id)).size
  const vencidos = avisos.some((a) => a.tipo === 'lote_vencido')
  const porVencer = avisos.some((a) => a.tipo === 'por_vencer')
  const que = vencidos && porVencer ? 'lote vencido o por vencer' : vencidos ? 'lote vencido' : 'lote por vencer'
  return `Hay ${productos} ${productos === 1 ? 'producto' : 'productos'} con ${que}`
}
