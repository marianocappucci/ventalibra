// El POS carga la lista de precio predeterminada (si existe) y aplica cantidad y
// vigencia por fecha/hora en vez del precio plano cuando:
// 1. Agrega un ítem (`elegirItem`) -- consulta `POST /api/listas-precio/{id}/precios`
// 2. Cambia la cantidad de una línea (`cambiarCantidad`) -- igual
// 3. Quita una línea -- las que quedan del mismo producto se vuelven a cotizar (ADR-078)
// El quiebre cuenta la cantidad del PRODUCTO, sumando sus líneas (ADR-078); el motor hace la cuenta.
// El fallback a precio plano nunca bloquea (mismo criterio que `mp-estado`).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { lineasDelPedido, responderPrecios } from './precios-de-lista'

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

const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }

const LOCATIONS = [
  { id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 },
]

function montarRed(
  precioUno = 2500, precioMuchos = precioUno, listas: unknown[] = [LISTA], fallaPrecio = false,
  precioBalanza: number | null = null,
) {
  const llamadas: string[] = []
  const pedidosDePrecios: { lineas: ReturnType<typeof lineasDelPedido>; en: string }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u === '/api/listas-precio/5/precios') {
      pedidosDePrecios.push({ lineas: lineasDelPedido(init), en: JSON.parse(String(init?.body)).en })
      if (fallaPrecio) return Promise.resolve(json({ detail: 'boom' }, 500))
      return Promise.resolve(responderPrecios(init, (cantidad) => (cantidad >= 2 ? precioMuchos : precioUno)))
    }
    if (u === '/api/listas-precio') return Promise.resolve(json(listas))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: precioBalanza, de_balanza: precioBalanza !== null }))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas, pedidosDePrecios }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto = '779000001') {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

async function abrirCantidad() {
  fireEvent.keyDown(window, { key: 'F6' })
  const dialogo = await screen.findByRole('dialog')
  return dialogo
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Precio de lista (cantidad + vigencia)', () => {
  it('carga la lista predeterminada al montar el POS', async () => {
    const { llamadas } = montarRed()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
  })

  it('al agregar, el precio sale de la lista (no del precio plano) y consulta con cantidad y fecha', async () => {
    const { llamadas, pedidosDePrecios } = montarRed(2500)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
    expect(pedidosDePrecios[0].lineas).toEqual([{ producto_id: 3, variante_id: null, cantidad: 1 }])
    expect(pedidosDePrecios[0].en).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('al cambiar la cantidad, vuelve a consultar y aplica el quiebre alcanzado', async () => {
    const { llamadas, pedidosDePrecios } = montarRed(2500, 2000)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)
    await screen.findAllByText(/2\.500,00/)

    const dialogo = await abrirCantidad()
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, '3')
    await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // 3 x 2.000 = 6.000: la cantidad quedó cargada y el precio se refrescó al del quiebre.
    await waitFor(() => expect(screen.getAllByText(/6\.000,00/).length).toBeGreaterThan(0))
    expect(pedidosDePrecios.at(-1)!.lineas).toEqual([{ producto_id: 3, variante_id: null, cantidad: 3 }])
  })

  it('sin lista predeterminada vende al precio plano y no consulta precios', async () => {
    const { llamadas } = montarRed(2500, 2000, [])
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((u) => u.includes('/precios'))).toBe(false)
  })

  it('si la consulta de precio falla, vende al precio plano sin bloquear', async () => {
    const { llamadas } = montarRed(2500, 2000, [LISTA], true)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((u) => u.includes('/precios'))).toBe(true)
  })

  it('una etiqueta de balanza con precio propio no se pisa con el de la lista', async () => {
    const { llamadas } = montarRed(2500, 2000, [LISTA], false, 4200)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/4\.200,00/)).length).toBeGreaterThan(0)
    // Se consulta igual (sus kilos suman al producto), pero la respuesta no pisa el precio de la etiqueta.
    await waitFor(() => expect(llamadas.some((u) => u.includes('/precios'))).toBe(true))
    expect(screen.queryByText(/2\.500,00/)).not.toBeInTheDocument()
  })

  it('la cantidad de una línea de balanza no se cambia: la fija su etiqueta, y el precio de la etiqueta queda (ADR-079)', async () => {
    // Antes (ADR-078) se podía cambiar y el precio de la etiqueta no se pisaba: 3 x 4.200. El servidor ahora valida la línea
    // contra la etiqueta (por importe, la cantidad es 1), así que otra cantidad no se cobraría: el POS no la deja cambiar.
    const { llamadas } = montarRed(2500, 2000, [LISTA], false, 4200)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)
    await screen.findAllByText(/4\.200,00/)

    fireEvent.keyDown(window, { key: 'F6' })

    expect(await screen.findByText(/la fija su etiqueta/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText(/12\.600,00/)).not.toBeInTheDocument()
  })
})
