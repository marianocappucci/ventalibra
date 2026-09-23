// La grilla de stock: cuánto hay de cada producto y EN QUÉ sucursal.
//
// Lo que cuidan estos tests, por orden de lo que dolería:
// - que el reparto se vea y no sólo el total (dos repartos muy distintos dan
//   el mismo total, y uno de los dos deja un local en cero);
// - que un depósito vacío aparezca en 0 y no se omita;
// - que un negativo se vea como negativo y no se maquille.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

import { Stock } from '../pages/Stock'

const GRILLA = {
  depositos: [
    { id: 1, nombre: 'Centro', tipo: 'store' },
    { id: 2, nombre: 'Costanera', tipo: 'store' },
    { id: 3, nombre: 'Depósito', tipo: 'warehouse' },
  ],
  items: [
    {
      item_id: 10, nombre: 'Dulce de leche 1kg', unit_code: 'u',
      por_deposito: { '1': '6', '2': '4', '3': '0' }, total: '10',
    },
    {
      item_id: 11, nombre: 'Todo en un local', unit_code: 'u',
      por_deposito: { '1': '10', '2': '0', '3': '0' }, total: '10',
    },
    {
      item_id: 12, nombre: 'Sin stock', unit_code: 'u',
      por_deposito: { '1': '0', '2': '0', '3': '0' }, total: '0',
    },
    {
      item_id: 13, nombre: 'En negativo', unit_code: 'u',
      por_deposito: { '1': '-2', '2': '0', '3': '0' }, total: '-2',
    },
  ],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function montarRed(grilla: unknown = GRILLA) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).startsWith('/stock/por-deposito/grilla')) return Promise.resolve(json(grilla))
    return Promise.resolve(json({}))
  }))
}

function filaDe(nombre: string) {
  return screen.getByText(nombre).closest('tr') as HTMLElement
}

/** Los valores de una fila, POR COLUMNA.
 *
 *  Se lee por celda y no por texto a propósito: una fila puede tener el mismo
 *  número dos veces —10 en Centro y 10 en Total— y un `getByText('10')`
 *  encuentra los dos, así que no distingue el reparto del total, que es
 *  justamente lo que estos tests tienen que mirar.
 *
 *  Columnas: 0 Producto · 1 Unidad · 2 Centro · 3 Costanera · 4 Depósito · 5 Total */
function celdas(nombre: string): string[] {
  return within(filaDe(nombre)).getAllByRole('cell').map((c) => c.textContent ?? '')
}

beforeEach(() => { montarRed() })

it('hay una columna por sucursal, además del total', async () => {
  render(<Stock />)
  await screen.findByText('Dulce de leche 1kg')

  for (const nombre of ['Centro', 'Costanera', 'Depósito', 'Total']) {
    expect(screen.getByRole('columnheader', { name: new RegExp(nombre) })).toBeInTheDocument()
  }
})

it('🔴 el reparto se ve: dos productos con el MISMO total se distinguen', async () => {
  // Es lo que esta pantalla agrega sobre la tarjeta de Reportes, que sólo
  // muestra el total. Sin el reparto, estos dos son indistinguibles.
  render(<Stock />)
  await screen.findByText('Dulce de leche 1kg')

  const repartido = celdas('Dulce de leche 1kg')
  const concentrado = celdas('Todo en un local')

  // Mismo total...
  expect(repartido[5]).toBe('10')
  expect(concentrado[5]).toBe('10')
  // ...y reparto completamente distinto: uno deja Costanera en CERO.
  expect(repartido.slice(2, 5)).toEqual(['6', '4', '0'])
  expect(concentrado.slice(2, 5)).toEqual(['10', '0', '0'])
})

it('🔑 un depósito vacío aparece en 0 y no se omite', async () => {
  // Un depósito que falta de la fila es indistinguible de uno vacío, y la
  // pregunta es justamente "¿de dónde saco esto?".
  render(<Stock />)
  await screen.findByText('Dulce de leche 1kg')

  // El Depósito no tiene nada de este producto, y aun asi tiene su celda.
  expect(celdas('Dulce de leche 1kg')[4]).toBe('0')
})

it('🔴 un stock negativo se muestra como negativo', async () => {
  // Significa que se vendió más de lo que el sistema creía tener. Taparlo con
  // un 0 borra la señal de que el inventario está mal cargado.
  render(<Stock />)
  await screen.findByText('En negativo')
  expect(celdas('En negativo')[2]).toBe('-2')
  expect(celdas('En negativo')[5]).toBe('-2')
})

it('el filtro deja sólo los que tienen stock', async () => {
  const user = userEvent.setup()
  render(<Stock />)
  await screen.findByText('Sin stock')

  await user.click(screen.getByLabelText('Sólo los que tienen stock'))
  await waitFor(() => expect(screen.queryByText('Sin stock')).not.toBeInTheDocument())
  expect(screen.getByText('Dulce de leche 1kg')).toBeInTheDocument()
  // El negativo NO es "sin stock": sigue estando.
  expect(screen.getByText('En negativo')).toBeInTheDocument()
})

it('la búsqueda filtra por nombre', async () => {
  const user = userEvent.setup()
  render(<Stock />)
  await screen.findByText('Dulce de leche 1kg')

  await user.type(screen.getByLabelText('Buscar producto'), 'dulce')
  await waitFor(() => expect(screen.queryByText('Todo en un local')).not.toBeInTheDocument())
  expect(screen.getByText('Dulce de leche 1kg')).toBeInTheDocument()
})

it('sin sucursales cargadas lo dice, en vez de una tabla vacía', async () => {
  montarRed({ depositos: [], items: [] })
  render(<Stock />)
  expect(
    await screen.findByText('Todavía no hay sucursales ni depósitos cargados.'),
  ).toBeInTheDocument()
})
