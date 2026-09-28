// El POS carga la lista de precio predeterminada (si existe) y aplica cantidad y
// vigencia por fecha/hora en vez del precio plano cuando:
// 1. Agrega un ítem (`elegirItem`) -- consulta `/api/listas-precio/{id}/precio`
// 2. Cambia la cantidad de una línea (`cambiarCantidad`) -- igual
// El fallback a precio plano nunca bloquea (mismo criterio que `mp-estado`).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana',
  apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null,
  estado: 'abierto', notas: '',
}

const ITEM = {
  id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001',
  unidad: 'u', precio_venta: 3000, activo: 1,
}

const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }

const LOCATIONS = [
  { id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 },
]

function montarRed(
  precioUno = 2500, precioMuchos = precioUno, listas: unknown[] = [LISTA], fallaPrecio = false,
  precioBalanza: number | null = null,
) {
  const llamadas: string[] = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/listas-precio/5/precio?')) {
      if (fallaPrecio) return Promise.resolve(json({ detail: 'boom' }, 500))
      const cantidad = Number(new URL(u, 'http://x').searchParams.get('cantidad') || 1)
      return Promise.resolve(json({ precio: cantidad >= 2 ? precioMuchos : precioUno }))
    }
    if (u === '/api/listas-precio') return Promise.resolve(json(listas))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: precioBalanza, de_balanza: precioBalanza !== null }))
    }
    return Promise.resolve(json([]))
  }))
  return { llamadas }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto = '779000001') {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

async function abrirCantidad() {
  fireEvent.keyDown(window, { key: 'F6' })
  const dialogo = await screen.findByRole('dialog')
  return dialogo
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Precio de lista (cantidad + vigencia)', () => {
  it('carga la lista predeterminada al montar el POS', async () => {
    const { llamadas } = montarRed()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
  })

  it('al agregar, el precio sale de la lista (no del precio plano) y consulta con cantidad y fecha', async () => {
    const { llamadas } = montarRed(2500)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/2\.500,00/)).length).toBeGreaterThan(0)
    expect(screen.queryByText(/3\.000,00/)).not.toBeInTheDocument()
    const consulta = llamadas.find((u) => u.includes('/api/listas-precio/5/precio?'))!
    expect(consulta).toContain('producto_id=3')
    expect(consulta).toContain('cantidad=1')
    expect(consulta).toMatch(/en=\d{4}-\d{2}-\d{2}T/)
  })

  it('al cambiar la cantidad, vuelve a consultar y aplica el quiebre alcanzado', async () => {
    const { llamadas } = montarRed(2500, 2000)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)
    await screen.findAllByText(/2\.500,00/)

    const dialogo = await abrirCantidad()
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, '3')
    await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // 3 x 2.000 = 6.000: la cantidad quedó cargada y el precio se refrescó al del quiebre.
    await waitFor(() => expect(screen.getAllByText(/6\.000,00/).length).toBeGreaterThan(0))
    expect(llamadas.some((u) => u.includes('/api/listas-precio/5/precio?') && u.includes('cantidad=3'))).toBe(true)
  })

  it('sin lista predeterminada vende al precio plano y no consulta precios', async () => {
    const { llamadas } = montarRed(2500, 2000, [])
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((u) => u.includes('/precio?'))).toBe(false)
  })

  it('si la consulta de precio falla, vende al precio plano sin bloquear', async () => {
    const { llamadas } = montarRed(2500, 2000, [LISTA], true)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/3\.000,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((u) => u.includes('/precio?'))).toBe(true)
  })

  it('una etiqueta de balanza con precio propio no se pisa con el de la lista', async () => {
    const { llamadas } = montarRed(2500, 2000, [LISTA], false, 4200)
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await screen.findByText(/Turno #/)
    await waitFor(() => expect(llamadas.some((u) => u === '/api/listas-precio')).toBe(true))
    await escanear(user)
    await screen.findByText(/Yerba 1kg/)

    expect((await screen.findAllByText(/4\.200,00/)).length).toBeGreaterThan(0)
    expect(llamadas.some((u) => u.includes('/precio?'))).toBe(false)
  })
})
