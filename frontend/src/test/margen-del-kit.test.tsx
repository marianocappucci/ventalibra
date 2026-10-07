// Margen y rotación es la pantalla del kit (`libra-ui/comercio/Margen`) sobre el router del motor (`/api/reportes/margen`, ADR-046).
// La cuenta (qué es una venta, las devoluciones, el costo, el descuento) es del motor y se prueba allá; acá, que la ruta existe, que
// es de quien tiene `margen` (admin y encargado) y que la pantalla habla con la API que el kit espera.
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

const cifras = { costo_estimado: true, sin_costo: false }
const MARGEN = {
  desde: '2026-09-01', hasta: '2026-09-29', agrupacion: 'dia', producto_id: null, orden: 'margen', sentido: 'desc',
  resumen: {
    unidades: 3, ingreso: 4500, costo: 2700, margen: 1800, margen_pct: 40, ...cifras,
    productos: 1, productos_costo_estimado: 1, productos_sin_costo: 0, dias: 29,
  },
  productos: [{ producto_id: 1, nombre: 'Yerba 1kg', unidades: 3, unidades_por_dia: 0.1, ingreso: 4500, costo: 2700, margen: 1800, margen_pct: 40, ...cifras }],
  periodos: [{ periodo: '2026-09-27', unidades: 3, ingreso: 4500, costo: 2700, margen: 1800, margen_pct: 40, ...cifras }],
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
    if (u.startsWith('/api/reportes/margen')) return Promise.resolve(json(MARGEN))
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

describe('ruta /margen', () => {
  it('el admin ve el margen y la rotación del motor, con los exports CSV', async () => {
    conSesion('admin')
    abrir('/margen')
    expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/margen?'))).toBe(true)
    expect(document.querySelector('a[href^="/api/reportes/margen/export/productos"]')).toBeTruthy()
    expect(document.querySelector('a[href^="/api/reportes/margen/export/periodos"]')).toBeTruthy()
    // La entrada del menú lleva a la misma ruta.
    expect(screen.getAllByRole('link', { name: /Margen y rotación/ })[0]).toHaveAttribute('href', '/margen')
  })

  it('un cajero no llega: la ruta pide `margen` y ni siquiera pide el reporte', async () => {
    conSesion('cajero')
    abrir('/margen')
    await screen.findByRole('link', { name: /Ventas/ })
    expect(screen.queryByText('Yerba 1kg')).toBeNull()
    expect(llamadas.some((u) => u.startsWith('/api/reportes/margen'))).toBe(false)
    expect(screen.queryByRole('link', { name: /Margen y rotación/ })).toBeNull()
  })
})
