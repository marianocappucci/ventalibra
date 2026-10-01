// Los avisos de vencimiento del POS (vencimientos y lotes, ADR-053; `libracommerce` v0.30.0). Dos cambios, los dos OPT-IN por lo que
// conteste el backend y ninguno puede bloquear ni demorar una venta si falla:
//
// 1. Antes de cobrar: `POST /api/ventas/plan-salida` con las líneas del carrito y el depósito de la venta. Si trae avisos de lote
//    vencido o por vencer, un diálogo NO bloqueante pregunta «¿Vender igual?» («Vender igual» / «Volver»). Sin avisos, con el
//    endpoint caído (404, 405, 500, la red) o lento (más de ~1,5 s), no se muestra nada y se cobra como siempre.
// 2. Después de cobrar: si la venta trae `avisos`, la pantalla de la venta cobrada los muestra, sin tocar el ticket.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { PLAN_SALIDA_TIMEOUT_MS } from '../lib/avisos-de-vencimiento'

const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'mercadopago', label: 'Mercado Pago' },
]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const ITEM = { id: 3, nombre: 'Yerba 500g', sku: 'YER5', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const SUCURSAL = { id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 }

const VENCIDO = {
  tipo: 'lote_vencido', producto_id: 3, nombre: 'Yerba 500g', lote: 'L1', vence: '2026-10-12', dias_para_vencer: -3, cantidad: 1,
  deposito_id: 11, variante_id: null,
}
const POR_VENCER = {
  tipo: 'por_vencer', producto_id: 4, nombre: 'Leche 1L', lote: 'L2', vence: '2026-10-20', dias_para_vencer: 5, cantidad: 2,
  deposito_id: 11, variante_id: null,
}
const FALTANTE = {
  tipo: 'faltante_sin_lote', producto_id: 3, nombre: 'Yerba 500g', lote: null, vence: null, dias_para_vencer: null, cantidad: 2,
  deposito_id: 11, variante_id: null,
}

function venta(overrides: Record<string, unknown> = {}) {
  return {
    id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 500g', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
    subtotal: 3000, descuento: 0, total: 3000, cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'efectivo', monto: 3000, referencia: '', recibido: 3000 }],
    factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '', created_at: '2026-08-23T10:05:00',
    ...overrides,
  }
}

type Llamada = { metodo: string; url: string; body: any }  // eslint-disable-line @typescript-eslint/no-explicit-any

/** `plan`: qué contesta `POST /api/ventas/plan-salida` (una función para simular demora o caída). */
function montarRed(opciones: {
  plan?: () => Promise<Response>
  ventaRespuesta?: Record<string, unknown>
  mp?: boolean
} = {}) {
  const llamadas: Llamada[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: opciones.mp ?? false, auto_facturar: false }))
    if (u.endsWith('/api/ventas/plan-salida') && metodo === 'POST') {
      return (opciones.plan ?? (() => Promise.resolve(json({ hoy: '2026-10-15', dias: 15, salidas: [], avisos: [] }))))()
    }
    if (u.match(/\/api\/ventas\/\d+\/mp-qr$/)) return Promise.resolve(json({ total: 3000 }))
    if (u.match(/\/api\/ventas\/\d+\/mp-status$/)) return Promise.resolve(json({ status: 'pending' }))
    if (u.match(/\/api\/ventas\/9$/) && metodo === 'GET') return Promise.resolve(json(venta(opciones.ventaRespuesta)))
    if (u.endsWith('/api/ventas') && metodo === 'POST') return Promise.resolve(json(venta(opciones.ventaRespuesta)))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
  return {
    llamadas,
    plan: () => llamadas.filter((l) => l.url.endsWith('/api/ventas/plan-salida')),
    registros: () => llamadas.filter((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas')),
  }
}

const conAvisos = (...avisos: unknown[]) => () => Promise.resolve(json({ hoy: '2026-10-15', dias: 15, salidas: [], avisos }))

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

async function escanear(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 500g/)
}

/** Escanea y aprieta «Cobrar» dos veces: la del carrito abre el cobro y la del diálogo lo confirma. */
async function cobrar(user: ReturnType<typeof userEvent.setup>) {
  await escanear(user)
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
}

