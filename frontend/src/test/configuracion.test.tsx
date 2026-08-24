// ⚠️ **Los selectores dicen `role="tab"` desde libra-ui v0.35.0.** El
// conmutador de `createConfiguracion` era un `<nav>` de botones con
// `aria-current="page"`; ahora es el `Tabs` de shadcn, el mismo que usa la
// Configuración de Contalibra, que anuncia `role="tab"` y `aria-selected`.
// No es un detalle de implementación que se pueda ignorar acá: es lo que un
// lector de pantalla anuncia, y estos tests son lo que lo fija.
// Configuración de VentaLibra (ítem 5, 2026-08-05).
//
// El armado y las secciones comunes viven en `libra-ui/Configuracion` y tienen
// sus tests ahí. Lo que se prueba acá es **la declaración de este producto**:
//
// 1. Que estén las seis secciones que le corresponden — el "según corresponda"
//    del pedido se declara en `pages/Configuracion.tsx`, y una sección que
//    falte no rompe nada: simplemente no aparece, y nadie lo nota.
// 2. Que las tres pantallas viejas redirijan en vez de dar 404. Eran entradas
//    del menú lateral: pueden estar en un favorito o en un mensaje, y un 404
//    en Configuración parece que se rompió el sistema.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Navigate } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/config/empresa/logo')) {
      return Promise.resolve(new Response('', { status: 404 }))
    }
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '',
        empresa_telefono: '', empresa_email: '', empresa_iibb: '',
        empresa_iva_condition: 'Monotributista', empresa_inicio_actividades: '',
      }))
    }
    if (u.includes('/api/config/backups')) return Promise.resolve(json([]))
    return Promise.resolve(json(null))
  }))
})

const montar = (ruta = '/configuracion') =>
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/configuracion" element={<Configuracion />} />
        <Route path="/config-arca" element={<Navigate to="/configuracion?seccion=arca" replace />} />
        <Route path="/config-balanza" element={<Navigate to="/configuracion?seccion=balanza" replace />} />
        <Route path="/config-ticket" element={<Navigate to="/configuracion?seccion=ticket" replace />} />
      </Routes>
    </MemoryRouter>,
  )


describe('Las secciones de VentaLibra', () => {
  it('están las siete que le corresponden', async () => {
    montar()

    // ⚠️ **La lista crece con las secciones.** Decía "las seis" hasta el
    // 2026-08-23, cuando entró Mercado Pago. Un guard que cubre "las N de
    // entonces" deja a la siguiente naciendo sin cobertura, y una sección que
    // falta no rompe nada: simplemente no aparece, y nadie lo nota.
    for (const seccion of [
      'Empresa', 'Correo', 'Datos / Backup', 'ARCA', 'Balanza', 'Ticket',
      'Mercado Pago',
    ]) {
      expect(await screen.findByRole('tab', { name: new RegExp(seccion) }))
        .toBeInTheDocument()
    }
  })

  it('arranca en Empresa, que es lo que se carga una vez y no se toca más', async () => {
    montar()

    expect(await screen.findByRole('tab', { name: /Empresa/ }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Datos de la empresa/)).toBeInTheDocument()
  })
})


describe('Las tres pantallas viejas', () => {
  it('/config-arca lleva a la sección de ARCA', async () => {
    montar('/config-arca')

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /ARCA/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
  })

  it('/config-balanza lleva a la sección de Balanza', async () => {
    montar('/config-balanza')

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Balanza/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
  })

  it('/config-ticket lleva a la sección de Ticket', async () => {
    montar('/config-ticket')

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Ticket/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
  })
})
