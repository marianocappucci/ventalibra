// La app entera con sesión de verdad (`AuthProvider` + `/auth/me`): los módulos que ve la SPA salen del usuario en sesión,
// no de un valor puesto a mano. Las pantallas sueltas están en `planes-y-modulos.test.tsx`.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AuthProvider } from '../context/AuthContext'

const PREMIUM = ['facturacion', 'multisucursal']
const BASICO: string[] = []

const CENTRO = {
  id: 1, nombre: 'Centro', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('App: los módulos salen del usuario en sesión', () => {
  function conSesion(modulos: string[] | undefined) {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/auth/me')) {
        return Promise.resolve(json({
          id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true, empresa_nombre: 'Prueba',
          ...(modulos === undefined ? {} : { modulos }),
        }))
      }
      if (u.includes('/api/sucursales')) return Promise.resolve(json([CENTRO]))
      return Promise.resolve(json([]))
    }))
    render(
      <MemoryRouter initialEntries={['/sucursales']}>
        <AuthProvider><App /></AuthProvider>
      </MemoryRouter>,
    )
  }

  it('un usuario de Básico ve el aviso en /sucursales', async () => {
    conSesion(BASICO)
    expect(await screen.findByRole('note')).toHaveTextContent('Más de una sucursal: disponible en Premium')
  })

  it('un usuario de Premium, no', async () => {
    conSesion(PREMIUM)
    expect(await screen.findByRole('button', { name: 'Nueva sucursal' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('sin el campo `modulos` (backend viejo) tampoco', async () => {
    conSesion(undefined)
    expect(await screen.findByRole('button', { name: 'Nueva sucursal' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})
