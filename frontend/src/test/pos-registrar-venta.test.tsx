// El cobro normal (sin QR) desde el POS: un solo `POST /api/ventas` con todo
// el carrito, el depósito de la sucursal elegida, y la factura -- si se pidió
// -- recién DESPUÉS de registrar (F4, DECISIONS.md ADR-025, D1).
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'tarjeta_debito', label: 'Tarjeta de débito' },
  { id: 'mercadopago', label: 'Mercado Pago' },
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

// Dos sucursales: sirve para afirmar que viaja la elegida, no "la primera".
const LOCATIONS = [
  { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: true },
  { id: 2, name: 'Sucursal Norte', branch_id: null, location_type: 'store', active: true, is_default: false },
]

function venta(overrides: Record<string, unknown> = {}) {
  return {
    id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
    items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
    subtotal: 3000, descuento: 0, total: 3000,
    cliente_id: null, cliente_nombre: '', observaciones: '',
    pagos: [{ medio: 'efectivo', monto: 3000, referencia: '', recibido: 3000 }],
    factura_id: null, factura_display: null, remito_id: null,
    mp_order_id: '', mp_payment_id: '', created_at: '2026-08-23T10:05:00',
    ...overrides,
  }
}

type Llamada = { metodo: string; url: string; body: unknown }

function montarRed(opciones: {
  facturarFalla?: boolean
  ventasPostFalla?: boolean
  locationId?: number
  locations?: typeof LOCATIONS
} = {}) {
  const llamadas: Llamada[] = []
  let postsAVentas = 0

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.match(/\/api\/ventas\/\d+\/facturar$/)) {
      if (opciones.facturarFalla) return Promise.resolve(json({ detail: 'ARCA no responde' }, 502))
      return Promise.resolve(json({}))
    }
    if (u.match(/\/api\/ventas\/9$/) && metodo === 'GET') {
      return Promise.resolve(json(venta({ factura_id: opciones.facturarFalla ? null : 55, factura_display: opciones.facturarFalla ? null : 'FACTURA C 0001-00000055' })))
    }
    if (u.endsWith('/api/ventas') && metodo === 'POST') {
      postsAVentas += 1
      if (opciones.ventasPostFalla && postsAVentas === 1) {
        return Promise.resolve(json({ detail: 'No se pudo registrar la venta.' }, 409))
      }
      return Promise.resolve(json(venta()))
    }
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json(opciones.locations ?? LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/catalog/items/scan')) {
      return Promise.resolve(json({ item: ITEM, quantity: '1', unit_price: null, from_scale: false }))
    }
    if (u.includes('/variants')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas, postsAVentas: () => postsAVentas }
}

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

