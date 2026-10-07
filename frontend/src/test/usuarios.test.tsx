// El shim `Usuarios` de VentaLibra sobre `libra-ui/Usuarios` (adopción del
// router de usuarios de libraauth, 2026-09-13, ADR-018).
//
// La lógica de la grilla (mostrar/ocultar "Eliminar" según `permitirEliminar`
// y `usuarioActualId`) ya la prueba a fondo `libra-ui` en su propia suite —
// no se repite acá, ver el comentario de cobertura en `vitest.config.ts`. Lo
// que este archivo verifica es el CABLEADO propio de VentaLibra: que el shim
// prenda `permitirEliminar` y le pase el id del usuario REALMENTE logueado
// (no un valor fijo) -- que es justo lo que un `git show`/lectura del código
// no distingue de "está todo bien" si nadie lo corre contra un usuario de
// verdad.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u-yo', username: 'yo', name: 'Yo Misma', role: 'admin' },
    loading: false,
  }),
}))

import { Usuarios } from '../pages/Usuarios'

const USUARIOS = [
  { id: 'u-yo', username: 'yo', name: 'Yo Misma', role: 'admin', active: true, email: '' },
  { id: 'u-otro', username: 'otro', name: 'Otra Persona', role: 'cajero', active: true, email: '' },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).startsWith('/users')) return Promise.resolve(json(USUARIOS))
    return Promise.resolve(json([]))
  }))
})

describe('Usuarios (shim de VentaLibra)', () => {
  it('permite eliminar, pero no en la fila del usuario logueado', async () => {
    render(<Usuarios />)

    await waitFor(() => {
      expect(screen.getByText('Otra Persona')).toBeInTheDocument()
    })

    // `permitirEliminar` está prendido: la fila ajena SÍ ofrece el botón.
    expect(screen.getByRole('button', { name: 'Eliminar Otra Persona' })).toBeInTheDocument()
    // `usuarioActualId` viene del `useAuth()` real (mockeado acá con 'u-yo'),
    // no de un valor fijo -- la propia fila NO lo ofrece.
    expect(screen.queryByRole('button', { name: 'Eliminar Yo Misma' })).not.toBeInTheDocument()
  })
})

describe('Usuarios: los roles (ADR-049)', () => {
  // El kit ya acepta la lista de roles por prop (`roles`), así que el shim la pasa: hasta acá el default del kit
  // (`admin`/`staff`) dejaba al alta sin los roles nuevos; `staff` se retiró (ADR-071).
  it('el alta ofrece los cinco roles (y ya no el `staff` heredado), con el cajero por defecto', async () => {
    render(<Usuarios />)
    await waitFor(() => expect(screen.getByText('Otra Persona')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: '+ Nuevo usuario' }))
    const selector = await screen.findByRole('combobox', { name: 'Rol' })
    // El primero de la lista es el que trae el formulario: el de menos privilegio que sirve para trabajar.
    expect(selector).toHaveTextContent('Cajero')

    await userEvent.click(selector)
    const opciones = (await screen.findAllByRole('option')).map((o) => o.textContent)
    expect(opciones).toEqual([
      'Cajero', 'Vendedor', 'Depósito', 'Encargado', 'Admin',
    ])
  })
})

