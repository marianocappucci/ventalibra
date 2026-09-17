// La cantidad de una línea del carrito no puede quedar en 0 en silencio: con
// un texto inválido en «Cantidad» (F6), `itemsPayload` la mandaba como
// `qty: 0` (`Number(x) || 0`). Mismo defecto que el «Efectivo contado» del
// cierre de turno (ver pos-cierre-turno.test.tsx). Ver `parseCantidad` en
// `Pos.tsx`.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

function montarRed() {
  const llamadas: string[] = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
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

async function escanear(user: ReturnType<typeof userEvent.setup>, texto = '779000001') {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

async function abrirCantidad() {
  fireEvent.keyDown(window, { key: 'F6' })
  const dialogo = await screen.findByRole('dialog')
  return dialogo
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Cantidad de una línea del carrito', () => {
  it('con «a3» muestra el error y no deja aceptar', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    const dialogo = await abrirCantidad()
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, 'a3')

    expect(await within(dialogo).findByText(/Cantidad inválida/)).toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: 'Aceptar' })).toBeDisabled()
  })

  it.each(['0', '-2', '1.5.0'])('«%s» también es inválida', async (tipeado) => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    const dialogo = await abrirCantidad()
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, tipeado)
    expect(within(dialogo).getByRole('button', { name: 'Aceptar' })).toBeDisabled()
  })

  it('con «2,5» acepta y el total pasa a $7.500,00', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    const dialogo = await abrirCantidad()
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, '2,5')
    await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getAllByText(/7\.500,00/).length).toBeGreaterThan(0)
  })

  it('«0 * código» no agrega una línea con cantidad 0', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '0*779000001')

    expect(await screen.findByText('La cantidad tiene que ser mayor a 0.')).toBeInTheDocument()
    expect(llamadas.some((u) => u.includes('/catalog/items/scan'))).toBe(false)
    expect(screen.queryByText(/Yerba 1kg/)).not.toBeInTheDocument()
  })
})
