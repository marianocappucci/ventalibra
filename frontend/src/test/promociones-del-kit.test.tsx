// Las promociones son la pantalla del kit (`libra-ui/comercio/Promociones`) sobre los routers del motor
// (ADR-043), sin wrapper ni variantes. El detalle de la pantalla lo prueban los tests del kit; acá, que se
// monta con las rutas de este producto y que la ruta y el menú son de admin.
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { cwd } from 'node:process'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { Promociones } from 'libra-ui/comercio/Promociones'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } }))
    if (String(url) === '/api/promociones') {
      return json([{
        id: 7, nombre: '2x1 alfajores', tipo: 'nxm', paga: 1, precio: null, desde: null, hasta: null, activa: 1,
        items: [{ producto_id: 1, cantidad: 2, nombre: 'Alfajor' }],
      }])
    }
    return json([])
  }))
})

it('lista las promociones del motor', async () => {
  render(<MemoryRouter><Promociones /></MemoryRouter>)
  expect(await screen.findByText('2x1 alfajores')).toBeInTheDocument()
  expect(screen.getByText(/Llevá 2 pagá 1/)).toBeInTheDocument()
})

it('la ruta y la entrada del menú son de admin', () => {
  const app = readFileSync(join(cwd(), 'src/App.tsx'), 'utf8')
  const ruta = app.match(/path="\/promociones"\s+element=\{\s*<ProtectedRoute( adminOnly)?>/)
  expect(ruta?.[1]).toBe(' adminOnly')
  const layout = readFileSync(join(cwd(), 'src/components/Layout.tsx'), 'utf8')
  expect(layout).toMatch(/to: '\/promociones'[^}]*adminOnly: true/)
})
