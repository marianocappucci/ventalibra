// Plan único (ADR-072; antes ADR-048 con Básico y Premium): trae facturación ARCA y multisucursal, así que la SPA no avisa
// nada. La SPA lee los módulos de `/auth/me` (`modulos`: los habilitados) y, si un administrador apagó alguno, avisa
// «sin activar en esta instancia» donde el backend cortaría con 403:
// el alta de una segunda sucursal, la transferencia entre sucursales y la facturación (config de ARCA y casillero del
// POS). **Sólo avisa**: el que corta es el backend (`tests/test_planes_y_sucursales.py`), así que si el campo falta se
// ofrece todo.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EmitirFactura } from '../components/emitir-factura'
import { Configuracion } from '../pages/Configuracion'
import { Sucursales } from '../pages/Sucursales'
import { Transferencias } from '../pages/Transferencias'
import { ModulosContext, modulosDe, tieneModulo } from '../lib/modulos'

// El rol de la sesión, para las pantallas que se montan sueltas (la app entera va en `planes-y-modulos-app.test.tsx`).
const sesion = vi.hoisted(() => ({ rol: 'admin' }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'u', name: 'U', role: sesion.rol }, loading: false }),
}))

const TODOS = ['facturacion', 'multisucursal'] // el plan único
const SIN_MODULOS: string[] = [] // alguno apagado por un administrador

const CENTRO = {
  id: 1, nombre: 'Centro', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  sesion.rol = 'admin'
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/sucursales')) return Promise.resolve(json([CENTRO]))
    if (u.includes('/api/config/empresa/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/config/arca')) return Promise.resolve(json({}))
    return Promise.resolve(json([]))
  }))
})

function conModulos(modulos: string[] | undefined, pantalla: React.ReactNode, ruta = '/') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <ModulosContext.Provider value={modulos}>{pantalla}</ModulosContext.Provider>
    </MemoryRouter>,
  )
}

describe('lib/modulos', () => {
  it('lee la lista de /auth/me y, si no viene, no decide nada', () => {
    expect(modulosDe({ modulos: ['facturacion'] })).toEqual(['facturacion'])
    expect(modulosDe({})).toBeUndefined()
    expect(modulosDe(null)).toBeUndefined()
    expect(modulosDe({ modulos: 'facturacion' })).toBeUndefined()
  })

  it('con la lista, el módulo está o no; sin lista se ofrece todo', () => {
    expect(tieneModulo(TODOS, 'multisucursal')).toBe(true)
    expect(tieneModulo(SIN_MODULOS, 'multisucursal')).toBe(false)
    expect(tieneModulo(undefined, 'multisucursal')).toBe(true)
  })
})

describe('Sucursales', () => {
  it('sin `multisucursal` avisa que más de una sucursal está sin activar y lo dice en el botón', async () => {
    conModulos(SIN_MODULOS, <Sucursales />)
    expect(await screen.findByRole('note')).toHaveTextContent('Más de una sucursal: sin activar en esta instancia')
    expect(await screen.findByRole('button', { name: /Nueva sucursal \(sin activar\)/ })).toBeInTheDocument()
    // Lo que ya hay sigue a la vista y editable.
    expect(await screen.findByText('Centro')).toBeInTheDocument()
  })

  it('con el plan único no avisa nada', async () => {
    conModulos(TODOS, <Sucursales />)
    expect(await screen.findByRole('button', { name: 'Nueva sucursal' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('si el backend no manda los módulos, no avisa (el 403 del backend es el que corta)', async () => {
    conModulos(undefined, <Sucursales />)
    expect(await screen.findByRole('button', { name: 'Nueva sucursal' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('un cajero no ve el aviso: no da de alta sucursales', async () => {
    sesion.rol = 'cajero'
    conModulos(SIN_MODULOS, <Sucursales />)
    expect(await screen.findByText('Centro')).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('Transferencias', () => {
  it('sin `multisucursal` avisa que entre sucursales está sin activar, y deja la pantalla', async () => {
    conModulos(SIN_MODULOS, <Transferencias />)
    expect(await screen.findByRole('note')).toHaveTextContent('Transferencias entre sucursales: sin activar en esta instancia')
    expect(screen.getByRole('note')).toHaveTextContent('entre los depósitos de tu sucursal')
    expect(await screen.findByRole('heading', { name: 'Transferir stock' })).toBeInTheDocument()
  })

  it('con el plan único no avisa nada', async () => {
    conModulos(TODOS, <Transferencias />)
    expect(await screen.findByRole('heading', { name: 'Transferir stock' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('Configuración: la integración con ARCA', () => {
  const irAArca = () => '/configuracion?seccion=integraciones&integracion=arca'

  it('sin `facturacion` la sección ARCA dice que está sin activar y no llama a /config/arca', async () => {
    conModulos(SIN_MODULOS, <Configuracion />, irAArca())
    expect(await screen.findByRole('note')).toHaveTextContent('Facturación electrónica ARCA: sin activar en esta instancia')
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining('/config/arca'), expect.anything())
  })

  it('sin `facturacion` las otras integraciones siguen', async () => {
    conModulos(SIN_MODULOS, <Configuracion />, irAArca())
    expect(await screen.findByRole('button', { name: /Email \/ SMTP/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ARCA \/ AFIP/ })).toBeInTheDocument()
  })

  it('con el plan único es la configuración de ARCA de siempre', async () => {
    conModulos(TODOS, <Configuracion />, irAArca())
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/config/arca'), expect.anything()))
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('Casillero «Emitir factura» del POS', () => {
  it('sin el módulo queda apagado, desmarcado y con el motivo', async () => {
    const onChange = vi.fn()
    render(<EmitirFactura marcado disponible={false} onChange={onChange} />)
    const casillero = screen.getByRole('checkbox', { name: /Emitir factura/ })
    expect(casillero).toBeDisabled()
    expect(casillero).not.toBeChecked()
    expect(screen.getByText('(no está habilitada en esta instancia; escribinos para activarla)')).toBeInTheDocument()
    await userEvent.click(casillero)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('con el módulo se marca y avisa el cambio', async () => {
    const onChange = vi.fn()
    render(<EmitirFactura marcado={false} disponible onChange={onChange} />)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Emitir factura' }))
    expect(onChange).toHaveBeenCalledWith(true)
    expect(screen.queryByText('(no está habilitada en esta instancia; escribinos para activarla)')).not.toBeInTheDocument()
  })
})
