// El detalle de una orden de compra: "Recibir mercadería" pasa a hacerse acá
// dentro (2026-09-17, pedido del humano) -- antes era un panel suelto de
// Compras.tsx, sin ligarse a una orden en particular.
//
// Lo que fija este archivo:
// - El flujo hace los TRES POST del backend, en orden (crear recepción →
//   cargar líneas → confirmar), con las cantidades que se hayan editado.
// - No deja pasar una cantidad mayor a lo pendiente ni negativa.
// - Si el flujo se corta a mitad de camino, la recepción en borrador queda
//   visible y confirmable desde "Recepciones de esta orden" -- no hay un
//   estado sin salida.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CompraDetalle } from '../pages/CompraDetalle'

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

const PROVEEDORES = [
  { id: 1, party_type: 'organization', display_name: 'Distribuidora Norte', email: null, phone: null, active: true, legal_name: null, tax_id: null },
]

const ORDEN = {
  id: 7, number: 'OC-000007', supplier_party_id: 1, status: 'sent',
  items: [
    { item_id: 1, quantity_ordered: '10', quantity_received: '0', pending_quantity: '10', unit_cost: '100.00', tax_rate: '0', subtotal: '1000.00' },
  ],
  is_fully_received: false,
}

const ITEMS = [
  { id: 1, item_type: 'product', name: 'Yerba', description: '', category_id: null, unit_code: 'kg', active: true, sellable: true, purchasable: true, default_sale_price: '0', default_cost: '0' },
]

const LOCATIONS = [{ id: 1, name: 'Depósito Central', branch_id: null, location_type: 'warehouse', active: true, is_default: true }]

const RECEIPT_CREADA = { id: 55, supplier_party_id: 1, purchase_order_id: 7, status: 'draft', items: [], received_at: null, document_reference: null }

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]
let recibidoDefinitivo: boolean

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  llamadas = []
  recibidoDefinitivo = false
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const cuerpo = init?.body ? JSON.parse(String(init.body)) : null
    llamadas.push({ url: u, metodo, cuerpo })

    if (u === '/purchase-orders/7') {
      const orden = recibidoDefinitivo
        ? { ...ORDEN, status: 'partial', items: [{ ...ORDEN.items[0], quantity_received: '5', pending_quantity: '5', unit_cost: '100.00' }] }
        : ORDEN
      return Promise.resolve(json(orden))
    }
    if (u === '/suppliers') return Promise.resolve(json(PROVEEDORES))
    if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
    if (u === '/locations') return Promise.resolve(json(LOCATIONS))
    if (metodo === 'POST' && u === '/purchase-receipts') return Promise.resolve(json(RECEIPT_CREADA))
    if (metodo === 'POST' && u === '/purchase-receipts/55/items') return Promise.resolve(json(RECEIPT_CREADA))
    if (metodo === 'POST' && u === '/purchase-receipts/55/confirm') {
      recibidoDefinitivo = true
      return Promise.resolve(json({ ...RECEIPT_CREADA, status: 'confirmed' }))
    }
    if (u === '/purchase-receipts') return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

