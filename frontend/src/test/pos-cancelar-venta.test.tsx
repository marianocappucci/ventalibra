// Cancelar la venta (Esc o el botón) pide confirmación: con muchos ítems cargados, un Esc sin querer no puede tirar todo.
import { render, screen, waitFor } from '@testing-library/react'
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

describe('Cancelar la venta pide confirmación', () => {
  it('Esc abre la confirmación y NO vacía el carrito hasta confirmar', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)

    await user.keyboard('{Escape}')
    expect(await screen.findByText('¿Cancelar la venta?')).toBeInTheDocument()
    expect(screen.getByText(/Vas a descartar 1 producto por \$/)).toBeInTheDocument()
    expect(screen.getByText('Yerba 1kg')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Sí, cancelar venta' }))
    await waitFor(() => expect(screen.queryByText('Yerba 1kg')).not.toBeInTheDocument())
  })

  it('arrepentirse (Cancelar) deja el carrito como estaba', async () => {
    const user = userEvent.setup()
    montar()
    await cargarUnItem(user)

    await user.click(screen.getByRole('button', { name: /Cancelar venta/ }))
    await screen.findByText('¿Cancelar la venta?')
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByText('¿Cancelar la venta?')).not.toBeInTheDocument())
    expect(screen.getByText('Yerba 1kg')).toBeInTheDocument()
  })

  it('con el carrito vacío, Esc no pregunta nada', async () => {
    const user = userEvent.setup()
    montar()
    await screen.findByPlaceholderText(/scane|Escane/i)
    await user.keyboard('{Escape}')
    expect(screen.queryByText('¿Cancelar la venta?')).not.toBeInTheDocument()
  })
})
