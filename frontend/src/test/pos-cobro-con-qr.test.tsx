// El cobro con QR de MercadoPago desde el POS.
//
// Portado a F4 del plan ERP (2026-09-15, DECISIONS.md ADR-025, D1/D2): el
// carrito vive en el navegador y la venta se registra completa con
// `POST /api/ventas` -- ya no hay un borrador (`POST /sales` + `.../items`,
// retirados) que crecía a medida que se escaneaba. El cobro con QR tampoco
// "pone el monto sobre un borrador que ya existe": la venta nace PENDIENTE
// recién al apretar "Cobrar con QR", con el pago `mercadopago` en
// `cobrar_con_qr: true`.
//
// Lo que se prueba acá es el **cableado de la pantalla**, que es donde vive la
// lógica que el backend no puede ver: cuándo se ofrece el botón, qué se llama
// al apretarlo, y qué se manda al confirmar cuando el pago se acredita. Las
// reglas del cobro en sí —el monto que va al QR, el sellado del `payment_id`,
// la factura automática— tienen sus tests del lado del backend
// (`tests/test_mp_qr.py`).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

/** Lo que contesta el backend: `medios_pago.para_selector()` de LibraCore. */
const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'transferencia', label: 'Transferencia' },
  { id: 'tarjeta_debito', label: 'Tarjeta de débito' },
  { id: 'tarjeta_credito', label: 'Tarjeta de crédito' },
  { id: 'mercadopago', label: 'Mercado Pago' },
  { id: 'cuenta_dni', label: 'Cuenta DNI' },
  { id: 'billetera', label: 'Otras billeteras' },
  { id: 'cheque', label: 'Cheque' },
  { id: 'cuenta_corriente', label: 'Cuenta corriente' },
]

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

const LOCATION = { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: true }

/** La venta ya registrada -- lo que devuelve `POST /api/ventas` (D1: nace
 *  completa, no un borrador vacío). */
function venta(overrides: Record<string, unknown> = {}) {
  return {
    id: 7, numero: 'POS-000007', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
    subtotal: 3000, descuento: 0, total: 3000,
    cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'mercadopago', monto: 3000, referencia: 'MP#112233', recibido: null }],
    factura_id: null, factura_display: null, remito_id: null,
    mp_order_id: '', mp_payment_id: '', created_at: '2026-08-23T10:05:00',
    ...overrides,
  }
}

type Llamada = { metodo: string; url: string; body: unknown }

/** El doble de la red. `mpStatus` es lo que contesta el poll; los tests lo
 *  mueven de `pending` a `approved` para simular que el cliente escaneó. */
function montarRed(opciones: {
  disponible?: boolean
  autoFacturar?: boolean
  ventaId?: number
  mpQrFalla?: boolean
  anularFalla?: boolean
  onPost?: (url: string, body: unknown) => void
} = {}) {
  const llamadas: Llamada[] = []
  const estado = { mpStatus: 'pending' as string }
  const vid = opciones.ventaId ?? 7

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })
    opciones.onPost?.(u, body)

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) {
      return Promise.resolve(json({
        disponible: opciones.disponible ?? true,
        auto_facturar: opciones.autoFacturar ?? true,
      }))
    }
    if (u.includes('/mp-status')) {
      return Promise.resolve(json(
        estado.mpStatus === 'approved'
          ? { status: 'approved', payment_id: '112233' }
          : { status: estado.mpStatus },
      ))
    }
    if (u.match(/\/api\/ventas\/\d+\/mp-qr$/)) {
      if (opciones.mpQrFalla) return Promise.resolve(json({ detail: 'MercadoPago no responde.' }, 502))
      return Promise.resolve(json({ total: 3000 }))
    }
    if (u.match(/\/api\/ventas\/\d+\/anular$/)) {
      if (opciones.anularFalla) return Promise.resolve(json({ detail: 'No se pudo anular.' }, 500))
      return Promise.resolve(json(venta({ id: vid, estado: 'anulada', status: 'cancelled' })))
    }
    if (u.match(/\/api\/ventas\/\d+\/facturar$/)) return Promise.resolve(json({}))
    if (u.match(new RegExp(`/api/ventas/${vid}$`)) && metodo === 'GET') {
      return Promise.resolve(json(venta({ id: vid })))
    }
    if (u.endsWith('/api/ventas') && metodo === 'POST') {
      return Promise.resolve(json(venta({ id: vid, estado: 'pendiente', status: 'confirmed' })))
    }
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json([LOCATION]))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/catalog/items/scan')) {
      return Promise.resolve(json({
        item: ITEM, quantity: '1', unit_price: null, from_scale: false,
      }))
    }
    // Sin variantes: el POS agrega el ítem pelado, sin diálogo intermedio.
    if (u.includes('/variants')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas, estado }
}

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

