// Proveedores sobre el router del motor y las pantallas del kit (ADR-030, 2026-09-26): las páginas de
// VentaLibra son el kit, con la variante que corresponde a este producto (sin egresos). El listado, el
// alta y la ficha los prueba el propio kit; acá se prueba el **montaje**: a qué API pega y qué apaga.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

import { ProveedorDetalle } from '../pages/ProveedorDetalle'
import { Proveedores } from '../pages/Proveedores'

const ACME = {
  id: 1, nombre: 'ACME SA', cuit_dni: '30-11111111-1', email: 'acme@x.com', phone: '222', address: '',
  iva_condition: 'Responsable Inscripto',
}

let pedidas: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  pedidas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidas.push(`${init?.method ?? 'GET'} ${u}`)
    if (u.startsWith('/api/proveedores')) return Promise.resolve(json([ACME]))
    return Promise.resolve(json([]))
  }))
})

afterEach(() => vi.unstubAllGlobals())

describe('Proveedores (kit sobre /api/proveedores)', () => {
  it('lista desde el router del motor, no desde /suppliers', async () => {
    render(<MemoryRouter><Proveedores /></MemoryRouter>)
    expect(await screen.findByText('ACME SA')).toBeInTheDocument()
    expect(pedidas.some((p) => p.startsWith('GET /api/proveedores'))).toBe(true)
    expect(pedidas.some((p) => p.includes('/suppliers'))).toBe(false)
  })

  // 🔴 Igual que en Clientes: el alta no está suelta en la página (2026-09-21) y aparece sólo al abrir el modal. La guarda
  // negativa va con su contraparte positiva (las mismas consultas sí encuentran el formulario abierto): sola, pasa
  // «por otra razón».
  it('el alta no está suelta en la página: sólo la lista y el botón, y el formulario aparece al abrir el modal', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Proveedores /></MemoryRouter>)
    await screen.findByText('ACME SA')

    const CAMPOS = ['Nombre', 'CUIT/DNI', 'Teléfono', 'Email', 'Condición de IVA']
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    for (const campo of CAMPOS) expect(screen.queryByLabelText(campo)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nuevo proveedor/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
    const dialogo = await screen.findByRole('dialog')
    for (const campo of CAMPOS) expect(within(dialogo).getByLabelText(campo)).toBeInTheDocument()

    await user.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    for (const campo of CAMPOS) expect(screen.queryByLabelText(campo)).not.toBeInTheDocument()
  })
})

describe('ProveedorDetalle (kit, sin egresos)', () => {
  function montarFicha() {
    render(
      <MemoryRouter initialEntries={['/proveedores/1']}>
        <Routes><Route path="/proveedores/:id" element={<ProveedorDetalle />} /></Routes>
      </MemoryRouter>,
    )
  }

  it('muestra la ficha y no pide ni ofrece egresos (VentaLibra no tiene ese módulo)', async () => {
    montarFicha()
    expect(await screen.findByText('Datos del proveedor')).toBeInTheDocument()
    expect(screen.getByText('30-11111111-1')).toBeInTheDocument()
    await waitFor(() => expect(pedidas.some((p) => p.startsWith('GET /api/proveedores'))).toBe(true))
    expect(pedidas.some((p) => p.includes('/api/egresos'))).toBe(false)
    expect(screen.queryByText('Egresos registrados')).not.toBeInTheDocument()
    expect(screen.queryByText('Nuevo egreso')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Eliminar proveedor/ })).toBeInTheDocument()
  })
})
