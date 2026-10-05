// La maqueta del ticket conserva el ancho real del papel (302 px en 80 mm): a 320 px de pantalla ensanchaba la página 23 px
// (medido en Chromium contra dev, 2026-10-05). Ahora scrollea dentro de su tarjeta. jsdom no mide el layout: se fijan las clases.
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConfigTicket } from '../pages/ConfigTicket'

afterEach(() => { vi.unstubAllGlobals() })

describe('Configuración del ticket a 320 px', () => {
  it('la maqueta scrollea dentro de su tarjeta y la columna puede achicarse', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      ancho_mm: '80', fuente_size: 12, mostrar_logo: false, pie: '', linea_corte: false,
    }), { status: 200, headers: { 'content-type': 'application/json' } }))))
    const { container } = render(<ConfigTicket />)
    const vista = await screen.findByTestId('vista-ticket')
    expect(vista.className).toContain('overflow-x-auto')
    expect(vista.className).toContain('max-w-full')
    // El ancho real del papel no se toca: la maqueta sigue en 302 px.
    expect((vista.firstElementChild as HTMLElement).style.width).toBe('302px')
    expect((container.firstElementChild as HTMLElement).className).toContain('grid-cols-[minmax(0,1fr)]')
  })
})
