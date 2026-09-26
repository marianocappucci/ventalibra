// Clientes sobre el router del motor y las pantallas del kit (ADR-029, 2026-09-26): las páginas de
// VentaLibra son el kit con las variantes que corresponden a este producto. El comportamiento del
// listado, el alta, la baja y la ficha lo prueba el propio kit (`comercio-clientes.test.tsx`); acá se
// prueba el **montaje**: a qué API pega y qué variantes apaga.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { ClienteDetalle } from '../pages/ClienteDetalle'
import { Clientes } from '../pages/Clientes'

const ANA = {
  id: 1, name: 'Ana Gomez', address: '', cuit_dni: '27-12345678-9', email: 'ana@x.com', phone: '111',
  iva_condition: 'Responsable Inscripto', auto_facturar: 0, activo: 1,
}
const FICHA = { ...ANA, alias_facturacion: [], facturas: [], presupuestos: [], remitos: [] }

let pedidas: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  pedidas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidas.push(`${init?.method ?? 'GET'} ${u}`)
    if (u === '/api/clientes/1') return Promise.resolve(json(FICHA))
    if (u === '/api/clientes') return Promise.resolve(json([ANA]))
    return Promise.resolve(json([]))
  }))
})

afterEach(() => vi.unstubAllGlobals())

describe('Clientes (kit sobre /api/clientes)', () => {
  it('lista desde el router del motor, no desde /customers', async () => {
    render(<MemoryRouter><Clientes /></MemoryRouter>)
    expect(await screen.findByText('Ana Gomez')).toBeInTheDocument()
    expect(pedidas).toContain('GET /api/clientes')
    expect(pedidas.some((p) => p.includes('/customers'))).toBe(false)
  })

  it('el alta no ofrece consultar el CUIT en ARCA (VentaLibra no tiene ese endpoint)', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Clientes /></MemoryRouter>)
    await screen.findByText('Ana Gomez')
    await user.click(screen.getByRole('button', { name: /Nuevo cliente/ }))
    await screen.findByRole('dialog')
    expect(screen.queryByTitle('Consultar datos en ARCA')).not.toBeInTheDocument()
  })
})

describe('ClienteDetalle (kit sobre /api/clientes/:id)', () => {
  function montarFicha() {
    render(
      <MemoryRouter initialEntries={['/clientes/1']}>
        <Routes><Route path="/clientes/:id" element={<ClienteDetalle />} /></Routes>
      </MemoryRouter>,
    )
  }

  it('muestra los datos del cliente y pega al router del motor', async () => {
    montarFicha()
    expect(await screen.findByText('Datos del cliente')).toBeInTheDocument()
    expect(screen.getByText('27-12345678-9')).toBeInTheDocument()
    await waitFor(() => expect(pedidas).toContain('GET /api/clientes/1'))
  })

  it('no ofrece lo que VentaLibra no tiene: MercadoPago, comprobantes ni consulta de CUIT', async () => {
    montarFicha()
    await screen.findByText('Datos del cliente')
    expect(screen.queryByText('Auto-factura MP:')).not.toBeInTheDocument()
    expect(screen.queryByText(/Alias de facturación/)).not.toBeInTheDocument()
    expect(screen.queryByText('Resumen')).not.toBeInTheDocument()
    expect(screen.queryByText(/Nueva factura/)).not.toBeInTheDocument()
    expect(document.querySelector('a[href="/facturas/nueva"]')).toBeNull()
    // Sí conserva la baja.
    expect(screen.getByRole('button', { name: /Eliminar cliente/ })).toBeInTheDocument()
  })
})
