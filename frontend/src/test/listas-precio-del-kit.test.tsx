// Las listas de precio son las pantallas del kit (`libra-ui/comercio/ListasPrecio`, `ListaPrecioDetalle`) sobre los routers del
// motor (ADR-034); VentaLibra suma los quiebres por cantidad (`conQuiebres`). El detalle de las pantallas lo prueban los tests del
// kit; acá, que se montan y que el detalle trae la variante de VentaLibra.
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import { ListaPrecioDetalle } from '../pages/ListaPrecioDetalle'
import { ListasPrecio } from '../pages/ListasPrecio'

const LISTA = { id: 3, nombre: 'Mayorista', descripcion: 'por bulto', activa: 1, es_default: 0, created_at: '2026-09-27' }
const ITEM = {
  id: 1, codigo: 'Y1', nombre: 'Yerba Playadito', unidad: 'kg', categoria: 'Almacén', precio_base: 3000, precio: 2500,
  precio_lista: 2500, precio_venta: 3000,
}

let llamadas: string[]

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } }))
    if (u === '/api/listas-precio') return json([LISTA])
    if (u.startsWith('/api/listas-precio/3/items')) return json([ITEM])
    return json([])
  }))
})

it('lista las listas de precio', async () => {
  render(<MemoryRouter><ListasPrecio /></MemoryRouter>)
  expect(await screen.findByText('Mayorista')).toBeInTheDocument()
})

it('el detalle de una lista trae los quiebres por cantidad', async () => {
  render(
    <MemoryRouter initialEntries={['/listas-precio/3']}>
      <Routes><Route path="/listas-precio/:id" element={<ListaPrecioDetalle />} /></Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('Yerba Playadito')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Quiebres' })).toBeInTheDocument()
})
