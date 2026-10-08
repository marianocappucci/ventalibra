// Los turnos de caja son la pantalla del kit (`libra-ui/comercio/Turnos`) con la variante de VentaLibra
// (`conCaja`, ADR-032): el cajero ve los suyos, el admin los de todos, y el turno se abre sobre una caja libre.
// Los detalles de la pantalla los prueban los tests del kit; acá, que el wrapper lee el rol y activa la variante.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

const sesion = vi.hoisted(() => ({ rol: 'admin' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol }, loading: false }),
}))

import { _resetCacheDeMedios } from 'libra-ui/comercio/medios-pago'
import { Turnos } from '../pages/Turnos'

const TURNO = {
  id: 5, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-09-26 08:00:00', cierre: null, monto_inicial: 100,
  monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
  caja_id: 2, caja: { id: 2, nombre: 'Mostrador', punto_venta: null }, sucursal: { id: 1, nombre: 'Salón' },
}
const CAJAS = [
  { id: 2, nombre: 'Mostrador', activo: 1, es_default: 1, tiene_turno_abierto: true, sucursal_nombre: 'Salón', medios_pago: [] },
  { id: 3, nombre: 'Barra', activo: 1, es_default: 0, tiene_turno_abierto: false, sucursal_nombre: 'Salón', medios_pago: [] },
]
let llamadas: { metodo: string; url: string; body?: Record<string, unknown> }[]

beforeEach(() => {
  _resetCacheDeMedios()
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const ruta = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: ruta, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const json = (data: unknown) => Promise.resolve(new Response(JSON.stringify(data), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
    if (ruta === '/api/turnos') return json({ turnos: [TURNO], turno_activo: null })
    if (ruta === '/api/cajas') return json(CAJAS)
    if (ruta === '/api/turnos/abrir') return json({ ...TURNO, id: 6, caja_id: 3 })
    return json([])
  }))
})

it('el admin ve los turnos de todos, con la caja de cada uno', async () => {
  sesion.rol = 'admin'
  render(<MemoryRouter><Turnos /></MemoryRouter>)
  expect(await screen.findByText('Todos los turnos')).toBeInTheDocument()
  expect(screen.getByText('Mostrador')).toBeInTheDocument()
})

it('el cajero ve «Mis turnos»', async () => {
  sesion.rol = 'cajero'
  render(<MemoryRouter><Turnos /></MemoryRouter>)
  expect(await screen.findByText('Mis turnos')).toBeInTheDocument()
})

it('abrir un turno ofrece sólo las cajas libres y manda caja_id', async () => {
  sesion.rol = 'admin'
  const user = userEvent.setup()
  render(<MemoryRouter><Turnos /></MemoryRouter>)
  await screen.findByText('Todos los turnos')
  await user.click(screen.getByRole('button', { name: /Abrir turno/ }))
  const dialogo = await screen.findByRole('dialog')
  // La única libre es «Barra» (Mostrador ya tiene un turno abierto) y queda preseleccionada.
  await waitFor(() => expect(within(dialogo).getByRole('combobox', { name: 'Caja' })).toHaveValue('Barra — Salón'))
  await user.click(within(dialogo).getByRole('button', { name: /Abrir turno ahora/ }))
  await waitFor(() => expect(llamadas.some((l) => l.url === '/api/turnos/abrir')).toBe(true))
  expect(llamadas.find((l) => l.url === '/api/turnos/abrir')!.body).toMatchObject({ caja_id: 3 })
})
