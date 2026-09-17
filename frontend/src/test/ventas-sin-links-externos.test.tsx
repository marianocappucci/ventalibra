// VentaLibra no tiene pantalla de facturas, remitos ni recibo -- sólo el
// listado y el detalle de venta (`Ventas.tsx`/`VentaDetalle.tsx`) y el ticket,
// que sirve el backend (F4, 2026-09-15, revisión adversarial, punto 5:
// libra-ui v0.72.1 hace nullables `rutaDeFactura`/`rutaDeRemito`/
// `rutaDeRemitoNuevo`/`rutaDeRecibo`).
//
// Lo que se prueba: con una venta facturada y con pagos -- el caso que antes
// ofrecía los tres links -- ninguno de los tres aparece, pero el dato de la
// factura sigue visible como texto y el ticket sigue con su link de siempre.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Ventas } from '../pages/Ventas'
import { VentaDetalle } from '../pages/VentaDetalle'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

const MEDIOS = [{ id: 'efectivo', label: 'Efectivo' }]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Venta facturada y con pagos: el caso que antes ofrecía los tres links
 *  (factura, remito, recibo). */
const VENTA_FACTURADA = {
  id: 42, numero: 'POS-000042', fecha: '2026-09-15', estado: 'cobrada',
  items: [{ id: 501, nombre: 'Yerba 1kg', qty: 5, precio: 1500, subtotal: 7500, producto_id: 3 }],
  subtotal: 7500, descuento: 0, total: 7500,
  cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 7500, referencia: '' }],
  factura_id: 55, factura_display: 'FACTURA C 0001-00000055',
  remito_id: 9,
  mp_order_id: '', mp_payment_id: '',
}

let pedidos: string[] = []

function montarRed(extra: Record<string, Response> = {}) {
  pedidos = []
  const fetchMock = vi.fn((url: string) => {
    const u = String(url)
    pedidos.push(u)
    if (extra[u]) return Promise.resolve(extra[u])
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.match(/\/api\/ventas\/42$/)) return Promise.resolve(json(VENTA_FACTURADA))
    if (u.startsWith('/api/ventas')) return Promise.resolve(json([VENTA_FACTURADA]))
    if (u.includes('/ventas/42/devuelto')) return Promise.resolve(json({ por_clave: [], deposito_id: null }))
    if (u.includes('/locations')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
}

beforeEach(() => {
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Sin facturas, remitos ni recibo propios', () => {
  it('el listado no linkea a /facturas/ ni a /recibo, pero sí al ticket', async () => {
    montarRed()
    render(<MemoryRouter><Ventas /></MemoryRouter>)

    await screen.findByText('POS-000042')
    // La factura sigue visible como dato -- sólo que ya no es un link.
    expect(screen.getByText('FACTURA C 0001-00000055')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /FACTURA C 0001-00000055/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /Ver recibo/i })).toBeNull()
    expect(screen.queryByTitle('Ver recibo')).toBeNull()
    // El ticket sigue pidiendo la ruta de siempre, la del backend. Desde
    // libra-ui v0.73.0 es un botón que la pide con fetch (así puede avisar en
    // un modal si no hay PDF), no un link. jsdom no tiene blobs de URL ni
    // ventanas: se simulan para que el camino feliz no tire.
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:ticket'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
    vi.spyOn(window, 'open').mockImplementation(() => ({}) as Window)
    await userEvent.setup().click(screen.getByTitle('Imprimir ticket'))
    await waitFor(() => expect(pedidos).toContain('/ventas/42/ticket'))
  })

  it('el ticket de un borrador descartado avisa en un modal, no muestra el JSON', async () => {
    // Lo que devuelve `app/routers/ventas_extra.py::ticket` para una venta
    // que no está confirmada.
    montarRed({ '/ventas/42/ticket': json({ detail: 'solo se imprime el ticket de una venta confirmada' }, 409) })
    const abrir = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<MemoryRouter><Ventas /></MemoryRouter>)

    await screen.findByText('POS-000042')
    await userEvent.setup().click(screen.getByTitle('Imprimir ticket'))

    const dialogo = await screen.findByRole('dialog')
    expect(dialogo).toHaveTextContent('No se puede imprimir el ticket')
    expect(dialogo).toHaveTextContent('Solo se imprime el ticket de una venta confirmada.')
    expect(abrir).not.toHaveBeenCalled()
  })

  it('el detalle no linkea a /facturas/ ni a /remitos/ ni ofrece recibo', async () => {
    montarRed()
    render(
      <MemoryRouter initialEntries={['/ventas/42']}>
        <Routes><Route path="/ventas/:id" element={<VentaDetalle />} /></Routes>
      </MemoryRouter>,
    )

    await screen.findByText('FACTURA C 0001-00000055')
    expect(screen.queryByRole('link', { name: /FACTURA C 0001-00000055/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /ver remito/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /Generar remito/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /Recibo/i })).toBeNull()
    // El ticket sigue ahí (botón desde libra-ui v0.73.0).
    expect(screen.getByRole('button', { name: /Ticket/i })).toBeInTheDocument()
  })
})
