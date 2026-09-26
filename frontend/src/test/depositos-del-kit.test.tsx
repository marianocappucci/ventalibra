// Sucursales/depósitos, stock y transferencias son las pantallas del kit (`libra-ui/comercio/*`) con las variantes de
// VentaLibra (ADR-033): los dos tipos que no se cambian, sólo lectura para el cajero, el stock con una columna por
// depósito y filtros, y la transferencia con historial. El detalle de cada pantalla lo prueban los tests del kit;
// acá, que los wrappers activan las variantes y que el contrato de la API (`/api/depositos`, `/api/stock`) es el que
// el kit espera.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

// El rol de la sesión, cambiable por test: alta y edición son sólo de admin.
const sesion = vi.hoisted(() => ({ rol: 'admin' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol }, loading: false }),
}))

import { Sucursales } from '../pages/Sucursales'
import { Stock } from '../pages/Stock'
import { Transferencias } from '../pages/Transferencias'

const SALON = { id: 1, nombre: 'Salón', descripcion: '', tipo: 'store', activo: 1, es_default: 1, total_productos: 2 }
const BODEGA = { id: 2, nombre: 'Bodega', descripcion: '', tipo: 'warehouse', activo: 1, es_default: 0, total_productos: 0 }

type Llamada = { url: string; metodo: string; cuerpo: Record<string, unknown> | null }
let llamadas: Llamada[]
let respuestas: Record<string, unknown>

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  sesion.rol = 'admin'
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
    if (u === '/api/depositos') return Promise.resolve(json([SALON, BODEGA]))
    return Promise.resolve(json([]))
  }))
})

