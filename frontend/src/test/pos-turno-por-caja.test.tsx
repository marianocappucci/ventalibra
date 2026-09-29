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

// Sucursales como las devuelve `GET /api/sucursales`. El depósito de venta nunca comparte id con su sucursal.
const LOCATIONS = [
  { id: 1, nombre: 'Sucursal Centro', codigo: null, direccion: null, activa: true, es_default: true,
    deposito_predeterminado_id: 11, depositos: 1 },
  { id: 2, nombre: 'Sucursal Norte', codigo: null, direccion: null, activa: true, es_default: false,
    deposito_predeterminado_id: 22, depositos: 2 },
]

const ITEM = {
  id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001',
  unidad: 'u', precio_venta: 3000, activo: 1,
}

const CAJAS_SUCURSAL_1 = [
  { id: 10, nombre: 'Caja 1', descripcion: '', medios_pago: ['efectivo'], punto_venta: null,
    activo: 1, es_default: 1, sucursal_id: 1, sucursal_nombre: 'Sucursal 1', tiene_turno_abierto: false },
  { id: 11, nombre: 'Caja 2', descripcion: '', medios_pago: ['efectivo'], punto_venta: null,
    activo: 1, es_default: 0, sucursal_id: 1, sucursal_nombre: 'Sucursal 1', tiene_turno_abierto: true },
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
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: opciones.turno ?? null }))
    if (u.match(/\/api\/cajas\?sucursal_id=1/)) return Promise.resolve(json(CAJAS_SUCURSAL_1))
    if (u.match(/\/api\/cajas\?sucursal_id=2/)) return Promise.resolve(json([]))
    if (u.endsWith('/api/turnos/abrir') && metodo === 'POST') {
      return Promise.resolve(json(opciones.aperturaBody ?? TURNO_CON_CAJA, opciones.aperturaStatus ?? 200))
    }
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u.endsWith('/api/ventas') && metodo === 'POST') {
      return Promise.resolve(json({
        id: 9, numero: 'POS-000009', fecha: '2026-09-16', estado: 'cobrada', status: 'confirmed', items: [],
        subtotal: 3000, descuento: 0, total: 3000, cliente_id: null, cliente_nombre: '', observaciones: '',
        pagos: [], factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '',
        created_at: '2026-09-16T10:05:00',
      }))
    }
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
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
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/turnos/abrir'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(abrir.body).toMatchObject({ caja_id: 10 })
  })

  it('no ofrece una caja inactiva, ni la preselecciona aunque sea la predeterminada', async () => {
    const inactiva = { id: 12, nombre: 'Caja dada de baja', descripcion: '', medios_pago: ['efectivo'],
      punto_venta: null, activo: 0, es_default: 1, sucursal_id: 1, sucursal_nombre: 'Sucursal 1', tiene_turno_abierto: false }
    CAJAS_SUCURSAL_1.unshift(inactiva)
    try {
      const { llamadas } = montarRedBase()
      montar()

      await screen.findByText(/No hay ningún turno de caja abierto/)
      const boton = await screen.findByRole('button', { name: /Abrir turno/ })
      await waitFor(() => expect(boton).toBeEnabled())
      const user = userEvent.setup()
      await user.click(screen.getByRole('combobox', { name: 'Caja' }))
      expect(screen.queryByRole('option', { name: /dada de baja/ })).not.toBeInTheDocument()
      await user.keyboard('{Escape}')
      await user.click(boton)
      const abrir = await waitFor(() => {
        const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/turnos/abrir'))
        expect(encontrada).toBeDefined()
        return encontrada!
      })
      expect(abrir.body).toMatchObject({ caja_id: 10 })
    } finally {
      CAJAS_SUCURSAL_1.shift()
    }
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

  it('la venta sale con el depósito de venta de la sucursal de la caja del turno, no con el id de la sucursal', async () => {
    // El turno es de la sucursal 2 (Norte), que vende del depósito 22; la predeterminada del sistema es la 1
    // (depósito 11): ni el 1, ni el 2, ni el 11 son un `deposito_id` válido para esta venta.
    const turnoNorte = { ...TURNO_CON_CAJA, sucursal: { id: 2, nombre: 'Sucursal Norte' } }
    const { llamadas } = montarRedBase({ turno: turnoNorte })
    montar()
    await screen.findByText(/Sucursal Norte · Caja 1/)
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/api/turnos/abrir'))).toBe(false)

    const user = userEvent.setup()
    await user.type(await screen.findByPlaceholderText(/scane|Escane|código|codigo/i), '779000001{Enter}')
    await screen.findByText(/Yerba 1kg/)
    await user.click(await screen.findByRole('button', { name: /Cobrar/ }))
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    const registro = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(registro.body).toMatchObject({ deposito_id: 22 })
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

  it('el botón "Cerrar turno" queda al final del encabezado, después de los badges', async () => {
    // Pedido del humano (2026-09-17): "Cerrar turno" es la acción y va
    // último, el más a la derecha -- primero el badge del turno, después el
    // de sucursal/caja. `compareDocumentPosition` compara nodos del DOM
    // real, no el orden en el JSX, así que un reordenamiento que se revierta
    // sin querer se nota acá.
    montarRedBase({ turno: TURNO_CON_CAJA })
    montar()

    const badgeTurno = await screen.findByText(/Turno #5/)
    const badgeSucursal = await screen.findByText(/Sucursal Centro · Caja 1/)
    const botonCerrar = await screen.findByRole('button', { name: 'Cerrar turno' })

    // DOCUMENT_POSITION_FOLLOWING: el argumento aparece DESPUES del nodo que
    // llama al método.
    expect(
      badgeTurno.compareDocumentPosition(badgeSucursal) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      badgeSucursal.compareDocumentPosition(botonCerrar) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
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
