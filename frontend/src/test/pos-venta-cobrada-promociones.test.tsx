// La pantalla de «venta cobrada» del POS dice qué promociones se aplicaron y cuánto ahorraron (ADR-045). La
// respuesta de `POST /api/ventas` ya trae `promociones` (el servidor las calcula y las suma al descuento).
import { render, screen, waitFor } from '@testing-library/react'
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
const ITEM = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
// Una sucursal como la devuelve `GET /api/sucursales`; su depósito de venta tiene OTRO id a propósito.
const LOCATIONS = [{
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}]

function venta(promociones?: unknown[]) {
  return {
    id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 1kg', qty: 2, precio: 3000, subtotal: 6000, producto_id: 3, variante_id: null }],
    subtotal: 6000, descuento: promociones?.length ? 3000 : 0, total: promociones?.length ? 3000 : 6000,
    cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'efectivo', monto: 3000, referencia: '', recibido: 3000 }],
    factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '',
    created_at: '2026-08-23T10:05:00', ...(promociones ? { promociones } : {}),
  }
}

function montarRed(promociones?: unknown[]) {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/promociones/calcular')) return Promise.resolve(json({ aplicadas: [], ahorro: 0 }))
    if (u.endsWith('/api/ventas') && metodo === 'POST') return Promise.resolve(json(venta(promociones)))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
}

async function venderYCobrar(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '2*779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
  await waitFor(() => expect(screen.getByRole('button', { name: /^Cobrar/ })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: /^Cobrar/ }))
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
  await screen.findByText(/Venta POS-000009 cobrada/)
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Venta cobrada con promociones', () => {
  it('dice qué promoción se aplicó, cuántas veces y cuánto ahorró', async () => {
    montarRed([{ promocion_id: 7, nombre: '2x1 yerba', veces: 2, ahorro: 3000 }])
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await venderYCobrar(user)
    expect(screen.getByText(/2x1 yerba × 2: ahorro \$3\.000,00/)).toBeInTheDocument()
  })

  it('una promoción aplicada una sola vez no dice «× 1»', async () => {
    montarRed([{ promocion_id: 7, nombre: '2x1 yerba', veces: 1, ahorro: 3000 }])
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await venderYCobrar(user)
    expect(screen.getByText(/^2x1 yerba: ahorro \$3\.000,00/)).toBeInTheDocument()
  })

  it('sin promociones no se muestra ningún ahorro', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await venderYCobrar(user)
    expect(screen.queryByText(/ahorro/)).not.toBeInTheDocument()
  })
})
