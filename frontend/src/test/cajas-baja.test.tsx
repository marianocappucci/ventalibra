// Desactivar una caja (2026-09-26): una caja con movimientos no se puede
// eliminar, así que la baja es «desactivar», y las acciones de la fila son
// botones con ícono (con el nombre accesible en `aria-label`).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { Cajas } from '../pages/Cajas'

const base = {
  descripcion: '', medios_pago: ['efectivo'], punto_venta: 3, mp_pos_id: 'POS1',
  es_default: false, sucursal_id: 1, tiene_turno_abierto: false,
}
let cajas: Record<string, unknown>[]
let put: { url: string; body: Record<string, unknown> } | null
let putStatus: number

beforeEach(() => {
  put = null
  putStatus = 200
  cajas = [
    { ...base, id: 2, nombre: 'Mostrador', activo: true },
    { ...base, id: 3, nombre: 'Vieja', activo: false },
  ]
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const ruta = String(url)
    const json = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), {
      status, headers: { 'content-type': 'application/json' },
    }))
    if (ruta.startsWith('/api/cajas/') && init?.method === 'PUT') {
      put = { url: ruta, body: JSON.parse(String(init.body)) }
      return putStatus === 200 ? json({}) : json({ detail: 'La sucursal necesita al menos una caja activa.' }, putStatus)
    }
    if (ruta === '/locations') return json([{ id: 1, name: 'Sucursal' }])
    if (ruta === '/api/cajas') return json(cajas)
    return json([])
  }))
})

it('las acciones de la fila son íconos con nombre accesible, sin botones de texto', async () => {
  render(<Cajas />)
  await screen.findByText('Mostrador')
  for (const nombre of ['Editar Mostrador', 'Desactivar Mostrador', 'Eliminar Mostrador',
    'Marcar Mostrador como predeterminada', 'Activar Vieja']) {
    expect(screen.getByRole('button', { name: nombre })).toBeInTheDocument()
  }
  // Nada de «Baja», «Editar» ni «Marcar predeterminada» como texto visible.
  for (const boton of screen.getAllByRole('button', { name: /Editar|Desactivar|Activar|Eliminar|Marcar/ })) {
    expect(boton.textContent).toBe('')
  }
  expect(screen.queryByText('Baja')).not.toBeInTheDocument()
})

it('desactivar manda el PUT con activo=false y sin tocar el POS de MercadoPago', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: 'Desactivar Mostrador' }))
  await waitFor(() => expect(put).not.toBeNull())
  expect(put!.url).toBe('/api/cajas/2')
  expect(put!.body).toMatchObject({ nombre: 'Mostrador', activo: false, punto_venta: 3 })
  // El PUT omite `mp_pos_id`: el backend lo conserva.
  expect(put!.body).not.toHaveProperty('mp_pos_id')
})

it('activar una caja inactiva manda activo=true', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Vieja')
  await user.click(screen.getByRole('button', { name: 'Activar Vieja' }))
  await waitFor(() => expect(put?.body).toMatchObject({ activo: true }))
})

it('un 409 del backend (última caja activa, turno abierto) se muestra tal cual', async () => {
  putStatus = 409
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: 'Desactivar Mostrador' }))
  expect(await screen.findByText('La sucursal necesita al menos una caja activa.')).toBeInTheDocument()
})
