// Las cajas son la pantalla del kit (`libra-ui/comercio/Cajas`) con las variantes de VentaLibra (ADR-032): la
// caja es de una sucursal, sólo las que venden admiten cajas nuevas, se activa y desactiva desde la tarjeta y no
// hay pantalla de movimientos. El detalle de la pantalla lo prueban los tests del kit; acá, que el wrapper
// arma bien las variantes y que el contrato de la API (`/locations`, `/api/cajas`) es el que el kit espera.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { _resetCacheDeMedios } from 'libra-ui/comercio/medios-pago'
import { Cajas } from '../pages/Cajas'

const base = {
  descripcion: '', medios_pago: ['efectivo'], punto_venta: 3, mp_pos_id: 'POS1',
  es_default: 0, sucursal_id: 1, sucursal_nombre: 'Sucursal', tiene_turno_abierto: false,
}
const SUCURSAL = { id: 1, name: 'Sucursal', location_type: 'store', active: true }
const DEPOSITO = { id: 2, name: 'Depósito', location_type: 'warehouse', active: true }

let cajas: Record<string, unknown>[]
let locations: Record<string, unknown>[]
let llamadas: { metodo: string; url: string; body?: Record<string, unknown> }[]
let putStatus: number

beforeEach(() => {
  _resetCacheDeMedios()
  llamadas = []
  putStatus = 200
  locations = [SUCURSAL, DEPOSITO]
  cajas = [
    { ...base, id: 2, nombre: 'Mostrador', activo: 1 },
    { ...base, id: 3, nombre: 'Vieja', activo: 0 },
  ]
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const ruta = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: ruta, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const json = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), {
      status, headers: { 'content-type': 'application/json' },
    }))
    if (metodo === 'PUT') {
      return putStatus === 200 ? json({}) : json({ detail: 'La sucursal necesita al menos una caja activa.' }, putStatus)
    }
    if (metodo === 'POST') return json({})
    if (ruta === '/locations') return json(locations)
    if (ruta === '/api/cajas/medios-disponibles') return json([{ id: 'efectivo', label: 'Efectivo' }])
    if (ruta === '/api/cajas') return json(cajas)
    return json([])
  }))
})

it('cada caja dice su sucursal y su estado; no hay enlace a movimientos de caja', async () => {
  render(<Cajas />)
  await screen.findByText('Mostrador')
  expect(screen.getAllByText('Sucursal: Sucursal')).toHaveLength(2)
  expect(screen.getByText('Inactiva')).toBeInTheDocument()
  expect(screen.queryByText('Ver movimientos')).not.toBeInTheDocument()
  // Acciones con ícono y nombre accesible.
  for (const nombre of ['Desactivar Mostrador', 'Activar Vieja']) {
    expect(screen.getByRole('button', { name: nombre })).toBeInTheDocument()
  }
})

it('desactivar manda el PUT con todos los campos: el motor pisa el POS de MercadoPago si falta', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: 'Desactivar Mostrador' }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
  const put = llamadas.find((l) => l.metodo === 'PUT')!
  expect(put.url).toBe('/api/cajas/2')
  expect(put.body).toEqual({
    nombre: 'Mostrador', descripcion: '', medios_pago: ['efectivo'], punto_venta: 3, mp_pos_id: 'POS1', activo: false,
  })
})

it('activar una caja inactiva manda activo=true', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Vieja')
  await user.click(screen.getByRole('button', { name: 'Activar Vieja' }))
  await waitFor(() => expect(llamadas.find((l) => l.metodo === 'PUT')?.body).toMatchObject({ activo: true }))
})

it('un 409 del backend (última caja activa, turno abierto) se muestra tal cual', async () => {
  putStatus = 409
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: 'Desactivar Mostrador' }))
  expect(await screen.findByText('La sucursal necesita al menos una caja activa.')).toBeInTheDocument()
})

it('el alta va a la sucursal que vende (preseleccionada) y manda sucursal_id', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: /Nueva caja/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Mostrador 2')
  await user.click(screen.getByRole('button', { name: /Crear caja/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'POST')).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'POST')!.body).toMatchObject({ nombre: 'Mostrador 2', sucursal_id: 1 })
})

it('sin ninguna sucursal que venda (sólo depósitos o inactivas) no se puede crear una caja', async () => {
  locations = [DEPOSITO, { ...SUCURSAL, active: false }]
  render(<Cajas />)
  await screen.findByText('Mostrador')
  expect(screen.getByRole('button', { name: /Nueva caja/ })).toBeDisabled()
})
