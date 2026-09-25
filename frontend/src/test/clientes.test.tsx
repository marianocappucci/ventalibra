// Clientes: el alta pasa a un botón arriba a la derecha y un modal, y la
// pantalla queda igual que Proveedores (2026-09-21, pedido del humano).
//
// El buscador NO es nuevo acá: la tabla ya lo traía por el prop `search` de
// `DataTable`. Se cubre igual, porque el pedido era que las dos pantallas
// queden iguales y eso incluye que ninguna lo pierda.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

// Radix Select usa pointer capture, que jsdom no trae.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

import { Clientes } from '../pages/Clientes'

const CLIENTES = [
  {
    id: 1, display_name: 'Bioko Centro', party_type: 'person', email: 'centro@bioko.test',
    phone: '11-4455-6677', cuit: '30-11111111-1', condicion_iva: 'Responsable Inscripto', active: true,
  },
  {
    id: 2, display_name: 'Panadería López', party_type: 'person', email: null,
    phone: '2255-4040', cuit: '27-22222222-2', condicion_iva: 'Monotributista', active: true,
  },
]

type Llamada = { url: string; metodo: string; cuerpo: unknown }
let llamadas: Llamada[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function montarRed(opciones: { postStatus?: number; postDetail?: string } = {}) {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST' && u === '/customers') {
      const status = opciones.postStatus ?? 200
      if (status >= 400) return Promise.resolve(json({ detail: opciones.postDetail ?? 'error' }, status))
      return Promise.resolve(json({ ...CLIENTES[0], id: 3, display_name: 'Nuevo' }))
    }
    if (u === '/customers') return Promise.resolve(json(CLIENTES))
    return Promise.resolve(json({}))
  }))
}

beforeEach(() => { montarRed() })

function montar() {
  render(<MemoryRouter><Clientes /></MemoryRouter>)
}

// ⚠️ **Este test resistió la mutación y no pude demostrar que custodie algo.**
// Probé tres formas de simular "el formulario volvió a estar suelto" —dejar el
// Dialog siempre abierto, reemplazarlo por un `<div>`— y la suite siguió en
// VERDE en las tres, cuando debería ponerse roja. Las otras cinco mutaciones
// de este archivo sí matan su test, así que el arnés funciona; lo que no
// entendí es por qué ésta no. Queda anotado: el assert de abajo parece el
// correcto, pero **nadie verificó que lo sea**. 2026-09-21.
it('🔴 el formulario ya NO está suelto en la página: sólo la lista y el botón', async () => {
  montar()
  await screen.findByText('Bioko Centro')
  expect(screen.getByRole('link', { name: 'Bioko Centro' })).toHaveAttribute('href', '/clientes/1')

  expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Condición de IVA')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Nuevo cliente/ })).toBeInTheDocument()
})

it('el botón abre el modal con todos los campos, incluida la condición de IVA', async () => {
  const user = userEvent.setup()
  montar()
  await screen.findByText('Bioko Centro')

  await user.click(screen.getByRole('button', { name: /Nuevo cliente/ }))

  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  for (const campo of ['Nombre', 'CUIT', 'Condición de IVA', 'Email', 'Teléfono']) {
    expect(screen.getByLabelText(campo)).toBeInTheDocument()
  }
})

it('el alta manda lo escrito, cierra el modal y recarga la lista', async () => {
  const user = userEvent.setup()
  montar()
  await screen.findByText('Bioko Centro')

  await user.click(screen.getByRole('button', { name: /Nuevo cliente/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Heladería Sur')
  await user.type(screen.getByLabelText('CUIT'), '20-33333333-3')
  await user.click(screen.getByRole('button', { name: 'Crear' }))

  await waitFor(() => {
    const envio = llamadas.find((l) => l.metodo === 'POST')
    expect(envio?.cuerpo).toEqual({
      display_name: 'Heladería Sur', party_type: 'person',
      email: null, phone: null, cuit: '20-33333333-3', condicion_iva: null,
    })
  })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(llamadas.filter((l) => l.url === '/customers' && l.metodo === 'GET')).toHaveLength(2)
})

it('🔴 sin nombre no se manda nada y el modal queda abierto', async () => {
  const user = userEvent.setup()
  montar()
  await screen.findByText('Bioko Centro')

  await user.click(screen.getByRole('button', { name: /Nuevo cliente/ }))
  await user.click(await screen.findByRole('button', { name: 'Crear' }))

  expect(await screen.findByText('El nombre es obligatorio.')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(llamadas.some((l) => l.metodo === 'POST')).toBe(false)
})

it('🔴 un error del backend se ve DENTRO del modal, que no se cierra', async () => {
  montarRed({ postStatus: 409, postDetail: 'Ya existe un cliente con ese CUIT.' })
  const user = userEvent.setup()
  montar()
  await screen.findByText('Bioko Centro')

  await user.click(screen.getByRole('button', { name: /Nuevo cliente/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Repetido')
  await user.click(screen.getByRole('button', { name: 'Crear' }))

  expect(await screen.findByText('Ya existe un cliente con ese CUIT.')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByLabelText('Nombre')).toHaveValue('Repetido')
})

it('el buscador de la tabla filtra, y busca también por un campo que NO es columna', async () => {
  // El teléfono no es columna y aun así se busca: es lo que queda anotado del
  // mostrador. Si el buscador mirara sólo lo visible, esto no encontraría nada.
  const user = userEvent.setup()
  montar()
  await screen.findByText('Bioko Centro')

  await user.type(screen.getByLabelText('Buscar cliente'), '2255-4040')

  await waitFor(() => expect(screen.queryByText('Bioko Centro')).not.toBeInTheDocument())
  expect(screen.getByText('Panadería López')).toBeInTheDocument()
})
