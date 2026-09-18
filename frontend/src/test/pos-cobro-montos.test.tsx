// Los montos del cobro se leen con la misma regla que el efectivo del turno
// (`parseMonto` en `Pos.tsx`): «3.000» son tres mil pesos, «3000,00» lleva coma
// decimal, y un texto que no se puede leer se marca en el campo y frena el
// cobro. Antes era `Number(x) || 0`: «3.000» valía 3 y el cajero quedaba en
// «Falta cubrir» sin saber por qué.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana',
  apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null,
  estado: 'abierto', notas: '',
}

const ITEM = {
  id: 3, name: 'Yerba 1kg', sku: 'YER1', barcode: '779000001',
  unit_code: 'u', default_sale_price: '3000.00', active: true,
}

const LOCATIONS = [
  { id: 1, name: 'Salón', branch_id: null, location_type: 'warehouse', active: true, is_default: true },
]

const VENTA = {
  id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
  items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
  subtotal: 3000, descuento: 0, total: 3000,
  cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 3000, referencia: '', recibido: 5000 }],
  factura_id: null, factura_display: null, remito_id: null,
  mp_order_id: '', mp_payment_id: '', created_at: '2026-08-23T10:05:00',
}

type Llamada = { metodo: string; url: string; body: unknown }

function montarRed() {
  const llamadas: Llamada[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.endsWith('/api/ventas') && metodo === 'POST') return Promise.resolve(json(VENTA))
    if (u.match(/\/api\/ventas\/9$/)) return Promise.resolve(json(VENTA))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/catalog/items/scan')) {
      return Promise.resolve(json({ item: ITEM, quantity: '1', unit_price: null, from_scale: false }))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas }
}

async function abrirCobro(user: ReturnType<typeof userEvent.setup>) {
  render(<MemoryRouter><Pos /></MemoryRouter>)
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
  return screen.findByRole('dialog')
}

function postDeVenta(llamadas: Llamada[]) {
  return llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Montos del cobro', () => {
  it.each([
    ['3.000', 3000],
    ['3000,00', 3000],
    ['3.000,00', 3000],
  ])('«%s» cubre el total y viaja como %d', async (tipeado, esperado) => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    const dialogo = await abrirCobro(user)

    const monto = within(dialogo).getByLabelText('Monto')
    await user.clear(monto)
    await user.type(monto, tipeado)

    const cobrar = within(dialogo).getByRole('button', { name: /^Cobrar/ })
    await waitFor(() => expect(cobrar).toBeEnabled())
    await user.click(cobrar)

    await waitFor(() => expect(postDeVenta(llamadas)).toBeDefined())
    expect(postDeVenta(llamadas)!.body).toMatchObject({ pagos: [{ medio: 'efectivo', monto: esperado }] })
  })

  it('con «a3000» marca el campo y no deja cobrar', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    const dialogo = await abrirCobro(user)

    const monto = within(dialogo).getByLabelText('Monto')
    await user.clear(monto)
    await user.type(monto, 'a3000')

    expect(await within(dialogo).findByText(/Monto inválido/)).toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: /^Cobrar/ })).toBeDisabled()
    expect(postDeVenta(llamadas)).toBeUndefined()
  })

  it('«Recibe» 5.000 manda recibido 5000', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    const dialogo = await abrirCobro(user)

    await user.type(within(dialogo).getByLabelText('Recibe'), '5.000')
    const cobrar = within(dialogo).getByRole('button', { name: /^Cobrar/ })
    await waitFor(() => expect(cobrar).toBeEnabled())
    await user.click(cobrar)

    await waitFor(() => expect(postDeVenta(llamadas)).toBeDefined())
    expect(postDeVenta(llamadas)!.body).toMatchObject({ pagos: [{ medio: 'efectivo', monto: 3000, recibido: 5000 }] })
  })

  it('un «Recibe» ilegible no deja cobrar', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    const dialogo = await abrirCobro(user)

    await user.type(within(dialogo).getByLabelText('Recibe'), '5x')
    expect(await within(dialogo).findByText(/Monto inválido/)).toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: /^Cobrar/ })).toBeDisabled()
    expect(postDeVenta(llamadas)).toBeUndefined()
  })
})
