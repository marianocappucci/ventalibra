// El catálogo partido en dos pestañas: Unidades y Productos.
//
// Lo que fija este archivo es la ESTRUCTURA, que es lo que se pidió: que cada
// mitad tenga su listado y su alta, y que una no se mezcle con la otra. Radix
// desmonta el contenido de la pestaña que no está elegida, así que cada
// afirmación de "está" tiene su control de "y en la otra no está" — sin eso,
// un `Tabs` mal armado que rinda las dos mitades a la vez pasaría en verde.
//
// ⚠️ Los rótulos de las pestañas se buscan por `role="tab"`, igual que en
// `configuracion.test.tsx`: es lo que anuncia un lector de pantalla.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Catalogo } from '../pages/Catalogo'

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

/** Monta y espera a que la carga inicial termine — hasta entonces las dos
 *  pestañas muestran "Cargando…" y no hay tabla que mirar. */
async function montar() {
  const usuario = userEvent.setup()
  render(<Catalogo />)
  await screen.findByText('Yerba Playadito')
  return usuario
}

describe('Las dos pestañas del catálogo', () => {
  it('están las dos, y abre en Productos', async () => {
    await montar()

    expect(screen.getByRole('tab', { name: /Unidades/ })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: /Productos/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('Productos muestra los productos y su alta, y nada de unidades', async () => {
    await montar()

    expect(screen.getByText('Yerba Playadito')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Nuevo producto' })).toBeInTheDocument()
    // El control: `Kilogramo` sólo existe en la tabla de la otra pestaña (en
    // ésta la unidad aparece por su código, `kg`).
    expect(screen.queryByText('Kilogramo')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Nueva unidad' })).not.toBeInTheDocument()
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

  it('Unidades muestra las unidades y su alta, y nada de productos', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))

    expect(await screen.findByText('Kilogramo')).toBeInTheDocument()
    expect(screen.getByText('Unidad')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Nueva unidad' })).toBeInTheDocument()
    expect(screen.queryByText('Yerba Playadito')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Nuevo producto' })).not.toBeInTheDocument()
  })

  it('el alta de unidad también está detrás del botón', async () => {
    const usuario = await montar()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')

    // Cerrado no hay ni un campo del alta. `Código` y `Nombre` son además los
    // encabezados de la tabla, así que se busca por rótulo y no por texto:
    // `getByLabelText` no matchea un `<th>`, que es lo que distingue "el campo
    // no está" de "la tabla no está".
    expect(screen.queryByLabelText('Código')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))

    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Nueva unidad')
    expect(screen.getByLabelText('Código')).toBeInTheDocument()
    expect(screen.getByLabelText('Nombre')).toBeInTheDocument()
    expect(screen.getByLabelText(/Se vende por fracción/)).toBeInTheDocument()
  })

  it('las dos pestañas se operan igual: mismo botón, mismo modal', async () => {
    // El punto del cambio del 2026-08-24 no es cada modal por separado sino que
    // las dos mitades se usen igual. Sin esta afirmación, volver una de las dos
    // a una tarjeta fija no rompería ningún test.
    const usuario = await montar()

    expect(screen.getByRole('button', { name: '+ Nuevo producto' })).toBeInTheDocument()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    expect(await screen.findByRole('button', { name: '+ Nueva unidad' })).toBeInTheDocument()

    // Y ninguna de las dos deja campos sueltos en la pantalla.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Código')).not.toBeInTheDocument()
    await usuario.click(screen.getByRole('tab', { name: /Productos/ }))
    await screen.findByText('Yerba Playadito')
    expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
  })

  it('la tabla de unidades dice si la unidad se vende por fracción', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')

    // `kg` admite fracción con 3 decimales; `u` no, con 0. Se afirman los dos
    // para que la columna no pueda pasar en verde devolviendo siempre lo mismo.
    const kg = screen.getByText('Kilogramo').closest('tr')!
    const unidad = screen.getByText('Unidad').closest('tr')!
    expect(kg).toHaveTextContent('Sí')
    expect(kg).toHaveTextContent('3')
    expect(unidad).toHaveTextContent('No')
    expect(unidad).toHaveTextContent('0')
  })
})

describe('Las altas, cada una en su pestaña', () => {
  it('desde Unidades se crea una unidad, y el modal se cierra', async () => {
    const usuario = await montar()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))
    await usuario.type(await screen.findByLabelText('Código'), 'lt')
    await usuario.type(screen.getByLabelText('Nombre'), 'Litro')
    await usuario.click(screen.getByLabelText(/Se vende por fracción/))
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => expect(posts('/catalog/units')).toHaveLength(1))
    expect(posts('/catalog/units')[0].cuerpo).toEqual({
      code: 'lt', name: 'Litro', allows_fraction: true, decimal_scale: 3,
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('el alta de unidad incompleta avisa en vez de no hacer nada', async () => {
    // 🔴 Antes de pasar a modal esto era un `return` mudo: apretar "Crear
    // unidad" con un campo vacío no hacía absolutamente nada. En una tarjeta a
    // la vista se perdonaba; detrás de un modal no hay nada que mirar.
    const usuario = await montar()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))
    await usuario.type(await screen.findByLabelText('Código'), 'lt')
    // Sin nombre.
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    expect(await screen.findByText(/Código y nombre son obligatorios/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(posts('/catalog/units')).toHaveLength(0)
  })

  it('cancelar el alta de unidad a medio cargar no arrastra el borrador', async () => {
    const usuario = await montar()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))
    await usuario.type(await screen.findByLabelText('Código'), 'xx')
    await usuario.click(screen.getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))

    expect(await screen.findByLabelText('Código')).toHaveValue('')
    expect(posts('/catalog/units')).toHaveLength(0)
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

  it('un alta recarga las dos mitades, no sólo la propia', async () => {
    // Una unidad nueva tiene que aparecer en el `Select` del modal de alta de
    // producto, que vive en la OTRA pestaña. Por eso el alta recarga todo y no
    // sólo su listado: sin esto, cargar `lt` y pasar a Productos no la ofrece
    // hasta recargar la pantalla a mano.
    const usuario = await montar()
    await usuario.click(screen.getByRole('tab', { name: /Unidades/ }))
    await screen.findByText('Kilogramo')
    const antes = llamadas.filter((l) => l.metodo === 'GET' && l.url.startsWith('/catalog/items')).length

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))
    await usuario.type(await screen.findByLabelText('Código'), 'lt')
    await usuario.type(screen.getByLabelText('Nombre'), 'Litro')
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const despues = llamadas.filter((l) => l.metodo === 'GET' && l.url.startsWith('/catalog/items')).length
      expect(despues).toBeGreaterThan(antes)
    })
  })
})