/** La venta se arma en el navegador: escanear sólo agrega al carrito local,
 *  sin ningún POST (D1). */
async function escanear(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
}

/** Con la venta armada, elegir Mercado Pago como único medio — que es la
 *  condición para que el QR aplique. */
async function abrirCobroConMercadoPago(user: ReturnType<typeof userEvent.setup>) {
  await escanear(user)
  await user.click(await screen.findByRole('button', { name: /Cobrar/ }))

  const combo = await screen.findByRole('combobox')
  await user.click(combo)
  await user.click(await screen.findByRole('option', { name: 'Mercado Pago' }))
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  // El hook cachea la lista a nivel de módulo: sin esto, el primer test del
  // archivo decide lo que ven todos los demás.
  _resetCacheDeMedios()
})

describe('El botón de cobrar con QR', () => {
  it('no se ofrece si la instancia no tiene MercadoPago configurado', async () => {
    montarRed({ disponible: false })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)

    // Control positivo del selector: el diálogo SÍ está abierto y el medio SÍ
    // es Mercado Pago. Sin esto, un `queryByRole` que no encuentra nada porque
    // el diálogo nunca abrió pasaría igual.
    expect(screen.getByText(/Dividir en otro medio/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cobrar con QR/ })).toBeNull()
  })

  it('no se ofrece en efectivo, aunque MercadoPago esté configurado', async () => {
    montarRed({ disponible: true })
    const user = userEvent.setup()
    montar()

    await escanear(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))

    expect(await screen.findByText(/Dividir en otro medio/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cobrar con QR/ })).toBeNull()
  })

  it('se ofrece cuando Mercado Pago cubre el total', async () => {
    montarRed({ disponible: true })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)

    expect(await screen.findByRole('button', { name: /Cobrar con QR/ })).toBeInTheDocument()
  })
})

