// El cobro con QR del POS sigue la conexión del nodo EN VIVO (libra-ui ADR-077, ADR-091 de este producto).
//
// Antes el POS preguntaba `GET /pos/mp-estado` una sola vez al abrir. Con un corte posterior el QR creaba la venta, recibía el
// 409 `sin_conexion` y la anulaba. Ahora el POS combina esa respuesta con `useConexionDelNodo()` (el estado que mantiene el
// cartel del layout): sin conexión el botón se apaga con el aviso del kit, y vuelve solo cuando vuelve la conexión.
//
// El layout no se monta acá: lo que consulta `GET /api/nodo/conexion` es un `CartelSinConexion` al lado del POS, que es lo que
// monta `createLayout({ conexionDelNodo: true })`. El doble de la red imita al backend: en un nodo sin conexión
// `mp-estado` contesta `disponible: false` aunque el QR esté configurado (`app/routers/ventas_extra.py`).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CartelSinConexion } from 'libra-ui/CartelSinConexion'
import { MENSAJE_QR_SIN_CONEXION, _reiniciarConexionDelNodo } from 'libra-ui/nodo-offline'
import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

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
const ITEM = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const LOCATION = {
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1,
}

function venta(overrides: Record<string, unknown> = {}) {
  return {
    id: 7, numero: 'S02-POS-000007', fecha: '2026-08-23', estado: 'pendiente', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
    subtotal: 3000, descuento: 0, total: 3000, cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'mercadopago', monto: 3000, referencia: '', recibido: null }],
    factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '',
    created_at: '2026-08-23T10:05:00', ...overrides,
  }
}

type Llamada = { metodo: string; url: string }

/** El doble de la red de un nodo. `red.enLinea` es lo que ve el servidor: lo mueven los tests para cortar y devolver la
 *  conexión. `mpQr409` hace que `POST .../mp-qr` conteste el 409 `sin_conexion` del motor (un corte que el cartel no vio). */
function montarRed(opciones: { enLinea?: boolean; esNodo?: boolean; mpQr409?: boolean } = {}) {
  const red = { enLinea: opciones.enLinea ?? true }
  const llamadas: Llamada[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: u })
    if (u.includes('/api/nodo/conexion')) {
      return Promise.resolve(json({
        es_nodo: opciones.esNodo ?? true, en_linea: red.enLinea, node_id: 'nodo-1', a_facturar: 0,
      }))
    }
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    // El QR está configurado; en un nodo sin conexión el servidor dice igual `disponible: false`.
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: red.enLinea, auto_facturar: false }))
    if (u.match(/\/api\/ventas\/\d+\/mp-qr$/)) {
      if (opciones.mpQr409) {
        return Promise.resolve(json({ detail: { codigo: 'sin_conexion', mensaje: MENSAJE_QR_SIN_CONEXION } }, 409))
      }
      return Promise.resolve(json({ total: 3000 }))
    }
    if (u.match(/\/api\/ventas\/\d+\/mp-status$/)) return Promise.resolve(json({ status: 'pending' }))
    if (u.match(/\/api\/ventas\/\d+\/anular$/)) return Promise.resolve(json(venta({ estado: 'anulada', status: 'cancelled' })))
    if (u.endsWith('/api/ventas') && metodo === 'POST') return Promise.resolve(json(venta()))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json([LOCATION]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
  return { red, llamadas }
}

/** El POS con lo que el layout le pone al lado: el cartel que consulta la conexión (cada `intervaloMs`). */
function montar(intervaloMs = 40) {
  render(
    <MemoryRouter>
      <CartelSinConexion intervaloMs={intervaloMs} />
      <Pos />
    </MemoryRouter>,
  )
}

async function abrirCobroConMercadoPago(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
  await user.click(await screen.findByRole('combobox'))
  await user.click(await screen.findByRole('option', { name: 'Mercado Pago' }))
}

const botonQr = () => screen.findByRole('button', { name: /Cobrar con QR/ })
const hizoPostDeVenta = (llamadas: Llamada[]) => llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
  _reiniciarConexionDelNodo()
})

afterEach(() => {
  _reiniciarConexionDelNodo()
})

describe('El QR del POS sigue la conexión del nodo en vivo', () => {
  it('un corte con el cobro abierto apaga el botón con el aviso del kit, y vuelve solo', async () => {
    const { red, llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await abrirCobroConMercadoPago(user)
    expect(await botonQr()).toBeEnabled()
    expect(screen.queryByText(MENSAJE_QR_SIN_CONEXION)).toBeNull()

    red.enLinea = false
    await waitFor(() => expect(screen.getByRole('button', { name: /Cobrar con QR/ })).toBeDisabled())
    expect(screen.getByText(MENSAJE_QR_SIN_CONEXION)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cobrar con QR/ })).toHaveAccessibleDescription(MENSAJE_QR_SIN_CONEXION)
    // Apagado de verdad: apretarlo no registra ninguna venta que después haya que anular.
    await user.click(screen.getByRole('button', { name: /Cobrar con QR/ }))
    expect(hizoPostDeVenta(llamadas)).toBe(false)

    red.enLinea = true
    await waitFor(() => expect(screen.getByRole('button', { name: /Cobrar con QR/ })).toBeEnabled())
    expect(screen.queryByText(MENSAJE_QR_SIN_CONEXION)).toBeNull()
  })

  it('un POS abierto durante el corte recupera el QR solo cuando vuelve la conexión', async () => {
    // Abierto sin conexión: `mp-estado` dice `disponible: false` y el QR no se ofrece (como siempre).
    const { red, llamadas } = montarRed({ enLinea: false })
    const user = userEvent.setup()
    montar()
    await abrirCobroConMercadoPago(user)
    expect(screen.getByText(/Dividir en otro medio/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cobrar con QR/ })).toBeNull()
    const preguntasAntes = llamadas.filter((l) => l.url.includes('/pos/mp-estado')).length

    // Vuelve la conexión: el POS vuelve a preguntar y ofrece el QR sin reabrir la pantalla.
    red.enLinea = true
    expect(await botonQr()).toBeEnabled()
    expect(llamadas.filter((l) => l.url.includes('/pos/mp-estado')).length).toBeGreaterThan(preguntasAntes)
  })

  it('un corte que el cartel no vio: el 409 sin_conexion anula la venta, avisa y apaga el botón ya', async () => {
    // Intervalo largo: la consulta siguiente no llega en el test. Lo que apaga el botón es el 409 (`marcarSinConexion`).
    const { llamadas } = montarRed({ mpQr409: true })
    const user = userEvent.setup()
    montar(60_000)
    await abrirCobroConMercadoPago(user)
    await user.click(await botonQr())

    expect(await screen.findByText(new RegExp(`${MENSAJE_QR_SIN_CONEXION} La venta se anuló`))).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/anular'))).toBe(true)
    await waitFor(() => expect(screen.getByRole('button', { name: /Cobrar con QR/ })).toBeDisabled())
    expect(screen.getAllByText(MENSAJE_QR_SIN_CONEXION).length).toBeGreaterThan(0)
  })

  it('fuera de un nodo el QR no cambia', async () => {
    const { llamadas } = montarRed({ esNodo: false })
    const user = userEvent.setup()
    montar()
    await abrirCobroConMercadoPago(user)

    expect(await botonQr()).toBeEnabled()
    expect(screen.queryByText(MENSAJE_QR_SIN_CONEXION)).toBeNull()
    expect(llamadas.filter((l) => l.url.includes('/pos/mp-estado'))).toHaveLength(1)
  })
})
