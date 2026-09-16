// Pantalla de Cierre diario (2026-09-16): preview del día, turnos abiertos
// que bloquean, confirmación al cerrar y listado con ticket.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CierreDiario } from '../pages/CierreDiario'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const LOCATIONS = [
  { id: 1, name: 'Sucursal Centro', branch_id: null, location_type: 'warehouse', active: true, is_default: true },
]

const PREVIEW_BLOQUEADO = {
  fecha: '2026-09-16', sucursal_id: 1,
  turnos_abiertos: [{
    id: 7, usuario_id: 2, usuario_nombre: 'Bruno', caja_id: 10, caja_nombre: 'Caja 1',
    apertura: '2026-09-16T09:00:00', cierre: null, estado: 'abierto',
    monto_inicial: 0, monto_esperado_cierre: null, monto_declarado_cierre: null,
    diferencia: 0, medios: [],
  }],
  turnos: [], medios: [], monto_esperado_total: 0, monto_declarado_total: 0,
  diferencia_total: 0, puede_cerrar: false, ya_cerrado: false,
}

const PREVIEW_LISTO = {
  ...PREVIEW_BLOQUEADO,
  turnos_abiertos: [],
  turnos: [{
    id: 7, usuario_id: 2, usuario_nombre: 'Bruno', caja_id: 10, caja_nombre: 'Caja 1',
    apertura: '2026-09-16T09:00:00', cierre: '2026-09-16T18:00:00', estado: 'cerrado',
    monto_inicial: 0, monto_esperado_cierre: 5000, monto_declarado_cierre: 5000,
    diferencia: 0, medios: [{ medio_pago: 'efectivo', ingresos: 5000, egresos: 0, neto: 5000 }],
  }],
  medios: [{ medio_pago: 'efectivo', ingresos: 5000, egresos: 0, neto: 5000 }],
  monto_esperado_total: 5000, monto_declarado_total: 5000,
  puede_cerrar: true,
}

function montarRed(opciones: { preview?: unknown; cerrarStatus?: number; cerrarBody?: unknown } = {}) {
  const llamadas: { metodo: string; url: string; body: unknown }[] = []

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: null }))
    if (u.includes('/locations')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/api/cierre-diario/preview')) return Promise.resolve(json(opciones.preview ?? PREVIEW_BLOQUEADO))
    if (u.endsWith('/api/cierre-diario/cerrar') && metodo === 'POST') {
      return Promise.resolve(json(opciones.cerrarBody ?? { id: 1 }, opciones.cerrarStatus ?? 200))
    }
    if (u.match(/\/api\/cierre-diario\?/)) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas }
}

function montar() {
  render(<MemoryRouter><CierreDiario /></MemoryRouter>)
}

beforeEach(() => {
  vi.useRealTimers()
})

describe('Cierre diario', () => {
  it('con turnos abiertos, los lista y no deja cerrar', async () => {
    montarRed({ preview: PREVIEW_BLOQUEADO })
    montar()

    await screen.findByText(/Bruno/)
    expect(screen.getByRole('button', { name: /Cerrar el día/ })).toBeDisabled()
  })

  it('sin turnos abiertos, cerrar pide confirmación antes de mandar el POST', async () => {
    const { llamadas } = montarRed({ preview: PREVIEW_LISTO })
    const user = userEvent.setup()
    montar()

    const boton = await screen.findByRole('button', { name: /Cerrar el día/ })
    expect(boton).not.toBeDisabled()
    await user.click(boton)

    await screen.findByText(/Confirmar cierre del día/)
    expect(llamadas.some((l) => l.url.endsWith('/api/cierre-diario/cerrar'))).toBe(false)

    await user.click(screen.getByRole('button', { name: /Confirmar cierre/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/api/cierre-diario/cerrar'))).toBe(true)
    })
  })

  it('un 422 (turnos abiertos que aparecieron después) se muestra legible', async () => {
    montarRed({
      preview: PREVIEW_LISTO,
      cerrarStatus: 422,
      cerrarBody: { detail: 'Hay 1 turno abierto en esta sucursal para el 2026-09-16.' },
    })
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Cerrar el día/ }))
    await user.click(await screen.findByRole('button', { name: /Confirmar cierre/ }))

    await screen.findByText(/Hay 1 turno abierto/)
  })

  it('un 409 (el día ya se cerró) se muestra legible', async () => {
    montarRed({
      preview: PREVIEW_LISTO,
      cerrarStatus: 409,
      cerrarBody: { detail: 'El día 2026-09-16 ya está cerrado para esta sucursal.' },
    })
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Cerrar el día/ }))
    await user.click(await screen.findByRole('button', { name: /Confirmar cierre/ }))

    await screen.findByText(/ya está cerrado/)
  })
})
