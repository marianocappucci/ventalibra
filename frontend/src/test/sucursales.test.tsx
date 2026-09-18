// Sucursales / depósitos.
// - Edición (2026-09-17): el diálogo de "Editar" cubre nombre, tipo,
//   predeterminada y activa, y muestra el `detail` del backend (409/422).
// - Pestañas y alta en modal (2026-09-18): la lista se separa en "Sucursales"
//   y "Depósitos", el botón de alta va arriba a la derecha y abre un modal
//   (ya no hay formulario suelto en la página), y el tipo se elige de un
//   desplegable que dice "Sucursal"/"Depósito" -- el código `store`/
//   `warehouse` sólo viaja al backend.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

// El rol de la sesión, cambiable por test: alta y edición son sólo de admin.
const sesion = vi.hoisted(() => ({ rol: 'admin' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol }, loading: false }),
}))

import { Sucursales } from '../pages/Sucursales'

const LOCATIONS = [
  { id: 1, name: 'Depósito principal', branch_id: null, location_type: 'warehouse', active: true, is_default: true },
  { id: 2, name: 'Sucursal Norte', branch_id: null, location_type: 'store', active: false, is_default: false },
]

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function montarRed(opciones: { putStatus?: number; putBody?: unknown } = {}) {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const cuerpo = init?.body ? JSON.parse(String(init.body)) : null
    llamadas.push({ url: u, metodo, cuerpo })

    if (metodo === 'PUT' && u.startsWith('/locations/')) {
      const status = opciones.putStatus ?? 200
      if (status >= 400) {
        return Promise.resolve(json({ detail: (opciones.putBody as { detail?: string })?.detail ?? 'error' }, status))
      }
      const id = Number(u.split('/').pop())
      const actualizada = { ...LOCATIONS.find((l) => l.id === id), ...(cuerpo as object) }
      return Promise.resolve(json(actualizada))
    }
    if (metodo === 'POST' && u === '/locations') {
      return Promise.resolve(json({ id: 3, branch_id: null, active: true, is_default: false, ...(cuerpo as object) }, 201))
    }
    if (u.startsWith('/locations')) return Promise.resolve(json(LOCATIONS))
    return Promise.resolve(json({}))
  }))
}

beforeEach(() => {
  sesion.rol = 'admin'
  montarRed()
})

// Arranca en la pestaña "Sucursales"; `irADepositos` pasa a la otra, donde
// vive "Depósito principal" (la predeterminada, la que usan los tests de
// edición).
async function montar({ irADepositos = true } = {}) {
  const usuario = userEvent.setup()
  render(<Sucursales />)
  await screen.findByText('Sucursal Norte')
  if (irADepositos) {
    await usuario.click(screen.getByRole('tab', { name: /Depósitos/ }))
    await screen.findByText('Depósito principal')
  }
  return usuario
}

