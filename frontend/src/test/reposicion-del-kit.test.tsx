// Reposición sugerida es la pantalla del kit (`libra-ui/comercio/Reposicion`) sobre el router del motor (`/api/reportes/reposicion`, ADR-051).
// La cuenta (rotación, cobertura, quiebres, lo que viene en camino) es del motor y se prueba allá; acá, que la ruta existe, que es de quien
// tiene `reposicion.ver` (admin y encargado) y que la pantalla habla con la API que el kit espera, incluidos los dos pedidos de sus filtros
// (`/api/sucursales` y `/api/productos/categorias`), que si fallan no la rompen.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

let llamadas: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const REPOSICION = {
  dias_rotacion: 30, dias_cobertura: 15, plazo_entrega_dias: 3, sucursal_id: null, categoria: null, producto_id: null, solo_a_pedir: true,
  resumen: { productos: 1, a_pedir: 1, posible_quiebre: 0, sin_ventas: 0 },
  productos: [{
    producto_id: 1, codigo: 'YERBA-1', nombre: 'Yerba 1kg', unidad: 'u', categoria: 'Almacén', stock: 13, en_camino: 4,
    en_camino_sin_sucursal: 0, stock_minimo: 30, unidades_vendidas: 7, dias_con_stock: 30, rotacion_diaria: 1, cobertura_dias: 13,
    sugerido: 13, motivo: 'ambos', sin_ventas: false, posible_quiebre: false, variantes: 0,
  }],
}

type Rol = 'admin' | 'encargado' | 'cajero' | 'vendedor' | 'deposito'

/** `filtros`: si `/api/sucursales` y `/api/productos/categorias` contestan bien o con 403. */
function conSesion(role: Rol, filtros: 'bien' | 'fallan' = 'bien') {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role, active: true,
        nombre: 'Ana', modulos: [], capacidades: CAPACIDADES_POR_ROL[role], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u.startsWith('/api/reportes/reposicion')) return Promise.resolve(json(REPOSICION))
    if (u === '/api/sucursales' || u === '/api/productos/categorias') {
      if (filtros === 'fallan') return Promise.resolve(json({ detail: 'forbidden' }, 403))
      return Promise.resolve(json(u === '/api/sucursales'
        ? [{ id: 1, nombre: 'Sucursal Centro', es_default: true }]
        : [{ id: 1, nombre: 'Almacén' }]))
    }
    return Promise.resolve(json([]))
  }))
}

function abrir(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('ruta /reposicion', () => {
  it.each(['admin', 'encargado'] as Rol[])('%s ve qué pedir, con el CSV y los filtros del kit', async (rol) => {
    conSesion(rol)
    abrir('/reposicion')
    expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/reposicion?'))).toBe(true)
    // Los dos pedidos de los filtros de la pantalla, y los filtros que arman con lo que contestan.
    expect(llamadas).toContain('/api/sucursales')
    expect(llamadas).toContain('/api/productos/categorias')
    expect(await screen.findByLabelText('Sucursal')).toBeInTheDocument()
    expect(screen.getByLabelText('Categoría')).toBeInTheDocument()
    expect(document.querySelector('a[href^="/api/reportes/reposicion/export?"]')).toBeTruthy()
    // La entrada del menú lleva a la misma ruta.
    expect(screen.getAllByRole('link', { name: /Reposición sugerida/ })[0]).toHaveAttribute('href', '/reposicion')
  })

  it('si fallan las sucursales y las categorías la pantalla sigue, sólo sin esos filtros', async () => {
    conSesion('encargado', 'fallan')
    abrir('/reposicion')
    expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByLabelText('Categoría')).toBeNull()
    expect(screen.getByLabelText('Días de cobertura')).toBeInTheDocument()
  })

  it.each(['cajero', 'vendedor'] as Rol[])('un %s no llega: la ruta pide `reposicion.ver`, ni siquiera pide el reporte, y no hay menú', async (rol) => {
    conSesion(rol)
    abrir('/reposicion')
    await screen.findByRole('link', { name: /Ventas/ })
    expect(screen.queryByText('Yerba 1kg')).toBeNull()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/reposicion'))).toBe(false)
    expect(screen.queryByRole('link', { name: /Reposición sugerida/ })).toBeNull()
  })
})

// ── Generar órdenes en borrador (ADR-057, kit v0.105.0) ──
// El botón escribe órdenes de compra: lo ofrece el wrapper a quien tiene `compras.escribir` y sólo si el motor maneja proveedores (el kit lo deduce de la respuesta).
describe('generar órdenes en borrador', () => {
  const CON_PROVEEDOR = { ...REPOSICION, proveedor_id: null, productos: [{ ...REPOSICION.productos[0], proveedor_id: 7, proveedor: 'Distribuidora Norte' }] }

  function sesionConProveedor(role: Rol) {
    conSesion(role)
    const base = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>)
    const previo = base.getMockImplementation()!
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      if (u.startsWith('/api/reportes/reposicion/ordenes') && init?.method === 'POST') {
        llamadas.push(`POST ${u}`)
        return Promise.resolve(json({
          ordenes: [{ id: 41, number: 'OC-000041', proveedor_id: 7, proveedor: 'Distribuidora Norte', branch_id: null, status: 'draft', total: '120', lineas: [] }],
          sin_proveedor: [], omitidos: [], repetida: false,
        }))
      }
      if (u.startsWith('/api/reportes/reposicion')) return Promise.resolve(json(CON_PROVEEDOR))
      if (u === '/api/proveedores') return Promise.resolve(json([{ id: 7, nombre: 'Distribuidora Norte' }]))
      return previo(url, init)
    }))
  }

  it.each(['admin', 'encargado'] as const)('el %s ve «Generar órdenes en borrador» y el número de la orden creada lleva a su detalle en Compras', async (rol) => {
    sesionConProveedor(rol)
    const user = userEvent.setup()
    abrir('/reposicion')
    await user.click(await screen.findByRole('button', { name: /Generar órdenes en borrador/ }))
    await user.click(await screen.findByRole('button', { name: 'Crear 1 orden' }))
    const enlace = await screen.findByRole('link', { name: 'OC-000041' })
    expect(enlace).toHaveAttribute('href', '/compras/41')
    expect(llamadas.some((l) => l.startsWith('POST /api/reportes/reposicion/ordenes'))).toBe(true)
  })

  it('un rol sin compras.escribir (el depósito) ve la reposición pero no el botón', async () => {
    conSesion('deposito')                           // la respuesta del motor trae proveedores, pero el rol no escribe Compras
    const previo = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).getMockImplementation()!
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      if (u.startsWith('/api/reportes/reposicion')) return Promise.resolve(json(CON_PROVEEDOR))
      return previo(url, init)
    }))
    abrir('/reposicion')
    expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Generar órdenes en borrador/ })).not.toBeInTheDocument()
  })

  it('el visitante de la demo (sólo lectura) ve la reposición pero no se le ofrece generar órdenes', async () => {
    conSesion('encargado')
    const previo = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).getMockImplementation()!
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url)
      if (u.includes('/auth/me')) {
        const r = await previo(url, init) as Response
        return json({ ...(await r.json()), demo_readonly: true })
      }
      if (u.startsWith('/api/reportes/reposicion')) return json(CON_PROVEEDOR)
      return previo(url, init)
    }))
    abrir('/reposicion')
    expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Generar órdenes en borrador/ })).not.toBeInTheDocument()
  })
})

