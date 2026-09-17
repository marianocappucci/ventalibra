// El catálogo de productos (renombrado de "Catálogo" a "Productos",
// 2026-09-17). La pestaña "Unidades" que tenía esta pantalla se fue a
// Configuración (ver `configuracion-unidades.test.tsx`) -- lo que fija este
// archivo es que acá ya no queda nada de eso: ni la pestaña, ni el alta de
// unidad, ni el `Tabs` que las separaba.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Navigate, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Productos } from '../pages/Productos'
import { REDIRECCIONES_DE_CATALOGO } from '../rutas-viejas'

// jsdom no implementa la API de pointer capture y Radix la toca al abrir un
// `Select`. Va acá y no en `test/setup.ts` porque es la única pantalla que
// abre un Select en los tests; si aparece una segunda, sube al setup.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

const UNIDADES = [
  { code: 'kg', name: 'Kilogramo', allows_fraction: true, decimal_scale: 3 },
  { code: 'u', name: 'Unidad', allows_fraction: false, decimal_scale: 0 },
]

const PRODUCTOS = [
  {
    id: 1, item_type: 'product', name: 'Yerba Playadito', description: '',
    category_id: null, unit_code: 'kg', active: true, sellable: true,
    purchasable: true, default_sale_price: '4500.00', default_cost: '3000.00',
  },
]

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST') return Promise.resolve(json({}))
    if (u.startsWith('/catalog/units')) return Promise.resolve(json(UNIDADES))
    if (u.startsWith('/catalog/items')) return Promise.resolve(json(PRODUCTOS))
    if (u.startsWith('/catalog/categories')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

const posts = (ruta: string) => llamadas.filter((l) => l.metodo === 'POST' && l.url === ruta)

/** Monta y espera a que la carga inicial termine. */
async function montar() {
  const usuario = userEvent.setup()
  render(<Productos />)
  await screen.findByText('Yerba Playadito')
  return usuario
}

describe('Productos', () => {
  it('muestra los productos y su alta, sin nada de unidades', async () => {
    await montar()

    expect(screen.getByText('Yerba Playadito')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Nuevo producto' })).toBeInTheDocument()
    // El control: `Kilogramo` es el NOMBRE de la unidad (sólo vivía en la
    // tabla de la pestaña que se fue); acá un producto muestra la unidad por
    // su código (`kg`), que sí sigue.
    expect(screen.queryByText('Kilogramo')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Nueva unidad' })).not.toBeInTheDocument()
  })

  it('no queda ningún `Tabs`: sin pestañas de "Unidades" ni "Productos"', async () => {
    // Antes de partirse, esta pantalla tenía dos `role="tab"` (Unidades y
    // Productos). Con una sola mitad no tiene sentido seguir separando en
    // pestañas -- si volviera un `Tabs` de una sola hoja sería ruido, no
    // una mejora.
    await montar()

    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('carga las unidades igual, sin mostrarlas: el alta de producto las necesita', async () => {
    await montar()

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'GET' && l.url.startsWith('/catalog/units'))).toBe(true)
    })
  })

  it('el alta de producto está detrás del botón, no puesta en la pantalla', async () => {
    const usuario = await montar()

    // Cerrado no hay ni un campo del alta: es lo que separa un modal de una
    // tarjeta escondida con CSS, que seguiría en el DOM.
    expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))

    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Nuevo producto')
    expect(screen.getByLabelText('Nombre')).toBeInTheDocument()
    expect(screen.getByLabelText('Unidad')).toBeInTheDocument()
    expect(screen.getByLabelText('Precio de venta')).toBeInTheDocument()
    expect(screen.getByLabelText('Costo')).toBeInTheDocument()
  })

  it('cerrar a medio cargar y volver a abrir no arrastra el borrador', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))
    await usuario.type(await screen.findByLabelText('Nombre'), 'a medio escribir')
    await usuario.click(screen.getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))

    expect(await screen.findByLabelText('Nombre')).toHaveValue('')
    // Y no se creó nada al cancelar.
    expect(posts('/catalog/items')).toHaveLength(0)
  })

  it('desde Productos se crea un producto, y el modal se cierra', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))
    await usuario.type(await screen.findByLabelText('Nombre'), 'Fideos')
    await usuario.click(screen.getByLabelText('Unidad'))
    await usuario.click(await screen.findByRole('option', { name: /^u —/ }))
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => expect(posts('/catalog/items')).toHaveLength(1))
    expect(posts('/catalog/items')[0].cuerpo).toMatchObject({
      name: 'Fideos', unit_code: 'u', category_id: null,
    })
    // Un alta que deja el modal abierto encima de la grilla parece que falló.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un alta incompleta avisa adentro del modal, sin cerrarlo ni postear', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))
    await usuario.type(await screen.findByLabelText('Nombre'), 'Fideos')
    // Sin elegir unidad.
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    expect(await screen.findByText(/Nombre y unidad son obligatorios/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(posts('/catalog/items')).toHaveLength(0)
  })
})

describe('La pantalla vieja', () => {
  /** 🔴 Las redirecciones salen de `REDIRECCIONES_DE_CATALOGO`, la MISMA
   *  tabla que monta `App.tsx` -- mismo criterio que
   *  `configuracion.test.tsx` con `REDIRECCIONES_DE_CONFIGURACION`: un test
   *  que reimplementa la ruta a mano puede seguir pasando mientras la app
   *  redirige a otro lado. */
  it('/catalogo lleva a /productos', async () => {
    render(
      <MemoryRouter initialEntries={['/catalogo']}>
        <Routes>
          <Route path="/productos" element={<Productos />} />
          {Object.entries(REDIRECCIONES_DE_CATALOGO).map(([desde, hacia]) => (
            <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
          ))}
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Productos')).toBeInTheDocument()
  })
})
