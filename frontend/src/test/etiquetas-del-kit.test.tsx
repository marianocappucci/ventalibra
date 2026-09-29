// Las etiquetas de góndola son la pantalla del kit (`libra-ui/comercio/EtiquetasGondola`) sobre los endpoints que el
// motor ya expone (ADR-047), sin wrapper ni endpoint propio. El detalle de la pantalla —el precio, la hoja, el CSS de
// impresión— lo prueban los tests del kit; acá, que se monta con las rutas de este producto y que la ruta y el menú
// piden `etiquetas`.
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { cwd } from 'node:process'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { EtiquetasGondola } from 'libra-ui/comercio/EtiquetasGondola'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } }))
    if (String(url) === '/api/productos') {
      return json([{
        id: 1, codigo: '5901234123457', nombre: 'Yerba Mate 500g', descripcion: '', precio_venta: 3000, precio_costo: 1800,
        unidad: 'u', categoria: 'Almacén', stock_minimo: 0, estacion: '', vendible: 1, activo: 1, tipo: 'producto',
      }])
    }
    return json([])
  }))
})

it('lista los productos del motor para elegir sus etiquetas', async () => {
  render(<MemoryRouter><EtiquetasGondola /></MemoryRouter>)
  expect(await screen.findByText('Yerba Mate 500g')).toBeInTheDocument()
  expect(screen.getByText('Etiquetas de góndola')).toBeInTheDocument()
})

it('la ruta y la entrada del menú piden la capacidad `etiquetas` (admin y encargado)', () => {
  const app = readFileSync(join(cwd(), 'src/App.tsx'), 'utf8')
  const ruta = app.match(/path="\/etiquetas"\s+element=\{\s*<ProtectedRoute cap="([^"]+)">/)
  expect(ruta?.[1]).toBe('etiquetas')
  const layout = readFileSync(join(cwd(), 'src/components/Layout.tsx'), 'utf8')
  expect(layout).toMatch(/to: '\/etiquetas'[^}]*hideFor: sinCapacidad\('etiquetas'\)/)
})
