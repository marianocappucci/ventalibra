import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { Cajas } from '../pages/Cajas'

const caja = {
  id: 2, nombre: 'Mostrador', descripcion: '', medios_pago: [],
  punto_venta: null, mp_pos_id: 'BIOKOCAJA01', activo: true,
  es_default: false, sucursal_id: 1, tiene_turno_abierto: false,
}
let putBody: Record<string, unknown> | null

beforeEach(() => {
  putBody = null
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const ruta = String(url)
    if (ruta === '/api/cajas/2' && init?.method === 'PUT') {
      putBody = JSON.parse(String(init.body))
      return Promise.resolve(new Response(JSON.stringify({ ...caja, ...putBody }), {
        status: 200, headers: { 'content-type': 'application/json' },
      }))
    }
    const data = ruta === '/locations'
      ? [{ id: 1, name: 'Sucursal' }]
      : ruta === '/api/cajas' ? [caja] : []
    return Promise.resolve(new Response(JSON.stringify(data), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
  }))
})

it('editar nombre no borra el POS de MercadoPago y permite cambiarlo', async () => {
  const user = userEvent.setup()
  render(<Cajas />)
  await screen.findByText('Mostrador')
  await user.click(screen.getByRole('button', { name: /^Editar/ }))
  const pos = screen.getByRole('textbox', { name: 'ID del POS de MercadoPago (opcional)' })
  expect(pos).toHaveValue('BIOKOCAJA01')
  await user.click(screen.getByRole('button', { name: 'Guardar' }))
  await waitFor(() => expect(putBody).toMatchObject({ mp_pos_id: 'BIOKOCAJA01' }))

  await user.click(screen.getByRole('button', { name: /^Editar/ }))
  await user.clear(screen.getByRole('textbox', { name: 'ID del POS de MercadoPago (opcional)' }))
  await user.click(screen.getByRole('button', { name: 'Guardar' }))
  await waitFor(() => expect(putBody).toMatchObject({ mp_pos_id: null }))
})
