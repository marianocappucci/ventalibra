// Productos es la pantalla del kit (`libra-ui/comercio/Productos`) con las variantes de VentaLibra (ADR-034): códigos y
// variantes por producto, el stock total, sin eliminar y las unidades de la instalación. El detalle de la pantalla lo prueban
// los tests del kit; acá, que el wrapper activa las variantes y que el contrato de la API (`/api/productos`, `/api/stock`)
// es el que el kit espera.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { Productos } from '../pages/Productos'

const YERBA = {
  id: 1, codigo: 'Y1', nombre: 'Yerba Playadito', descripcion: '', precio_venta: 3000, precio_costo: 2000,
  unidad: 'KG', categoria: 'Almacén', categoria_id: 1, stock_minimo: 0, estacion: '', vendible: 1, activo: 1, tipo: 'producto',
}

type Llamada = { url: string; metodo: string; cuerpo: Record<string, unknown> | null }
let llamadas: Llamada[]
let respuestas: Record<string, unknown>

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  llamadas = []
  respuestas = {}
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    const clave = `${metodo} ${u.split('?')[0]}`
    if (clave in respuestas) {
      const r = respuestas[clave]
      if (r && typeof r === 'object' && 'status' in r && 'detail' in r) {
        const e = r as { status: number; detail: string }
        return Promise.resolve(json({ detail: e.detail }, e.status))
      }
      return Promise.resolve(json(r))
    }
    if (u.startsWith('/api/productos?') || u === '/api/productos') return Promise.resolve(json([YERBA]))
    if (u === '/api/productos/categorias') return Promise.resolve(json([{ id: 1, nombre: 'Almacén' }]))
    if (u === '/api/productos/unidades') return Promise.resolve(json(['KG', 'UN']))
    if (u === '/api/stock') return Promise.resolve(json({ productos: [{ id: 1, stock_actual: 7 }], alertas: [] }))
    return Promise.resolve(json([]))
  }))
})

it('la fila trae códigos y variantes y el stock total, y no ofrece eliminar (se desactiva)', async () => {
  render(<MemoryRouter><Productos /></MemoryRouter>)
  await screen.findByText('Yerba Playadito')
  expect(screen.getByLabelText('Gestionar códigos y variantes')).toBeInTheDocument()
  expect(screen.getByLabelText('Editar producto')).toBeInTheDocument()
  expect(screen.queryByLabelText('Eliminar producto')).not.toBeInTheDocument()
  expect(screen.getByText('Stock total')).toBeInTheDocument()
  expect(await within(screen.getByText('Yerba Playadito').closest('tr')!).findByText('7')).toBeInTheDocument()
})

it('el alta ofrece las unidades de la instalación y manda el producto del motor', async () => {
  respuestas['POST /api/productos'] = YERBA
  const user = userEvent.setup()
  render(<MemoryRouter><Productos /></MemoryRouter>)
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByRole('button', { name: /Nuevo producto/ }))
  const dialogo = await screen.findByRole('dialog')
  const unidad = within(dialogo).getAllByRole('combobox').find((el) => el.tagName !== 'INPUT')
  expect(unidad).toBeTruthy()
  await user.type(within(dialogo).getByLabelText(/Nombre/), 'Café')
  await user.click(within(dialogo).getByRole('button', { name: /Crear producto|Guardar/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'POST' && l.url === '/api/productos')).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'POST')!.cuerpo).toMatchObject({ nombre: 'Café' })
})

it('el 409 de cambiarle la unidad a un producto con movimientos se muestra en el diálogo', async () => {
  respuestas['PUT /api/productos/1'] = {
    status: 409, detail: 'No se puede cambiar la unidad de un producto que ya tiene movimientos.',
  }
  const user = userEvent.setup()
  render(<MemoryRouter><Productos /></MemoryRouter>)
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
  expect(await within(dialogo).findByText(/ya tiene movimientos/)).toBeInTheDocument()
})

it('el detalle abre los códigos y las variantes del producto', async () => {
  respuestas['GET /api/productos/1/codigos'] = [
    { id: 1, producto_id: 1, tipo: 'internal', codigo: 'Y1', es_principal: true },
    { id: 2, producto_id: 1, tipo: 'scale', codigo: '0012', es_principal: false },
  ]
  respuestas['GET /api/productos/1/variantes'] = [{ id: 5, producto_id: 1, sku: 'Y-500', nombre: '500 g', atributos: {}, activa: true }]
  const user = userEvent.setup()
  render(<MemoryRouter><Productos /></MemoryRouter>)
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Gestionar códigos y variantes'))
  const dialogo = await screen.findByRole('dialog')
  expect(await within(dialogo).findByText('Balanza: 0012')).toBeInTheDocument()
  expect(within(dialogo).getByText('Y-500 — 500 g')).toBeInTheDocument()
})

// Sin `costos.ver` (vendedor, cajero, depósito) el backend saca `precio_costo` de la respuesta (`app/costos.py`, ADR-049).
// La pantalla del kit no tiene un modo «sin costos»: acá se comprueba que con el campo AUSENTE no se rompe (sigue listando,
// buscando y abriendo el detalle) y que el costo real no aparece en ningún lado. Lo que se ve en la columna «Precio costo»
// (sin dato) es una limitación del kit, anotada en ADR-049.
it('con la respuesta de un rol sin costos.ver (sin precio_costo) la pantalla no se rompe y no muestra ningún costo', async () => {
  const { precio_costo: _costo, ...sinCosto } = YERBA
  respuestas['GET /api/productos'] = [sinCosto, { ...sinCosto, id: 2, codigo: 'Y2', nombre: 'Azúcar Ledesma' }]
  const user = userEvent.setup()
  render(<MemoryRouter><Productos /></MemoryRouter>)
  const fila = (await screen.findByText('Yerba Playadito')).closest('tr')!
  expect(screen.getByText('Azúcar Ledesma')).toBeInTheDocument()
  expect(within(fila).getByText(/3\.000/)).toBeInTheDocument()   // el precio de venta sigue
  expect(document.body.textContent).not.toMatch(/2\.000/)         // y el costo que tenía el dato completo no está
  // La edición abre (aunque guardar dé 403 a este rol: el kit no tiene modo de sólo lectura) y no inventa un costo.
  await user.click(within(fila).getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  expect(within(dialogo).getByLabelText(/Nombre/)).toHaveValue('Yerba Playadito')
})
