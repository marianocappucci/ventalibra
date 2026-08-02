// Humo del SPA: que la app monte y que el guard de rutas haga lo que dice.
//
// Es poco codigo para lo que cubre -- si alguien rompe el import de una
// pagina, cambia una ruta o toca el guard, esto se pone rojo. Hasta el
// 2026-07-31 nada de eso lo veia nadie hasta abrir el navegador.
//
// El Login y las pantallas de recuperacion vienen de libra-ui (que tiene
// sus propios 68 tests): aca se prueba el cableado de ESTE producto.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

const RUTA_PROTEGIDA = '/pos'
const PRODUCTO = 'VentaLibra'
const RUTA_SESION = '/auth/me'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Sin sesion: la ruta de sesion responde 401, como con la cookie vencida. */
function sinSesion() {
  fetchMock.mockImplementation(() => Promise.resolve(json({ detail: 'No autenticado' }, 401)))
}

/** Con sesion: devuelve un usuario; el resto de las llamadas, vacio. */
function conSesion() {
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes(RUTA_SESION)
        ? json({
            id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true,
            // Forma extendida de Contalibra/Restolibra: el Layout arma el
            // sidebar con `modulos`.
            nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
          })
        : json([]),
    ),
  )
}

function montar(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('arranque', () => {
  it('la app monta y llega al login sin errores de consola', async () => {
    const errores = vi.spyOn(console, 'error').mockImplementation(() => {})
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    expect(errores).not.toHaveBeenCalled()
  })

  it('consulta la sesion al arrancar', async () => {
    sinSesion()
    montar(RUTA_PROTEGIDA)
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes(RUTA_SESION))).toBe(true),
    )
  })
})

describe('guard de rutas', () => {
  it('sin sesion, una ruta protegida redirige al login', async () => {
    sinSesion()
    montar(RUTA_PROTEGIDA)
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Ingresar' })).toBeInTheDocument()
  })

  it('con sesion, la ruta protegida se muestra', async () => {
    conSesion()
    montar(RUTA_PROTEGIDA)
    // Se afirma que el shell autenticado RENDERIZO, no solo que el login
    // desaparecio. Entre uno y otro hay un instante en que no esta ninguno de
    // los dos (AuthContext todavia resolviendo /auth/me), y esperar unicamente
    // la ausencia del login daba por bueno ese instante intermedio: el test
    // pasaba aunque la pantalla protegida no llegara a montar nunca.
    //
    // No es teorico. Se vio al medir cobertura el 2026-07-31: en LibraDesk
    // saltaba entre 412 y 462 lineas cubiertas en corridas identicas, con los
    // 6 tests en verde siempre. Esas ~50 lineas eran la pantalla protegida,
    // que a veces alcanzaba a renderizar y a veces no.
    //
    // `findAllByText` y no `findByText`: el Layout de libra-ui pinta el nombre
    // del producto dos veces (sidebar y pie), y la forma singular tira error
    // si hay mas de una coincidencia.
    expect(await screen.findAllByText(PRODUCTO)).not.toHaveLength(0)
    // Y que el usuario de la sesion llego hasta la UI, no solo que hubo shell.
    expect(await screen.findAllByText('Ana')).not.toHaveLength(0)
    expect(screen.queryByLabelText('Usuario')).not.toBeInTheDocument()
  })
})

describe('las pantallas de recuperacion son publicas', () => {
  // Invariante con comentario propio en App.tsx: son publicas a proposito,
  // porque quien las necesita no puede iniciar sesion. Si el guard las
  // capturara, el enlace del mail llevaria al login y la funcion quedaria
  // inutilizable justo para quien la necesita.
  it('/forgot-password se ve sin sesion', async () => {
    sinSesion()
    montar('/forgot-password')
    expect(await screen.findByLabelText('Usuario o correo')).toBeInTheDocument()
  })

  it('/reset-password se ve sin sesion', async () => {
    sinSesion()
    montar('/reset-password?token=abc123')
    expect(await screen.findByLabelText('Contraseña nueva')).toBeInTheDocument()
  })
})