function montar(ruta = '/compras/7') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/compras/:id" element={<CompraDetalle />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('El detalle de una orden de compra', () => {
  it('muestra las líneas con pedido/recibido/pendiente/costo/subtotal', async () => {
    montar()

    expect(await screen.findByText(/^Orden OC-000007/)).toBeInTheDocument()
    const fila = screen.getByText('Yerba').closest('tr')!
    const celdas = within(fila).getAllByRole('cell').map((c) => c.textContent)
    // Producto, Pedido, Recibido, Pendiente, Costo unitario, Subtotal -- en
    // ese orden. Pedido y Pendiente valen los dos "10" (nada recibido
    // todavía), así que se afirma por POSICIÓN de columna, no por texto: un
    // `getByText('10')` sería ambiguo entre las dos.
    expect(celdas).toEqual(['Yerba', '10', '0', '10', '$100,00', '$1.000,00'])
  })

  it('"Recibir mercadería" hace los tres POST en orden, con la cantidad editada', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText(/^Orden OC-000007/)

    await usuario.click(screen.getByRole('button', { name: /Recibir mercadería/ }))

    // Precargada con lo pendiente.
    const cantidad = await screen.findByLabelText('Cantidad a recibir de Yerba')
    expect(cantidad).toHaveValue('10')
    const costo = screen.getByLabelText('Costo unitario de Yerba')
    expect(costo).toHaveValue('100.00')

    // Se edita a menos de lo pendiente.
    await usuario.clear(cantidad)
    await usuario.type(cantidad, '5')

    await usuario.click(screen.getByRole('button', { name: 'Recibir' }))

    await waitFor(() => expect(llamadas.some((l) => l.metodo === 'POST' && l.url === '/purchase-receipts/55/confirm')).toBe(true))

    // Las tres llamadas, EN ORDEN, con la cantidad editada.
    const posts = llamadas.filter((l) => l.metodo === 'POST')
    expect(posts.map((p) => p.url)).toEqual([
      '/purchase-receipts', '/purchase-receipts/55/items', '/purchase-receipts/55/confirm',
    ])
    expect(posts[0].cuerpo).toEqual({ supplier_party_id: 1, purchase_order_id: 7, document_reference: null })
    expect(posts[1].cuerpo).toEqual({ item_id: 1, quantity: '5', unit_cost: '100.00' })
    expect(posts[2].cuerpo).toEqual({ location_id: 1 })

    // Y el diálogo se cierra, con la orden recargada.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('no deja recibir más que lo pendiente, ni un valor negativo', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText(/^Orden OC-000007/)
    await usuario.click(screen.getByRole('button', { name: /Recibir mercadería/ }))

    const cantidad = await screen.findByLabelText('Cantidad a recibir de Yerba')

    await usuario.clear(cantidad)
    await usuario.type(cantidad, '20')
    expect(await screen.findByText(/No puede superar lo pendiente \(10\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recibir' })).toBeDisabled()

    await usuario.clear(cantidad)
    await usuario.type(cantidad, '-1')
    expect(await screen.findByText(/tiene que ser un número igual o mayor a 0/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recibir' })).toBeDisabled()

    // Y no salió ningún POST mientras estuvo inválido.
    expect(llamadas.some((l) => l.metodo === 'POST')).toBe(false)
  })

  it('una recepción en borrador queda visible y confirmable desde el detalle', async () => {
    // Simula lo que deja un "Recibir mercadería" cortado a mitad de camino:
    // la recepción existe en borrador (sin líneas) y no está en la respuesta
    // de la orden todavía. Lo que importa acá es que "Recepciones de esta
    // orden" la muestre con su botón "Confirmar" -- no hace falta reabrir el
    // diálogo de "Recibir mercadería" para no dejarla huérfana.
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      const cuerpo = init?.body ? JSON.parse(String(init.body)) : null
      llamadas.push({ url: u, metodo, cuerpo })
      if (u === '/purchase-orders/7') return Promise.resolve(json(ORDEN))
      if (u === '/suppliers') return Promise.resolve(json(PROVEEDORES))
      if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
      if (u === '/locations') return Promise.resolve(json(LOCATIONS))
      // Con una línea cargada: un borrador vacío no es confirmable (ver el
      // test siguiente).
      if (u === '/purchase-receipts') {
        return Promise.resolve(json([{ ...RECEIPT_CREADA, items: [{ item_id: 1, quantity: '5', unit_cost: '100.00', lot_code: null, expires_at: null }] }]))
      }
      if (metodo === 'POST' && u === '/purchase-receipts/55/confirm') {
        return Promise.resolve(json({ ...RECEIPT_CREADA, status: 'confirmed' }))
      }
      return Promise.resolve(json([]))
    }))

    const usuario = userEvent.setup()
    montar()
    await screen.findByText(/^Orden OC-000007/)

    const fila = (await screen.findByText('#55')).closest('tr')!
    expect(within(fila).getByText('Borrador')).toBeInTheDocument()
    await usuario.click(within(fila).getByRole('button', { name: 'Confirmar' }))

    const dialogo = await screen.findByRole('dialog')
    expect(dialogo).toHaveTextContent('Confirmar recepción #55')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url === '/purchase-receipts/55/confirm')).toBe(true)
    })
  })

  it('un borrador SIN líneas no ofrece "Confirmar": el backend lo rechaza siempre', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u === '/purchase-orders/7') return Promise.resolve(json(ORDEN))
      if (u === '/suppliers') return Promise.resolve(json(PROVEEDORES))
      if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
      if (u === '/locations') return Promise.resolve(json(LOCATIONS))
      if (u === '/purchase-receipts') return Promise.resolve(json([RECEIPT_CREADA]))
      return Promise.resolve(json([]))
    }))
    montar()
    const fila = (await screen.findByText('#55')).closest('tr')!
    expect(within(fila).getByText('Borrador')).toBeInTheDocument()
    expect(within(fila).queryByRole('button', { name: 'Confirmar' })).not.toBeInTheDocument()
  })

  it('si "Recibir" se corta a mitad de camino, el modal queda abierto con el error y la lista se recarga', async () => {
    let pedidosDeRecepciones = 0
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      if (u === '/purchase-orders/7') return Promise.resolve(json(ORDEN))
      if (u === '/suppliers') return Promise.resolve(json(PROVEEDORES))
      if (u.startsWith('/catalog/items')) return Promise.resolve(json(ITEMS))
      if (u === '/locations') return Promise.resolve(json(LOCATIONS))
      if (metodo === 'POST' && u === '/purchase-receipts') return Promise.resolve(json(RECEIPT_CREADA))
      if (metodo === 'POST' && u === '/purchase-receipts/55/items') {
        return Promise.resolve(new Response(JSON.stringify({ detail: 'la recepcion no admite esa linea' }), {
          status: 409, headers: { 'content-type': 'application/json' },
        }))
      }
      if (u === '/purchase-receipts') {
        pedidosDeRecepciones += 1
        return Promise.resolve(json([]))
      }
      return Promise.resolve(json([]))
    }))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText(/^Orden OC-000007/)
    await waitFor(() => expect(pedidosDeRecepciones).toBe(1))

    await usuario.click(screen.getByRole('button', { name: /Recibir mercadería/ }))
    await usuario.click(await screen.findByRole('button', { name: 'Recibir' }))

    const dialogo = await screen.findByRole('dialog')
    expect(await within(dialogo).findByText('la recepcion no admite esa linea')).toBeInTheDocument()
    await waitFor(() => expect(pedidosDeRecepciones).toBe(2))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
