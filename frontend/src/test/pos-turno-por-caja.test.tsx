// Cajas por sucursal (2026-09-16): abrir turno pide sucursal y caja, y con
// turno abierto la sucursal del POS queda fija a la de esa caja (sin
// selector) -- ver `Pos.tsx::AbrirTurno` y el `useEffect` que sincroniza
// `locationId` con `turno.sucursal`.
import { render, screen, waitFor } from '@testing-library/react'
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

const MEDIOS = [{ id: 'efectivo', label: 'Efectivo' }]

const LOCATIONS = [
  { id: 1, name: 'Sucursal Centro', branch_id: null, location_type: 'warehouse', active: true, is_default: true },
  { id: 2, name: 'Sucursal Norte', branch_id: null, location_type: 'warehouse', active: true, is_default: false },
]

const CAJAS_SUCURSAL_1 = [
  { id: 10, nombre: 'Caja 1', descripcion: '', medios_pago: ['efectivo'], punto_venta: null,
    activo: true, es_default: true, sucursal_id: 1, tiene_turno_abierto: false },
  { id: 11, nombre: 'Caja 2', descripcion: '', medios_pago: ['efectivo'], punto_venta: null,
    activo: true, es_default: false, sucursal_id: 1, tiene_turno_abierto: true },
]

const TURNO_CON_CAJA = {
  id: 5, usuario_id: 1, usuario_nombre: 'Ana',
  apertura: '2026-09-16T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null,
  estado: 'abierto', notas: '', caja_id: 10,
  caja: { id: 10, nombre: 'Caja 1', punto_venta: null },
  sucursal: { id: 1, nombre: 'Sucursal Centro' },
}

function montarRedBase(opciones: { turno?: unknown; aperturaBody?: unknown; aperturaStatus?: number } = {}) {
  const llamadas: { metodo: string; url: string; body: unknown }[] = []

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: opciones.turno ?? null }))
    if (u.match(/\/api\/cajas\?sucursal_id=1/)) return Promise.resolve(json(CAJAS_SUCURSAL_1))
    if (u.match(/\/api\/cajas\?sucursal_id=2/)) return Promise.resolve(json([]))
    if (u.endsWith('/shifts/open') && metodo === 'POST') {
      return Promise.resolve(json(opciones.aperturaBody ?? { turno: TURNO_CON_CAJA }, opciones.aperturaStatus ?? 200))
    }
    if (u.includes('/locations')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas }
}

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Abrir turno pide sucursal y caja', () => {
  it('preselecciona la sucursal default y su caja predeterminada, y manda caja_id', async () => {
    const { llamadas } = montarRedBase()
    montar()

    await screen.findByText(/No hay ningún turno de caja abierto/)
    // La sucursal default (Sucursal Centro) trae sus cajas, y la
    // predeterminada sin turno abierto (Caja 1) queda preseleccionada -- se
    // espera a que el botón se habilite, que es la señal de que las dos
    // cadenas de `useEffect` (sucursales -> cajas -> preselección) ya
    // resolvieron, y no hay una carrera con el click.
    const boton = await screen.findByRole('button', { name: /Abrir turno/ })
    await waitFor(() => expect(boton).toBeEnabled())

    const user = userEvent.setup()
    await user.click(boton)

    const abrir = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/open'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(abrir.body).toMatchObject({ caja_id: 10 })
  })

  it('no ofrece una caja que ya tiene un turno abierto', async () => {
    montarRedBase()
    montar()

    await screen.findByText(/No hay ningún turno de caja abierto/)
    const combo = await screen.findByRole('combobox', { name: 'Caja' })
    await waitFor(() => expect(combo).toBeEnabled())

    const user = userEvent.setup()
    await user.click(combo)

    const opcionOcupada = await screen.findByRole('option', { name: /Caja 2/ })
    expect(opcionOcupada).toHaveAttribute('aria-disabled', 'true')
  })
})

