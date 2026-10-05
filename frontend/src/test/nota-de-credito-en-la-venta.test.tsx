// La nota de crédito en el detalle de la venta (libra-ui 0.113.0, libracore v1.129.0): una venta cuya factura tiene CAE
// pide la nota antes de anularse, y la emite quien tiene `facturas.nota_credito` (admin). El cajero, que sí puede anular
// (decisión del 2026-09-15), ve el aviso pero no el botón.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { VentaDetalle } from '../pages/VentaDetalle'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

const sesion = vi.hoisted(() => ({ rol: 'admin' as 'admin' | 'staff' | 'cajero' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol, capacidades: (CAPACIDADES_POR_ROL as Record<string, string[]>)[sesion.rol] },
    loading: false,
  }),
}))

const CON_CAE = {
  id: 42, numero: 'POS-000042', fecha: '2026-09-15', estado: 'cobrada',
  items: [{ id: 501, nombre: 'Yerba 1kg', qty: 5, precio: 1500, subtotal: 7500, producto_id: 3 }],
  subtotal: 7500, descuento: 0, total: 7500, cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 7500, referencia: '' }],
  factura_id: 55, factura_display: 'FACTURA C 0001-00000055', factura_cae: '75123456789012',
  remito_id: null, mp_order_id: '', mp_payment_id: '',
}

let pedidos: string[] = []

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function montarRed(venta: unknown = CON_CAE) {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidos.push(`${init?.method ?? 'GET'} ${u}`)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.match(/\/api\/ventas\/42$/)) return Promise.resolve(json(venta))
    if (u.includes('/ventas/42/devuelto')) return Promise.resolve(json({ por_clave: [], deposito_id: null }))
    if (u.includes('/nota-credito')) return Promise.resolve(json({ id: 90, tipo: 13 }))
    return Promise.resolve(json([]))
  }))
}

function montar() {
  return render(
    <MemoryRouter initialEntries={['/ventas/42']}>
      <Routes><Route path="/ventas/:id" element={<VentaDetalle />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Nota de crédito en el detalle de la venta', () => {
  it('el admin ve el aviso y emite la nota por la ruta del motor, con confirmación', async () => {
    sesion.rol = 'admin'
    montarRed()
    montar()
    const user = userEvent.setup()

    expect((await screen.findByRole('note')).textContent).toMatch(/75123456789012/)
    await user.click(screen.getByRole('button', { name: /Emitir nota de crédito/ }))
    // libra-ui 0.115.0: el diálogo de la nota es un `Dialog` (con saldo pide el importe), ya no un `alertdialog` de confirmación.
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Emitir nota' }))

    await waitFor(() => expect(pedidos).toContain('POST /api/facturas/55/nota-credito'))
    expect((await screen.findByRole('note')).textContent).toMatch(/ya podés anular la venta/)
  })

  it('el cajero puede anular pero no emitir la nota: ve el aviso que le dice a quién pedírsela', async () => {
    sesion.rol = 'cajero'
    montarRed()
    montar()

    expect((await screen.findByRole('note')).textContent).toMatch(/administrador/)
    expect(screen.queryByRole('button', { name: /Emitir nota de crédito/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Anular venta/ })).toBeTruthy()
  })

  it('una factura sin CAE no cambia nada: ni aviso ni botón', async () => {
    sesion.rol = 'admin'
    montarRed({ ...CON_CAE, factura_cae: null })
    montar()

    await screen.findByText('FACTURA C 0001-00000055')
    expect(screen.queryByRole('note')).toBeNull()
    expect(screen.queryByRole('button', { name: /Emitir nota de crédito/ })).toBeNull()
  })
})
