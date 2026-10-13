// Las listas de precio son las pantallas del kit (`libra-ui/comercio/ListasPrecio`, `ListaPrecioDetalle`) sobre los routers del
// motor (ADR-034); VentaLibra suma los quiebres por cantidad (`conQuiebres`). El detalle de las pantallas lo prueban los tests del
// kit; acá, que se montan y que el detalle trae la variante de VentaLibra.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import { ListaPrecioDetalle } from '../pages/ListaPrecioDetalle'
import { ListasPrecio } from '../pages/ListasPrecio'

const LISTA = { id: 3, nombre: 'Mayorista', descripcion: 'por bulto', activa: 1, es_default: 0, created_at: '2026-09-27' }
const ITEM = {
  id: 1, codigo: 'Y1', nombre: 'Yerba Playadito', unidad: 'kg', categoria: 'Almacén', precio_base: 3000, precio: 2500,
  precio_lista: 2500, precio_venta: 3000,
}

const SUCURSALES = [
  { id: 1, nombre: 'Centro', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 },
  { id: 2, nombre: 'Norte', codigo: null, direccion: null, activa: true, es_default: false, deposito_predeterminado_id: 22, depositos: 1 },
]

let llamadas: string[]

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } }))
    if (u === '/api/listas-precio') return json([LISTA])
    if (u.startsWith('/api/listas-precio/3/items')) return json([ITEM])
    if (u === '/api/sucursales') return json(SUCURSALES)
    return json([])
  }))
})

it('lista las listas de precio', async () => {
  render(<MemoryRouter><ListasPrecio /></MemoryRouter>)
  expect(await screen.findByText('Mayorista')).toBeInTheDocument()
})

it('el detalle de una lista trae los quiebres por cantidad y las promociones con vigencia', async () => {
  render(
    <MemoryRouter initialEntries={['/listas-precio/3']}>
      <Routes><Route path="/listas-precio/:id" element={<ListaPrecioDetalle />} /></Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('Yerba Playadito')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Quiebres' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Promociones' })).toBeInTheDocument()
})

// libra-ui 0.147.0 (ADR-059 del kit; ADR-083 de este repo): con libracommerce 0.59.0 la validación de la venta respeta el precio de la
// sucursal, así que el alta de una promoción ofrece el select «Sucursal» (`conSucursal`). Con dos o más sucursales activas.
it('«Nueva promoción» ofrece la sucursal (`conSucursal`)', async () => {
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/listas-precio/3']}>
      <Routes><Route path="/listas-precio/:id" element={<ListaPrecioDetalle />} /></Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByRole('button', { name: 'Promociones' }))
  const dialogo = await screen.findByRole('dialog')
  expect(within(dialogo).getByText('Nueva promoción')).toBeInTheDocument()
  expect(await within(dialogo).findByLabelText(/Sucursal/)).toBeInTheDocument()
  expect(llamadas).toContain('/api/sucursales')
})