describe('Con turno abierto en una caja, la sucursal queda fija', () => {
  it('muestra "Sucursal X · Caja Y" y no deja elegir otra sucursal', async () => {
    montarRedBase({ turno: TURNO_CON_CAJA })
    montar()

    // Los nombres del fixture ya vienen con el prefijo puesto ("Sucursal
    // Centro", "Caja 1"): no se duplica ("Sucursal Sucursal Centro"), que
    // era el defecto encontrado en la prueba en pantalla del 2026-09-17.
    await screen.findByText(/Sucursal Centro · Caja 1/)
    expect(screen.queryByText(/Sucursal Sucursal Centro/)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Sucursal' })).not.toBeInTheDocument()
  })

  it('la venta sale con el deposito_id de la sucursal de la caja del turno', async () => {
    const { llamadas } = montarRedBase({ turno: TURNO_CON_CAJA })
    // Sólo hace falta comprobar que el POS fija `locationId` a la sucursal
    // del turno -- lo que realmente viaja en `POST /api/ventas` ya lo cubre
    // `pos-registrar-venta.test.tsx`. Acá se verifica que NINGÚN pedido de
    // apertura de turno ocurre (ya hay uno) y que el badge fijo reemplaza al
    // selector, que es lo que garantiza que no se pueda desalinear a mano.
    montar()
    await screen.findByText(/Sucursal Centro · Caja 1/)
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/open'))).toBe(false)
  })

  it('el badge indica cómo trabajar en otra sucursal sin agregar un botón nuevo', async () => {
    // Pedido del humano (2026-09-17): con turno abierto tiene que quedar
    // claro cómo cambiar de sucursal, sin robarle alto a la pantalla. La
    // solución elegida es un `title` en el badge fijo -- "Cerrar turno" ya
    // está un click al lado, así que un segundo botón "Cambiar" haría lo
    // mismo dos veces.
    montarRedBase({ turno: TURNO_CON_CAJA })
    montar()

    const badge = await screen.findByText(/Sucursal Centro · Caja 1/)
    expect(badge).toHaveAttribute('title', 'Para trabajar en otra sucursal, cerrá el turno.')
    expect(screen.queryByRole('button', { name: /Cambiar/ })).not.toBeInTheDocument()
  })
})

describe('Encabezado del POS (2026-09-17)', () => {
  it('identifica la pantalla como "POS (Caja)"', async () => {
    montarRedBase({ turno: TURNO_CON_CAJA })
    montar()
    await screen.findByText('POS (Caja)')
  })

  it('con nombres que ya traen el prefijo, no lo duplica', async () => {
    // Mismo fixture que el resto del describe de arriba: "Sucursal Centro" /
    // "Caja 1".
    montarRedBase({ turno: TURNO_CON_CAJA })
    montar()
    await screen.findByText(/Sucursal Centro · Caja 1/)
    expect(screen.queryByText(/Sucursal Sucursal/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Caja Caja/)).not.toBeInTheDocument()
  })

  it('con nombres pelados (sin el prefijo), lo antepone', async () => {
    const turnoSinPrefijo = {
      ...TURNO_CON_CAJA,
      sucursal: { id: 1, nombre: 'Centro' },
      caja: { id: 10, nombre: '1' },
    }
    montarRedBase({ turno: turnoSinPrefijo })
    montar()
    await screen.findByText(/Sucursal Centro · Caja 1/)
  })
})

describe('Un turno viejo sin caja conserva el selector', () => {
  it('muestra el selector de sucursal y un aviso para migrarlo', async () => {
    const turnoSinCaja = { ...TURNO_CON_CAJA, caja_id: null, caja: null, sucursal: null }
    montarRedBase({ turno: turnoSinCaja })
    montar()

    await screen.findByRole('combobox', { name: 'Sucursal' })
    await screen.findByText(/Turno sin caja asignada/)
  })
})
