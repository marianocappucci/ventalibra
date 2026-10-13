// El precio de venta por sucursal (libracommerce ADR-058, v0.59.0; ADR-083 de este repo). Lo que le toca al POS:
//
// 1. Mandar `sucursal_id` en la cotización (`POST /api/listas-precio/{id}/precios`) Y en el cuerpo de `POST /api/ventas` (cobro normal
//    y cobro con QR). Un POS que la manda le declara al servidor que sabe de precios por sucursal; sin ella el servidor valida contra
//    el precio general, como hasta v0.58 (la transición, ver `exigir_precio_de_sucursal` en ADR-083).
// 2. La sucursal es la del turno (o la elegida sin turno) y coincide con la del depósito de la venta: el servidor no le cree al pedido a
//    qué sucursal pertenece el depósito, así que si no coincidieran validaría contra la del depósito.
// 3. Tolerar el `sucursal_id` opcional del `detail` del 409 `precios_distintos`: el carrito toma el `esperado` igual que siempre.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api'
import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { preciosDistintosDe, sucursalDeLosPrecios } from '../lib/precios-distintos'
import { responderPrecios } from './precios-de-lista'

const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'mercadopago', label: 'Mercado Pago' },
]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const YERBA = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }
const SALON = { id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 }
const NORTE = { id: 2, nombre: 'Norte', codigo: null, direccion: null, activa: true, es_default: false, deposito_predeterminado_id: 22, depositos: 1 }

function turnoEn(sucursal?: { id: number; nombre: string }) {
  return {
    id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
    monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
    ...(sucursal ? { sucursal, caja: { id: 1, nombre: 'Caja 1' } } : {}),
  }
}

function venta(total: number) {
  return {
    id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: total, subtotal: total, producto_id: 3, variante_id: null }],
    subtotal: total, descuento: 0, total, cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'efectivo', monto: total, referencia: '', recibido: total }],
    factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '',
    created_at: '2026-08-23T10:05:00',
  }
}

type Cuerpo = Record<string, unknown>

/** El POS contra un motor 0.59.0 de mentira: la lista predeterminada cotiza `precio` y `alVender` contesta cada `POST /api/ventas`. */
function montarRed({ turno, sucursales = [SALON], precio = 2500, alVender = () => json(venta(2500)), mpDisponible = false }: {
  turno: ReturnType<typeof turnoEn>
  sucursales?: unknown[]
  precio?: number
  alVender?: (body: Cuerpo) => Response
  mpDisponible?: boolean
}) {
  const cotizaciones: Cuerpo[] = []
  const ventas: Cuerpo[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: mpDisponible, auto_facturar: false }))
    if (u === '/api/listas-precio/5/precios') {
      cotizaciones.push(JSON.parse(String(init?.body)))
      return Promise.resolve(responderPrecios(init, () => precio))
    }
    if (u === '/api/listas-precio') return Promise.resolve(json([LISTA]))
    if (u.endsWith('/api/ventas') && metodo === 'POST') {
      const body = JSON.parse(String(init?.body))
      ventas.push(body)
      return Promise.resolve(alVender(body))
    }
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(sucursales))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: YERBA, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
  return { cotizaciones, ventas }
}

async function agregarYerba(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
}

