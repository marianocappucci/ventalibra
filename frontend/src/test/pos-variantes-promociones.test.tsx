// Una variante recibe lo mismo que su producto (ADR-074): el precio de la lista predeterminada
// (cantidad y vigencia, ADR-042) y las promociones «llevá N pagá M» y combos (ADR-043).
// Antes la ruta de variantes (`ElegirVariante`) agregaba la línea al precio plano y sólo cuando se
// cambiaba la cantidad el precio saltaba al de la lista: el mismo producto cobraba distinto según
// cómo hubiera entrado.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
const VARIANTES = [
  { id: 31, producto_id: 3, sku: 'REM-M', nombre: 'Talle M', atributos: {}, activa: true },
  { id: 32, producto_id: 3, sku: 'REM-L', nombre: 'Talle L', atributos: {}, activa: true },
]
const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }
const LOCATIONS = [{
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}]
const DOS_POR_UNO = { aplicadas: [{ promocion_id: 7, nombre: '2x1 remeras', veces: 1, ahorro: 2500 }], ahorro: 2500 }

function montarRed(
  { listas = [LISTA], fallaPrecio = false, precioBalanza = null }:
    { listas?: unknown[]; fallaPrecio?: boolean; precioBalanza?: number | null } = {},
) {
  const llamadas: { url: string; body?: unknown; lineas?: ReturnType<typeof lineasDelPedido> }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    llamadas.push({
      url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined,
      lineas: u.endsWith('/precios') ? lineasDelPedido(init) : undefined,
    })
    if (u.includes('/api/promociones/calcular')) {
      const items = (JSON.parse(String(init?.body)).items ?? []) as { qty: number }[]
      const unidades = items.reduce((a, l) => a + l.qty, 0)
      return Promise.resolve(json(unidades >= 2 ? DOS_POR_UNO : { aplicadas: [], ahorro: 0 }))
    }
    if (u === '/api/listas-precio/5/precios') {
      if (fallaPrecio) return Promise.resolve(json({ detail: 'boom' }, 500))
      return Promise.resolve(responderPrecios(init, (cantidad) => (cantidad >= 3 ? 2000 : 2500)))
    }
    if (u === '/api/listas-precio') return Promise.resolve(json(listas))
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/3/variantes')) return Promise.resolve(json(VARIANTES))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: REMERA, cantidad: 1, precio_unitario: precioBalanza, de_balanza: precioBalanza !== null }))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto = '779000001') {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

async function elegirVariante(user: ReturnType<typeof userEvent.setup>, nombre: string) {
  const dialogo = await screen.findByRole('dialog')
  await user.click(within(dialogo).getByRole('button', { name: nombre }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
}

async function montarYEsperarLista() {
  const red = montarRed()
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

describe('Variantes: el precio de la lista (ADR-042)', () => {
  it('una variante entra al precio de la lista, no al plano, y la consulta lleva la variante', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user)
    await elegirVariante(user, 'Talle M')

    await screen.findByText(/Remera \(Talle M\)/)
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
    expect(llamadas.find((l) => l.url === '/api/listas-precio/5/precios')!.lineas).toEqual([{ producto_id: 3, variante_id: 31, cantidad: 1 }])
  })

  it('con un multiplicador, la variante consulta el quiebre de esa cantidad', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user, '3*779000001')
    await elegirVariante(user, 'Talle L')

    // 3 x 2.000 = 6.000 (el quiebre de 3 unidades), no 3 x 3.000 ni 3 x 2.500.
    await waitFor(() => expect(screen.getAllByText(/6\.000,00/).length).toBeGreaterThan(0))
    expect(llamadas.some((l) => l.lineas?.some((x) => x.cantidad === 3 && x.variante_id === 32))).toBe(true)
  })

  it('al cambiar la cantidad de una línea con variante, la consulta conserva la variante', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user)
    await elegirVariante(user, 'Talle M')
    await screen.findAllByText(/2\.500,00/)

    fireEvent.keyDown(window, { key: 'F6' })
    const dialogo = await screen.findByRole('dialog')
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, '3')
    await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }))

    await waitFor(() => expect(screen.getAllByText(/6\.000,00/).length).toBeGreaterThan(0))
    expect(llamadas.some((l) => l.lineas?.some((x) => x.cantidad === 3 && x.variante_id === 31))).toBe(true)
  })

  it('sin lista predeterminada la variante se vende al precio plano y no consulta precios', async () => {
    const { llamadas } = montarRed({ listas: [] })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((l) => l.url === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await elegirVariante(user, 'Talle M')

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((l) => l.url.endsWith('/precios'))).toBe(false)
  })

  it('un precio de etiqueta de balanza no se pierde ni se pisa al elegir la variante', async () => {
    const { llamadas } = montarRed({ precioBalanza: 4200 })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((l) => l.url === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await elegirVariante(user, 'Talle M')

    expect((await screen.findAllByText(/4\.200,00/)).length).toBeGreaterThan(0)
    // Se consulta igual (el peso suma al producto), pero la lista no pisa el precio de la etiqueta.
    await waitFor(() => expect(llamadas.some((l) => l.url.endsWith('/precios'))).toBe(true))
    expect(screen.queryByText(/2\.500,00/)).not.toBeInTheDocument()
  })

  it('si la consulta de precio falla, la variante se vende al precio plano sin bloquear', async () => {
    const { llamadas } = montarRed({ fallaPrecio: true })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((l) => l.url === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await elegirVariante(user, 'Talle M')

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((l) => l.url.endsWith('/precios'))).toBe(true)
  })
})

describe('Variantes: las promociones «llevá N pagá M» y combos (ADR-043)', () => {
  it('dos variantes del mismo producto cuentan juntas: el POS manda el producto de cada línea y muestra el ahorro', async () => {
    const { llamadas, user } = await montarYEsperarLista()
    await escanear(user)
    await elegirVariante(user, 'Talle M')
    await screen.findByText(/Remera \(Talle M\)/)
    await escanear(user)
    await elegirVariante(user, 'Talle L')
    await screen.findByText(/Remera \(Talle L\)/)

    expect(await screen.findByText('2x1 remeras')).toBeInTheDocument()
    const consulta = llamadas.filter((l) => l.url.includes('/api/promociones/calcular')).at(-1)!
    expect(consulta.body).toMatchObject({
      items: [{ producto_id: 3, qty: 1, precio: 2500 }, { producto_id: 3, qty: 1, precio: 2500 }],
    })
    // 2 x 2.500 − 2.500 de la promoción.
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$2.500,00')
  })
})
