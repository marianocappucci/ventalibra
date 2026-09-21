// Proveedores: el alta pasó de un formulario suelto arriba de la lista a un
// botón arriba a la derecha que abre un modal (2026-09-21, pedido del humano).
// Mismo patrón que Sucursales (#295).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

import { Proveedores } from '../pages/Proveedores'

const SUPPLIERS = [
  {
    id: 1, display_name: 'Trapani', party_type: 'organization',
    tax_id: '30-11111111-1', email: null, phone: '11-4455-6677', active: true,
  },
  {
    id: 2, display_name: 'Fredo', party_type: 'organization',
    tax_id: '30-22222222-2', email: null, phone: '2255-4040', active: true,
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
    if (metodo === 'POST' && u === '/suppliers') {
      const status = opciones.postStatus ?? 200
      if (status >= 400) return Promise.resolve(json({ detail: opciones.postDetail ?? 'error' }, status))
      return Promise.resolve(json({ ...SUPPLIERS[0], id: 2, display_name: 'Fredo' }))
    }
    if (u === '/suppliers') return Promise.resolve(json(SUPPLIERS))
    return Promise.resolve(json({}))
  }))
}

beforeEach(() => { montarRed() })

it('🔴 el formulario ya NO está suelto en la página: sólo se ve la lista', async () => {
  // El control de que el cambio pasó: si el alta siguiera arriba, estos campos
  // estarían en pantalla sin tocar nada.
  render(<Proveedores />)
  await screen.findByText('Trapani')

  expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('CUIT')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Nuevo proveedor/ })).toBeInTheDocument()
})

it('el botón abre el modal con los campos del proveedor', async () => {
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))

  const modal = await screen.findByRole('dialog')
  expect(modal).toBeInTheDocument()
  expect(screen.getByLabelText('Nombre')).toBeInTheDocument()
  expect(screen.getByLabelText('CUIT')).toBeInTheDocument()
  expect(screen.getByLabelText('Email')).toBeInTheDocument()
  expect(screen.getByLabelText('Teléfono')).toBeInTheDocument()
})

it('el alta manda lo escrito, cierra el modal y recarga la lista', async () => {
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Fredo')
  await user.type(screen.getByLabelText('CUIT'), '30-22222222-2')
  await user.click(screen.getByRole('button', { name: 'Crear' }))

  await waitFor(() => {
    const envio = llamadas.find((l) => l.metodo === 'POST')
    expect(envio?.cuerpo).toEqual({
      display_name: 'Fredo', party_type: 'organization',
      tax_id: '30-22222222-2', email: null, phone: null,
    })
  })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  // Se releyó la lista: dos GET a /suppliers, el de la carga y el de después.
  expect(llamadas.filter((l) => l.url === '/suppliers' && l.metodo === 'GET')).toHaveLength(2)
})

it('🔴 sin nombre no se manda nada y el modal queda abierto', async () => {
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
  await user.click(await screen.findByRole('button', { name: 'Crear' }))

  expect(await screen.findByText('El nombre es obligatorio.')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(llamadas.some((l) => l.metodo === 'POST')).toBe(false)
})

it('🔴 un error del backend se ve DENTRO del modal, que no se cierra', async () => {
  // Si se cerrara, lo escrito se pierde y el mensaje queda detrás, sobre una
  // lista que no cambió.
  montarRed({ postStatus: 409, postDetail: 'Ya existe un proveedor con ese CUIT.' })
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Fredo')
  await user.click(screen.getByRole('button', { name: 'Crear' }))

  expect(await screen.findByText('Ya existe un proveedor con ese CUIT.')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByLabelText('Nombre')).toHaveValue('Fredo')
})

it('cancelar cierra el modal y descarta lo escrito', async () => {
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
  await user.type(await screen.findByLabelText('Nombre'), 'Descartar')
  await user.click(screen.getByRole('button', { name: 'Cancelar' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

  await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
  expect(await screen.findByLabelText('Nombre')).toHaveValue('')
})

it('el buscador de la tabla filtra, y busca tambien por un campo que NO es columna', async () => {
  // Mismo buscador y mismos campos que Clientes (2026-09-21): las dos
  // pantallas son la misma cosa con otro nombre. El telefono se busca aunque
  // aca tambien sea columna; el CUIT es lo que se tiene del papel.
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.type(screen.getByLabelText('Buscar proveedor'), '2255-4040')

  await waitFor(() => expect(screen.queryByText('Trapani')).not.toBeInTheDocument())
  expect(screen.getByText('Fredo')).toBeInTheDocument()
})

it('el buscador encuentra por CUIT', async () => {
  const user = userEvent.setup()
  render(<Proveedores />)
  await screen.findByText('Trapani')

  await user.type(screen.getByLabelText('Buscar proveedor'), '30-22222222-2')

  await waitFor(() => expect(screen.queryByText('Trapani')).not.toBeInTheDocument())
  expect(screen.getByText('Fredo')).toBeInTheDocument()
})