async function escanear(user: ReturnType<typeof userEvent.setup>) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, '779000001{Enter}')
  await screen.findByText(/Yerba 1kg/)
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Registrar la venta (D1: una sola llamada)', () => {
  it('manda deposito_id de la sucursal elegida en el POS', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)

    // Elegir la segunda sucursal antes de cobrar -- arranca en "Salón" (la
    // primera de la lista, ver el efecto de `Pos.tsx` que fija el default).
    await user.click(await screen.findByRole('combobox', { name: 'Sucursal' }))
    await user.click(await screen.findByRole('option', { name: 'Sucursal Norte' }))

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    const registro = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(registro.body).toMatchObject({ deposito_id: 2 })
  })

  it('un doble click en Cobrar manda un solo POST', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    const cobrar = await screen.findByRole('button', { name: /Cobrar/ })
    // Dos clicks SIN esperar entre uno y otro -- `fireEvent`, no
    // `userEvent`, a propósito: `userEvent.click` deja que React re-renderice
    // (y deshabilite el botón) entre un click y el siguiente, que es un
    // guardia real pero no el que este test tiene que ejercitar. Un
    // double-click de mouse de verdad, o un Enter que repite antes de que
    // React pinte, dispara los dos `onClick` en el MISMO tick -- ahí es
    // donde el `disabled` (basado en estado) todavía no actuó y sólo el
    // guardia sincrónico (`enviandoRef`) puede frenar el segundo POST.
    fireEvent.click(cobrar)
    fireEvent.click(cobrar)

    await waitFor(() => {
      expect(screen.getByText(/Venta POS-000009 cobrada/)).toBeInTheDocument()
    })
    const posts = llamadas.filter((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
    expect(posts).toHaveLength(1)
  })

  it('si el registro falla, no queda bloqueado: se puede reintentar', async () => {
    const { llamadas } = montarRed({ ventasPostFalla: true })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await screen.findByText(/No se pudo registrar la venta/)

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await waitFor(() => {
      expect(screen.getByText(/Venta POS-000009 cobrada/)).toBeInTheDocument()
    })
    const posts = llamadas.filter((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
    expect(posts).toHaveLength(2)
  })

  it('pide la factura DESPUÉS de registrar, nunca antes ni en el mismo POST', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByLabelText(/Emitir factura/))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    await waitFor(() => {
      expect(screen.getByText(/Venta POS-000009 cobrada/)).toBeInTheDocument()
    })

    const registro = llamadas.findIndex((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
    const facturar = llamadas.findIndex((l) => l.url.includes('/api/ventas/9/facturar'))
    expect(registro).toBeGreaterThanOrEqual(0)
    expect(facturar).toBeGreaterThan(registro)
    // Y el POST que registra la venta no lleva ningún indicio de facturación:
    // pedirla es una llamada aparte, no un campo del payload.
    const cuerpoRegistro = llamadas[registro].body as Record<string, unknown>
    expect(cuerpoRegistro).not.toHaveProperty('invoice')
    expect(cuerpoRegistro).not.toHaveProperty('factura')
  })

  it('si facturar falla, la venta queda igual y se puede reintentar desde el detalle', async () => {
    montarRed({ facturarFalla: true })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByLabelText(/Emitir factura/))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    // La venta se muestra cobrada igual -- no se pierde por el error de facturar.
    await screen.findByText(/Venta POS-000009 cobrada/)
    expect(screen.getByText(/No se pudo emitir la factura/)).toBeInTheDocument()
    expect(screen.getByText(/ARCA no responde/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /el detalle de la venta/ })).toHaveAttribute('href', '/ventas/9')
  })
})

describe('La sucursal inicial del POS', () => {
  it('preselecciona la marcada is_default, no la primera de la lista', async () => {
    // La primera que devuelve el backend es "Depósito" (no default); la
    // marcada `is_default` es la segunda -- si el POS tomara `items[0]` como
    // antes, mostraría "Depósito" en vez de "Salón".
    montarRed({
      locations: [
        { id: 2, name: 'Depósito', branch_id: null, location_type: 'store', active: true, is_default: false },
        { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: true },
      ],
    })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    // La etiqueta accesible del combobox es fija ("Sucursal"); lo que cambia
    // con la selección es su TEXTO visible (el valor elegido).
    expect(await screen.findByRole('combobox', { name: 'Sucursal' })).toHaveTextContent('Salón')
  })

  it('sin ninguna marcada is_default, cae a la primera de la lista', async () => {
    montarRed({
      locations: [
        { id: 2, name: 'Depósito', branch_id: null, location_type: 'store', active: true, is_default: false },
        { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: false },
      ],
    })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    expect(await screen.findByRole('combobox', { name: 'Sucursal' })).toHaveTextContent('Depósito')
  })

  it('no ofrece los depósitos: sólo una sucursal `store` vende', async () => {
    montarRed({
      locations: [
        { id: 3, name: 'Depósito', branch_id: null, location_type: 'warehouse', active: true, is_default: true },
        { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: false },
      ],
    })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    // El depósito es el default del sistema, pero no vende: queda Salón.
    const combo = await screen.findByRole('combobox', { name: 'Sucursal' })
    expect(combo).toHaveTextContent('Salón')
    await user.click(combo)
    expect(screen.queryByRole('option', { name: 'Depósito' })).not.toBeInTheDocument()
  })
})
