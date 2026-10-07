// El menú y el ruteo por rol (ADR-049): la app entera con sesión de verdad (`AuthProvider` + `/auth/me`), un usuario de cada
// rol, y lo que ve y a dónde lo mandan cuando entra a una ruta que no es suya.
//
// 🔑 **De dónde salen las capacidades.** De `capacidades-por-rol.json`, que se genera desde `app/permisos.py` (la única matriz)
// y que un test del backend (`tests/test_roles_matriz.py`) obliga a mantener al día. Así la SPA se prueba contra lo que el
// backend de verdad manda en `/auth/me`, sin una tercera copia de la matriz.
//
// 🔴 **Lo que cada rol DEBE ver está escrito acá a mano, a propósito** (`MENU_ESPERADO`): si se afloja una capacidad en el
// backend y se regenera el JSON, este archivo se pone rojo. Es la contraparte de la tabla de `test_roles_matriz.py`.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import { CAPACIDADES, inicioDe, puede } from '../lib/permisos'

// Las pantallas donde caen los roles: se reemplazan por una marca, porque lo que se prueba es a dónde llega cada uno y
// no lo que la pantalla hace (eso lo cubren los tests de cada una).
vi.mock('../pages/Pos', () => ({ Pos: () => <div>PANTALLA-POS</div> }))
vi.mock('../pages/Dashboard', () => ({ Dashboard: () => <div>PANTALLA-DASHBOARD</div> }))
vi.mock('../pages/Stock', () => ({ Stock: () => <div>PANTALLA-STOCK</div> }))
vi.mock('../pages/Reportes', () => ({ Reportes: () => <div>PANTALLA-REPORTES</div> }))
vi.mock('../pages/Reposicion', () => ({ Reposicion: () => <div>PANTALLA-REPOSICION</div> }))
vi.mock('../pages/Vencimientos', () => ({ Vencimientos: () => <div>PANTALLA-VENCIMIENTOS</div> }))
vi.mock('../pages/Usuarios', () => ({ Usuarios: () => <div>PANTALLA-USUARIOS</div> }))

type Rol = keyof typeof CAPACIDADES_POR_ROL

/** Todas las entradas del menú, tal como se leen en la barra lateral. */
const MENU = [
  'POS (Caja)', 'Ventas', 'Productos', 'Compras', 'Proveedores', 'Egresos', 'Clientes', 'Cuentas corrientes',
  'Sucursales y depósitos', 'Listas de precio', 'Actualización de precios', 'Promociones', 'Etiquetas', 'Stock', 'Transferencias',
  'Cajas', 'Tesorería', 'Turnos', 'Cierre diario', 'Dashboard', 'Reportes', 'Margen y rotación', 'Reposición sugerida', 'Vencimientos y lotes', 'Libros IVA',
  'Caja por medio', 'Usuarios', 'Logs', 'Configuración',
]

const TODO = MENU

/** Lo que cada rol ve en el menú. Escrito a mano (ver arriba). */
const MENU_ESPERADO: Record<Rol, string[]> = {
  admin: TODO,
  encargado: TODO.filter((m) => !['Cajas', 'Usuarios', 'Logs', 'Configuración'].includes(m)),
  vendedor: ['POS (Caja)', 'Ventas', 'Productos', 'Clientes', 'Cuentas corrientes', 'Stock', 'Turnos'],
  // ADR-054: el mostrador y nada más (POS, ventas para reimprimir, turnos para abrir y cerrar la caja).
  cajero: ['POS (Caja)', 'Ventas', 'Turnos'],
  deposito: ['Productos', 'Compras', 'Sucursales y depósitos', 'Stock', 'Vencimientos y lotes', 'Transferencias', 'Reposición sugerida'],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function usuarioDe(rol: Rol, extra: Record<string, unknown> = {}) {
  return {
    id: '7', username: `u-${rol}`, name: `Persona ${rol}`, role: rol, active: true, empresa_nombre: 'Prueba',
    capacidades: CAPACIDADES_POR_ROL[rol], modulos: ['facturacion', 'multisucursal'], ...extra,
  }
}

function DondeEstoy() {
  return <div data-testid="ruta">{useLocation().pathname}</div>
}

function entrar(usuario: Record<string, unknown>, ruta: string) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).includes('/auth/me')) return Promise.resolve(json(usuario))
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
      <DondeEstoy />
    </MemoryRouter>,
  )
}

/** Las entradas del menú que hay en pantalla. El menú es la barra lateral: se cuentan sólo los links que llevan a una ruta
 *  del menú, por nombre exacto. */
function menuVisible(): string[] {
  const enPantalla = new Set(screen.queryAllByRole('link').map((a) => a.textContent?.trim()))
  return MENU.filter((m) => enPantalla.has(m))
}

beforeEach(() => { vi.unstubAllGlobals() })

describe('el menú de cada rol', () => {
  it.each(Object.keys(MENU_ESPERADO) as Rol[])('%s ve lo suyo y nada más', async (rol) => {
    // Una ruta que todos los roles con menú alcanzan tiene una marca conocida; se espera a que cargue la sesión.
    entrar(usuarioDe(rol), inicioDe(usuarioDe(rol)) ?? '/pos')
    await screen.findByText(/PANTALLA-(POS|STOCK|DASHBOARD)/)
    expect(menuVisible().sort()).toEqual([...MENU_ESPERADO[rol]].sort())
  })

  it('el visitante de la demo ve todos los menús, aunque su rol sea encargado', async () => {
    entrar(usuarioDe('encargado', { demo_readonly: true }), '/pos')
    await screen.findByText('PANTALLA-POS')
    expect(menuVisible().sort()).toEqual([...TODO].sort())
  })

  it('con un backend viejo (sin `capacidades`) el admin sigue viéndolo todo', async () => {
    const { capacidades: _quitadas, ...sinCapacidades } = usuarioDe('admin')
    entrar(sinCapacidades, '/pos')
    await screen.findByText('PANTALLA-POS')
    expect(menuVisible().sort()).toEqual([...TODO].sort())
  })
})

