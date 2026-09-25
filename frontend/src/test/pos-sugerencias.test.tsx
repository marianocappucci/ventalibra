// Búsqueda en vivo en el campo de escaneo (2026-09-17): al tipear un nombre
// se muestran coincidencias sin apretar Enter, sin romper el flujo del
// lector de código de barras (que tipea rápido y termina con Enter). Ver
// `Pos.tsx`, el useEffect de sugerencias y `elegirSugerencia`.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const MEDIOS = [{ id: 'efectivo', label: 'Efectivo' }]

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana',
  apertura: '2026-09-17T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null,
  estado: 'abierto', notas: '',
}

const LOCATIONS = [
  { id: 1, name: 'Salón', branch_id: null, location_type: 'store', active: true, is_default: true },
]

const CONO_SIMPLE = {
  id: 3, name: 'Cono Simple', unit_code: 'u', default_sale_price: '500.00', active: true,
}
const CONO_DOBLE = {
  id: 4, name: 'Cono Doble', unit_code: 'u', default_sale_price: '800.00', active: true,
}
const YERBA = {
  id: 5, name: 'Yerba 1kg', unit_code: 'u', default_sale_price: '3000.00', active: true,
  barcode: '779000001',
}

type Llamada = { metodo: string; url: string }

function montarRedBase() {
  const llamadas: Llamada[] = []
  const busquedas: string[] = []

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    llamadas.push({ metodo, url: u })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/pos/mp-estado')) return Promise.resolve(json({ disponible: false, auto_facturar: false }))
    if (u.includes('/shifts/current')) return Promise.resolve(json({ turno: TURNO }))
    if (u.includes('/locations')) return Promise.resolve(json(LOCATIONS))
    if (u.includes('/customers')) return Promise.resolve(json([]))
    if (u.includes('/variants')) return Promise.resolve(json([]))

    if (u.includes('/catalog/items/scan')) {
      if (u.includes('779000001')) {
        return Promise.resolve(json({ item: YERBA, quantity: '1', unit_price: null, from_scale: false }))
      }
      return Promise.resolve(json({ detail: 'no encontrado' }, 404))
    }
    if (u.includes('/catalog/items?search=')) {
      const termino = decodeURIComponent(u.split('search=')[1] ?? '')
      busquedas.push(termino)
      // Emula el LIKE del backend: coincide si el NOMBRE del producto
      // contiene el término (no al revés -- "con" es más corto que "cono" y
      // nunca lo "contendría").
      const coincidencias = [CONO_SIMPLE, CONO_DOBLE].filter(
        (p) => p.name.toLowerCase().includes(termino.toLowerCase()),
      )
      return Promise.resolve(json(coincidencias))
    }
    return Promise.resolve(json([]))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { llamadas, busquedas }
}

function montar() {
  render(<MemoryRouter><Pos /></MemoryRouter>)
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('Búsqueda en vivo del POS', () => {
  it('al tipear 3 letras aparecen las coincidencias sin apretar Enter', async () => {
    const { busquedas } = montarRedBase()
    const user = userEvent.setup()
    montar()

    const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
    await user.type(campo, 'con')

    // El debounce es de 250ms -- se espera a que la sugerencia aparezca en
    // vez de dormir un tiempo fijo, que es lo mismo que ve un cajero
    // esperando sin apretar nada.
    await screen.findByRole('option', { name: /Cono Simple/ })
    expect(await screen.findByRole('option', { name: /Cono Doble/ })).toBeInTheDocument()
    expect(busquedas).toContain('con')
  })

  it('elegir una sugerencia la agrega al carrito, limpia el campo y devuelve el foco', async () => {
    montarRedBase()
    const user = userEvent.setup()
    montar()

    const campo = await screen.findByPlaceholderText<HTMLInputElement>(/scane|Escane|código|codigo/i)
    await user.type(campo, 'cono')

    const opcion = await screen.findByRole('option', { name: /Cono Simple/ })
    await user.click(opcion)

    // Se agrega igual que cualquier otro camino: aparece en el ticket.
    await waitFor(() => {
      expect(screen.getAllByText(/Cono Simple/).length).toBeGreaterThan(0)
    })
    expect(campo).toHaveValue('')
    await waitFor(() => expect(campo).toHaveFocus())
    // La lista se cierra -- no queda una sugerencia pegada en pantalla.
    expect(screen.queryByRole('option', { name: /Cono Doble/ })).not.toBeInTheDocument()
  })

  it('el flujo del lector (código completo + Enter) sigue agregando por código, sin sugerencia pegada', async () => {
    const { busquedas } = montarRedBase()
    const user = userEvent.setup()
    montar()

    const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
    // Un lector tipea todo el código de una y termina con Enter -- sin pausas,
    // así que el debounce de las sugerencias no llega a dispararse antes.
    await user.type(campo, '779000001{Enter}')

    await screen.findByText(/Yerba 1kg/)
    // El código exacto nunca pasa por la búsqueda por nombre.
    expect(busquedas).toHaveLength(0)
    expect(screen.queryByRole('listbox', { name: 'Sugerencias' })).not.toBeInTheDocument()
  })

  it('con menos de 2 caracteres no se pide ninguna sugerencia', async () => {
    const { busquedas } = montarRedBase()
    const user = userEvent.setup()
    montar()

    const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
    await user.type(campo, 'c')

    // Se espera más que el debounce para confirmar que NO se disparó nada,
    // no para confirmar que sí.
    await new Promise((resolve) => { setTimeout(resolve, 400) })
    expect(busquedas).toHaveLength(0)
    expect(screen.queryByRole('listbox', { name: 'Sugerencias' })).not.toBeInTheDocument()
  })

  it('un multiplicador delante ("3 * cono") busca por el resto y respeta la cantidad al elegir', async () => {
    montarRedBase()
    const user = userEvent.setup()
    montar()

    const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
    await user.type(campo, '3 * cono')

    const opcion = await screen.findByRole('option', { name: /Cono Simple/ })
    await user.click(opcion)

    // La línea del ticket entra con cantidad 3, no 1 -- la fila del producto
    // elegido trae la columna "Cant." en 3.
    const fila = await waitFor(() => {
      const celda = screen.getByText('Cono Simple').closest('tr')
      expect(celda).not.toBeNull()
      return celda as HTMLElement
    })
    expect(within(fila).getByText('3')).toBeInTheDocument()
  })
})
