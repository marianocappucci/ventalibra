// El cobro con QR de MercadoPago desde el POS.
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

const VENTA_VACIA = {
  id: 7, number: 'POS-000007', status: 'draft', items: [], pagos: [],
  vuelto_total: '0.00', subtotal: '0.00', discount_total: '0.00',
  tax_total: '0.00', total: '0.00', confirmed_at: null, factura: null,
}

const VENTA = {
  ...VENTA_VACIA,
  items: [{
    kind: 'product', item_id: 3, variant_id: null,
    description_snapshot: 'Yerba 1kg', quantity: '1', unit_price: '3000.00',
    discount_amount: '0.00', tax_amount: '0.00', line_total: '3000.00',
  }],
  subtotal: '3000.00', total: '3000.00',
}

type Llamada = { metodo: string; url: string; body: unknown }

/** El doble de la red. `mpStatus` es lo que contesta el poll; los tests lo
 *  mueven de `pending` a `approved` para simular que el cliente escaneó. */
function montarRed(opciones: { disponible?: boolean; autoFacturar?: boolean } = {}) {
  const llamadas: Llamada[] = []
  const estado = { mpStatus: 'pending' as string }

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({
      metodo, url: u,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    })

    if (u.includes('/sales/mp/estado')) {
      return Promise.resolve(json({
        disponible: opciones.disponible ?? true,
        auto_facturar: opciones.autoFacturar ?? true,
      }))
    }
    if (u.includes('/mp-status')) {
      return Promise.resolve(json({
        status: estado.mpStatus,
        payment_id: estado.mpStatus === 'approved' ? '112233' : null,
      }))
    }
    if (u.includes('/mp-qr')) return Promise.resolve(json({
      external_reference: 'vl-7-abc123', amount: 3000,
    }))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json([{ id: 1, name: 'Salón', active: true }]))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/catalog/items/scan')) {
      return Promise.resolve(json({
        item: ITEM, quantity: '1', unit_price: null, from_scale: false,
      }))
    }
    // Sin variantes: el POS agrega el ítem pelado, sin diálogo intermedio.
    if (u.includes('/variants')) return Promise.resolve(json([]))
    if (u.includes('/confirm')) {
      return Promise.resolve(json({ ...VENTA, status: 'confirmed', confirmed_at: '2026-08-23T10:05:00' }))
    }
    if (u.includes('/sales/7/items')) return Promise.resolve(json(VENTA))
    if (u.endsWith('/sales') && metodo === 'POST') return Promise.resolve(json(VENTA_VACIA))
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas, estado }
}

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

/** La venta nace al escanear: el POS no crea el borrador al montar. */
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
  it('pone el monto en el QR y avisa que el cliente lo escanee', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.includes('/sales/7/mp-qr')))
        .toBe(true)
    })
    expect(await screen.findByText(/Pedile al cliente que lo escanee/)).toBeInTheDocument()
  })

  it('al acreditarse, confirma la venta sin mandar `invoice`', async () => {
    // 🔑 **La factura automática la decide el backend.** Si la pantalla mandara
    // `invoice: true`, cualquier otro cliente de la API cobraría por QR sin
    // facturar y nada avisaría. Este test es lo que fija que el POS no la
    // pida: pasa con `auto_facturar: true` en la config.
    const { llamadas, estado } = montarRed({ autoFacturar: true })
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    estado.mpStatus = 'approved'

    const confirm = await waitFor(
      () => {
        const encontrada = llamadas.find((l) => l.url.includes('/sales/7/confirm'))
        expect(encontrada).toBeDefined()
        return encontrada!
      },
      { timeout: 6000 },
    )
    expect(confirm.body).toMatchObject({
      location_id: 1,
      pagos: [{ medio: 'mercadopago', monto: '3000.00' }],
      invoice: false,
    })
  }, 10000)

  it('cancelar el cobro baja el monto del QR', async () => {
    // 🔴 Una orden que queda puesta le cobra ese monto al próximo que escanee.
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()

    await abrirCobroConMercadoPago(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))
    await screen.findByText(/Pedile al cliente que lo escanee/)

    await user.click(screen.getByRole('button', { name: /Cancelar el cobro por QR/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'DELETE' && l.url.includes('/sales/7/mp-qr')))
        .toBe(true)
    })
  })
})
