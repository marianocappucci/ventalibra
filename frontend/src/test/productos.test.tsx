// El catálogo de productos (renombrado de "Catálogo" a "Productos",
// 2026-09-17). La pestaña "Unidades" que tenía esta pantalla se fue a
// Configuración (ver `configuracion-unidades.test.tsx`) -- lo que fija este
// archivo es que acá ya no queda nada de eso: ni la pestaña, ni el alta de
// unidad, ni el `Tabs` que las separaba.
import { render, screen, waitFor, within } from '@testing-library/react'
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

/** Monta y espera a que la carga inicial termine.
 *
 *  Envuelto en `MemoryRouter` desde que el alta/edición de producto puede
 *  mostrar un `Link` a Configuración › Categorías (cuando no hay ninguna
 *  categoría cargada -- ver `ItemFormFields` en `Productos.tsx`): sin
 *  Router, ese `Link` revienta con "useHref() may be used only in the
 *  context of a <Router>", aunque la pantalla no navegue nunca en este
 *  archivo. */
async function montar() {
  const usuario = userEvent.setup()
  render(<MemoryRouter><Productos /></MemoryRouter>)
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

describe('Edición de un producto', () => {
  it('el lápiz abre el modal con los datos precargados', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))

    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Editar producto')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Yerba Playadito')
    expect(screen.getByLabelText('Unidad')).toHaveTextContent('kg')
    expect(screen.getByLabelText('Precio de venta')).toHaveValue('4500.00')
    expect(screen.getByLabelText('Costo')).toHaveValue('3000.00')
    expect(screen.getByRole('switch', { name: 'Activo' })).toBeChecked()
  })

  it('guardar manda un PUT con el nombre, el precio y el estado editados', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))
    const nombre = await screen.findByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Yerba Playadito 1kg')
    const precio = screen.getByLabelText('Precio de venta')
    await usuario.clear(precio)
    // Con coma decimal, como lo tipearía un cajero -- mismo criterio que
    // `parseMonto` en Pos.tsx.
    await usuario.type(precio, '5000,50')
    await usuario.click(screen.getByRole('switch', { name: 'Activo' }))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(true))
    const put = llamadas.find((l) => l.metodo === 'PUT')!
    expect(put.url).toBe('/catalog/items/1')
    expect(put.cuerpo).toMatchObject({
      name: 'Yerba Playadito 1kg',
      unit_code: 'kg',
      category_id: null,
      default_sale_price: '5000.5',
      default_cost: '3000',
      active: false,
    })
    // Un guardado que deja el modal abierto encima de la grilla parece que falló.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un precio invalido avisa adentro del modal, sin mandar el PUT', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))
    const precio = await screen.findByLabelText('Precio de venta')
    await usuario.clear(precio)
    await usuario.type(precio, 'no-es-un-numero')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText(/números válidos, no negativos/)).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(false)
  })

  it('un 409 por cambiarle la unidad a un producto con movimientos se muestra en el modal', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (metodo === 'PUT') {
        return Promise.resolve(new Response(
          JSON.stringify({ detail: 'No se puede cambiar la unidad de un producto que ya tiene movimientos.' }),
          { status: 409, headers: { 'content-type': 'application/json' } },
        ))
      }
      if (u.startsWith('/catalog/units')) return Promise.resolve(json(UNIDADES))
      if (u.startsWith('/catalog/items')) return Promise.resolve(json(PRODUCTOS))
      if (u.startsWith('/catalog/categories')) return Promise.resolve(json([]))
      return Promise.resolve(json([]))
    }))

    const usuario = await montar()
    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))
    await usuario.click(await screen.findByLabelText('Unidad'))
    await usuario.click(await screen.findByRole('option', { name: /^u —/ }))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText(/ya tiene movimientos/)).toBeInTheDocument()
    // El modal sigue abierto: el 409 no se lleva puesto lo que se estaba editando.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('cancelar no manda ningún PUT', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))
    await usuario.type(await screen.findByLabelText('Nombre'), ' (borrador)')
    await usuario.click(screen.getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(llamadas.some((l) => l.metodo === 'PUT')).toBe(false)
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

describe('Columna Categoría', () => {
  it('muestra el nombre de la categoría, y "—" para el que no tiene', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (metodo === 'POST') return Promise.resolve(json({}))
      if (u.startsWith('/catalog/units')) return Promise.resolve(json(UNIDADES))
      if (u.startsWith('/catalog/items')) {
        return Promise.resolve(json([
          ...PRODUCTOS,
          {
            id: 2, item_type: 'product', name: 'Fideos', description: '',
            category_id: 1, unit_code: 'u', active: true, sellable: true,
            purchasable: true, default_sale_price: '1500.00', default_cost: '900.00',
          },
        ]))
      }
      if (u.startsWith('/catalog/categories')) {
        return Promise.resolve(json([{ id: 1, name: 'Almacén', parent_id: null, active: true }]))
      }
      return Promise.resolve(json([]))
    }))

    await montar()
    await screen.findByText('Fideos')

    // 🔴 Mutación (b): si la columna mostrara el `category_id` en vez del
    // nombre, acá se vería "1" y no "Almacén".
    expect(screen.getByText('Almacén')).toBeInTheDocument()

    // El "—" se busca POR CELDA y no por texto: desde que existe la columna
    // "Stock total" (2026-09-21) hay más de un "—" en pantalla, y un
    // `getByText('—')` encuentra los tres y falla por ambiguo. Las columnas
    // son: 0 Nombre · 1 Unidad · 2 Categoría · 3 Precio · 4 Stock total ·
    // 5 Estado · 6 Acciones.
    const filaSinCategoria = screen.getByText('Yerba Playadito').closest('tr') as HTMLElement
    expect(within(filaSinCategoria).getAllByRole('cell')[2]).toHaveTextContent('—')
  })
})

