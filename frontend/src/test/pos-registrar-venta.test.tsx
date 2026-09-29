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
  id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001',
  unidad: 'u', precio_venta: 3000, activo: 1,
}

// Una sucursal como la devuelve `GET /api/sucursales`. Sucursal y depósito son entidades distintas: el depósito de
// venta (`deposito_predeterminado_id`) NUNCA tiene el mismo id que la sucursal en estos tests, a propósito, para que
// mandar el id equivocado se note.
function sucursal(id: number, nombre: string, depositoDeVenta: number | null, esDefault = false) {
  return {
    id, nombre, codigo: null, direccion: null, activa: true, es_default: esDefault,
    deposito_predeterminado_id: depositoDeVenta, depositos: 1,
  }
}

// Dos sucursales: sirve para afirmar que viaja la elegida, no "la primera".
const LOCATIONS = [
  sucursal(1, 'Salón', 11, true),
  sucursal(7, 'Sucursal Norte', 12),
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
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(opciones.locations ?? LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    if (u.includes('/variantes')) return Promise.resolve(json([]))
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
  it('manda como deposito_id el depósito de venta de la sucursal elegida, no el id de la sucursal', async () => {
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
    // La sucursal 7 vende del depósito 12: el 7 sería un depósito de otra sucursal (el backend lo rechaza con 422).
    expect(registro.body).toMatchObject({ deposito_id: 12 })
    expect(registro.body).not.toMatchObject({ deposito_id: 7 })
  })

  it('la sucursal predeterminada (preseleccionada) también manda su depósito de venta, no su id', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    const registro = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(registro.body).toMatchObject({ deposito_id: 11 })
  })

  it('la sucursal recordada en localStorage (misma clave de siempre) vende de su depósito de venta', async () => {
    localStorage.setItem('ventalibra.pos.location', '7')
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)
    expect(await screen.findByRole('combobox', { name: 'Sucursal' })).toHaveTextContent('Sucursal Norte')
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    const registro = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(registro.body).toMatchObject({ deposito_id: 12 })
    expect(localStorage.getItem('ventalibra.pos.location')).toBe('7')
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
    // La primera que devuelve el backend es "Sucursal Sur" (no default); la
    // marcada `es_default` es la segunda -- si el POS tomara `items[0]`,
    // mostraría "Sucursal Sur" en vez de "Salón".
    montarRed({
      locations: [
        sucursal(2, 'Sucursal Sur', 22),
        sucursal(1, 'Salón', 11, true),
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
        sucursal(2, 'Sucursal Sur', 22),
        sucursal(1, 'Salón', 11),
      ],
    })
    const user = userEvent.setup()
    montar()
    await escanear(user)

    expect(await screen.findByRole('combobox', { name: 'Sucursal' })).toHaveTextContent('Sucursal Sur')
  })

  it('la lista sale de /api/sucursales: no se le piden los depósitos al motor para elegir dónde vender', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    await escanear(user)

    const combo = await screen.findByRole('combobox', { name: 'Sucursal' })
    await user.click(combo)
    expect(await screen.findByRole('option', { name: 'Salón' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Sucursal Norte' })).toBeInTheDocument()
    expect(llamadas.some((l) => l.url === '/api/sucursales')).toBe(true)
    expect(llamadas.some((l) => l.url.includes('/api/depositos'))).toBe(false)
  })
})