describe('El cobro con QR', () => {
  it('registra la venta pendiente con deposito_id y pone el monto en el QR', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    const registro = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(registro.body).toMatchObject({
      deposito_id: 1,
      pagos: [{ medio: 'mercadopago', monto: 3000, cobrar_con_qr: true }],
    })

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/mp-qr')))
        .toBe(true)
    })
    expect(await screen.findByText(/Pedile al cliente que lo escanee/)).toBeInTheDocument()
  })

  it('al acreditarse, refresca la venta y no pide facturar sola', async () => {
    // 🔑 **La factura automática la decide el backend.** El POS no manda
    // ningún pedido de facturar cuando la automática está prendida -- si lo
    // hiciera, una venta con la automática apagada podría terminar facturada
    // igual por el POS, sin que el backend lo hubiera decidido.
    const { llamadas, estado } = montarRed({ autoFacturar: true })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    estado.mpStatus = 'approved'

    await screen.findByText(/Venta POS-000007 cobrada/, {}, { timeout: 6000 })
    expect(llamadas.some((l) => l.url.includes('/api/ventas/7/facturar'))).toBe(false)
  }, 10000)

  it('cancelar el cobro pide confirmación y anula la venta pendiente', async () => {
    // D2: no hay "bajar del QR" -- cancelar es anular la venta pendiente.
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    await user.click(screen.getByRole('button', { name: /Cancelar el cobro por QR/ }))
    // Con confirmación: el primer click no dispara la anulación todavía.
    expect(screen.queryByRole('button', { name: /Cobrar con QR/ })).toBeNull()
    expect(llamadas.some((l) => l.url.includes('/anular'))).toBe(false)

    await user.click(await screen.findByRole('button', { name: /Anular la venta/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/anular')))
        .toBe(true)
    })
    expect(await screen.findByText(/se anuló/)).toBeInTheDocument()
  })

  it('un pago rechazado por MercadoPago también anula la venta pendiente', async () => {
    const { llamadas, estado } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    estado.mpStatus = 'rejected'

    // El poll tarda `QR_POLL_MS` (3s) en volver a preguntar: el default de
    // `waitFor` (1s) no alcanza a verlo.
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/anular')))
        .toBe(true)
    }, { timeout: 6000 })
    expect(await screen.findByText(/rechazado o cancelado/)).toBeInTheDocument()
  }, 10000)

  // ── Revisión adversarial (2026-09-15): QR huérfano ──────────────────────
  it('si "poner el monto en el QR" falla, anula la venta que ya se había registrado', async () => {
    // 🔴 La venta se registra (PENDIENTE, stock ya descontado) ANTES de
    // pedirle a MercadoPago que ponga el monto en el QR: si ese segundo POST
    // falla, sin este arreglo la venta quedaba huérfana -- nadie la volvía a
    // mencionar, sin ticket y sin aparecer como cobrada.
    const { llamadas } = montarRed({ mpQrFalla: true })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    // Se registró...
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))).toBe(true)
    })
    // ...mp-qr falló...
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/mp-qr'))).toBe(true)
    })
    // ...y por eso se anula esa MISMA venta (id 7), sin esperar al poll.
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/anular')))
        .toBe(true)
    })
    expect(await screen.findByText(/La venta se anuló/)).toBeInTheDocument()
  })

  it('si además falla anular, el aviso nombra la venta para anularla a mano', async () => {
    montarRed({ mpQrFalla: true, anularFalla: true })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    expect(await screen.findByText(/No se pudo anular sola/)).toBeInTheDocument()
    expect(screen.getByText(/POS-000007/)).toBeInTheDocument()
  })

  // ── Revisión adversarial (2026-09-15): la carrera del cancelar ──────────
  it('cancelar cuando el pago ya se acreditó no anula: la venta queda cobrada', async () => {
    // El cliente escanea justo cuando el cajero aprieta "Cancelar": el chequeo
    // final (`verificarYAnular`) tiene que ganarle a la cancelación.
    const { llamadas, estado } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    estado.mpStatus = 'approved'
    await user.click(screen.getByRole('button', { name: /Cancelar el cobro por QR/ }))
    await user.click(await screen.findByRole('button', { name: /Anular la venta/ }))

    await screen.findByText(/Venta POS-000007 cobrada/)
    expect(llamadas.some((l) => l.url.includes('/anular'))).toBe(false)
    expect(screen.getByText(/se acreditó justo ahora/)).toBeInTheDocument()
  })

  it('cancelar con el pago todavía pendiente sí anula', async () => {
    const { llamadas, estado } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    expect(estado.mpStatus).toBe('pending')
    await user.click(screen.getByRole('button', { name: /Cancelar el cobro por QR/ }))
    await user.click(await screen.findByRole('button', { name: /Anular la venta/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/7/anular')))
        .toBe(true)
    })
    expect(await screen.findByText(/Cobro por QR cancelado/)).toBeInTheDocument()
  })
})

describe('Los medios del cobro', () => {
  it('son los que manda el backend, no una lista propia', async () => {
    montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('combobox'))

    const opciones = (await screen.findAllByRole('option')).map((o) => o.textContent)
    // Lo único propio del POS es el nombre del fiado en el mostrador.
    expect(opciones).toEqual(MEDIOS.map((m) => (
      m.id === 'cuenta_corriente' ? 'Cuenta corriente (fiado)' : m.label
    )))
    // Los tres que la lista propia no ofrecía: la prueba de que la lista cambió de dueño.
    expect(opciones).toEqual(expect.arrayContaining(['Cuenta DNI', 'Otras billeteras', 'Cheque']))
  })
})