async function cobrarEnEfectivo(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
  await user.click(await screen.findByRole('button', { name: 'Cobrar' }))
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('El POS manda la sucursal (ADR-058 del motor)', () => {
  it('la cotización de la lista lleva el `sucursal_id` de la sucursal', async () => {
    const red = montarRed({ turno: turnoEn() })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await agregarYerba(user)

    await waitFor(() => expect(red.cotizaciones.length).toBeGreaterThan(0))
    for (const pedido of red.cotizaciones) expect(pedido).toMatchObject({ sucursal_id: 1 })
  })

  it('la venta lleva el mismo `sucursal_id` que la cotización, junto al depósito de esa sucursal', async () => {
    const red = montarRed({ turno: turnoEn() })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await agregarYerba(user)

    await cobrarEnEfectivo(user)

    await waitFor(() => expect(red.ventas).toHaveLength(1))
    expect(red.ventas[0]).toMatchObject({ sucursal_id: 1, deposito_id: 11 })
    expect(red.cotizaciones.at(-1)).toMatchObject({ sucursal_id: red.ventas[0].sucursal_id })
  })

  it('con el turno en otra sucursal, cotiza y vende por ESA sucursal y por su depósito', async () => {
    const red = montarRed({ turno: turnoEn({ id: 2, nombre: 'Norte' }), sucursales: [SALON, NORTE] })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await agregarYerba(user)

    await cobrarEnEfectivo(user)

    await waitFor(() => expect(red.ventas).toHaveLength(1))
    expect(red.ventas[0]).toMatchObject({ sucursal_id: 2, deposito_id: 22 })
    expect(red.cotizaciones.at(-1)).toMatchObject({ sucursal_id: 2 })
  })

  it('el cobro con QR también declara la sucursal', async () => {
    const red = montarRed({
      turno: turnoEn(), mpDisponible: true,
      alVender: () => json({ detail: { mensaje: 'x', codigo: 'precios_distintos', precios: [{ indice: 0, producto_id: 3, variante_id: null, enviado: 3000, esperado: 2500 }], sucursal_id: 1 } }, 409),
    })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await agregarYerba(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Mercado Pago' }))

    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    await waitFor(() => expect(red.ventas).toHaveLength(1))
    expect(red.ventas[0]).toMatchObject({ sucursal_id: 1, deposito_id: 11, pagos: [{ medio: 'mercadopago', cobrar_con_qr: true }] })
  })
})

describe('El 409 `precios_distintos` con `sucursal_id` en el detail', () => {
  it('el carrito toma el precio esperado y avisa, igual que sin sucursal', async () => {
    const red = montarRed({
      turno: turnoEn(), precio: 3000,
      alVender: () => json({
        detail: {
          mensaje: 'Cambió el precio de 1 producto: revisá el total y volvé a cobrar.', codigo: 'precios_distintos', sucursal_id: 1,
          precios: [{ indice: 0, producto_id: 3, variante_id: null, enviado: 3000, esperado: 2500 }],
        },
      }, 409),
    })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await agregarYerba(user)

    await cobrarEnEfectivo(user)

    expect(await screen.findByText('Cambió el precio de 1 producto; revisá el total y volvé a cobrar.')).toBeInTheDocument()
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(red.ventas).toHaveLength(1)
  })
})

describe('`sucursalDeLosPrecios` y `preciosDistintosDe` con el campo opcional', () => {
  const precio = { indice: 0, producto_id: 3, variante_id: null, enviado: 3000, esperado: 2500 }

  it('lee la sucursal cuando el servidor validó por sucursal', () => {
    const err = new ApiError(409, 'x', { codigo: 'precios_distintos', precios: [precio], sucursal_id: 7 })
    expect(sucursalDeLosPrecios(err)).toBe(7)
    expect(preciosDistintosDe(err)).toEqual([precio])
  })

  it.each([
    ['falta (cuerpo de siempre)', { codigo: 'precios_distintos', precios: [precio] }],
    ['null', { codigo: 'precios_distintos', precios: [precio], sucursal_id: null }],
    ['no es un entero', { codigo: 'precios_distintos', precios: [precio], sucursal_id: 'Norte' }],
  ])('si %s, no hay sucursal y el 409 se reconoce igual', (_, detalle) => {
    const err = new ApiError(409, 'x', detalle)
    expect(sucursalDeLosPrecios(err)).toBeNull()
    expect(preciosDistintosDe(err)).toEqual([precio])
  })

  it('otro error no tiene sucursal', () => {
    expect(sucursalDeLosPrecios(new Error('boom'))).toBeNull()
    expect(sucursalDeLosPrecios(new ApiError(409, 'x', { codigo: 'otra', sucursal_id: 7 }))).toBeNull()
    expect(sucursalDeLosPrecios(new ApiError(422, 'x', { codigo: 'precios_distintos', sucursal_id: 7 }))).toBeNull()
  })
})
