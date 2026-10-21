// La bandeja de comprobantes pendientes del nodo offline (libra-ui ADR-087, ADR-091 de este producto): la pantalla del kit
// montada en `/comprobantes-pendientes`, sin `alFacturar`. Lo que se prueba es el cableado de VentaLibra: la ruta existe para
// quien ve las ventas de todos, trae la venta cobrada sin conexión rotulada como tal, sin casillas ni «Descartar», y con
// «Facturar ahora» (`POST /api/nodo/facturar-pendientes`, que ya estaba montado). La tabla, las pestañas y el descarte tienen
// sus tests en el kit.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ETIQUETA_VENTA_SIN_CONEXION, _reiniciarConexionDelNodo } from 'libra-ui/nodo-offline'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const VENTA_SIN_CONEXION = {
  id: 1, origen_producto: 'ventalibra', origen_instancia: '', origen_tipo: 'venta', origen_id: '7',
  cliente_id: null, cliente_cuit: '', cliente_razon: 'Cliente ficticio', cliente_domicilio: '',
  periodo_desde: '2026-10-21', periodo_hasta: '2026-10-21', concepto: 'Venta S02-POS-000007', condicion_venta: 'contado',
  observaciones: '', items: [{ description: 'Yerba 1kg', qty: 1, unit_price: 3000, iva_rate: 0.21 }], total: 3000,
  estado: 'pendiente', factura_id: null, motivo_descarte: '', resuelto_at: '', resuelto_por: '', created_at: '2026-10-21T10:00:00',
}

type Rol = keyof typeof CAPACIDADES_POR_ROL

function usuarioDe(rol: Rol) {
  return {
    id: '7', username: `u-${rol}`, name: `Persona ${rol}`, role: rol, active: true, empresa_nombre: 'Prueba',
    capacidades: CAPACIDADES_POR_ROL[rol], modulos: ['facturacion', 'multisucursal'],
  }
}

function entrar(rol: Rol, opciones: { enLinea?: boolean } = {}) {
  const llamadas: { metodo: string; url: string }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    llamadas.push({ metodo: init?.method ?? 'GET', url: u })
    if (u.includes('/auth/me')) return Promise.resolve(json(usuarioDe(rol)))
    if (u.includes('/api/nodo/conexion')) {
      return Promise.resolve(json({ es_nodo: true, en_linea: opciones.enLinea ?? true, node_id: 'nodo-1', a_facturar: 1 }))
    }
    if (u.includes('/api/nodo/facturar-pendientes')) return Promise.resolve(json({ facturadas: [], fallidas: [], omitidas: [] }))
    if (u.includes('/api/comprobantes-pendientes')) {
      return Promise.resolve(json({ pendientes: [VENTA_SIN_CONEXION], facturados: [], descartados: [], total_pendientes: 1 }))
    }
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={['/comprobantes-pendientes']}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
  return llamadas
}

beforeEach(() => {
  vi.unstubAllGlobals()
  _reiniciarConexionDelNodo()
})
afterEach(() => { _reiniciarConexionDelNodo() })

describe('La bandeja de comprobantes del nodo', () => {
  it.each(['admin', 'encargado'] as Rol[])('%s ve la venta cobrada sin conexión, sin casillas ni descarte', async (rol) => {
    const llamadas = entrar(rol)

    expect(await screen.findByRole('heading', { name: /Comprobantes a facturar/ })).toBeInTheDocument()
    expect(await screen.findByText(ETIQUETA_VENTA_SIN_CONEXION)).toBeInTheDocument()
    // Sin `alFacturar` no hay formulario: ni casillas ni «Facturar»; y una venta del nodo no se descarta.
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByTitle('Descartar')).toBeNull()
    expect(screen.getByRole('button', { name: /Facturar ahora/ })).toBeEnabled()
    expect(llamadas.some((l) => l.metodo === 'GET' && l.url.endsWith('/api/comprobantes-pendientes'))).toBe(true)
  })

  it('«Facturar ahora» llama a la tanda del nodo, que ya estaba montada', async () => {
    const llamadas = entrar('admin')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Facturar ahora/ }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'POST' && l.url.endsWith('/api/nodo/facturar-pendientes'))).toBe(true)
    })
  })

  it('sin conexión «Facturar ahora» está apagado', async () => {
    entrar('admin', { enLinea: false })

    await screen.findByText(ETIQUETA_VENTA_SIN_CONEXION)
    await waitFor(() => expect(screen.getByRole('button', { name: /Facturar ahora/ })).toBeDisabled())
  })

  it.each(['cajero', 'vendedor'] as Rol[])('%s no la ve: lo mandan a su pantalla de inicio', async (rol) => {
    const llamadas = entrar(rol)

    await waitFor(() => expect(llamadas.some((l) => l.url.includes('/auth/me'))).toBe(true))
    // La bandeja nunca se pide (sería un 403 del backend) y no aparece en el menú.
    await screen.findAllByRole('link')
    expect(screen.queryByText(ETIQUETA_VENTA_SIN_CONEXION)).toBeNull()
    expect(llamadas.some((l) => l.url.endsWith('/api/comprobantes-pendientes'))).toBe(false)
    expect(screen.queryByRole('link', { name: 'Comprobantes a facturar' })).toBeNull()
  })
})
