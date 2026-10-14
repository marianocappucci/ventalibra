// Una venta devuelta EN PARTE sigue ofreciendo «Devolver» (libra-ui 0.148.0, ADR-060 del kit; ADR-084 de este repo).
//
// Con el kit de verdad y la app entera. Hasta 0.147.0 el detalle sólo dibujaba las acciones con la venta en `cobrada` o `parcial`: tras la
// primera devolución parcial (`devuelta_parcial`) el botón desaparecía, y el servidor no deja anular esa venta («devolvé el resto de las
// líneas»), así que no tenía salida desde la pantalla. El diálogo ya descuenta lo devuelto (`/ventas/{id}/devuelto`).
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const venta = (estado: string) => ({
  id: 42, numero: 'POS-000042', fecha: '2026-10-14', estado,
  items: [{ id: 501, nombre: 'Yerba 1kg', qty: 5, precio: 1500, subtotal: 7500, producto_id: 3 }],
  subtotal: 7500, descuento: 0, total: 7500, cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 7500, referencia: '' }],
  factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '',
})

function conVenta(estado: string) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const path = String(url).split('?')[0]
    if (path.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '7', username: 'u-encargado', name: 'encargado', role: 'encargado', active: true, empresa_nombre: 'Prueba',
        modulos: ['multisucursal'], capacidades: CAPACIDADES_POR_ROL.encargado,
      }))
    }
    if (path === '/api/ventas/42') return Promise.resolve(json(venta(estado)))
    if (path === '/api/ventas/42/devuelto') return Promise.resolve(json({ por_clave: [{ sale_item_id: 501, item_id: 3, variant_id: null, cantidad: 2 }] }))
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={['/ventas/42']}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

const enLaPantalla = () => within(screen.getByRole('main'))

beforeEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear() })

describe('El detalle de una venta ya devuelta en parte', () => {
  it('ofrece «Devolver» para seguir devolviendo, y no ofrece anularla', async () => {
    conVenta('devuelta_parcial')
    await screen.findByText(/POS-000042/)
    expect(await enLaPantalla().findByRole('button', { name: /Devolver/ })).toBeInTheDocument()
    expect(enLaPantalla().queryByRole('button', { name: /Anular venta/ })).toBeNull()
  })

  it('una venta cobrada ofrece las dos (control)', async () => {
    conVenta('cobrada')
    await screen.findByText(/POS-000042/)
    expect(await enLaPantalla().findByRole('button', { name: /Devolver/ })).toBeInTheDocument()
    expect(enLaPantalla().getByRole('button', { name: /Anular venta/ })).toBeInTheDocument()
  })

  it('una venta devuelta por completo no ofrece devolver', async () => {
    conVenta('devuelta')
    await screen.findByText(/POS-000042/)
    expect(enLaPantalla().queryByRole('button', { name: /Devolver/ })).toBeNull()
  })
})
