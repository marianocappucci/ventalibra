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
import { REDIRECCIONES_DE_CONFIGURACION } from '../rutas-viejas'

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

/** 🔴 Las redirecciones salen de `REDIRECCIONES_DE_CONFIGURACION`, la MISMA
 *  tabla que monta `App.tsx`. Hasta el 2026-08-30 este archivo las escribia de
 *  nuevo, asi que medía su propia copia: cuando el destino de ARCA cambio --de
 *  pestaña de primer nivel a sub-seccion de "Integraciones"-- estos tests
 *  siguieron pasando sobre la ruta vieja mientras la app redirigia a otro
 *  lado. Un doble de prueba que reimplementa lo que mide no mide nada. */
const montar = (ruta = '/configuracion') =>
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/configuracion" element={<Configuracion />} />
        {Object.entries(REDIRECCIONES_DE_CONFIGURACION).map(([desde, hacia]) => (
          <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
        ))}
      </Routes>
    </MemoryRouter>,
  )


describe('Las secciones de VentaLibra', () => {
  // El listado de pestañas se fue a `configuracion-forma.test.tsx`, que además
  // afirma el ORDEN y las dos ausencias que importan (el webhook de MercadoPago
  // y la ruta del certificado de ARCA). Acá queda lo que es propio de este
  // archivo: por dónde se entra.

  it('arranca en Empresa, que es lo que se carga una vez y no se toca más', async () => {
    montar()

    expect(await screen.findByRole('tab', { name: /Empresa/ }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Datos de la empresa/)).toBeInTheDocument()
  })
})


describe('Las tres pantallas viejas', () => {
  it('/config-arca lleva a la sección de ARCA, adentro de Integraciones', async () => {
    // ⚠️ Con `?seccion=arca` a secas la redirección NO falla: aterriza en
    // Empresa. Por eso se afirman las dos cosas —la pestaña marcada y el
    // contenido— y no sólo que la navegación no rompió.
    montar('/config-arca')

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Integraciones/ }))
        .toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByText('ARCA (facturación electrónica)')).toBeInTheDocument()
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
