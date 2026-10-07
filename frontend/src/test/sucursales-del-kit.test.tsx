// Sucursales, depósitos, stock y transferencias son las pantallas del kit (`libra-ui/comercio/*`) con las variantes de
// VentaLibra (ADR-033), sobre el modelo jerárquico sucursal → depósitos: la sucursal (`/api/sucursales`) agrupa
// depósitos (`/api/depositos`, con `branch_id`) y el stock vive en éstos. El detalle de cada pantalla lo prueban los
// tests del kit; acá, que cada página monta la pantalla con SUS rutas y su `soloLectura` según el rol, que la ruta
// `/depositos/:id` existe para el rol que mira, y que el contrato de la API es el que el kit espera.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
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
import { SucursalDetalle } from '../pages/SucursalDetalle'
import { DepositoDetalle } from '../pages/DepositoDetalle'
import { Stock } from '../pages/Stock'
import { Transferencias } from '../pages/Transferencias'

// Ids distintos a propósito: la sucursal 7 tiene los depósitos 12 (de venta) y 13; la sucursal 1, el 11.
const NORTE = {
  id: 7, nombre: 'Norte', codigo: null, direccion: 'Calle 1', activa: true, es_default: false,
  deposito_predeterminado_id: 12, depositos: 2,
}
const CENTRO = {
  id: 1, nombre: 'Centro', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}
const dep = (id: number, nombre: string, branch_id: number, es_default = 0) => (
  { id, nombre, descripcion: '', tipo: 'warehouse', activo: 1, es_default, branch_id, total_productos: 0 }
)
const DEPOSITOS = [dep(11, 'Salón Centro', 1, 1), dep(12, 'Salón Norte', 7), dep(13, 'Bodega Norte', 7)]

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
    if (u.startsWith('/api/sucursales/')) {
      const id = Number(u.split('?')[0].split('/').pop())
      return Promise.resolve(json([CENTRO, NORTE].find((x) => x.id === id) ?? { detail: 'No existe' }))
    }
    if (u.startsWith('/api/sucursales')) return Promise.resolve(json([CENTRO, NORTE]))
    if (u === '/api/depositos') return Promise.resolve(json(DEPOSITOS))
    if (u.match(/^\/api\/depositos\/\d+\/stock$/)) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

function enRuta(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/sucursales" element={<Sucursales />} />
        <Route path="/sucursales/:id" element={<SucursalDetalle />} />
        <Route path="/depositos/:id" element={<DepositoDetalle />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Sucursales', () => {
  it('lleva su título, lista las sucursales y enlaza al detalle y a la transferencia de VentaLibra', async () => {
    enRuta('/sucursales')
    expect(await screen.findByText('Sucursales')).toBeInTheDocument()
    await screen.findByText('Norte')
    // Cada tarjeta lleva a `/sucursales/{id}` (el id de la sucursal, no el de un depósito).
    const hrefs = screen.getAllByRole('link', { name: /Ver depósitos/ }).map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['/sucursales/1', '/sucursales/7'])
    expect(screen.getByRole('link', { name: /Transferir stock/ })).toHaveAttribute('href', '/transferencias')
    // La pantalla ya no es la plana con tipos: nada de `store`/`warehouse` ni de filtro por tipo.
    expect(screen.queryByRole('group', { name: 'Filtrar por tipo' })).not.toBeInTheDocument()
    expect(screen.queryByText('store')).not.toBeInTheDocument()
    expect(llamadas.some((l) => l.url.startsWith('/api/sucursales'))).toBe(true)
    expect(llamadas.some((l) => l.url === '/api/depositos')).toBe(false)
  })

  it('el admin da de alta con «Nueva sucursal»; el 409 del backend se muestra tal cual', async () => {
    respuestas['POST /api/sucursales'] = { status: 409, detail: 'Ya existe una sucursal con ese código.' }
    const user = userEvent.setup()
    enRuta('/sucursales')
    await screen.findByText('Norte')
    await user.click(screen.getByRole('button', { name: /Nueva sucursal/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByLabelText(/^Nombre\s*\*/), 'Sur')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar|Crear/ }))
    expect(await screen.findByText(/Ya existe una sucursal/)).toBeInTheDocument()
    expect(llamadas.find((l) => l.metodo === 'POST')!.cuerpo).toMatchObject({ nombre: 'Sur' })
  })

  it('el cajero sólo mira: sin alta ni edición, pero sí ve los depósitos', async () => {
    sesion.rol = 'cajero'
    enRuta('/sucursales')
    await screen.findByText('Norte')
    expect(screen.queryByRole('button', { name: /Nueva/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Ver depósitos/ })).toHaveLength(2)
  })
})