describe('Sucursales / depósitos', () => {
  it('lleva su título, los dos tipos con su cuenta y los tipos como palabra, nunca como código', async () => {
    render(<MemoryRouter><Sucursales /></MemoryRouter>)
    expect(await screen.findByText('Sucursales / depósitos')).toBeInTheDocument()
    const grupo = screen.getByRole('group', { name: 'Filtrar por tipo' })
    expect(within(grupo).getByRole('button', { name: 'Sucursales (1)' })).toBeInTheDocument()
    expect(within(grupo).getByRole('button', { name: 'Depósitos (1)' })).toBeInTheDocument()
    expect(screen.queryByText('store')).not.toBeInTheDocument()
    expect(screen.queryByText('warehouse')).not.toBeInTheDocument()
  })

  it('el alta manda el tipo que se está mirando; el 409 del backend se muestra tal cual', async () => {
    respuestas['POST /api/depositos'] = { status: 409, detail: 'La instancia necesita como mínimo una sucursal y un depósito activos.' }
    const user = userEvent.setup()
    render(<MemoryRouter><Sucursales /></MemoryRouter>)
    await screen.findByText('Bodega')
    await user.click(screen.getByRole('button', { name: 'Depósitos (1)' }))
    await user.click(screen.getByRole('button', { name: /Nueva sucursal \/ depósito/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByLabelText('Nombre'), 'Norte')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
    expect(await screen.findByText(/como mínimo una sucursal/)).toBeInTheDocument()
    expect(llamadas.find((l) => l.metodo === 'POST')!.cuerpo).toEqual({ nombre: 'Norte', descripcion: '', tipo: 'warehouse' })
  })

  it('el cajero sólo mira: sin alta, edición, predeterminar ni borrar', async () => {
    sesion.rol = 'staff'
    render(<MemoryRouter><Sucursales /></MemoryRouter>)
    await screen.findByText('Bodega')
    expect(screen.queryByRole('button', { name: /Nueva/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('Ver stock')).toHaveLength(2)
  })

  it('el admin edita: PUT a /api/depositos/{id} con el activo y sin tipo (no se cambia)', async () => {
    respuestas['PUT /api/depositos/2'] = { ...BODEGA, nombre: 'Bodega 2' }
    const user = userEvent.setup()
    render(<MemoryRouter><Sucursales /></MemoryRouter>)
    await screen.findByText('Bodega')
    await user.click(screen.getAllByRole('button', { name: /Editar/ })[1])
    const dialogo = await screen.findByRole('dialog')
    const nombre = within(dialogo).getByLabelText('Nombre')
    await user.clear(nombre)
    await user.type(nombre, 'Bodega 2')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
    expect(llamadas.find((l) => l.metodo === 'PUT')!.cuerpo).toEqual({ nombre: 'Bodega 2', descripcion: '', activo: true })
  })
})

describe('Stock', () => {
  const ITEM = {
    id: 1, codigo: 'Y1', nombre: 'Yerba', unidad: 'kg', categoria: '', stock_minimo: 0, activo: 1,
    stock_actual: 13, por_deposito: { '1': 10, '2': 3 },
  }
  const CERO = { ...ITEM, id: 2, nombre: 'Azúcar', stock_actual: 0, por_deposito: {} }

  beforeEach(() => {
    respuestas['GET /api/stock'] = {
      productos: [ITEM, CERO], alertas: [],
      depositos: [{ id: 1, nombre: 'Salón', tipo: 'store', es_default: 1 }, { id: 2, nombre: 'Bodega', tipo: 'warehouse', es_default: 0 }],
    }
  })

  it('una columna por sucursal/depósito y el total; los depósitos en cero se ven en cero', async () => {
    render(<MemoryRouter><Stock /></MemoryRouter>)
    await screen.findByText('Yerba')
    for (const columna of ['Salón', 'Bodega', 'Total']) expect(screen.getByText(columna)).toBeInTheDocument()
    const fila = screen.getByText('Yerba').closest('tr')!
    expect(within(fila).getByText('10')).toBeInTheDocument()
    expect(within(fila).getByText('13')).toBeInTheDocument()
    // Azúcar no tiene nada en ningún lado: sus dos columnas dicen 0 (no quedan vacías).
    expect(within(screen.getByText('Azúcar').closest('tr')!).getAllByText('0').length).toBeGreaterThanOrEqual(3)
  })

  it('trae el buscador y «sólo los que tienen stock», que era lo que esta pantalla tenía', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Stock /></MemoryRouter>)
    await screen.findByText('Yerba')
    await user.click(screen.getByLabelText('Sólo los que tienen stock'))
    expect(screen.queryByText('Azúcar')).not.toBeInTheDocument()
    await user.click(screen.getByLabelText('Sólo los que tienen stock'))
    await user.type(screen.getByLabelText('Buscar producto'), 'zúc')
    expect(screen.queryByText('Yerba')).not.toBeInTheDocument()
    expect(screen.getByText('Azúcar')).toBeInTheDocument()
  })

  it('ajustar el stock va al depósito elegido', async () => {
    respuestas['POST /api/stock/1/ajuste'] = { producto: {}, stock_actual: 12, stock_deposito: 9 }
    const user = userEvent.setup()
    render(<MemoryRouter><Stock /></MemoryRouter>)
    await screen.findByText('Yerba')
    await user.click(screen.getAllByLabelText('Ajustar stock')[0])
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: 'Salida' }))
    await user.type(within(dialogo).getByRole('spinbutton', { name: /Cantidad/ }), '1')
    await user.click(within(dialogo).getByRole('button', { name: 'Guardar movimiento' }))
    await waitFor(() => expect(llamadas.some((l) => l.url === '/api/stock/1/ajuste')).toBe(true))
    expect(llamadas.find((l) => l.url === '/api/stock/1/ajuste')!.cuerpo).toMatchObject({ modo: 'salida', cantidad: 1, deposito_id: 1 })
  })
})

describe('Transferencias', () => {
  it('muestra el historial de transferencias debajo del formulario', async () => {
    respuestas['GET /api/depositos/transferencias'] = [{
      id: 5, producto_id: 1, producto: 'Yerba', variant_id: null, cantidad: 4, origen_id: 1, origen: 'Salón',
      destino_id: 2, destino: 'Bodega', fecha: '2026-09-26T10:00:00', observaciones: 'reposición del sábado', usuario_id: 1,
    }]
    respuestas['GET /api/productos'] = []
    render(<MemoryRouter><Transferencias /></MemoryRouter>)
    expect(await screen.findByText('Transferencias realizadas')).toBeInTheDocument()
    expect(await screen.findByText('reposición del sábado')).toBeInTheDocument()
  })
})
