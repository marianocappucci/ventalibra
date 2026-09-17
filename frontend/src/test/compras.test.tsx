// El listado de compras, a todo el ancho -- misma forma que Ventas del kit y
// las pantallas propias del producto (2026-09-17: hasta acá era una grilla al
// 50% con el detalle desplegado al costado). Lo que fija este archivo:
// - La tabla ocupa el ancho completo (no hay una segunda columna/`Card` al
//   lado) y "Nueva compra" está arriba a la derecha, junto al título.
// - Click en una fila navega al detalle de esa orden.
//
// El flujo de "Recibir mercadería" -- que ahora vive DENTRO del detalle -- se
// prueba en `compra-detalle.test.tsx`.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Compras } from '../pages/Compras'
import { CompraDetalle } from '../pages/CompraDetalle'

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

const PROVEEDORES = [
  {
    id: 1, party_type: 'organization', display_name: 'Distribuidora Norte',
    email: null, phone: null, active: true, legal_name: null, tax_id: '30111111112',
  },
]

const ORDENES = [
  {
    id: 7, number: 'OC-000007', supplier_party_id: 1, status: 'sent',
    items: [
      { item_id: 1, quantity_ordered: '10', quantity_received: '0', pending_quantity: '10', unit_cost: '100.00', tax_rate: '0', subtotal: '1000.00' },
      { item_id: 2, quantity_ordered: '5', quantity_received: '0', pending_quantity: '5', unit_cost: '50.00', tax_rate: '0', subtotal: '250.00' },
    ],
    is_fully_received: false,
  },
]

const ORDEN_NUEVA = { id: 8, number: 'OC-000008', supplier_party_id: 1, status: 'draft', items: [], is_fully_received: false }

const ITEMS = [
  { id: 1, item_type: 'product', name: 'Yerba', description: '', category_id: null, unit_code: 'kg', active: true, sellable: true, purchasable: true, default_sale_price: '0', default_cost: '0' },
  { id: 2, item_type: 'product', name: 'Azúcar', description: '', category_id: null, unit_code: 'kg', active: true, sellable: true, purchasable: true, default_sale_price: '0', default_cost: '0' },
]

const LOCATIONS = [{ id: 1, name: 'Depósito Central', branch_id: null, location_type: 'warehouse', active: true, is_default: true }]

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST' && u === '/purchase-orders') return Promise.resolve(json(ORDEN_NUEVA))
    if (u === '/purchase-orders/7') return Promise.resolve(json(ORDENES[0]))
    if (u === '/purchase-orders/8') return Promise.resolve(json(ORDEN_NUEVA))
    if (u === '/purchase-orders') return Promise.resolve(json(ORDENES))
    if (u === '/suppliers') return Promise.resolve(json(PROVEEDORES))
    if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
    if (u === '/locations') return Promise.resolve(json(LOCATIONS))
    if (u === '/purchase-receipts') return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

function montarListado(ruta = '/compras') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/compras" element={<Compras />} />
        <Route path="/compras/:id" element={<CompraDetalle />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('El listado de compras', () => {
  it('muestra la tabla a todo el ancho, sin un detalle desplegado al costado', async () => {
    montarListado()

    expect(await screen.findByText('OC-000007')).toBeInTheDocument()
    // El detalle viejo era un segundo `Card` con "Orden {number}" apenas se
    // elegía una fila -- acá elegir NO despliega nada al costado, sólo existe
    // la tabla y el botón de alta.
    expect(screen.queryByText(/^Orden OC-000007/)).not.toBeInTheDocument()
    expect(screen.getByText('Distribuidora Norte')).toBeInTheDocument()
    expect(screen.getByText('$1.250,00')).toBeInTheDocument()
  })

  it('"Nueva compra" está arriba, junto al título', async () => {
    montarListado()
    await screen.findByText('OC-000007')

    expect(screen.getByRole('heading', { name: /Compras/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nueva compra/ })).toBeInTheDocument()
  })

  it('click en una fila navega al detalle de esa orden', async () => {
    const usuario = userEvent.setup()
    montarListado()
    await screen.findByText('OC-000007')

    await usuario.click(screen.getByText('OC-000007'))

    expect(await screen.findByText(/^Orden OC-000007/)).toBeInTheDocument()
    // Y las líneas de la orden, que sólo se ven en el detalle.
    expect(await screen.findByText('Yerba')).toBeInTheDocument()
  })

  it('"Nueva compra" elige proveedor, crea la orden y navega a su detalle', async () => {
    const usuario = userEvent.setup()
    montarListado()
    await screen.findByText('OC-000007')

    await usuario.click(screen.getByRole('button', { name: /Nueva compra/ }))
    await usuario.click(screen.getByRole('combobox', { name: 'Proveedor' }))
    await usuario.click(await screen.findByRole('option', { name: /Distribuidora Norte/ }))
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url === '/purchase-orders')
      expect(post).toBeTruthy()
      expect(post!.cuerpo).toEqual({ supplier_party_id: 1 })
    })
    expect(await screen.findByText(/^Orden OC-000008/)).toBeInTheDocument()
  })
})
