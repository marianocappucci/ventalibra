/** El aviso de los cobros que entraron y quedaron sin registrar.
 *
 * 🔴 **El agujero que este producto declara.** El orden acá es "primero la
 * plata, después la venta" —a propósito, así no hay ventas cobradas que nadie
 * pagó—. Pero si el navegador se muere entre el poll y la confirmación, la
 * plata entró y la venta no quedó registrada.
 *
 * La orden aprobada se guardaba desde siempre, pero sólo se la consultaba **por
 * venta**: sólo aparecía si alguien volvía a abrir ESE borrador. Sin este aviso
 * el endpoint no lo mira nadie.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Ventas } from '../pages/Ventas'

const COBRO = {
  sale_id: 42,
  numero: null,
  amount: 1500.5,
  payment_id: '112233',
  external_reference: 'vl-42-abc',
  acreditado_el: '2026-08-31 12:00:00',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function backend(cobros: unknown[], { falla = false } = {}) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    // 🔑 La rama del aviso va PRIMERO: `/sales` matchea también
    // `/sales/mp/cobros-sin-venta`, y al revés el aviso recibiría el listado de
    // ventas y el test mediría otra cosa.
    if (u.includes('/sales/mp/cobros-sin-venta')) {
      return Promise.resolve(falla ? json({ detail: 'boom' }, 500) : json(cobros))
    }
    if (u.includes('/sales')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('el aviso de cobros sin registrar', () => {
  it('🔴 avisa cuando hay plata que entró y no quedó registrada', async () => {
    backend([COBRO])
    render(<Ventas />)

    expect(await screen.findByText(/quedó sin registrar/)).toBeInTheDocument()
    expect(screen.getByText(/112233/)).toBeInTheDocument()
    expect(screen.getByText(/#42/)).toBeInTheDocument()
  })

  it('🔑 y NO avisa cuando no hay ninguno', async () => {
    // El negativo, y el que hace que el aviso signifique algo: uno que estuviera
    // siempre se vuelve parte del fondo y nadie lo lee.
    backend([])
    render(<Ventas />)

    await waitFor(() => expect(screen.getByText('Ventas')).toBeInTheDocument())
    expect(screen.queryByText(/sin registrar/)).toBeNull()
  })

  it('el plural cambia con la cantidad', async () => {
    backend([COBRO, { ...COBRO, sale_id: 43, external_reference: 'vl-43-x', payment_id: '9' }])
    render(<Ventas />)

    expect(await screen.findByText(/Hay 2 cobros que entraron/)).toBeInTheDocument()
  })

  it('🔴 si el chequeo falla, la pantalla de ventas sigue andando', async () => {
    // El historial de ventas es lo que se usa para anular la venta de ayer. Que
    // un chequeo secundario lo tumbe sería cambiar un problema por otro peor.
    backend([], { falla: true })
    render(<Ventas />)

    await waitFor(() => expect(screen.getByText('Ventas')).toBeInTheDocument())
    expect(screen.queryByText(/sin registrar/)).toBeNull()
  })
})