describe('el ruteo por rol', () => {
  async function iraDe(rol: Rol, ruta: string) {
    entrar(usuarioDe(rol), ruta)
    await screen.findByText(/PANTALLA-(POS|STOCK|DASHBOARD)/, undefined, { timeout: 3000 }).catch(() => undefined)
    return screen.getByTestId('ruta').textContent
  }

  it.each([
    ['cajero', '/reportes'], ['cajero', '/reposicion'], ['cajero', '/vencimientos'], ['cajero', '/usuarios'], ['cajero', '/cierre-diario'], ['cajero', '/configuracion'],
    ['vendedor', '/margen'], ['vendedor', '/reposicion'], ['vendedor', '/vencimientos'], ['vendedor', '/tesoreria'], ['vendedor', '/logs'], ['vendedor', '/'],
    // El cajero no tiene las pantallas de gestión aunque el backend le deje leer el catálogo, el stock y los clientes.
    ['cajero', '/productos'], ['cajero', '/stock'], ['cajero', '/clientes'], ['cajero', '/proveedores'],
  ] as [Rol, string][])('%s en %s vuelve al POS', async (rol, ruta) => {
    expect(await iraDe(rol, ruta)).toBe('/pos')
  })

  it.each([
    ['encargado', '/usuarios'], ['encargado', '/configuracion'], ['encargado', '/logs'], ['encargado', '/cajas'], ['admin', '/'],
    ['encargado', '/'],
  ] as [Rol, string][])('%s en %s va al dashboard', async (rol, ruta) => {
    expect(await iraDe(rol, ruta)).toBe('/dashboard')
  })

  it.each([
    ['deposito', '/pos'], ['deposito', '/ventas'], ['deposito', '/reportes'], ['deposito', '/clientes'],
    ['deposito', '/turnos'], ['deposito', '/proveedores'], ['deposito', '/'], ['deposito', '/una-ruta-que-no-existe'],
  ] as [Rol, string][])('%s en %s va al stock', async (rol, ruta) => {
    expect(await iraDe(rol, ruta)).toBe('/stock')
  })

  it.each([
    ['deposito', '/stock'], ['cajero', '/pos'], ['vendedor', '/stock'], ['encargado', '/reportes'], ['admin', '/usuarios'],
    ['encargado', '/reposicion'], ['admin', '/reposicion'], ['deposito', '/reposicion'],
    // Las tres capacidades de vencimientos: el depósito llega a la pantalla (que ve y mueve, pero no marca).
    ['encargado', '/vencimientos'], ['admin', '/vencimientos'], ['deposito', '/vencimientos'],
  ] as [Rol, string][])('%s entra a %s sin que lo muevan', async (rol, ruta) => {
    entrar(usuarioDe(rol), ruta)
    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent(ruta))
    // Y se queda: si hubiera una redirección, la ruta ya habría cambiado antes de que termine la carga de la sesión.
    await screen.findAllByRole('link')
    expect(screen.getByTestId('ruta')).toHaveTextContent(ruta)
  })

  it('sin sesión, cualquier ruta lleva al login', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ detail: 'not authenticated' }, 401))))
    render(
      <MemoryRouter initialEntries={['/reportes']}>
        <AuthProvider><App /></AuthProvider>
        <DondeEstoy />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent('/login'))
  })

  it('un rol sin ninguna pantalla inicial no rebota en círculo: avisa', async () => {
    entrar({ ...usuarioDe('cajero'), capacidades: ['reportes'] }, '/pos')
    expect(await screen.findByText(/no tiene pantallas asignadas/)).toBeInTheDocument()
  })
})

describe('permisos.ts', () => {
  it('las capacidades que manda el backend son las que conoce la SPA', () => {
    const conocidas = new Set<string>(CAPACIDADES)
    for (const [rol, capacidades] of Object.entries(CAPACIDADES_POR_ROL)) {
      for (const c of capacidades) expect(conocidas.has(c), `${rol} recibe «${c}», que la SPA no conoce`).toBe(true)
    }
  })

  it('el admin las tiene todas', () => {
    expect([...CAPACIDADES].sort()).toEqual([...CAPACIDADES_POR_ROL.admin].sort())
  })

  it('puede() acepta una lista y alcanza con una', () => {
    const cajero = usuarioDe('cajero')
    expect(puede(cajero, ['reportes', 'ventas.pos'])).toBe(true)
    expect(puede(cajero, ['reportes', 'margen', 'reposicion.ver'])).toBe(false)
    expect(puede(null, 'ventas.pos')).toBe(false)
  })

  it('el inicio de cada rol', () => {
    expect(inicioDe(usuarioDe('admin'))).toBe('/dashboard')
    expect(inicioDe(usuarioDe('encargado'))).toBe('/dashboard')
    expect(inicioDe(usuarioDe('vendedor'))).toBe('/pos')
    expect(inicioDe(usuarioDe('cajero'))).toBe('/pos')
    expect(inicioDe(usuarioDe('deposito'))).toBe('/stock')
  })
})
