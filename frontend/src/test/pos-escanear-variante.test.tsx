// Escanear el SKU de una variante ya identifica la variante: `GET /api/productos/escanear` la devuelve y el POS la
// agrega directo, sin volver a preguntar «Elegí la variante» (ADR-075). Escanear el código del producto, que no
// dice cuál variante es, sigue preguntando; y un producto sin variantes entra como siempre.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { lineasDelPedido, responderPrecios } from './precios-de-lista'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const REMERA = { id: 3, nombre: 'Remera', sku: 'REM', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const CAFE = { id: 4, nombre: 'Café', sku: 'CAF', barcode: '779000002', unidad: 'u', precio_venta: 1500, activo: 1 }
const VARIANTES = [
  { id: 31, producto_id: 3, sku: 'REM-M', nombre: 'Talle M', atributos: {}, activa: true },
  { id: 32, producto_id: 3, sku: 'REM-L', nombre: 'Talle L', atributos: {}, activa: true },
]
const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }
const LOCATIONS = [{
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}]

/** Lo que responde `escanear` según el código, como el motor: el SKU de una variante trae `variante`; el código de
 *  barras del producto, no. El precio de la lista (2.500) difiere del plano (3.000) para ver cuál se cobra. */
function montarRed({ precioBalanza = null }: { precioBalanza?: number | null } = {}) {
  const llamadas: { url: string; lineas?: ReturnType<typeof lineasDelPedido> }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    llamadas.push({ url: u, lineas: u.endsWith('/precios') ? lineasDelPedido(init) : undefined })
    if (u.includes('/api/promociones/calcular')) return Promise.resolve(json({ aplicadas: [], ahorro: 0 }))
    if (u === '/api/listas-precio/5/precios') return Promise.resolve(responderPrecios(init, () => 2500))
    if (u === '/api/listas-precio') return Promise.resolve(json([LISTA]))
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/3/variantes')) return Promise.resolve(json(VARIANTES))
    if (u.includes('/api/productos/4/variantes')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      const code = new URL(u, 'http://x').searchParams.get('code')
      const base = { cantidad: 1, precio_unitario: precioBalanza, de_balanza: precioBalanza !== null }
      if (code === 'REM-M') return Promise.resolve(json({ producto: REMERA, variante: VARIANTES[0], ...base }))
      if (code === '779000001') return Promise.resolve(json({ producto: REMERA, ...base }))
      if (code === '779000002') return Promise.resolve(json({ producto: CAFE, ...base }))
      return Promise.resolve(json({ detail: 'No hay ningún ítem con ese código.' }, 404))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto: string) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

async function montarYEsperarLista(opciones: { precioBalanza?: number | null } = {}) {
  const red = montarRed(opciones)
  const user = userEvent.setup()
  render(<MemoryRouter><Pos /></MemoryRouter>)
  await screen.findByText(/Turno #/)
  await waitFor(() => expect(red.llamadas.some((l) => l.url === '/api/listas-precio')).toBe(true))
  return { ...red, user }
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Escanear: el SKU de una variante la identifica', () => {
  it('agrega la línea con esa variante, sin abrir el diálogo, al precio de la lista', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user, 'REM-M')

    await screen.findByText(/Remera \(Talle M\)/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // La lista (2.500), no el precio plano (3.000): igual que al elegir la variante en el diálogo (ADR-074).
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
    expect(llamadas.find((l) => l.url === '/api/listas-precio/5/precios')!.lineas).toEqual([{ producto_id: 3, variante_id: 31, cantidad: 1 }])
    // La variante ya vino en el escaneo: no hace falta pedir las del producto.
    expect(llamadas.some((l) => l.url.includes('/api/productos/3/variantes'))).toBe(false)
  })

  it('respeta el multiplicador tipeado antes del código', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user, '3*REM-M')

    await screen.findByText(/Remera \(Talle M\)/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas.some((l) => l.lineas?.some((x) => x.cantidad === 3 && x.variante_id === 31))).toBe(true)
  })

  it('el precio de una etiqueta de balanza no se pisa con el de la lista', async () => {
    const { llamadas, user } = await montarYEsperarLista({ precioBalanza: 4200 })
    await escanear(user, 'REM-M')

    await screen.findByText(/Remera \(Talle M\)/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect((await screen.findAllByText(/4\.200,00/)).length).toBeGreaterThan(0)
    // Se consulta igual (el peso suma al producto), pero la lista no pisa el precio de la etiqueta.
    await waitFor(() => expect(llamadas.some((l) => l.url.endsWith('/precios'))).toBe(true))
    expect(screen.queryByText(/2\.500,00/)).not.toBeInTheDocument()
  })
})

describe('Escanear: lo que no identifica la variante sigue como siempre', () => {
  it('el código del producto con variantes sigue preguntando cuál', async () => {
    const { user } = await montarYEsperarLista()
    await escanear(user, '779000001')

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Talle M' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Talle L' })).toBeInTheDocument()
    expect(screen.queryByText(/Remera \(Talle/)).not.toBeInTheDocument()
  })

  it('un producto sin variantes entra directo al precio de la lista', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user, '779000002')

    await screen.findByText('Café')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(llamadas.find((l) => l.url === '/api/listas-precio/5/precios')!.lineas).toEqual([{ producto_id: 4, variante_id: null, cantidad: 1 }])
  })
})
