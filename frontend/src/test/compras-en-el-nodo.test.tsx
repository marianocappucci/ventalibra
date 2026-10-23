// Compras en un nodo offline (ADR-093): los proveedores y las órdenes de compra se cargan en la versión web y bajan al equipo del
// local; en el nodo sólo se recibe contra la orden. Con el kit de verdad y la app entera, un encargado en un nodo (`GET
// /api/nodo/conexion` dice `es_nodo`) no ve «Nueva compra», «Agregar línea», «Enviar al proveedor» ni «Cancelar orden», sí ve
// «Recibir mercadería», y las pantallas lo explican. Fuera de un nodo no cambia nada (control). El que corta de verdad es el backend
// (409 `solo_en_el_central`, `tests/test_stock_del_nodo.py`); esto sólo decide qué se ofrece.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _reiniciarConexionDelNodo } from 'libra-ui/nodo-offline'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'
import App from '../App'
import { TEXTO_COMPRAS_EN_EL_NODO } from '../components/aviso-compras-en-el-nodo'
import { AuthProvider } from '../context/AuthContext'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const LINEA = { item_id: 1, quantity_ordered: '10', quantity_received: '0', pending_quantity: '10', unit_cost: '900.00', tax_rate: '0', subtotal: '9000.00' }
const ORDEN = { id: 10, number: 'OC-000010', proveedor_id: 1, status: 'sent', items: [LINEA], is_fully_received: false }
const PRODUCTO = {
  id: 1, codigo: 'Y001', nombre: 'Yerba 1kg', descripcion: '', precio_venta: 1500, unidad: 'kg', categoria: '', stock_minimo: 0,
  estacion: '', vendible: 1, activo: 1, tipo: 'producto',
}

function entrar(ruta: string, { esNodo }: { esNodo: boolean }) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const path = String(url).split('?')[0]
    if (path.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '7', username: 'u-encargado', name: 'encargado', role: 'encargado', active: true, empresa_nombre: 'Prueba',
        modulos: ['multisucursal'], capacidades: CAPACIDADES_POR_ROL.encargado,
      }))
    }
    if (path === '/api/nodo/conexion') {
      return Promise.resolve(json({ es_nodo: esNodo, en_linea: true, node_id: esNodo ? 'nodo-1' : null, a_facturar: 0 }))
    }
    if (path === '/api/purchase-orders') return Promise.resolve(json([ORDEN]))
    if (path === '/api/purchase-orders/10') return Promise.resolve(json(ORDEN))
    if (path === '/api/proveedores') return Promise.resolve(json([{ id: 1, nombre: 'Distribuidora SA', cuit_dni: '30-1', email: '', phone: '', address: '', iva_condition: '' }]))
    if (path === '/api/productos') return Promise.resolve(json([PRODUCTO]))
    if (path === '/api/depositos') return Promise.resolve(json([{ id: 1, nombre: 'Central', descripcion: '', es_default: 1, activo: 1 }]))
    if (path === '/api/purchase-receipts') return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); _reiniciarConexionDelNodo() })
afterEach(() => { _reiniciarConexionDelNodo() })

describe('Compras en un nodo', () => {
  it('la lista de órdenes explica que se cargan en la web y no ofrece «Nueva compra»', async () => {
    entrar('/compras', { esNodo: true })
    await screen.findByText('OC-000010')
    expect(await screen.findByText(TEXTO_COMPRAS_EN_EL_NODO)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Nueva compra/ })).toBeNull()
  })

  it('la orden sólo se recibe: sin «Agregar línea», «Enviar al proveedor» ni «Cancelar orden», y con «Recibir mercadería»', async () => {
    entrar('/compras/10', { esNodo: true })
    await screen.findByText(/OC-000010/)
    expect(await screen.findByText(TEXTO_COMPRAS_EN_EL_NODO)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Recibir mercadería/ })).toBeInTheDocument()
    for (const nombre of ['Agregar línea', 'Enviar al proveedor', 'Cancelar orden']) {
      expect(screen.queryByRole('button', { name: new RegExp(nombre) }), nombre).toBeNull()
    }
  })

  it('los proveedores se leen con el aviso de que se cargan en la web', async () => {
    entrar('/proveedores', { esNodo: true })
    await screen.findByText('Distribuidora SA')
    expect(await screen.findByText(TEXTO_COMPRAS_EN_EL_NODO)).toBeInTheDocument()
  })
})

describe('Compras fuera de un nodo (control)', () => {
  it('el central ofrece «Nueva compra» y no muestra ningún aviso', async () => {
    entrar('/compras', { esNodo: false })
    await screen.findByText('OC-000010')
    expect(await screen.findByRole('button', { name: /Nueva compra/ })).toBeInTheDocument()
    expect(screen.queryByText(TEXTO_COMPRAS_EN_EL_NODO)).toBeNull()
  })

  it('el central ofrece escribir la orden', async () => {
    entrar('/compras/10', { esNodo: false })
    await screen.findByText(/OC-000010/)
    for (const nombre of ['Agregar línea', 'Recibir mercadería', 'Cancelar orden']) {
      expect(await screen.findByRole('button', { name: new RegExp(nombre) }), nombre).toBeInTheDocument()
    }
  })
})
