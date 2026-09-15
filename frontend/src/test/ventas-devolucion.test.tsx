// La devolución parcial de VentaLibra, montada como `accionesExtra` de
// `VentaDetalle` (libra-ui) desde F4 (2026-09-15, DECISIONS.md ADR-025).
//
// Se prueba el componente solo (`DevolucionDeVenta`), no la pantalla entera:
// lo que hace falta cubrir es que manda `sale_item_id` -- no el índice de la
// línea, que era como indexaba el modelo viejo (`POST /sales/{id}/returns`,
// retirado) -- junto con `cantidad`, `deposito_id` y `medio_pago`, y que
// recarga el detalle al terminar.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DevolucionDeVenta } from '../pages/Ventas'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import type { Venta } from '../api'

const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'tarjeta_debito', label: 'Tarjeta de débito' },
]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const DETALLE: Venta = {
  id: 42, numero: 'POS-000042', fecha: '2026-09-15', estado: 'cobrada',
  items: [
    { id: 501, nombre: 'Yerba 1kg', qty: 5, precio: 1500, subtotal: 7500, producto_id: 3 },
  ],
  subtotal: 7500, descuento: 0, total: 7500,
  cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 7500, referencia: '' }],
  factura_id: null, factura_display: null, remito_id: null,
  mp_order_id: '', mp_payment_id: '',
}

type Llamada = { metodo: string; url: string; body: unknown }

function montarRed(opciones: { yaDevuelto?: number; depositoId?: number | null } = {}) {
  const llamadas: Llamada[] = []
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/ventas/42/devuelto')) {
      return Promise.resolve(json({
        por_clave: opciones.yaDevuelto
          ? [{ producto_id: 3, variante_id: null, cantidad: opciones.yaDevuelto }]
          : [],
        deposito_id: opciones.depositoId ?? 1,
      }))
    }
    if (u.includes('/locations')) {
      return Promise.resolve(json([
        { id: 1, name: 'Depósito principal', branch_id: null, location_type: 'warehouse', active: true },
        { id: 2, name: 'Sucursal Once', branch_id: null, location_type: 'warehouse', active: true },
      ]))
    }
    if (u.includes('/api/ventas/42/devolver')) return Promise.resolve(json({ importe: 1500, venta: DETALLE }))
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return { llamadas }
}

beforeEach(() => {
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('La devolución de una venta', () => {
  it('manda sale_item_id, cantidad, deposito_id y medio_pago, y recarga', async () => {
    const { llamadas } = montarRed()
    const recargar = vi.fn()
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={recargar} />)

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    const cantidad = await screen.findByPlaceholderText(/máx\. 5/)
    await user.type(cantidad, '2')

    await user.click(await screen.findByRole('button', { name: /Confirmar devolución/ }))

    const devolucion = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.url.includes('/api/ventas/42/devolver'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(devolucion.body).toMatchObject({
      lineas: [{ sale_item_id: 501, cantidad: 2 }],
      deposito_id: 1,
      medio_pago: 'efectivo',
    })
    // Nada de `index`: la forma vieja del payload (`POST /sales/{id}/returns`,
    // retirado) indexaba por posición de línea.
    expect(devolucion.body).not.toHaveProperty('lineas.0.index')
    await waitFor(() => expect(recargar).toHaveBeenCalled())
  })

  it('propone el depósito de la venta original', async () => {
    montarRed({ depositoId: 2 })
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))

    // El combobox de depósito (no el de "Devolver por") tiene que mostrar
    // "Sucursal Once" como valor ya elegido -- no hace falta abrirlo.
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Depósito' })).toHaveTextContent('Sucursal Once')
    })
  })

  it('topea la cantidad a lo que todavía no se devolvió', async () => {
    montarRed({ yaDevuelto: 4 })
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))

    // Vendido 5, ya devuelto 4: queda 1 disponible.
    await screen.findByPlaceholderText(/máx\. 1/)
  })
})