describe('Sin categorías cargadas', () => {
  it('el alta de producto muestra un enlace a Configuración › Categorías', async () => {
    // El mock por defecto del `beforeEach` ya devuelve `[]` para
    // `/catalog/categories` -- es el caso "todavía no hay ninguna".
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: '+ Nuevo producto' }))

    expect(await screen.findByText(/Todavía no hay categorías cargadas/)).toBeInTheDocument()
    const enlace = screen.getByRole('link', { name: /Configuración › Categorías/ })
    expect(enlace).toHaveAttribute('href', '/configuracion?seccion=categorias')
  })

  it('la edición de producto muestra el mismo enlace', async () => {
    const usuario = await montar()

    await usuario.click(screen.getByRole('button', { name: 'Editar producto' }))

    expect(await screen.findByText(/Todavía no hay categorías cargadas/)).toBeInTheDocument()
  })
})

describe('Columna Stock total', () => {
  // La columna se llama "Stock total" y no "Stock" a proposito: es la suma de
  // TODOS los depositos. Con varias sucursales, un "Stock: 10" al lado de un
  // producto se lee como "hay 10 aca", y puede ser 10 en el otro local.
  function conStock(grilla: unknown) {
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (metodo === 'POST') return Promise.resolve(json({}))
      if (u.startsWith('/stock/por-deposito/grilla')) return Promise.resolve(json(grilla))
      if (u.startsWith('/catalog/units')) return Promise.resolve(json(UNIDADES))
      if (u.startsWith('/catalog/items')) return Promise.resolve(json(PRODUCTOS))
      return Promise.resolve(json([]))
    }))
  }

  it('muestra el total sumado de todos los depositos', async () => {
    conStock({
      depositos: [{ id: 1, nombre: 'Centro', tipo: 'store' }],
      items: [{ item_id: 1, nombre: 'Yerba Playadito', unit_code: 'kg', por_deposito: { '1': '7' }, total: '7' }],
    })
    await montar()
    await screen.findByText('Yerba Playadito')

    expect(screen.getByRole('columnheader', { name: /Stock total/ })).toBeInTheDocument()
    const fila = screen.getByText('Yerba Playadito').closest('tr') as HTMLElement
    expect(within(fila).getAllByRole('cell')[4]).toHaveTextContent('7')
  })

  // 🔑 NO hay test del aislamiento del pedido de stock, y es a propósito.
  //
  // El código lo pide fuera del `Promise.all` y con su propio `.catch`, para
  // que un 500 en stock no deje a Productos sin catálogo. Escribí un test para
  // eso y **pasaba con y sin el aislamiento**: mutando el pedido para que
  // corriera dentro del `try` que corta `loadAll`, el test seguía en verde.
  // No encontré qué lo sostiene, y un test que pasa bajo toda mutación es peor
  // que ninguno: da confianza falsa sobre una guarda que nadie verificó.
  //
  // Queda anotado como cobertura faltante. Si alguien lo retoma, el camino es
  // averiguar primero por qué el 500 del stub no llega a `setError`.
})
