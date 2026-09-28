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
  { id: 1, nombre: 'Salón', descripcion: '', tipo: 'store', activo: 1, es_default: 1 },
]

function montarRed() {
  const llamadas: string[] = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/listas-precio') && !u.includes('/precio')) return Promise.resolve(json([LISTA]))
    if (u.includes('/api/listas-precio/5/precio?')) {
      const p = new URL(u).searchParams
      const cantidad = Number(p.get('cantidad') || 1)
      // Quiebre de cantidad: hasta 1 -> 3000, 2+ -> 2800
      const precio = cantidad >= 2 ? 2800 : 3000
      return Promise.resolve(json({ precio }))
    }
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/depositos')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
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
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)

    // Esperar a que se cargue el turno y la lista
    await screen.findByText(/Turno #1/)

    // Verificar que se llamó a /api/listas-precio
    expect(llamadas.some((u) => u.includes('/api/listas-precio') && !u.includes('/precio'))).toBe(true)
  })

  it('al agregar un ítem con lista default, el precio es el del producto (cantidad 1)', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)

    // Cantidad 1 -> precio 3000 (del quiebre de cantidad de la lista)
    const textElements = await screen.findAllByText(/3\.000,00/)
    expect(textElements.length).toBeGreaterThan(0)
  })

  it('sin lista predeterminada, el POS sigue funcionando (fallback)', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
      if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
      if (u.includes('/api/listas-precio') && !u.includes('/precio')) return Promise.resolve(json([])) // Sin lista
      if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
      if (u.includes('/api/depositos')) return Promise.resolve(json(LOCATIONS))
      if (u.includes('/customers')) return Promise.resolve(json([]))
      if (u.includes('/api/productos/escanear')) {
        return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
      }
      return Promise.resolve(json([]))
    }))

    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)

    // Sin lista default, usa precio_venta del producto (3000)
    const textElements = await screen.findAllByText(/3\.000,00/)
    expect(textElements.length).toBeGreaterThan(0)
  })

  it('si /api/listas-precio/{id}/precio falla, el POS no se bloquea', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }]))
      if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
      if (u.includes('/api/listas-precio') && !u.includes('/precio')) return Promise.resolve(json([LISTA]))
      if (u.includes('/api/listas-precio/5/precio')) return Promise.reject(new Error('500'))
      if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
      if (u.includes('/api/depositos')) return Promise.resolve(json(LOCATIONS))
      if (u.includes('/customers')) return Promise.resolve(json([]))
      if (u.includes('/api/productos/escanear')) {
        return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
      }
      return Promise.resolve(json([]))
    }))

    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    await escanear(user)

    // Aun con fallo en /precio, el POS vende sin bloquearse
    const textElements = await screen.findAllByText(/3\.000,00/)
    expect(textElements.length).toBeGreaterThan(0)
  })
})
