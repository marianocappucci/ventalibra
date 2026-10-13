// Roles parciales (libra-ui 0.146.0, ADR-058 del kit; ADR-083 de este repo). Con el kit de verdad y la app entera, un usuario de cada rol
// con las capacidades que el backend le manda (`capacidades-por-rol.json`, generado desde `app/permisos.py`):
//
//  - El **depósito** tiene `compras.ver` pero no `compras.escribir`, `compras.recibir` ni `costos.ver`: no ve «Nueva compra», «Agregar línea»,
//    «Enviar al proveedor», «Cancelar orden», «Recibir mercadería» ni «Confirmar recepción», y la API le saca `subtotal` y `unit_cost`
//    (`app/costos.py`): el kit no formatea lo que no llegó, así que no hay «$NaN».
//  - El **vendedor** ve Stock (`stock.ver`) pero no tiene `stock.ajustar`: no ve «Ajustar stock», y sí «Ver movimientos».
//  - Los roles que sí tienen cada capacidad (el encargado) lo siguen viendo: son los controles que hacen que lo anterior mida algo.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

type Rol = keyof typeof CAPACIDADES_POR_ROL

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const LINEA = { item_id: 1, quantity_ordered: '10', quantity_received: '0', pending_quantity: '10', unit_cost: '900.00', tax_rate: '0', subtotal: '9000.00' }
const ORDEN_ENVIADA = { id: 10, number: 'OC-000010', proveedor_id: 1, status: 'sent', items: [LINEA], is_fully_received: false }
const ORDEN_BORRADOR = { id: 11, number: 'OC-000011', proveedor_id: 1, status: 'draft', items: [LINEA], is_fully_received: false }

/** Lo que el backend le manda a un rol sin `costos.ver`: las claves de plata NO vienen (no vienen en cero). */
function sinCostos<T extends { items: object[] }>(orden: T): T {
  return {
    ...orden,
    items: orden.items.map((l) => {
      const { unit_cost: _c, subtotal: _s, ...resto } = l as Record<string, unknown>
      return resto
    }),
  }
}

const PRODUCTO = {
  id: 1, codigo: 'Y001', nombre: 'Yerba 1kg', descripcion: '', precio_venta: 1500, unidad: 'kg', categoria: '', stock_minimo: 0,
  estacion: '', vendible: 1, activo: 1, tipo: 'producto',
}
const STOCK = [
  { id: 1, codigo: 'Y001', nombre: 'Yerba 1kg', unidad: 'kg', categoria: 'Almacén', stock_minimo: 5, activo: 1, stock_actual: 3 },
  { id: 2, codigo: null, nombre: 'Sal fina', unidad: 'kg', categoria: '', stock_minimo: 0, activo: 1, stock_actual: 40 },
]

function conSesion(rol: Rol, ruta: string) {
  const conCostos = CAPACIDADES_POR_ROL[rol].includes('costos.ver')
  const ordenes = [ORDEN_ENVIADA, ORDEN_BORRADOR].map((o) => (conCostos ? o : sinCostos(o)))
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    const path = u.split('?')[0]
    if (path.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '7', username: `u-${rol}`, name: rol, role: rol, active: true, empresa_nombre: 'Prueba', modulos: ['multisucursal'],
        capacidades: CAPACIDADES_POR_ROL[rol],
      }))
    }
    if (path === '/api/purchase-orders') return Promise.resolve(json(ordenes))
    if (path === '/api/purchase-orders/10') return Promise.resolve(json(ordenes[0]))
    if (path === '/api/purchase-orders/11') return Promise.resolve(json(ordenes[1]))
    if (path === '/api/proveedores') return Promise.resolve(json([{ id: 1, nombre: 'Distribuidora SA', cuit_dni: '30-1', email: '', phone: '', address: '', iva_condition: '' }]))
    if (path === '/api/productos') return Promise.resolve(json([PRODUCTO]))
    if (path === '/api/depositos') return Promise.resolve(json([{ id: 1, nombre: 'Central', descripcion: '', es_default: 1, activo: 1 }]))
    if (path === '/api/purchase-receipts') return Promise.resolve(json([]))
    if (path === '/api/stock') return Promise.resolve(json({ productos: STOCK, alertas: [] }))
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