describe('Detalle de una sucursal', () => {
  it('lista los depósitos de ESA sucursal, marca el de venta y cada uno lleva a /depositos/{id}', async () => {
    enRuta('/sucursales/7')
    expect(await screen.findByText('Bodega Norte')).toBeInTheDocument()
    expect(screen.queryByText('Salón Centro')).not.toBeInTheDocument()
    expect(screen.getAllByText('Depósito de venta').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: /Ver stock/ }).map((a) => a.getAttribute('href'))).toEqual(['/depositos/12', '/depositos/13'])
    expect(screen.getByRole('link', { name: /Volver/ })).toHaveAttribute('href', '/sucursales')
    expect(screen.getByRole('link', { name: /Transferir stock/ })).toHaveAttribute('href', '/transferencias')
    expect(llamadas.some((l) => l.url === '/api/sucursales/7')).toBe(true)
  })

  it('el admin agrega un depósito a la sucursal: el POST manda su branch_id', async () => {
    respuestas['POST /api/depositos'] = dep(20, 'Freezer', 7)
    const user = userEvent.setup()
    enRuta('/sucursales/7')
    await screen.findByText('Bodega Norte')
    await user.click(screen.getByRole('button', { name: /Nuevo depósito/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByLabelText(/^Nombre\s*\*/), 'Freezer')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar|Crear/ }))
    await waitFor(() => expect(llamadas.some((l) => l.metodo === 'POST')).toBe(true))
    expect(llamadas.find((l) => l.metodo === 'POST')!.cuerpo).toMatchObject({ nombre: 'Freezer', branch_id: 7 })
  })

  it('el cajero sólo mira: sin alta, edición, «Depósito de venta» ni borrar', async () => {
    sesion.rol = 'cajero'
    enRuta('/sucursales/7')
    await screen.findByText('Bodega Norte')
    expect(screen.queryByRole('button', { name: /Nuevo depósito/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Depósito de venta/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Ver stock/ })).toHaveLength(2)
  })
})

describe('Detalle de un depósito', () => {
  it('muestra el depósito, vuelve a la lista de sucursales y transfiere por /transferencias', async () => {
    enRuta('/depositos/12')
    expect(await screen.findByText('Salón Norte')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Volver/ })).toHaveAttribute('href', '/sucursales')
    expect(screen.getByRole('link', { name: /Transferir/ })).toHaveAttribute('href', '/transferencias')
    expect(llamadas.some((l) => l.url === '/api/depositos/12/stock')).toBe(true)
  })

  it('el admin edita: PUT a /api/depositos/{id} con el activo y sin tipo ni branch_id', async () => {
    respuestas['PUT /api/depositos/12'] = { ...dep(12, 'Salón Norte 2', 7) }
    const user = userEvent.setup()
    enRuta('/depositos/12')
    await screen.findByText('Salón Norte')
    await user.click(screen.getByRole('button', { name: /Editar/ }))
    const dialogo = await screen.findByRole('dialog')
    const nombre = within(dialogo).getByLabelText('Nombre')
    await user.clear(nombre)
    await user.type(nombre, 'Salón Norte 2')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
    expect(llamadas.find((l) => l.metodo === 'PUT')!.cuerpo).toEqual({ nombre: 'Salón Norte 2', descripcion: '', activo: true })
  })

  it('el cajero sólo mira: sin edición', async () => {
    sesion.rol = 'cajero'
    enRuta('/depositos/12')
    await screen.findByText('Salón Norte')
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
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
      depositos: [{ id: 1, nombre: 'Salón', branch_id: 1, es_default: 1 }, { id: 2, nombre: 'Bodega', branch_id: 1, es_default: 0 }],
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
