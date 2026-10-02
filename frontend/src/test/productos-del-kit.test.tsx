// Productos es la pantalla del kit (`libra-ui/comercio/Productos`) con las variantes de VentaLibra (ADR-034): códigos y
// variantes por producto, el stock total, sin eliminar y las unidades de la instalación. El detalle de la pantalla lo prueban
// los tests del kit; acá, que el wrapper activa las variantes y que el contrato de la API (`/api/productos`, `/api/stock`)
// es el que el kit espera. Y, desde el kit v0.92.0 (ADR-053), el interruptor «Vence»: lo ofrece el wrapper sólo a quien tiene
// `vencimientos.marcar` (encargado y admin), aunque el catálogo esté vacío, y nunca a quien no (el staff heredado edita productos pero el
// backend le contesta 403 si cambia la marca).
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { AuthProvider } from '../context/AuthContext'
import { Productos } from '../pages/Productos'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

const YERBA = {
  id: 1, codigo: 'Y1', nombre: 'Yerba Playadito', descripcion: '', precio_venta: 3000, precio_costo: 2000,
  unidad: 'KG', categoria: 'Almacén', categoria_id: 1, stock_minimo: 0, estacion: '', vendible: 1, activo: 1, tipo: 'producto',
}

type Llamada = { url: string; metodo: string; cuerpo: Record<string, unknown> | null }
let llamadas: Llamada[]
let respuestas: Record<string, unknown>
let rol: keyof typeof CAPACIDADES_POR_ROL

/** La pantalla con la sesión del rol de turno (por defecto el encargado: edita productos y marca). */
function abrir() {
  return render(<MemoryRouter><AuthProvider><Productos /></AuthProvider></MemoryRouter>)
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  llamadas = []
  respuestas = {}
  rol = 'encargado'
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role: rol, active: true, nombre: 'Ana', modulos: [],
        capacidades: CAPACIDADES_POR_ROL[rol], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
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
  abrir()
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
  abrir()
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
  abrir()
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
  abrir()
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
  abrir()
  const fila = (await screen.findByText('Yerba Playadito')).closest('tr')!
  expect(screen.getByText('Azúcar Ledesma')).toBeInTheDocument()
  expect(within(fila).getByText(/3\.000/)).toBeInTheDocument()   // el precio de venta sigue
  expect(document.body.textContent).not.toMatch(/2\.000/)         // y el costo que tenía el dato completo no está
  // La edición abre (aunque guardar dé 403 a este rol: el kit no tiene modo de sólo lectura) y no inventa un costo.
  await user.click(within(fila).getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  expect(within(dialogo).getByLabelText(/Nombre/)).toHaveValue('Yerba Playadito')
})

const INTERRUPTOR = /Vence \(maneja lotes y fecha de vencimiento\)/

// ── El interruptor «Vence» (kit v0.92.0, ADR-053) ────────────────────────────

it('el encargado ve el interruptor «Vence» en el alta aunque el catálogo esté vacío, y marcarlo manda `vence: true`', async () => {
  respuestas['GET /api/productos'] = []
  respuestas['POST /api/productos'] = { ...YERBA, vence: true }
  const user = userEvent.setup()
  abrir()
  await user.click(await screen.findByRole('button', { name: /Nuevo producto/ }))
  const dialogo = await screen.findByRole('dialog')
  const interruptor = await within(dialogo).findByRole('switch', { name: INTERRUPTOR })
  expect(interruptor).not.toBeChecked()
  await user.type(within(dialogo).getByLabelText(/Nombre/), 'Leche')
  await user.click(interruptor)
  await user.click(within(dialogo).getByRole('button', { name: /Crear producto|Guardar/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'POST' && l.url === '/api/productos')).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'POST')!.cuerpo).toMatchObject({ nombre: 'Leche', vence: true })
})

it('editar un producto marcado muestra el interruptor prendido y guardar sin tocarlo NO manda la marca', async () => {
  respuestas['GET /api/productos'] = [{ ...YERBA, vence: true }]
  respuestas['PUT /api/productos/1'] = { ...YERBA, vence: true }
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  expect(await within(dialogo).findByRole('switch', { name: INTERRUPTOR })).toBeChecked()
  await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'PUT')!.cuerpo).not.toHaveProperty('vence')
})

it('desmarcar un producto que vence manda `vence: false`', async () => {
  respuestas['GET /api/productos'] = [{ ...YERBA, vence: true }]
  respuestas['PUT /api/productos/1'] = { ...YERBA, vence: false }
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  await user.click(await within(dialogo).findByRole('switch', { name: INTERRUPTOR }))
  await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'PUT')!.cuerpo).toMatchObject({ vence: false })
})

it('el staff heredado edita productos pero no ve el interruptor (marcar es de `vencimientos.marcar`), aunque el backend traiga `vence`', async () => {
  rol = 'staff'
  respuestas['GET /api/productos'] = [{ ...YERBA, vence: true }]
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  expect(within(dialogo).getByLabelText(/Nombre/)).toHaveValue('Yerba Playadito')
  expect(within(dialogo).queryByRole('switch', { name: INTERRUPTOR })).toBeNull()
})

it('el admin también lo ve', async () => {
  rol = 'admin'
  respuestas['GET /api/productos'] = [{ ...YERBA, vence: false }]
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  expect(await within(await screen.findByRole('dialog')).findByRole('switch', { name: INTERRUPTOR })).not.toBeChecked()
})

// Plazo de entrega y stock máximo de reposición (ADR-055, kit v0.96.0): el wrapper los ofrece sólo a quien tiene `reposicion.parametros`
// (encargado y admin). Se leen y se guardan aparte del producto, en `/api/productos/{id}/reposicion`.
const REPOSICION = '/api/productos/1/reposicion'

it.each(['encargado', 'admin'] as const)('el %s ve el plazo y el stock máximo de reposición, los lee del producto y los guarda aparte', async (quien) => {
  rol = quien
  respuestas[`GET ${REPOSICION}`] = { producto_id: 1, nombre: 'Yerba Playadito', plazo_entrega_dias: 7, stock_maximo: null, stock_minimo: 0 }
  respuestas[`PUT ${REPOSICION}`] = { producto_id: 1, nombre: 'Yerba Playadito', plazo_entrega_dias: 7, stock_maximo: 40, stock_minimo: 0 }
  respuestas['PUT /api/productos/1'] = YERBA
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  await waitFor(() => expect(within(dialogo).getByLabelText('Plazo de entrega (días)')).toHaveValue('7'))
  await user.type(within(dialogo).getByLabelText('Stock máximo'), '40')
  await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
  await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT' && l.url === REPOSICION)).toBe(true))
  expect(llamadas.find((l) => l.metodo === 'PUT' && l.url === REPOSICION)!.cuerpo).toEqual({ plazo_entrega_dias: 7, stock_maximo: 40 })
})

it.each(['vendedor', 'cajero', 'deposito'] as const)('el %s no ve esos campos ni se pide nada de reposición del producto', async (quien) => {
  rol = quien
  const user = userEvent.setup()
  abrir()
  await screen.findByText('Yerba Playadito')
  await user.click(screen.getByLabelText('Editar producto'))
  const dialogo = await screen.findByRole('dialog')
  expect(within(dialogo).queryByLabelText('Plazo de entrega (días)')).not.toBeInTheDocument()
  expect(llamadas.some((l) => l.url.includes('/reposicion'))).toBe(false)
})
