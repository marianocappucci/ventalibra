// Edición de sucursales (2026-09-17): antes se podían crear pero no editar.
// El diálogo de "Editar" cubre nombre, tipo, predeterminada y activa, y
// muestra el `detail` que devuelve el backend en un 409/422 tal cual.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
    if (u.startsWith('/locations')) return Promise.resolve(json(LOCATIONS))
    return Promise.resolve(json({}))
  }))
}

beforeEach(() => {
  sesion.rol = 'admin'
  montarRed()
})

async function montar() {
  const usuario = userEvent.setup()
  render(<Sucursales />)
  await screen.findByText('Depósito principal')
  return usuario
}

describe('Sucursales', () => {
  it('el cajero (staff) ve la lista, sin «Nueva sucursal» ni «Editar»', async () => {
    sesion.rol = 'staff'
    await montar()
    expect(screen.queryByText('Nueva sucursal')).toBeNull()
    expect(screen.queryByRole('button', { name: /Editar/ })).toBeNull()
  })

  it('el admin ve «Nueva sucursal» y «Editar»', async () => {
    await montar()
    expect(screen.getByText('Nueva sucursal')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Editar/ }).length).toBe(2)
  })

  it('pide la lista con incluir_inactivas: la de edición es la única forma de reactivar una', async () => {
    await montar()
    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'GET' && l.url.includes('incluir_inactivas=true'))).toBe(true)
    })
    // Y la inactiva se ve en la tabla (a diferencia del selector del POS, que
    // filtra por activas): es justo lo que hace falta para poder reactivarla.
    expect(screen.getByText('Sucursal Norte')).toBeInTheDocument()
  })

  it('el botón Editar abre el diálogo con los datos de esa sucursal', async () => {
    const usuario = await montar()

    const filas = screen.getAllByRole('button', { name: /Editar/ })
    await usuario.click(filas[0])

    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Editar sucursal')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Depósito principal')
    expect(screen.getByLabelText('Tipo')).toHaveValue('warehouse')
    expect(screen.getByLabelText('Predeterminada')).toBeChecked()
    expect(screen.getByLabelText('Activa')).toBeChecked()
  })

  it('guardar manda el PUT con los cuatro campos y recarga la lista', async () => {
    const usuario = await montar()

    await usuario.click(screen.getAllByRole('button', { name: /Editar/ })[0])
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

    await usuario.click(screen.getAllByRole('button', { name: /Editar/ })[0])
    await screen.findByRole('dialog')
    await usuario.click(screen.getByLabelText('Activa'))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await screen.findByText(/tiene un turno de caja abierto/)
    // Sigue abierto: nada que reintentar a mano si el pedido se rechazó.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('un 422 (nombre vacío) también se muestra, y no llega a mandar el PUT', async () => {
    const usuario = await montar()

    await usuario.click(screen.getAllByRole('button', { name: /Editar/ })[0])
    await screen.findByRole('dialog')
    const nombre = screen.getByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText('El nombre es obligatorio.')).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(false)
  })
})
