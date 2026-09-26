// Las rutas del kit para la cuenta corriente.
//
// Desde P9-M4 la pantalla es la del kit (`libra-ui/comercio/CuentaCorriente*`,
// la misma que montan Contalibra y Restolibra) y el cableado de ESTE producto
// son tres cosas: la lista montada en `/cuentas-corrientes`, el detalle en
// `/cuenta-corriente/:id`, la redirección de "Volver" (`/cuenta-corriente`)
// y la ficha propia a la que apunta el kit (`/clientes/:id`). Si falta, el link manda al POS por el
// catch-all y parece que se rompió el sistema.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

const RUTA_SESION = '/auth/me'

const SESION = {
  id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true,
  nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
}

const LISTA_VACIA = { clientes: [], total_deuda: 0 }

const DETALLE = {
  cliente: { id: 7, name: 'Vecina del 12', cuit_dni: '' },
  movimientos: [],
  saldo: 0,
}

// La ficha del kit sobre el router del motor (`/api/clientes/:id`, ADR-029): el cliente más lo que
// la ficha espera aunque VentaLibra no muestre esos módulos.
const CLIENTE = {
  id: 7, name: 'Vecina del 12', address: '', cuit_dni: '', email: 'vecina@ejemplo.com', phone: '',
  iva_condition: 'Consumidor Final', auto_facturar: 0, activo: 1,
  alias_facturacion: [], facturas: [], presupuestos: [], remitos: [],
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Sesion valida; las rutas del kit responden su forma, el resto, vacio. */
function conSesion(clienteStatus = 200) {
  fetchMock.mockImplementation((url: string) => {
    const u = String(url)
    // 🔴 `/cajas` antes que `/7`: ambos contienen `/api/cuenta-corriente`.
    if (u.includes(RUTA_SESION)) return Promise.resolve(json(SESION))
    if (u.includes('/api/cuenta-corriente/cajas')) return Promise.resolve(json([]))
    if (u.includes('/api/cuenta-corriente/7')) return Promise.resolve(json(DETALLE))
    if (u.includes('/api/cuenta-corriente')) return Promise.resolve(json(LISTA_VACIA))
    if (u.includes('/api/clientes/7')) return Promise.resolve(json(
      clienteStatus === 200 ? CLIENTE : { detail: 'Cliente no encontrado' }, clienteStatus,
    ))
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  })
}

function montar(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('rutas del kit de cuenta corriente', () => {
  it('el "Volver" del kit (/cuenta-corriente) aterriza en la lista', async () => {
    const errores = vi.spyOn(console, 'error').mockImplementation(() => {})
    conSesion()
    montar('/cuenta-corriente')
    // La lista del kit montó (la redirección pasó por /cuentas-corrientes).
    await screen.findByText('Cuenta Corriente')
    expect(errores).not.toHaveBeenCalled()
  })

  it('el detalle del kit vive en /cuenta-corriente/:id y pega al contrato', async () => {
    const errores = vi.spyOn(console, 'error').mockImplementation(() => {})
    conSesion()
    montar('/cuenta-corriente/7')
    await waitFor(() => {
      const pedidas = fetchMock.mock.calls.map(([u]) => String(u))
      expect(pedidas.some((u) => u.includes('/api/cuenta-corriente/7'))).toBe(true)
      expect(pedidas.some((u) => u.includes('/api/cuenta-corriente/cajas'))).toBe(true)
    })
    expect(errores).not.toHaveBeenCalled()
  })

  it('el "Ficha cliente" del kit (/clientes/:id) muestra los datos del cliente', async () => {
    const errores = vi.spyOn(console, 'error').mockImplementation(() => {})
    conSesion()
    montar('/clientes/7')
    expect((await screen.findAllByText('Vecina del 12')).length).toBeGreaterThan(0)
    expect(screen.getByText('vecina@ejemplo.com')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clientes/7'))).toBe(true)
    expect(errores).not.toHaveBeenCalled()
  })

  it('si el cliente no existe muestra el 404, no redirige al POS ni inventa datos', async () => {
    conSesion(404)
    montar('/clientes/7')
    expect((await screen.findAllByText(/Cliente no encontrado/)).length).toBeGreaterThan(0)
    expect(screen.queryByText('Vecina del 12')).not.toBeInTheDocument()
  })
})
