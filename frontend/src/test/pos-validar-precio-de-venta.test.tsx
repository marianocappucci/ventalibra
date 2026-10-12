// El servidor valida el precio de cada línea de la venta (ADR-079; libracommerce ADR-049). Lo que le toca al POS:
//
// 1. Mandar la `etiqueta` cruda de las líneas que salieron de la balanza, para que el servidor valide contra ella (por importe,
//    el precio; por peso, la cantidad). Las demás líneas no llevan esa clave.
// 2. Si el servidor contesta 409 `precios_distintos` -- y no escribió nada --, tomar los precios que espera, cerrar el cobro,
//    avisarle al cajero («Cambiaron los precios de N productos; revisá el total y volvé a cobrar») y NO cobrar solo. Con el
//    cobro normal y con el QR. Cualquier otro 409 sigue siendo un error común dentro del diálogo.
// 3. No dejar cambiar la cantidad de una línea de balanza: la fija su etiqueta.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api'
import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { avisoDePreciosDistintos, preciosDistintosDe } from '../lib/precios-distintos'

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
const YERBA = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const CAFE = { id: 4, nombre: 'Café', sku: 'CAF', barcode: '779000002', unidad: 'u', precio_venta: 1500, activo: 1 }
const JAMON = { id: 5, nombre: 'Jamón cocido', sku: 'JAM', barcode: '', unidad: 'kg', precio_venta: 8000, activo: 1 }
const QUESO = { id: 6, nombre: 'Queso', sku: 'QUE', barcode: '', unidad: 'kg', precio_venta: 9000, activo: 1 }
const LOCATION = {
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}