const cobrada = () => screen.findByText(/Venta POS-000009 cobrada/)

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Antes de cobrar: «¿Vender igual?»', () => {
  it('con un lote vencido y otro por vencer pregunta, con la fecha en dd-mm-aaaa, y «Vender igual» registra UNA venta', async () => {
    const red = montarRed({ plan: conAvisos(VENCIDO, POR_VENCER) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)

    const dialogo = await screen.findByRole('alertdialog')
    expect(within(dialogo).getByText('Hay 2 productos con lote vencido o por vencer')).toBeInTheDocument()
    expect(within(dialogo).getByText('Yerba 500g, lote L1, vence 12-10-2026 (vencido hace 3 días)')).toBeInTheDocument()
    expect(within(dialogo).getByText('Leche 1L, lote L2, vence 20-10-2026 (vence en 5 días)')).toBeInTheDocument()
    expect(within(dialogo).getByText('¿Vender igual?')).toBeInTheDocument()
    // La consulta lleva las líneas del carrito y el depósito de la venta (no el id de la sucursal).
    expect(red.plan()).toHaveLength(1)
    expect(red.plan()[0].body).toEqual({ items: [{ producto_id: 3, qty: 1, variante_id: null }], deposito_id: 11 })
    // Mientras se decide, NO se registró nada.
    expect(red.registros()).toHaveLength(0)

    await user.click(within(dialogo).getByRole('button', { name: 'Vender igual' }))
    await cobrada()
    expect(red.registros()).toHaveLength(1)
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('un doble clic en «Vender igual» registra una sola venta', async () => {
    const red = montarRed({ plan: conAvisos(VENCIDO) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)

    const boton = within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Vender igual' })
    fireEvent.click(boton)
    fireEvent.click(boton)
    await cobrada()
    expect(red.registros()).toHaveLength(1)
  })

  it('«Volver» no registra nada, vuelve al cobro y se puede cobrar después', async () => {
    const red = montarRed({ plan: conAvisos(VENCIDO) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)

    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Volver' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(red.registros()).toHaveLength(0)
    // El cobro sigue abierto y el guardia se soltó: otro intento vuelve a preguntar y ahora sigue.
    expect(screen.getByText(/Dividir en otro medio/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Vender igual' }))
    await cobrada()
    expect(red.plan()).toHaveLength(2)
    expect(red.registros()).toHaveLength(1)
  })

  it('Escape cierra el diálogo como «Volver»: no se vende', async () => {
    const red = montarRed({ plan: conAvisos(VENCIDO) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await screen.findByRole('alertdialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(red.registros()).toHaveLength(0)
  })

  it('con un solo producto el título va en singular y dice «vencido» o «por vencer» según el caso', async () => {
    montarRed({ plan: conAvisos(POR_VENCER) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    expect(await screen.findByText('Hay 1 producto con lote por vencer')).toBeInTheDocument()
  })

  it('sin avisos no muestra nada y cobra directo', async () => {
    const red = montarRed({ plan: conAvisos() })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(red.plan()).toHaveLength(1)
    expect(red.registros()).toHaveLength(1)
  })

  it('un faltante sin lote no frena la venta antes de cobrar (sólo se informa después)', async () => {
    const red = montarRed({ plan: conAvisos(FALTANTE) })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(red.registros()).toHaveLength(1)
  })

  it.each([
    ['404', () => Promise.resolve(json({ detail: 'Not Found' }, 404))],
    ['405 (un backend sin la opción: lo captura `GET /{vid}`)', () => Promise.resolve(json({ detail: 'Method Not Allowed' }, 405))],
    ['500', () => Promise.resolve(json({ detail: 'boom' }, 500))],
    ['403', () => Promise.resolve(json({ detail: 'forbidden' }, 403))],
    ['un error de red', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['una respuesta que no es la esperada', () => Promise.resolve(json([1, 2, 3]))],
    ['una respuesta sin avisos', () => Promise.resolve(json({ hoy: '2026-10-15' }))],
  ])('con el plan de salida caído (%s) se cobra como siempre, sin diálogo ni error', async (_caso, plan) => {
    const red = montarRed({ plan })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(red.registros()).toHaveLength(1)
  })

  it('si el plan de salida tarda más que el tope, se cobra sin esperarlo y la respuesta tardía no abre nada', async () => {
    // El plan contesta con avisos a los 4 s; el tope es de ~1,5 s: la venta sigue sin ellos.
    const red = montarRed({
      plan: () => new Promise((resolver) => setTimeout(() => resolver(json({ avisos: [VENCIDO] })), 4000)),
    })
    const user = userEvent.setup()
    montar()
    const antes = Date.now()
    await cobrar(user)
    await screen.findByText(/Venta POS-000009 cobrada/, undefined, { timeout: 4000 })
    const tardo = Date.now() - antes
    expect(tardo).toBeGreaterThanOrEqual(PLAN_SALIDA_TIMEOUT_MS - 100)
    expect(red.registros()).toHaveLength(1)
    // Pasado el tiempo en que llegaba la respuesta tardía, tampoco aparece un diálogo sobre la venta ya cobrada.
    await new Promise((r) => setTimeout(r, 2800))
    expect(screen.queryByRole('alertdialog')).toBeNull()
  }, 15000)

  it('un carrito sin productos (líneas sin `producto_id`) no pide el plan', async () => {
    // La regla está en `consultarAvisosDeSalida`: una línea suelta o de cantidad no positiva no se manda (el motor contestaría 422).
    const { consultarAvisosDeSalida } = await import('../lib/avisos-de-vencimiento')
    const red = montarRed({ plan: conAvisos(VENCIDO) })
    expect(await consultarAvisosDeSalida([{ producto_id: null, qty: '1', variante_id: null }], 11)).toEqual([])
    expect(await consultarAvisosDeSalida([{ producto_id: 3, qty: '0', variante_id: null }], 11)).toEqual([])
    expect(red.plan()).toHaveLength(0)
  })

  it('el cobro por QR también pregunta antes de registrar la venta pendiente; «Volver» no la registra', async () => {
    const red = montarRed({ plan: conAvisos(VENCIDO), mp: true })
    const user = userEvent.setup()
    montar()
    await escanear(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Mercado Pago' }))
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    const dialogo = await screen.findByRole('alertdialog')
    expect(red.registros()).toHaveLength(0)
    await user.click(within(dialogo).getByRole('button', { name: 'Volver' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(red.registros()).toHaveLength(0)
    // El botón del QR vuelve a estar disponible (no quedó «Preparando el QR…»).
    expect(await screen.findByRole('button', { name: /Cobrar con QR/ })).toBeEnabled()

    // Y con «Vender igual» registra la venta pendiente (una sola vez) y sigue con el QR.
    await user.click(screen.getByRole('button', { name: /Cobrar con QR/ }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Vender igual' }))
    await waitFor(() => expect(red.registros()).toHaveLength(1))
    expect(red.registros()[0].body).toMatchObject({ pagos: [{ medio: 'mercadopago', cobrar_con_qr: true }], deposito_id: 11 })
  })
})

describe('Después de cobrar: los avisos de la venta', () => {
  it('si la respuesta trae `avisos`, la venta cobrada los muestra y el ticket sigue ahí', async () => {
    montarRed({ ventaRespuesta: { avisos: [VENCIDO, POR_VENCER, FALTANTE] } })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()

    const nota = screen.getByRole('note', { name: 'Avisos de vencimiento' })
    expect(within(nota).getByText('Yerba 500g, lote L1, vence 12-10-2026 (vencido hace 3 días)')).toBeInTheDocument()
    expect(within(nota).getByText('Leche 1L, lote L2, vence 20-10-2026 (vence en 5 días)')).toBeInTheDocument()
    expect(within(nota).getByText(/Yerba 500g: 2 salieron sin lote que las respaldara/)).toBeInTheDocument()
    // El comprobante y el cierre no cambian.
    expect(screen.getByRole('button', { name: /Imprimir ticket/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nueva venta/ })).toBeInTheDocument()
    expect(screen.getByText('$3.000,00')).toBeInTheDocument()
  })

  it('sin `avisos` (la clave no existe) la venta cobrada es la de siempre', async () => {
    montarRed()
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()
    expect(screen.queryByRole('note', { name: 'Avisos de vencimiento' })).toBeNull()
  })

  it('unos `avisos` que no son una lista no rompen la pantalla', async () => {
    montarRed({ ventaRespuesta: { avisos: 'raro' } })
    const user = userEvent.setup()
    montar()
    await cobrar(user)
    await cobrada()
    expect(screen.queryByRole('note', { name: 'Avisos de vencimiento' })).toBeNull()
  })
})
