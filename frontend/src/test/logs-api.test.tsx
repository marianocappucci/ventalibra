// La pantalla de Logs pide sus datos a `/api/logs`: en `/logs` (el default del kit) el endpoint tapaba la ruta de la pantalla y
// un F5 o un link pegado devolvía el JSON crudo (medido en Chromium contra dev, 2026-10-05).
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Logs } from '../pages/Logs'

afterEach(() => { vi.unstubAllGlobals() })

describe('Logs', () => {
  it('pide la actividad a /api/logs, no a /logs', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ actividad: [], accesos: [], total: 0, total_pages: 1, page: 1, entidades: [], acciones: {}, usuarios: [] }), {
      status: 200, headers: { 'content-type': 'application/json' },
    })))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><Logs /></MemoryRouter>)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]))
    expect(urls.some((u) => u.startsWith('/api/logs?'))).toBe(true)
    expect(urls.some((u) => u.startsWith('/logs'))).toBe(false)
  })
})