describe('Sucursales', () => {
  it('el cajero (staff) ve la lista, sin botón de alta ni «Editar»', async () => {
    sesion.rol = 'staff'
    await montar()
    expect(screen.queryByRole('button', { name: /Nuev[oa]/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Editar/ })).toBeNull()
  })

  it('no hay formulario de alta en la página: sólo la lista y el botón', async () => {
    await montar({ irADepositos: false })
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByText('warehouse')).toBeNull()
    expect(screen.getByRole('button', { name: 'Nueva sucursal' })).toBeInTheDocument()
  })

  it('separa sucursales y depósitos en pestañas', async () => {
    const usuario = userEvent.setup()
    render(<Sucursales />)
    await screen.findByText('Sucursal Norte')

    expect(screen.getByRole('tab', { name: 'Sucursales (1)' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Depósitos (1)' })).toBeInTheDocument()
    expect(screen.queryByText('Depósito principal')).toBeNull()

    await usuario.click(screen.getByRole('tab', { name: /Depósitos/ }))
    expect(await screen.findByText('Depósito principal')).toBeInTheDocument()
    expect(screen.queryByText('Sucursal Norte')).toBeNull()
    // El botón acompaña a la pestaña.
    expect(screen.getByRole('button', { name: 'Nuevo depósito' })).toBeInTheDocument()
  })

  it('el alta se hace en un modal, con el tipo de la pestaña ya elegido', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Nuevo depósito' }))
    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Nueva sucursal / depósito')
    // Muestra la palabra, no el código.
    expect(within(modal).getByRole('combobox', { name: 'Tipo' })).toHaveTextContent('Depósito')
    expect(modal).not.toHaveTextContent('warehouse')

    await usuario.type(within(modal).getByLabelText('Nombre'), 'Depósito Sur')
    await usuario.click(within(modal).getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url === '/locations')
      expect(post?.cuerpo).toEqual({ name: 'Depósito Sur', location_type: 'warehouse' })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('el tipo se cambia desde el desplegable: Sucursal manda `store`', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Nuevo depósito' }))
    const modal = await screen.findByRole('dialog')
    await usuario.type(within(modal).getByLabelText('Nombre'), 'Sucursal Centro')
    await usuario.click(within(modal).getByRole('combobox', { name: 'Tipo' }))
    await usuario.click(await screen.findByRole('option', { name: 'Sucursal' }))
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url === '/locations')
      expect(post?.cuerpo).toEqual({ name: 'Sucursal Centro', location_type: 'store' })
    })
  })

  it('el alta con nombre vacío no manda el POST', async () => {
    const usuario = await montar({ irADepositos: false })
    await usuario.click(screen.getByRole('button', { name: 'Nueva sucursal' }))
    await screen.findByRole('dialog')
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    expect(await screen.findByText('El nombre es obligatorio.')).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'POST')).toBe(false)
  })

  it('pide la lista con incluir_inactivas: la de edición es la única forma de reactivar una', async () => {
    await montar({ irADepositos: false })
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'GET' && l.url.includes('incluir_inactivas=true'))).toBe(true)
    })
    // Y la inactiva se ve en la tabla (a diferencia del selector del POS, que
    // filtra por activas): es justo lo que hace falta para poder reactivarla.
    expect(screen.getByText('Sucursal Norte')).toBeInTheDocument()
  })

  it('el botón Editar abre el diálogo con los datos de esa sucursal', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: /Editar/ }))

    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Editar depósito')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Depósito principal')
    expect(screen.getByRole('combobox', { name: 'Tipo' })).toHaveTextContent('Depósito')
    expect(screen.getByLabelText('Predeterminada')).toBeChecked()
    expect(screen.getByLabelText('Activa')).toBeChecked()
  })

  it('guardar manda el PUT con los cuatro campos y recarga la lista', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: /Editar/ }))
    await screen.findByRole('dialog')

    const nombre = screen.getByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Depósito renombrado')

    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      const put = llamadas.find((l) => l.metodo === 'PUT' && l.url === '/locations/1')
      expect(put).toBeDefined()
      expect(put!.cuerpo).toEqual({
        name: 'Depósito renombrado', location_type: 'warehouse',
        is_default: true, active: true,
      })
    })
    // El diálogo se cierra sólo si el guardado salió bien.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un 409 del backend (default/turno abierto) se muestra tal cual, sin cerrar el diálogo', async () => {
    montarRed({ putStatus: 409, putBody: { detail: 'No se puede desactivar la sucursal: tiene un turno de caja abierto.' } })
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: /Editar/ }))
    await screen.findByRole('dialog')
    await usuario.click(screen.getByLabelText('Activa'))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await screen.findByText(/tiene un turno de caja abierto/)
    // Sigue abierto: nada que reintentar a mano si el pedido se rechazó.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('un 422 (nombre vacío) también se muestra, y no llega a mandar el PUT', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: /Editar/ }))
    await screen.findByRole('dialog')
    const nombre = screen.getByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText('El nombre es obligatorio.')).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(false)
  })
})
