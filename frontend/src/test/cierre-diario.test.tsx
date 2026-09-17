// Pantalla de Cierre diario (2026-09-16): preview del día, turnos abiertos
// que bloquean, confirmación al cerrar y listado con ticket. Reabrir día
// (2026-09-17, LibraCore v1.107.0) se sumó acá mismo: sólo admin, motivo
// obligatorio y el anulado se ve en el historial.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// El rol de la sesión, cambiable por test -- mismo patrón que
// `sucursales.test.tsx`: "Reabrir día" es sólo de admin.
const sesion = vi.hoisted(() => ({ rol: 'admin' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol }, loading: false }),
}))

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

// Un faltante: lo declarado quedó por debajo de lo esperado -- la
// diferencia es negativa. Es el caso que muestra el defecto de formato
// (2026-09-17): "$-500,00" en vez de "-$500,00".
const PREVIEW_CON_FALTANTE = {
  ...PREVIEW_LISTO,
  monto_esperado_total: 5000, monto_declarado_total: 4500,
  diferencia_total: -500,
}

const CIERRE_ACTIVO = {
  id: 1, sucursal_id: 1, numero: 1, fecha: '2026-09-16', usuario_id: 1,
  cerrado_por_nombre: 'Admin', monto_esperado_total: 5000, monto_declarado_total: 5000,
  diferencia_total: 0, notas: '', created_at: '2026-09-16T20:00:00',
  anulado_en: null, anulado_por: null, motivo_anulacion: null,
}

const CIERRE_ANULADO = {
  ...CIERRE_ACTIVO,
  id: 2, numero: 2,
  anulado_en: '2026-09-17T09:00:00', anulado_por: 1, motivo_anulacion: 'Faltaba abrir turno',
}

function montarRed(opciones: {
  preview?: unknown; cerrarStatus?: number; cerrarBody?: unknown
  historial?: unknown[]; reabrirStatus?: number; reabrirBody?: unknown
} = {}) {
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
    if (u.match(/\/api\/cierre-diario\/\d+\/reabrir$/) && metodo === 'POST') {
      return Promise.resolve(json(opciones.reabrirBody ?? CIERRE_ANULADO, opciones.reabrirStatus ?? 200))
    }
    if (u.match(/\/api\/cierre-diario\?/)) return Promise.resolve(json(opciones.historial ?? []))
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
  sesion.rol = 'admin'
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

  it('con una diferencia negativa (faltante), el signo va antes del $', async () => {
    montarRed({ preview: PREVIEW_CON_FALTANTE })
    montar()

    await screen.findByText('-$500,00')
    expect(screen.queryByText('$-500,00')).not.toBeInTheDocument()
  })

  // ── Reabrir día (2026-09-17) ────────────────────────────────────────────

  it('el admin ve «Reabrir día» en un cierre activo y no en uno anulado', async () => {
    montarRed({ preview: PREVIEW_LISTO, historial: [CIERRE_ACTIVO, CIERRE_ANULADO] })
    montar()

    await screen.findByText('Cierre #1')
    expect(screen.getAllByRole('button', { name: /Reabrir día/ }).length).toBe(1)
  })

  it('el staff no ve «Reabrir día»', async () => {
    sesion.rol = 'staff'
    montarRed({ preview: PREVIEW_LISTO, historial: [CIERRE_ACTIVO] })
    montar()

    await screen.findByText('Cierre #1')
    expect(screen.queryByRole('button', { name: /Reabrir día/ })).toBeNull()
  })

  it('un cierre anulado muestra el badge «Anulado» y el motivo', async () => {
    montarRed({ preview: PREVIEW_LISTO, historial: [CIERRE_ANULADO] })
    montar()

    await screen.findByText('Anulado')
    expect(screen.getByText(/Faltaba abrir turno/)).toBeInTheDocument()
  })

  it('reabrir manda el POST con el motivo y recarga', async () => {
    const { llamadas } = montarRed({ preview: PREVIEW_LISTO, historial: [CIERRE_ACTIVO] })
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Reabrir día/ }))
    const dialogo = await screen.findByRole('dialog')

    await user.type(within(dialogo).getByPlaceholderText('Motivo (obligatorio)'), 'Faltaba abrir turno')
    await user.click(within(dialogo).getByRole('button', { name: /^Reabrir día$/ }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/cierre-diario/1/reabrir'))
      expect(post).toBeDefined()
      expect(post!.body).toEqual({ motivo: 'Faltaba abrir turno' })
    })
  })

  it('con el motivo vacío, el botón de confirmar queda deshabilitado', async () => {
    montarRed({ preview: PREVIEW_LISTO, historial: [CIERRE_ACTIVO] })
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Reabrir día/ }))
    const dialogo = await screen.findByRole('dialog')

    const confirmar = within(dialogo).getByRole('button', { name: /^Reabrir día$/ })
    expect(confirmar).toBeDisabled()

    await user.type(within(dialogo).getByPlaceholderText('Motivo (obligatorio)'), '   ')
    expect(confirmar).toBeDisabled()
  })

  it('un 409 al reabrir (cierre posterior activo) se muestra en el diálogo', async () => {
    montarRed({
      preview: PREVIEW_LISTO, historial: [CIERRE_ACTIVO],
      reabrirStatus: 409,
      reabrirBody: { detail: 'La sucursal ya tiene el cierre #2, posterior al 16-09-2026.' },
    })
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Reabrir día/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByPlaceholderText('Motivo (obligatorio)'), 'Faltaba abrir turno')
    await user.click(within(dialogo).getByRole('button', { name: /^Reabrir día$/ }))

    await within(dialogo).findByText(/posterior al 16-09-2026/)
  })
})
