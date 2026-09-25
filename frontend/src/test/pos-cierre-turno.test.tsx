// Cierre de turno: el "Efectivo contado" es dinero que DECLARA el cajero, y
// no puede caer a $0 en silencio con un texto inválido -- hallazgo del
// humano en la prueba en pantalla del 2026-09-17 (`Pos.tsx::CerrarTurno`,
// antes `Number(declarado) || 0`). Ver `parseMonto` en `Pos.tsx`.
import { render, screen, waitFor, within } from '@testing-library/react'
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
  { id: 1, name: 'Sucursal Centro', branch_id: null, location_type: 'store', active: true, is_default: true },
]

const TURNO = {
  id: 5, usuario_id: 1, usuario_nombre: 'Ana',
  apertura: '2026-09-17T10:00:00', cierre: null,
  monto_inicial: 1000, monto_declarado_cierre: null, monto_esperado_cierre: null,
  estado: 'abierto', notas: '', caja_id: 10,
  caja: { id: 10, nombre: 'Caja 1' },
  sucursal: { id: 1, nombre: 'Sucursal Centro' },
}

const RESUMEN = {
  movimientos: [],
  pagos_por_medio: { efectivo: 4000 },
  total_ventas: 4000,
  efectivo_ventas: 4000,
}

function montarRed() {
  const llamadas: { metodo: string; url: string; body: unknown }[] = []

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.match(/\/shifts\/5\/summary/)) return Promise.resolve(json({ turno: TURNO, resumen: RESUMEN }))
    if (u.match(/\/shifts\/5\/close$/) && metodo === 'POST') {
      return Promise.resolve(json({ turno: { ...TURNO, estado: 'cerrado' } }))
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

// Devuelve el `<dialog>` ya abierto: hace falta acotar las búsquedas del
// botón a su interior, porque el botón "Cerrar turno" del encabezado del POS
// (el que ABRE el diálogo) queda en el DOM con el mismo texto que el botón
// de submit DENTRO del diálogo (el que cierra).
async function abrirDialogoDeCierre(user: ReturnType<typeof userEvent.setup>) {
  const boton = await screen.findByRole('button', { name: /Cerrar turno/ })
  await user.click(boton)
  await screen.findByText(/Cerrar turno #5/)
  return screen.getByRole('dialog')
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Cerrar turno: "Efectivo contado" no cae a $0 en silencio', () => {
  it('con "a500" muestra el error, deshabilita el botón y no manda el POST de cierre', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    const dialog = await abrirDialogoDeCierre(user)

    const campo = within(dialog).getByLabelText('Efectivo contado')
    await user.type(campo, 'a500')

    await within(dialog).findByText(/Monto inválido/)
    const botonCerrar = within(dialog).getByRole('button', { name: /^Cerrar turno$/ })
    expect(botonCerrar).toBeDisabled()

    // No hay "Diferencia" visible con un monto inválido -- antes tampoco se
    // veía, pero el cierre se mandaba igual con $0 declarado.
    expect(within(dialog).queryByText('Diferencia')).not.toBeInTheDocument()

    // El botón deshabilitado no dispara nada -- el guardia del POST es la
    // otra prueba: ningún click, con el botón disabled, generó el POST.
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/5/close'))).toBe(false)
  })

  it('con "1500,50" manda el POST de cierre con monto_declarado 1500.5', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    const dialog = await abrirDialogoDeCierre(user)

    const campo = within(dialog).getByLabelText('Efectivo contado')
    await user.type(campo, '1500,50')

    const botonCerrar = within(dialog).getByRole('button', { name: /^Cerrar turno$/ })
    await waitFor(() => expect(botonCerrar).toBeEnabled())
    await user.click(botonCerrar)

    const cierre = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/5/close'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(cierre.body).toMatchObject({ monto_declarado: 1500.5 })
  })

  it.each([
    ['1.500', 1500],
    ['1.250.000,5', 1250000.5],
    ['500.25', 500.25],
  ])('"%s" se declara como %d (el punto de miles no se lee como decimal)', async (tipeado, esperado) => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    const dialog = await abrirDialogoDeCierre(user)

    await user.type(within(dialog).getByLabelText('Efectivo contado'), tipeado)
    const botonCerrar = within(dialog).getByRole('button', { name: /^Cerrar turno$/ })
    await waitFor(() => expect(botonCerrar).toBeEnabled())
    await user.click(botonCerrar)

    await waitFor(() => {
      const cierre = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/5/close'))
      expect(cierre?.body).toMatchObject({ monto_declarado: esperado })
    })
  })

  it('"1.5.0,50" es inválido: no se adivina qué quiso escribir', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    montar()
    const dialog = await abrirDialogoDeCierre(user)

    await user.type(within(dialog).getByLabelText('Efectivo contado'), '1.5.0,50')
    await within(dialog).findByText(/Monto inválido/)
    expect(within(dialog).getByRole('button', { name: /^Cerrar turno$/ })).toBeDisabled()
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/shifts/5/close'))).toBe(false)
  })

  it('con el campo vacío el botón queda deshabilitado, sin mostrar error', async () => {
    montarRed()
    const user = userEvent.setup()
    montar()
    const dialog = await abrirDialogoDeCierre(user)

    const botonCerrar = within(dialog).getByRole('button', { name: /^Cerrar turno$/ })
    expect(botonCerrar).toBeDisabled()
    expect(within(dialog).queryByText(/Monto inválido/)).not.toBeInTheDocument()
  })
})
