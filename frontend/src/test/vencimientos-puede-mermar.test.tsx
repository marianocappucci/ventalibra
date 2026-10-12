// El wrapper de Vencimientos le pasa al kit `puedeMermar` (dar de baja un lote) aparte de `puedeMover` (asignar y cargar stock con lote), ADR-076 /
// ADR-051 del kit. Hoy las dos salen de `vencimientos.mover`; este archivo fija CUÁL capacidad manda en cada una y que la baja no sale de la marca.
// El kit se reemplaza por un doble que anota las props: lo que se prueba es el cableado, no el dibujo (eso es de `vencimientos-del-kit.test.tsx`,
// con el kit de verdad).
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import CAPACIDADES_POR_ROL from './capacidades-por-rol.json'

const props = vi.hoisted(() => ({ ultimas: null as null | Record<string, unknown> }))

vi.mock('libra-ui/comercio/Vencimientos', () => ({
  Vencimientos: (p: Record<string, unknown>) => {
    props.ultimas = p
    return <div>KIT-VENCIMIENTOS</div>
  },
}))

type Rol = 'admin' | 'encargado' | 'deposito'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function conSesion(capacidades: string[], role: Rol = 'deposito') {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role, active: true, nombre: 'Ana', modulos: [], capacidades, empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    return Promise.resolve(json([]))
  }))
  render(
    <MemoryRouter initialEntries={['/vencimientos']}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { vi.unstubAllGlobals(); props.ultimas = null })

describe('las props de la baja y del movimiento que el wrapper le pone al kit', () => {
  it.each(['admin', 'encargado', 'deposito'] as Rol[])('%s mueve: puedeMover y puedeMermar verdaderas; puedeMarcar sólo con `vencimientos.marcar`', async (rol) => {
    conSesion(CAPACIDADES_POR_ROL[rol], rol)
    await screen.findByText('KIT-VENCIMIENTOS')
    expect(props.ultimas).toMatchObject({ puedeMover: true, puedeMermar: true, puedeMarcar: rol !== 'deposito' })
  })

  it('la baja sale de `vencimientos.mover` y no de la marca: con `marcar` y sin `mover`, no se puede dar de baja', async () => {
    conSesion(['vencimientos.ver', 'vencimientos.marcar'], 'encargado')
    await screen.findByText('KIT-VENCIMIENTOS')
    expect(props.ultimas).toMatchObject({ puedeMover: false, puedeMermar: false, puedeMarcar: true })
  })

  it('con sólo `vencimientos.ver` la pantalla es de lectura: ninguna de las tres', async () => {
    conSesion(['vencimientos.ver'])
    await screen.findByText('KIT-VENCIMIENTOS')
    expect(props.ultimas).toMatchObject({ puedeMover: false, puedeMermar: false, puedeMarcar: false })
  })
})