/** El 409 de la validación de precios, como lo manda el motor: el `detail` es un objeto con `mensaje`, `codigo` y `precios`. */
function preciosDistintos(precios: { indice: number; producto_id: number; enviado: number; esperado: number }[]) {
  return json({
    detail: {
      mensaje: `Cambiaron los precios de ${precios.length} productos: revisá el total y volvé a cobrar.`,
      codigo: 'precios_distintos',
      precios: precios.map((p) => ({ variante_id: null, ...p })),
    },
  }, 409)
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

type Llamada = { metodo: string; url: string; body: Record<string, unknown> | undefined }

/** `alVender(n, body)` contesta el n-ésimo `POST /api/ventas` (desde 1). Los códigos de balanza se resuelven como los resuelve
 *  `GET /api/productos/escanear` del motor: el importe (código 2000123...) o el peso (2000456...). */
function montarRed({ alVender, mpDisponible = false }: {
  alVender: (n: number, body: Record<string, unknown>) => Response
  mpDisponible?: boolean
}) {
  const llamadas: Llamada[] = []
  let ventas = 0
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: mpDisponible, auto_facturar: false }))
    if (u.endsWith('/api/ventas') && metodo === 'POST') {
      ventas += 1
      return Promise.resolve(alVender(ventas, body))
    }
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json([LOCATION]))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      const code = new URL(u, 'http://x').searchParams.get('code')
      const base = { cantidad: 1, precio_unitario: null, de_balanza: false }
      if (code === '779000001') return Promise.resolve(json({ producto: YERBA, ...base }))
      if (code === '779000002') return Promise.resolve(json({ producto: CAFE, ...base }))
      // Por importe: la etiqueta trae el precio del paquete ($4.200).
      if (code === '2000123042004') return Promise.resolve(json({ producto: QUESO, cantidad: 1, precio_unitario: 4200, de_balanza: true }))
      // Por peso: la etiqueta trae los kilos (0,750).
      if (code === '2000456007504') return Promise.resolve(json({ producto: JAMON, cantidad: 0.75, precio_unitario: null, de_balanza: true }))
      return Promise.resolve(json({ detail: 'No hay ningún ítem con ese código.' }, 404))
    }
    if (u.includes('/variantes')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
  return { llamadas, ventasPosteadas: () => llamadas.filter((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas')) }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, codigo: string, nombre: RegExp) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${codigo}{Enter}`)
  await screen.findByText(nombre)
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

describe('La etiqueta de la balanza viaja con la venta', () => {
  it('una línea por importe y otra por peso mandan la etiqueta cruda; la línea común no lleva la clave', async () => {
    const red = montarRed({ alVender: () => json(venta(3000)) })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)
    await escanear(user, '2000123042004', /Queso/)
    await escanear(user, '2000456007504', /Jamón cocido/)

    await cobrarEnEfectivo(user)

    const enviada = await waitFor(() => {
      const [primera] = red.ventasPosteadas()
      expect(primera).toBeDefined()
      return primera
    })
    const items = enviada.body!.items as Record<string, unknown>[]
    expect(items).toHaveLength(3)
    expect(items[0]).not.toHaveProperty('etiqueta')
    expect(items[1]).toMatchObject({ producto_id: 6, qty: 1, precio: 4200, etiqueta: '2000123042004' })
    expect(items[2]).toMatchObject({ producto_id: 5, qty: 0.75, etiqueta: '2000456007504' })
    // Y nunca un descuento manual: el servidor lo rechaza con la validación prendida.
    expect(enviada.body).not.toHaveProperty('descuento')
  })

  it('la cantidad de una línea de balanza no se cambia: la fija la etiqueta', async () => {
    montarRed({ alVender: () => json(venta(3000)) })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '2000456007504', /Jamón cocido/)

    fireEvent.keyDown(window, { key: 'F6' })

    expect(await screen.findByText(/la fija su etiqueta/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('la cantidad de una línea común sí se cambia', async () => {
    montarRed({ alVender: () => json(venta(3000)) })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)

    fireEvent.keyDown(window, { key: 'F6' })

    expect(within(await screen.findByRole('dialog')).getByLabelText('Cantidad')).toBeInTheDocument()
  })
})

describe('El servidor no acepta el precio (409 precios_distintos)', () => {
  it('toma los precios esperados, cierra el cobro, avisa y no cobra solo; al volver a cobrar manda los nuevos', async () => {
    const red = montarRed({
      alVender: (n) => (n === 1 ? preciosDistintos([{ indice: 0, producto_id: 3, enviado: 3000, esperado: 2500 }]) : json(venta(2500))),
    })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)
    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)

    await cobrarEnEfectivo(user)

    // El aviso, en castellano y con la cuenta; el cobro se cerró y la línea quedó al precio vigente.
    expect(await screen.findByText('Cambió el precio de 1 producto; revisá el total y volvé a cobrar.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
    // No se cobró solo: un único intento, y no hay ticket de venta cobrada.
    expect(red.ventasPosteadas()).toHaveLength(1)
    expect(screen.queryByText(/POS-000009/)).not.toBeInTheDocument()

    // El cajero revisa el total y vuelve a cobrar: ahora viaja el precio vigente y el aviso se va.
    await cobrarEnEfectivo(user)
    await waitFor(() => expect(red.ventasPosteadas()).toHaveLength(2))
    expect((red.ventasPosteadas()[1].body!.items as { precio: number }[])[0].precio).toBe(2500)
    await screen.findByText(/POS-000009/)
    expect(screen.queryByText(/Cambió el precio de 1 producto/)).not.toBeInTheDocument()
  })

  it('con varios productos cuenta cuántos cambiaron y corrige sólo esas líneas', async () => {
    montarRed({
      alVender: () => preciosDistintos([
        { indice: 0, producto_id: 3, enviado: 3000, esperado: 2500 },
        { indice: 2, producto_id: 5, enviado: 8000, esperado: 7000 },
      ]),
    })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)
    await escanear(user, '779000002', /Café/)
    await escanear(user, '2000456007504', /Jamón cocido/)

    await cobrarEnEfectivo(user)

    expect(await screen.findByText('Cambiaron los precios de 2 productos; revisá el total y volvé a cobrar.')).toBeInTheDocument()
    // La yerba a 2.500, el café sigue a 1.500 y el jamón (0,750 kg) a 7.000 el kilo.
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/1\.500,00/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/7\.000,00/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
  })

  it('con el cobro por QR tampoco se escribe nada: se corrige el carrito y no se pide el QR', async () => {
    const red = montarRed({
      mpDisponible: true,
      alVender: () => preciosDistintos([{ indice: 0, producto_id: 3, enviado: 3000, esperado: 2500 }]),
    })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Mercado Pago' }))

    await user.click(await screen.findByRole('button', { name: /Cobrar con QR/ }))

    expect(await screen.findByText('Cambió el precio de 1 producto; revisá el total y volvé a cobrar.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(red.llamadas.some((l) => l.url.endsWith('/mp-qr'))).toBe(false)
  })

  it('otro 409 (sin turno, conflicto) sigue siendo un error común dentro del diálogo: nada se corrige', async () => {
    montarRed({ alVender: () => json({ detail: 'No hay un turno de caja abierto.' }, 409) })
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await escanear(user, '779000001', /Yerba 1kg/)

    await cobrarEnEfectivo(user)

    expect(await screen.findByText('No hay un turno de caja abierto.')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.queryByText(/Cambió el precio|Cambiaron los precios/)).not.toBeInTheDocument()
    expect(screen.getAllByText(/3\.000,00/).length).toBeGreaterThan(0)
  })
})

describe('preciosDistintosDe', () => {
  const precio = { indice: 1, producto_id: 3, variante_id: null, enviado: 3000, esperado: 2500 }

  it('reconoce el 409 de precios y devuelve las líneas', () => {
    const err = new ApiError(409, 'Cambiaron...', { mensaje: 'Cambiaron...', codigo: 'precios_distintos', precios: [precio] })
    expect(preciosDistintosDe(err)).toEqual([precio])
  })

  it.each([
    ['otro error', new Error('boom')],
    ['otro 409 con detail de texto', new ApiError(409, 'No hay un turno abierto.')],
    ['otro código', new ApiError(409, 'x', { codigo: 'otra_cosa', precios: [precio] })],
    ['no es 409', new ApiError(422, 'x', { codigo: 'precios_distintos', precios: [precio] })],
    ['sin lista de precios', new ApiError(409, 'x', { codigo: 'precios_distintos' })],
    ['lista vacía', new ApiError(409, 'x', { codigo: 'precios_distintos', precios: [] })],
    ['líneas sin forma', new ApiError(409, 'x', { codigo: 'precios_distintos', precios: [{ indice: 'a' }, null] })],
  ])('no confunde %s con el de precios', (_, err) => {
    expect(preciosDistintosDe(err)).toBeNull()
  })

  it('el aviso va en singular o plural', () => {
    expect(avisoDePreciosDistintos([precio])).toBe('Cambió el precio de 1 producto; revisá el total y volvé a cobrar.')
    expect(avisoDePreciosDistintos([precio, precio, precio])).toBe('Cambiaron los precios de 3 productos; revisá el total y volvé a cobrar.')
  })
})
