// Categorías de producto como sección de Configuración (2026-09-17, nueva --
// ver `ConfigCategorias.tsx`). Mismo criterio que
// `configuracion-unidades.test.tsx`: lo que fija este archivo es la sección
// DECLARADA por VentaLibra en `pages/Configuracion.tsx`; el armado de
// pestañas en sí tiene sus tests en `configuracion-forma.test.tsx`.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

// jsdom no implementa la API de pointer capture y Radix la toca al montar el
// resto de las secciones de Configuración (Integraciones) -- mismo shim que
// `configuracion-unidades.test.tsx` y `productos.test.tsx`.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

const CATEGORIAS = [
  { id: 1, name: 'Bebidas', parent_id: null, active: true },
  { id: 2, name: 'Descontinuadas', parent_id: null, active: false },
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
    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (metodo === 'POST' && u.startsWith('/catalog/categories')) return Promise.resolve(json({}))
    if (metodo === 'PUT' && u.startsWith('/catalog/categories')) return Promise.resolve(json({}))
    if (u.startsWith('/catalog/categories')) return Promise.resolve(json(CATEGORIAS))
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '', empresa_telefono: '',
        empresa_email: '', empresa_iibb: '', empresa_iva_condition: 'Monotributista',
        empresa_inicio_actividades: '',
      }))
    }
    if (u.includes('/api/config/backups')) return Promise.resolve(json([]))
    return Promise.resolve(json(null))
  }))
})

const montar = (ruta = '/configuracion?seccion=categorias') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('La sección "Categorías" de Configuración', () => {
  it('se llega desde su pestaña y muestra el listado, activas e inactivas', async () => {
    montar()

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Categorías/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
    expect(await screen.findByText('Bebidas')).toBeInTheDocument()
    expect(screen.getByText('Descontinuadas')).toBeInTheDocument()
    expect(screen.getByText('Activa')).toBeInTheDocument()
    expect(screen.getByText('Inactiva')).toBeInTheDocument()
  })

  it('el alta de categoría manda el nombre y refresca el listado', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Bebidas')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva categoría' }))
    await usuario.type(await screen.findByLabelText('Nombre'), 'Limpieza')
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url === '/catalog/categories')
      expect(post).toBeTruthy()
      expect(post!.cuerpo).toEqual({ name: 'Limpieza' })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un alta sin nombre avisa adentro del modal, sin postear', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Bebidas')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva categoría' }))
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    expect(await screen.findByText(/El nombre es obligatorio/)).toBeInTheDocument()
    expect(llamadas.some((l) => l.metodo === 'POST' && l.url === '/catalog/categories')).toBe(false)
  })

  it('el lápiz abre la edición precargada y guarda nombre + estado', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Bebidas')

    await usuario.click(screen.getAllByRole('button', { name: 'Editar categoría' })[0])
    const modal = await screen.findByRole('dialog')
    expect(modal).toHaveTextContent('Editar categoría')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Bebidas')
    expect(screen.getByRole('switch', { name: 'Activa' })).toBeChecked()

    const nombre = screen.getByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Bebidas frías')
    await usuario.click(screen.getByRole('switch', { name: 'Activa' }))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      const put = llamadas.find((l) => l.metodo === 'PUT' && l.url === '/catalog/categories/1')
      expect(put).toBeTruthy()
      expect(put!.cuerpo).toEqual({ name: 'Bebidas frías', active: false })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un 422 por nombre repetido se muestra en el modal de edición', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const u = String(url)
      const metodo = init?.method ?? 'GET'
      llamadas.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (metodo === 'PUT' && u.startsWith('/catalog/categories')) {
        return Promise.resolve(new Response(
          JSON.stringify({ detail: "ya existe una categoria activa llamada 'Descontinuadas'" }),
          { status: 422, headers: { 'content-type': 'application/json' } },
        ))
      }
      if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
      if (u.startsWith('/catalog/categories')) return Promise.resolve(json(CATEGORIAS))
      return Promise.resolve(json(null))
    }))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Bebidas')

    await usuario.click(screen.getAllByRole('button', { name: 'Editar categoría' })[0])
    const nombre = await screen.findByLabelText('Nombre')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Descontinuadas')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText(/ya existe una categoria activa/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
