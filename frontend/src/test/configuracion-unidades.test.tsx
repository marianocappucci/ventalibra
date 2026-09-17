// Unidades de medida como sección de Configuración (2026-09-17, movida desde
// la pestaña "Unidades" de lo que era Catálogo -- hoy `Productos.tsx`, ver
// `productos.test.tsx`). Lo que fija este archivo es la sección DECLARADA
// por VentaLibra en `pages/Configuracion.tsx`; el armado de pestañas en sí
// tiene sus tests en `configuracion-forma.test.tsx`.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

// jsdom no implementa la API de pointer capture y Radix la toca al abrir un
// `Select` -- acá no hay ninguno, pero el resto de las secciones de
// Configuración que se montan igual (Integraciones) sí, y sin esto el
// `beforeEach` de la carga inicial puede fallar. Mismo shim que usa
// `productos.test.tsx`.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

const UNIDADES = [
  { code: 'kg', name: 'Kilogramo', allows_fraction: true, decimal_scale: 3 },
  { code: 'u', name: 'Unidad', allows_fraction: false, decimal_scale: 0 },
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
    if (metodo === 'POST' && u.startsWith('/catalog/units')) return Promise.resolve(json({}))
    if (u.startsWith('/catalog/units')) return Promise.resolve(json(UNIDADES))
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

const montar = (ruta = '/configuracion?seccion=unidades') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('La sección "Unidades de medida" de Configuración', () => {
  it('se llega desde su pestaña y muestra el listado', async () => {
    montar()

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Unidades de medida/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
    expect(await screen.findByText('Kilogramo')).toBeInTheDocument()
    expect(screen.getByText('Unidad')).toBeInTheDocument()
  })

  it('el alta de unidad sigue funcionando igual, ahora acá', async () => {
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Kilogramo')

    await usuario.click(screen.getByRole('button', { name: '+ Nueva unidad' }))
    await usuario.type(await screen.findByLabelText('Código'), 'lt')
    await usuario.type(screen.getByLabelText('Nombre'), 'Litro')
    await usuario.click(screen.getByRole('button', { name: 'Crear' }))

    await waitFor(() => {
      const post = llamadas.find((l) => l.metodo === 'POST' && l.url === '/catalog/units')
      expect(post).toBeTruthy()
      expect(post!.cuerpo).toEqual({ code: 'lt', name: 'Litro', allows_fraction: false, decimal_scale: 0 })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
