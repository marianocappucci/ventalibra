// Mermas es la pantalla del kit (`libra-ui/comercio/Mermas`) sobre el router del motor (`/api/reportes/mermas`, ADR-086). La cuenta es del
// motor; acá, que la ruta existe, que es de quien tiene `costos.ver` (admin y encargado: el humano decidió que los importes de merma no los vea
// nadie más) y que la pantalla habla con la API que el kit espera.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

let llamadas: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const MERMAS = {
  desde: '2026-10-01', hasta: '2026-10-14', deposito_id: null, producto_id: null,
  resumen: { cantidad: 4, costo_total: 2172.84, movimientos: 1, movimientos_sin_costo: 0, cantidad_sin_costo: 0, sin_costo: false, productos: 1, productos_sin_costo: 0 },
  productos: [{ producto_id: 1, codigo: 'LECHE-1', nombre: 'Leche 1L', unidad: 'u', cantidad: 4, costo_total: 2172.84, movimientos: 1, movimientos_sin_costo: 0, cantidad_sin_costo: 0, sin_costo: false }],
}

function conSesion(role: 'admin' | 'cajero') {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role, active: true,
        nombre: 'Ana', modulos: [], capacidades: CAPACIDADES_POR_ROL[role], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u.startsWith('/api/reportes/mermas')) return Promise.resolve(json(MERMAS))
    return Promise.resolve(json([]))
  }))
}

function abrir(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('ruta /mermas', () => {
  it('el admin ve las mermas del motor, con el export CSV y la entrada del menú', async () => {
    conSesion('admin')
    abrir('/mermas')
    expect(await screen.findByText('Leche 1L')).toBeInTheDocument()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/mermas'))).toBe(true)
    expect(document.querySelector('a[href^="/api/reportes/mermas/export"]')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /^Mermas/ })[0]).toHaveAttribute('href', '/mermas')
  })

  it('un cajero no llega: la ruta pide `costos.ver` y ni siquiera pide el reporte', async () => {
    conSesion('cajero')
    abrir('/mermas')
    await screen.findByRole('link', { name: /Ventas/ })
    expect(screen.queryByText('Leche 1L')).toBeNull()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/mermas'))).toBe(false)
    expect(screen.queryByRole('link', { name: /^Mermas/ })).toBeNull()
  })
})
