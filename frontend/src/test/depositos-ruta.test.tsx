// `/depositos/:id` (el stock de un depósito, al que llega «Ver stock» desde el detalle de una sucursal) lleva el mismo
// gate que `/sucursales/:id`: lo mira también el cajero. Sin `adminOnly`, que lo mandaría de vuelta al POS. El
// backend rechaza sus escrituras y la pantalla no se las ofrece (eso lo prueba `sucursales-del-kit.test.tsx`).
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function conSesion(role: 'admin' | 'staff') {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role, active: true,
        nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u === '/api/depositos') {
      return Promise.resolve(json([
        { id: 12, nombre: 'Salón Norte', descripcion: '', branch_id: 7, tipo: 'warehouse', activo: 1, es_default: 0, total_productos: 0 },
      ]))
    }
    return Promise.resolve(json([]))
  }))
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('ruta /depositos/:id', () => {
  it.each(['admin', 'staff'] as const)('la abre el rol %s, sin mandarlo al POS', async (rol) => {
    conSesion(rol)
    render(
      <MemoryRouter initialEntries={['/depositos/12']}>
        <AuthProvider><App /></AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: /Salón Norte/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Volver/ })).toHaveAttribute('href', '/sucursales')
  })
})
