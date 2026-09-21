// Transferencias entre sucursales (2026-09-21).
//
// Lo que cuidan estos tests, por orden de lo que dolería:
// - que no se pueda disparar una transferencia incompleta o de cantidad 0
//   (el ledger es inmutable: lo que se escribe mal se arregla con otro
//   movimiento, no borrando);
// - que el 422 del backend se VEA, en vez de morir en silencio;
// - que la pantalla diga que no hay recepción pendiente del otro lado.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: 'admin' }, loading: false }),
}))

import { Transferencias } from '../pages/Transferencias'

const LOCATIONS = [
  { id: 1, name: 'Centro', branch_id: null, location_type: 'store', active: true, is_default: true },
  { id: 2, name: 'Costanera', branch_id: null, location_type: 'store', active: true, is_default: false },
]

const ITEMS = [
  {
    id: 7, item_type: 'product', name: 'Dulce de leche 1kg', description: '',
    category_id: null, unit_code: 'u', active: true, sellable: true,
    purchasable: true, default_sale_price: '0', default_cost: '0',
  },
]

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function montarRed(opciones: { postStatus?: number; postDetail?: string } = {}) {
  llamadas = []
  let historial: unknown[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const cuerpo = init?.body ? JSON.parse(String(init.body)) : null
    llamadas.push({ url: u, metodo, cuerpo })

    if (metodo === 'POST' && u === '/stock/transferir') {
      const status = opciones.postStatus ?? 200
      if (status >= 400) {
        return Promise.resolve(json({ detail: opciones.postDetail ?? 'error' }, status))
      }
      historial = [{
        id: 1, item_id: 7, item: 'Dulce de leche 1kg', variant_id: null,
        cantidad: '4', origen_id: 1, origen: 'Centro',
        destino_id: 2, destino: 'Costanera',
        fecha: '2026-09-21T10:00:00', nota: '', usuario_id: 1,
      }]
      return Promise.resolve(json({
        origen: { id: 1, nombre: 'Centro', stock: '6' },
        destino: { id: 2, nombre: 'Costanera', stock: '4' },
        cantidad: '4',
      }))
    }
    if (u.startsWith('/stock/transferencias/historial')) return Promise.resolve(json(historial))
    if (u === '/locations') return Promise.resolve(json(LOCATIONS))
    if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
    return Promise.resolve(json({}))
  }))
}

async function elegirDeposito(etiqueta: string, nombre: string) {
  const user = userEvent.setup()
  await user.click(screen.getByLabelText(etiqueta))
  await user.click(await screen.findByRole('option', { name: nombre }))
}

beforeEach(() => { montarRed() })

it('el boton arranca deshabilitado: sin producto ni depositos no hay nada que mover', async () => {
  render(<Transferencias />)
  await screen.findByText('Mover mercadería')
  expect(screen.getByRole('button', { name: 'Transferir' })).toBeDisabled()
})

it('🔴 con cantidad 0 el boton NO se habilita', async () => {
  // `Number(x) || 0` mandaría un 0 en silencio, y una transferencia de nada
  // igual queda escrita en el ledger. Mismo defecto que el POS ya tuvo dos
  // veces (ver `pos-cantidad-invalida.test.tsx`).
  const user = userEvent.setup()
  render(<Transferencias />)
  await screen.findByText('Mover mercadería')

  await user.click(screen.getByLabelText('Producto'))
  await user.click(await screen.findByRole('option', { name: 'Dulce de leche 1kg' }))
  await elegirDeposito('Desde', 'Centro')
  await elegirDeposito('Hasta', 'Costanera')
  await user.type(screen.getByLabelText('Cantidad'), '0')

  expect(screen.getByRole('button', { name: 'Transferir' })).toBeDisabled()
  expect(screen.getByText('Escribí una cantidad mayor que cero.')).toBeInTheDocument()
  expect(llamadas.some((l) => l.url === '/stock/transferir')).toBe(false)
})

it('🔴 con el mismo deposito de los dos lados avisa y no deja transferir', async () => {
  const user = userEvent.setup()
  render(<Transferencias />)
  await screen.findByText('Mover mercadería')

  await user.click(screen.getByLabelText('Producto'))
  await user.click(await screen.findByRole('option', { name: 'Dulce de leche 1kg' }))
  await elegirDeposito('Desde', 'Centro')
  await elegirDeposito('Hasta', 'Centro')
  await user.type(screen.getByLabelText('Cantidad'), '4')

  expect(screen.getByText(/no movería nada/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Transferir' })).toBeDisabled()
})

it('una transferencia valida manda el cuerpo esperado y muestra como quedo cada lado', async () => {
  const user = userEvent.setup()
  render(<Transferencias />)
  await screen.findByText('Mover mercadería')

  await user.click(screen.getByLabelText('Producto'))
  await user.click(await screen.findByRole('option', { name: 'Dulce de leche 1kg' }))
  await elegirDeposito('Desde', 'Centro')
  await elegirDeposito('Hasta', 'Costanera')
  await user.type(screen.getByLabelText('Cantidad'), '4')
  await user.click(screen.getByRole('button', { name: 'Transferir' }))

  await waitFor(() => {
    const envio = llamadas.find((l) => l.url === '/stock/transferir')
    expect(envio?.cuerpo).toEqual({
      item_id: 7, origen_id: 1, destino_id: 2, cantidad: '4', nota: '',
    })
  })
  expect(await screen.findByText(/Quedan 6 en el/)).toBeInTheDocument()
  // Y el historial se releyó: la fila nueva está en pantalla.
  expect(await screen.findByText('Costanera', { selector: 'td' })).toBeInTheDocument()
})

it('🔴 un 422 del backend se VE en pantalla', async () => {
  montarRed({ postStatus: 422, postDetail: 'No hay stock suficiente en el origen.' })
  const user = userEvent.setup()
  render(<Transferencias />)
  await screen.findByText('Mover mercadería')

  await user.click(screen.getByLabelText('Producto'))
  await user.click(await screen.findByRole('option', { name: 'Dulce de leche 1kg' }))
  await elegirDeposito('Desde', 'Centro')
  await elegirDeposito('Hasta', 'Costanera')
  await user.type(screen.getByLabelText('Cantidad'), '99')
  await user.click(screen.getByRole('button', { name: 'Transferir' }))

  expect(await screen.findByText('No hay stock suficiente en el origen.')).toBeInTheDocument()
})

it('la pantalla dice que el destino cuenta la mercaderia en el acto', async () => {
  // No es cosmético: sin esto alguien supone que hay una recepción pendiente
  // del otro lado, y no la hay.
  render(<Transferencias />)
  expect(await screen.findByText(/no queda\s+pendiente de recepción/)).toBeInTheDocument()
})
