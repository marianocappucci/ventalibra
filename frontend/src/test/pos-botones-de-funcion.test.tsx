// Los botones de función del POS (F3 dividir pago abre el cobro ya dividido; F2 lo abre con un solo medio).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const ITEM = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const SUCURSAL = {
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}

function montar() {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

async function cargarUnItem(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText('Yerba 1kg')
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Botones de función del POS', () => {
  it('Cobrar (F2) abre el cobro con UN solo medio', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))
    await screen.findAllByLabelText('Monto')
    expect(screen.getAllByLabelText('Monto')).toHaveLength(1)
  })

  it('Dividir pago (F3) abre el cobro ya dividido en dos medios que suman el total', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)
    await user.click(screen.getByRole('button', { name: /Dividir pago/ }))
    await screen.findAllByLabelText('Monto')
    const montos = screen.getAllByLabelText('Monto') as HTMLInputElement[]
    expect(montos).toHaveLength(2)
    expect(montos.map((m) => m.value)).toEqual(['1500.00', '1500.00'])
  })

  it('la tecla F3 hace lo mismo que el botón', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)
    await user.keyboard('{F3}')
    await screen.findAllByLabelText('Monto')
    expect(screen.getAllByLabelText('Monto')).toHaveLength(2)
  })

  it('Factura (F9) e Imprimir (F8) arrancan apagados: todavía no hay una venta anterior', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)
    expect(screen.getByRole('button', { name: /Factura/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Imprimir/ })).toBeDisabled()
  })
})