// Los botones de la pantalla, sin los del marco (menú lateral, tema, usuario): sólo lo que está dentro de `<main>`.
const botones = () => within(screen.getByRole('main')).queryAllByRole('button')
  .map((b) => b.textContent || b.getAttribute('aria-label'))
  .filter((t) => t !== 'Toggle Sidebar')
const textoDeLaPantalla = () => document.body.textContent ?? ''

beforeEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear() })

describe('Compras: el depósito lee, no escribe y no ve plata', () => {
  it('el depósito no ve «Nueva compra» y no hay «$NaN» ni importes', async () => {
    conSesion('deposito', '/compras')
    await screen.findByText('OC-000010')
    expect(screen.queryByRole('button', { name: /Nueva compra/ })).toBeNull()
    expect(textoDeLaPantalla()).not.toMatch(/NaN/)
    expect(textoDeLaPantalla()).not.toContain('$')
  })

  it('el encargado sí: «Nueva compra» y los importes (control)', async () => {
    conSesion('encargado', '/compras')
    await screen.findByText('OC-000010')
    expect(screen.getByRole('button', { name: /Nueva compra/ })).toBeInTheDocument()
    expect(screen.getAllByText('$9.000,00').length).toBeGreaterThan(0)
  })
})

describe('CompraDetalle: cada acción sigue a su capacidad', () => {
  it.each([['10', 'enviada'], ['11', 'en borrador']])(
    'el depósito lee la orden %s (%s) sin ningún botón de escritura y sin «$NaN»', async (id) => {
      conSesion('deposito', `/compras/${id}`)
      await screen.findByText(new RegExp(`OC-0000${id}`))
      for (const nombre of ['Agregar línea', 'Recibir mercadería', 'Confirmar recepción', 'Enviar al proveedor', 'Cancelar orden']) {
        expect(screen.queryByRole('button', { name: new RegExp(nombre) }), nombre).toBeNull()
      }
      expect(botones().filter(Boolean)).toEqual([])
      expect(textoDeLaPantalla()).not.toMatch(/NaN/)
      expect(textoDeLaPantalla()).not.toContain('$')
    },
  )

  it('el encargado de una orden enviada: «Agregar línea», «Recibir mercadería» y «Cancelar orden» (control)', async () => {
    conSesion('encargado', '/compras/10')
    await screen.findByText(/OC-000010/)
    for (const nombre of ['Agregar línea', 'Recibir mercadería', 'Cancelar orden']) {
      expect(screen.getByRole('button', { name: new RegExp(nombre) }), nombre).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: /Enviar al proveedor/ })).toBeNull() // ya está enviada
  })

  it('el encargado de una orden en borrador puede enviarla (control)', async () => {
    conSesion('encargado', '/compras/11')
    await screen.findByText(/OC-000011/)
    expect(screen.getByRole('button', { name: /Enviar al proveedor/ })).toBeInTheDocument()
  })
})

describe('Stock: ajustar es de quien tiene `stock.ajustar`', () => {
  it('el vendedor ve el stock y los movimientos, pero no «Ajustar stock»', async () => {
    conSesion('vendedor', '/stock')
    await screen.findAllByText('Sal fina')
    expect(screen.queryAllByRole('button', { name: 'Ajustar stock' })).toHaveLength(0)
    expect(screen.getAllByRole('button', { name: 'Ver movimientos' }).length).toBeGreaterThan(0)
  })

  it.each(['encargado', 'deposito'] as Rol[])('%s sí lo ve (control)', async (rol) => {
    conSesion(rol, '/stock')
    await screen.findAllByText('Sal fina')
    expect(screen.getAllByRole('button', { name: 'Ajustar stock' }).length).toBeGreaterThan(0)
  })
})
