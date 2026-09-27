// Reportes y Caja por medio son las pantallas del kit (`libra-ui/comercio/Reportes`, `CajaMedios`) sobre el router del motor
// (`/api/reportes`, ADR-035). Las variantes de VentaLibra (la venta anulada no cuenta, fiar no es cobrar) viven en el backend; acá,
// que las pantallas se montan y hablan con la API que el kit espera.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import { CajaPorMedio } from '../pages/CajaPorMedio'
import { Reportes } from '../pages/Reportes'

let llamadas: string[]

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    llamadas.push(u)
    const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } }))
    if (u.startsWith('/api/reportes/caja-medios')) {
      return json({
        desde: '2026-09-01', hasta: '2026-09-27', cajas_config: [{ id: 1, nombre: 'Caja 1', activo: 1 }],
        cajas: [{
          id: 1, nombre: 'Caja 1', medios: { efectivo: { ingresos: 500, ingresos_ops: 1, egresos: 0, egresos_ops: 0 } },
          total_ingresos: 500, total_egresos: 0, saldo: 500,
        }],
        totales: { efectivo: { ingresos: 500, ingresos_ops: 1, egresos: 0, egresos_ops: 0 } }, medio_label: { efectivo: 'Efectivo' },
      })
    }
    if (u.startsWith('/api/reportes')) {
      return json({
        desde: '2026-09-01', hasta: '2026-09-27', agrupacion: 'dia',
        resumen: { ventas_cantidad: 3, ventas_total: 4500, facturas_cantidad: 0, caja_saldo: 1500 },
        ventas_ts: [{ periodo: '2026-09-27', cantidad: 3, total: 4500 }], medios: [{ medio: 'efectivo', operaciones: 3, total: 4500 }],
        productos: [{ nombre: 'Yerba 1kg', cantidad: 3, total: 4500 }], caja: [{ tipo: 'ingreso', cantidad: 3, total: 1500 }],
        stock_bajo: [{ id: 1, nombre: 'Arroz', codigo: null, stock_actual: 2, stock_minimo: 5 }], medio_label: { efectivo: 'Efectivo' },
      })
    }
    return json([])
  }))
})

it('Reportes trae ventas, medios, productos y stock bajo del motor, con los exports', async () => {
  render(<MemoryRouter><Reportes /></MemoryRouter>)
  expect(await screen.findByText('Yerba 1kg')).toBeInTheDocument()
  expect(screen.getByText('Arroz')).toBeInTheDocument()
  expect(llamadas.some((u) => u.startsWith('/api/reportes?'))).toBe(true)
  expect(document.querySelector('a[href^="/reportes/export/ventas"]')).toBeTruthy()
})

it('la Caja por medio pide el pivot de caja-medios', async () => {
  render(<MemoryRouter><CajaPorMedio /></MemoryRouter>)
  expect((await screen.findAllByText('Caja 1')).length).toBeGreaterThan(0)
  expect(llamadas.some((u) => u.startsWith('/api/reportes/caja-medios'))).toBe(true)
})
