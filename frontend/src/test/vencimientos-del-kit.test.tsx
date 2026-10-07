// Vencimientos y lotes es la pantalla del kit (`libra-ui/comercio/Vencimientos`) sobre los routers del motor (`/api/vencimientos`, ADR-052).
// La cuenta (ventana, vencido, sin lote) es del motor y el dibujo del kit; acá, que la ruta existe, que es de quien tiene
// `vencimientos.ver` (encargado y depósito, más el admin), que la pantalla habla con la API que el kit espera (los dos pedidos de sus
// filtros y el de productos, que si fallan no la rompen) y —lo que decide este archivo— que las dos props que le pone el wrapper llegan
// según el rol: `puedeMover` (`vencimientos.mover`: asignar y dar de baja) y `puedeMarcar` (`vencimientos.marcar`: sólo el encargado).
// El kit oculta los botones con esas props; el que corta de verdad es el backend (`tests/test_vencimientos.py`).
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

let llamadas: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const UBICACION = {
  deposito_id: 1, deposito: 'Depósito Sucursal 1', deposito_activo: true, sucursal_id: 1, sucursal: 'Sucursal 1', variante_id: null, variante: null,
}
const LECHE = { producto_id: 1, codigo: 'LECHE-1', nombre: 'Leche 1L', unidad: 'u', categoria: 'Almacén' }

const VENCIMIENTOS = {
  sucursal_id: null, deposito_id: null, categoria: null, producto_id: null, incluir_vencidos: true,
  hoy: '2026-09-30', dias: 15, hasta: '2026-10-15',
  resumen: {
    lotes_por_vencer: 0, lotes_vencidos: 1, unidades_por_vencer: 0, unidades_vencidas: 4, productos: 1, productos_sin_lote: 1,
    productos_con_salidas_sin_lote: 0, saldos_sin_fecha: 1, saldos_con_salidas_sin_lote: 0,
  },
  lotes: [{ ...LECHE, ...UBICACION, lote: 'L-VENCIDO', vence: '2026-09-27', dias_para_vencer: -3, saldo: 4, estado: 'vencido' }],
  sin_lote: [{ ...LECHE, ...UBICACION, saldo: 8, situacion: 'sin_fecha' }],
}

type Rol = 'admin' | 'encargado' | 'deposito' | 'cajero' | 'vendedor'

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
    if (u.startsWith('/api/vencimientos?')) return Promise.resolve(json(VENCIMIENTOS))
    if (u === '/api/sucursales' || u === '/api/productos/categorias') {
      if (filtros === 'fallan') return Promise.resolve(json({ detail: 'forbidden' }, 403))
      return Promise.resolve(json(u === '/api/sucursales'
        ? [{ id: 1, nombre: 'Sucursal Centro', es_default: true }]
        : [{ id: 1, nombre: 'Almacén' }]))
    }
    if (u === '/api/productos') return Promise.resolve(json([]))
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

const DAR_DE_BAJA = /Dar de baja \(merma\) Leche 1L, lote L-VENCIDO/
const ASIGNAR = /Asignar vencimiento Leche 1L/
const MARCAR = /marcarlo o desmarcarlo/

