// El cliente de la venta sale del router del motor (`/api/clientes`, ADR-029): el listado trae
// también a los inactivos (la pantalla de Clientes los marca) y el POS sólo ofrece los activos.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const LOCATIONS = [
  { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: true },
]
const CLIENTES = [
  { id: 1, name: 'Ana Gomez', address: '', cuit_dni: '27-12345678-9', email: '', phone: '', iva_condition: '', auto_facturar: 0, activo: 1 },
  { id: 2, name: 'Beto Dado de Baja', address: '', cuit_dni: '', email: '', phone: '', iva_condition: '', auto_facturar: 0, activo: 0 },
]

let llamadas: string[]

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json(LOCATIONS))
    if (u === '/api/clientes') return Promise.resolve(json(CLIENTES))
    return Promise.resolve(json([]))
  }))
})

describe('Elegir el cliente de la venta', () => {
  it('lo pide al router del motor y ofrece sólo a los activos', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    fireEvent.keyDown(window, { key: 'F7' })
    const dialogo = await screen.findByRole('dialog')
    expect(await within(dialogo).findByText('Ana Gomez')).toBeInTheDocument()
    // El CUIT del cliente (`cuit_dni` en el motor) se muestra junto al nombre.
    expect(within(dialogo).getByText('27-12345678-9')).toBeInTheDocument()
    expect(within(dialogo).queryByText('Beto Dado de Baja')).not.toBeInTheDocument()
    expect(llamadas).toContain('/api/clientes')
    expect(llamadas.some((u) => u.includes('/customers'))).toBe(false)

    await user.click(within(dialogo).getByText('Ana Gomez'))
    await waitFor(() => expect(screen.getByRole('button', { name: /Ana Gomez/ })).toBeInTheDocument())
  })

  it('filtra por nombre', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    fireEvent.keyDown(window, { key: 'F7' })
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByText('Ana Gomez')
    await user.type(within(dialogo).getByRole('textbox'), 'zzz')
    expect(within(dialogo).queryByText('Ana Gomez')).not.toBeInTheDocument()
  })
})
