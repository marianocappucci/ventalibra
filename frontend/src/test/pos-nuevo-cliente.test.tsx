// «Nuevo cliente» dentro del diálogo «Cliente de la venta» del POS (ADR-071 del kit, libra-ui v0.158.0; ADR-087 de este repo).
//
// Si el cliente no está cargado, el cajero lo da de alta ahí mismo (el panel `AltaDeCliente` del kit, contra el `POST /api/clientes` del motor) y la
// venta queda con él, sin salir del POS. El guard `campos-de-cliente.test.ts` NO ve este diálogo (no es un desplegable): lo cubre este test.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const ITEM = { id: 3, nombre: 'Yerba 1kg', sku: 'YER1', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const LOCATIONS = [
  { id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true, deposito_predeterminado_id: 11, depositos: 1 },
]
const CLIENTES = [
  { id: 1, name: 'Ana Gomez', address: '', cuit_dni: '27-12345678-9', email: '', phone: '', iva_condition: '', auto_facturar: 0, activo: 1 },
]
const CREADO = { id: 7, name: 'Carla Nueva', address: '', cuit_dni: '', email: '', phone: '', iva_condition: '', auto_facturar: 0, activo: 1 }
const VENTA = {
  id: 9, numero: 'POS-000009', fecha: '2026-08-23', estado: 'cobrada', status: 'confirmed',
  items: [{ id: 1, nombre: 'Yerba 1kg', qty: 1, precio: 3000, subtotal: 3000, producto_id: 3, variante_id: null }],
  subtotal: 3000, descuento: 0, total: 3000, cliente_id: 7, cliente_nombre: 'Carla Nueva', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 3000, referencia: '', recibido: 3000 }],
  factura_id: null, factura_display: null, remito_id: null, mp_order_id: '', mp_payment_id: '', created_at: '2026-08-23T10:05:00',
}

type Llamada = { metodo: string; url: string; body: Record<string, unknown> | undefined }
let llamadas: Llamada[]

function montarRed(altaRespuesta: () => Response = () => json(CREADO, 201), capacidades: string[] = []) {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({ id: '1', username: 'cami', name: 'Cami', role: 'cajero', active: true, empresa_nombre: 'Prueba', capacidades }))
    }
    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json([{ id: 'efectivo', label: 'Efectivo' }, { id: 'cuenta_corriente', label: 'Cuenta corriente' }]))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/api/turnos/actual')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/api/sucursales')) return Promise.resolve(json(LOCATIONS))
    if (u === '/api/clientes' && metodo === 'POST') return Promise.resolve(altaRespuesta())
    if (u === '/api/clientes') return Promise.resolve(json(CLIENTES))
    if (u.endsWith('/api/ventas') && metodo === 'POST') return Promise.resolve(json(VENTA))
    if (u.includes('/api/productos/escanear')) {
      return Promise.resolve(json({ producto: ITEM, cantidad: 1, precio_unitario: null, de_balanza: false }))
    }
    return Promise.resolve(json([]))
  }))
}

const altas = () => llamadas.filter((l) => l.metodo === 'POST' && l.url === '/api/clientes')

