// El POS muestra el ahorro de las promociones («llevá N pagá M» y combos, ADR-043) y cobra
// el total con el ahorro descontado -- el mismo que el servidor registra al vender
// (`OpcionesVentas.promociones`). `Cobrar` espera el cálculo para no abrir el cobro con un
// total viejo, y si el cálculo falla se vende sin descuento, sin bloquear.
import { render, screen, waitFor, within } from '@testing-library/react'
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
const ITEM = { id: 3, nombre: 'Alfajor', sku: 'ALF1', barcode: '779000001', unidad: 'u', precio_venta: 100, activo: 1 }
const LOCATIONS = [{ id: 1, nombre: 'Salón', descripcion: '', tipo: 'store', activo: 1, es_default: 1 }]

const DOS_POR_UNO = { aplicadas: [{ promocion_id: 7, nombre: '2x1 alfajores', veces: 1, ahorro: 100 }], ahorro: 100 }

type Calculo = () => Promise<Response>

function montarRed(calculo: Calculo) {
  const llamadas: { url: string; body?: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    llamadas.push({ url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (u.includes('/api/promociones/calcular')) return calculo()
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/depositos')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto: string) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

const botonCobrar = () => screen.getByRole('button', { name: /^Cobrar/ })

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Promociones en el POS', () => {
  it('muestra subtotal, la promoción y el total con el ahorro, y cobra ese total', async () => {
    const { llamadas } = montarRed(() => Promise.resolve(json(DOS_POR_UNO)))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '2*779000001')

    expect(await screen.findByText('2x1 alfajores')).toBeInTheDocument()
    expect(screen.getByText('Subtotal').parentElement).toHaveTextContent(/\$200,00/)
    expect(screen.getByText('2x1 alfajores').parentElement).toHaveTextContent(/−\$100,00/)
    // Total grande: 200 − 100.
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$100,00')

    // Lo que el POS le pide al motor: las líneas con producto, cantidad y precio, y el instante.
    const consulta = llamadas.filter((l) => l.url.includes('/api/promociones/calcular')).at(-1)!
    expect(consulta.body).toMatchObject({ items: [{ producto_id: 3, qty: 2, precio: 100 }] })
    expect((consulta.body as { en: string }).en).toMatch(/^\d{4}-\d{2}-\d{2}T/)

    await waitFor(() => expect(botonCobrar()).toBeEnabled())
    await user.click(botonCobrar())
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/Cobrar \$100,00/)).toBeInTheDocument()
  })

  it('sin promoción aplicable no muestra subtotal ni descuento', async () => {
    montarRed(() => Promise.resolve(json({ aplicadas: [], ahorro: 0 })))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '779000001')
    await screen.findByText(/Alfajor/)
    await waitFor(() => expect(botonCobrar()).toBeEnabled())
    expect(screen.queryByText('Subtotal')).not.toBeInTheDocument()
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$100,00')
  })

  it('Cobrar espera el cálculo: no se abre el cobro con un total viejo', async () => {
    let resolver: (r: Response) => void = () => {}
    montarRed(() => new Promise<Response>((res) => { resolver = res }))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '2*779000001')
    await screen.findByText(/Alfajor/)
    expect(botonCobrar()).toBeDisabled()

    resolver(json(DOS_POR_UNO))
    await waitFor(() => expect(botonCobrar()).toBeEnabled())
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$100,00')
  })

  it('si el cálculo falla, vende sin descuento y no bloquea el cobro', async () => {
    montarRed(() => Promise.resolve(json({ detail: 'boom' }, 500)))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '2*779000001')
    await screen.findByText(/Alfajor/)
    await waitFor(() => expect(botonCobrar()).toBeEnabled())
    expect(screen.queryByText('Subtotal')).not.toBeInTheDocument()
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$200,00')
  })

  it('una respuesta que no tiene la forma esperada se trata como sin promociones', async () => {
    montarRed(() => Promise.resolve(json([])))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user, '779000001')
    await screen.findByText(/Alfajor/)
    await waitFor(() => expect(botonCobrar()).toBeEnabled())
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$100,00')
  })
})