describe('ruta /vencimientos', () => {
  it.each(['admin', 'encargado', 'deposito'] as Rol[])('%s ve lo que vence, con el CSV y los filtros del kit', async (rol) => {
    conSesion(rol)
    abrir('/vencimientos')
    expect(await screen.findByText('L-VENCIDO')).toBeInTheDocument()
    expect(llamadas.some((u) => u.startsWith('/api/vencimientos?'))).toBe(true)
    // Los pedidos de los filtros de la pantalla y el de los productos («Productos que vencen»).
    expect(llamadas).toContain('/api/sucursales')
    expect(llamadas).toContain('/api/productos/categorias')
    expect(llamadas).toContain('/api/productos')
    expect(await screen.findByLabelText('Sucursal')).toBeInTheDocument()
    expect(document.querySelector('a[href^="/api/vencimientos/export?"]')).toBeTruthy()
    // La entrada del menú lleva a la misma ruta.
    expect(screen.getAllByRole('link', { name: /Vencimientos y lotes/ })[0]).toHaveAttribute('href', '/vencimientos')
  })

  it('si fallan las sucursales y las categorías la pantalla sigue, sólo sin esos filtros', async () => {
    conSesion('deposito', 'fallan')
    abrir('/vencimientos')
    expect(await screen.findByText('L-VENCIDO')).toBeInTheDocument()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByLabelText('Categoría')).toBeNull()
    expect(screen.getByLabelText('Días de anticipación')).toBeInTheDocument()
  })

  it.each(['cajero', 'vendedor'] as Rol[])('un %s no llega: la ruta pide `vencimientos.ver`, ni siquiera pide el reporte, y no hay menú', async (rol) => {
    conSesion(rol)
    abrir('/vencimientos')
    await screen.findByRole('link', { name: /Ventas/ })
    expect(screen.queryByText('L-VENCIDO')).toBeNull()
    expect(llamadas.some((u) => u.startsWith('/api/vencimientos'))).toBe(false)
    expect(screen.queryByRole('link', { name: /Vencimientos y lotes/ })).toBeNull()
  })
})

describe('las props que le pone el wrapper al kit, por rol', () => {
  it.each(['admin', 'encargado'] as Rol[])('%s puede mover y marcar: dar de baja y marcar productos', async (rol) => {
    conSesion(rol)
    abrir('/vencimientos')
    expect(await screen.findByRole('button', { name: DAR_DE_BAJA })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: ASIGNAR })).toBeInTheDocument()
    // Una columna «Acciones» por tabla: la de los lotes (dar de baja) y la de sin lote (asignar).
    expect(screen.getAllByRole('columnheader', { name: 'Acciones' })).toHaveLength(2)
    expect(screen.getByText(MARCAR)).toBeInTheDocument()
  })

  it('el depósito puede mover pero NO marcar: da de baja y asigna, y «Productos que vencen» es sólo de consulta', async () => {
    conSesion('deposito')
    abrir('/vencimientos')
    expect(await screen.findByRole('button', { name: DAR_DE_BAJA })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: ASIGNAR })).toBeInTheDocument()
    // Una columna «Acciones» por tabla: la de los lotes (dar de baja) y la de sin lote (asignar).
    expect(screen.getAllByRole('columnheader', { name: 'Acciones' })).toHaveLength(2)
    expect(screen.queryByText(MARCAR)).toBeNull()
    expect(screen.getByText(/Elegí un producto para ver si vence\./)).toBeInTheDocument()
  })

  it('con sólo `vencimientos.ver` (ni mover ni marcar) la pantalla es de lectura', async () => {
    // Un usuario que el backend no arma hoy, pero que fija que las dos props salen de las dos capacidades y no del rol.
    llamadas = []
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/auth/me')) {
        return Promise.resolve(json({
          id: '1', username: 'ana', name: 'Ana', role: 'deposito', active: true, nombre: 'Ana', modulos: [],
          capacidades: ['stock.ver', 'vencimientos.ver'], empresa_nombre: 'Prueba', mp_pending_count: 0,
        }))
      }
      if (u.startsWith('/api/vencimientos?')) return Promise.resolve(json(VENCIMIENTOS))
      return Promise.resolve(json([]))
    }))
    abrir('/vencimientos')
    expect(await screen.findByText('L-VENCIDO')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: DAR_DE_BAJA })).toBeNull()
    expect(screen.queryByRole('button', { name: ASIGNAR })).toBeNull()
    expect(screen.queryAllByRole('columnheader', { name: 'Acciones' })).toHaveLength(0)
    expect(screen.queryByText(MARCAR)).toBeNull()
  })
})