async function abrirElClienteYEscribir(user: ReturnType<typeof userEvent.setup>, texto: string) {
  fireEvent.keyDown(window, { key: 'F7' })
  const dialogo = await screen.findByRole('dialog')
  await within(dialogo).findByText('Ana Gomez')
  if (texto) await user.type(within(dialogo).getByPlaceholderText('Buscar por nombre'), texto)
  return dialogo
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Nuevo cliente desde el diálogo del cliente de la venta', () => {
  it('trae lo escrito en el buscador, da el alta en el motor y el cliente queda elegido', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
    const dialogo = await abrirElClienteYEscribir(user, 'Carla Nueva')

    await user.click(within(dialogo).getByRole('button', { name: /Nuevo cliente/ }))
    // El panel reemplaza a la lista y el nombre ya viene escrito.
    const panel = within(dialogo).getByRole('group', { name: 'Nuevo cliente' })
    expect(within(panel).getByLabelText(/Nombre/)).toHaveValue('Carla Nueva')
    expect(within(dialogo).queryByText('Ana Gomez')).not.toBeInTheDocument()
    // Es el alta del cliente del motor, con lo fiscal: documento y condición frente al IVA.
    expect(within(panel).getByLabelText('CUIT/DNI')).toBeInTheDocument()
    expect(within(panel).getByLabelText('Condición frente al IVA')).toBeInTheDocument()

    await user.type(within(panel).getByLabelText('CUIT/DNI'), '20111111112')
    await user.click(within(panel).getByRole('button', { name: /Crear cliente/ }))

    await waitFor(() => expect(altas()).toHaveLength(1))
    expect(altas()[0].body).toEqual({
      name: 'Carla Nueva', cuit_dni: '20111111112', iva_condition: '', email: '', phone: '',
    })
    // Igual que al elegir uno de la lista: el diálogo se cierra y el cliente figura en el botón F7.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Carla Nueva/ })).toBeInTheDocument()
  })

  it('la venta se registra con el cliente recién creado', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
    await user.type(await screen.findByPlaceholderText(/scane|Escane/i), '779000001{Enter}')
    await screen.findByText('Yerba 1kg')

    const dialogo = await abrirElClienteYEscribir(user, 'Carla Nueva')
    await user.click(within(dialogo).getByRole('button', { name: /Nuevo cliente/ }))
    await user.click(within(dialogo).getByRole('button', { name: /Crear cliente/ }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /Cobrar/ }))
    await user.click(await screen.findByRole('button', { name: /^Cobrar/ }))
    const registro = await waitFor(() => {
      const r = llamadas.find((l) => l.metodo === 'POST' && l.url.endsWith('/api/ventas'))
      expect(r).toBeDefined()
      return r!
    })
    expect(registro.body).toMatchObject({ cliente_id: 7 })
  })

  it('al fiar, «Elegir cliente (F7)» del cobro ofrece el alta y la deuda queda a nombre del cliente creado', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
    await user.type(await screen.findByPlaceholderText(/scane|Escane/i), '779000001{Enter}')
    await screen.findByText('Yerba 1kg')
    await user.click(screen.getByRole('button', { name: /Cobrar/ }))

    const medio = await screen.findByRole('combobox', { name: 'Medio de pago' })
    await user.click(medio)
    await user.keyboard('{Control>}a{/Control}cuenta{Enter}')
    expect(await screen.findByText(/Para fiar hace falta saber a quién/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Elegir cliente \(F7\)/ }))

    const elegir = (await screen.findAllByRole('dialog')).find((d) => within(d).queryByText('Cliente de la venta'))!
    await user.click(within(elegir).getByRole('button', { name: /Nuevo cliente/ }))
    await user.type(within(elegir).getByLabelText(/Nombre/), 'Carla Nueva')
    await user.click(within(elegir).getByRole('button', { name: /Crear cliente/ }))

    await waitFor(() => expect(screen.queryByText('Cliente de la venta')).not.toBeInTheDocument())
    expect(altas()).toHaveLength(1)
    expect(await screen.findByText('Carla Nueva', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.queryByText(/Para fiar hace falta saber a quién/)).not.toBeInTheDocument()
  })

  describe('teclado', () => {
    it('F10 abre el alta; Enter en el nombre crea el cliente y no hace nada más', async () => {
      montarRed()
      const user = userEvent.setup()
      render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
      const dialogo = await abrirElClienteYEscribir(user, '')

      await user.keyboard('{F10}')
      const panel = within(dialogo).getByRole('group', { name: 'Nuevo cliente' })
      expect(within(panel).getByLabelText(/Nombre/)).toHaveFocus()
      // Sin nombre, Enter no crea.
      await user.keyboard('{Enter}')
      expect(altas()).toHaveLength(0)

      await user.keyboard('Carla Nueva{Enter}')
      await waitFor(() => expect(altas()).toHaveLength(1))
      expect(altas()[0].body).toMatchObject({ name: 'Carla Nueva' })
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })

    it('Escape con el panel abierto cierra sólo el panel; el siguiente cierra el diálogo', async () => {
      montarRed()
      const user = userEvent.setup()
      render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
      const dialogo = await abrirElClienteYEscribir(user, 'Carla')
      await user.click(within(dialogo).getByRole('button', { name: /Nuevo cliente/ }))
      expect(within(dialogo).getByRole('group', { name: 'Nuevo cliente' })).toBeInTheDocument()

      await user.keyboard('{Escape}')
      // El diálogo sigue, con el buscador y lo que se había escrito, y el foco vuelve ahí.
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(within(dialogo).queryByRole('group', { name: 'Nuevo cliente' })).not.toBeInTheDocument()
      const filtro = within(dialogo).getByPlaceholderText('Buscar por nombre')
      expect(filtro).toHaveValue('Carla')
      expect(filtro).toHaveFocus()
      expect(altas()).toHaveLength(0)

      await user.keyboard('{Escape}')
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })
  })

  it('si el alta falla, lo dice dentro del panel y no se pierde lo cargado ni se elige a nadie', async () => {
    montarRed(() => json({ detail: 'Ya existe un cliente con ese CUIT.' }, 409))
    const user = userEvent.setup()
    render(<MemoryRouter><Pos puedeCrearCliente /></MemoryRouter>)
    const dialogo = await abrirElClienteYEscribir(user, 'Carla Nueva')
    await user.click(within(dialogo).getByRole('button', { name: /Nuevo cliente/ }))
    await user.click(within(dialogo).getByRole('button', { name: /Crear cliente/ }))

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Ya existe un cliente con ese CUIT.')
    expect(within(dialogo).getByLabelText(/Nombre/)).toHaveValue('Carla Nueva')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('sin el permiso clientes.alta no se ofrece «Nuevo cliente» ni F10 lo abre', async () => {
    montarRed()
    const user = userEvent.setup()
    render(<MemoryRouter><Pos /></MemoryRouter>)
    const dialogo = await abrirElClienteYEscribir(user, '')
    expect(within(dialogo).queryByRole('button', { name: /Nuevo cliente/ })).not.toBeInTheDocument()
    await user.keyboard('{F10}')
    expect(within(dialogo).queryByRole('group', { name: 'Nuevo cliente' })).not.toBeInTheDocument()
    expect(within(dialogo).getByText('Ana Gomez')).toBeInTheDocument()
  })
})

// El permiso llega por la sesión: `App.tsx` lo lee de `/auth/me` (`capacidades`) y se lo pasa al POS.
describe('Nuevo cliente: el permiso sale del usuario en sesión', () => {
  async function pos(capacidades: string[]) {
    montarRed(() => json(CREADO, 201), capacidades)
    render(
      <MemoryRouter initialEntries={['/pos']}>
        <AuthProvider><App /></AuthProvider>
      </MemoryRouter>,
    )
    await screen.findByPlaceholderText(/scane|Escane/i)
    fireEvent.keyDown(window, { key: 'F7' })
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByText('Ana Gomez')
    return dialogo
  }

  it('el cajero (tiene clientes.alta) lo ofrece', async () => {
    const dialogo = await pos(['ventas.pos', 'clientes.ver', 'clientes.alta'])
    expect(within(dialogo).getByRole('button', { name: /Nuevo cliente/ })).toBeInTheDocument()
  })

  it('quien no tiene clientes.alta no lo ve', async () => {
    const dialogo = await pos(['ventas.pos', 'clientes.ver'])
    expect(within(dialogo).queryByRole('button', { name: /Nuevo cliente/ })).not.toBeInTheDocument()
  })
})
