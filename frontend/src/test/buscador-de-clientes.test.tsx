// El módulo de clientes no tenía con qué buscar.
//
// La tabla no pagina —`DataTable` no arma row model de paginación—, así que
// con cientos de clientes la única forma de llegar a uno era scrollear. El
// buscador existe en `libra-ui/data-table` desde su v0.8.0: lo que faltaba
// acá era pasarle la prop, y eso es lo que fija este archivo.
//
// Se prueba por lo que hace quien atiende: teclea y las filas que no coinciden
// dejan de estar. El teléfono vale doble como control: **no es columna de esta
// tabla**, así que si alguien recorta `campos` a lo que se ve, esto se pone
// rojo.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Clientes } from '../pages/Clientes'

const CLIENTES = [
  {
    id: 1, party_type: 'organization', display_name: 'Panadería del Sol',
    email: 'pedidos@delsol.com.ar', phone: '2324441122', active: true,
    cuit: '30999999995', condicion_iva: 'Responsable Inscripto',
  },
  {
    id: 2, party_type: 'organization', display_name: 'Ferretería Suárez',
    email: 'ventas@suarez.com.ar', phone: '1155667788', active: true,
    cuit: '20111111112', condicion_iva: 'Monotributista',
  },
  {
    id: 3, party_type: 'person', display_name: 'Kiosco 24hs',
    email: null, phone: null, active: true,
    cuit: null, condicion_iva: null,
  },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const cuerpo = String(url).startsWith('/customers') ? CLIENTES : []
    return Promise.resolve(new Response(JSON.stringify(cuerpo), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
  }))
})

/** Monta y espera a que la carga inicial termine: antes de eso la tarjeta dice
 *  "Cargando…" y no hay tabla que mirar. */
async function montar() {
  const usuario = userEvent.setup()
  render(<Clientes />)
  await screen.findByText('Panadería del Sol')
  return usuario
}

const buscador = () => screen.getByRole('searchbox', { name: 'Buscar cliente' })

it('filtra la lista por nombre', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'kiosco')

  expect(screen.getByText('Kiosco 24hs')).toBeInTheDocument()
  expect(screen.queryByText('Panadería del Sol')).not.toBeInTheDocument()
  expect(screen.queryByText('Ferretería Suárez')).not.toBeInTheDocument()
})

it('filtra por CUIT, que es lo que se tiene del papel', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), '20111111112')

  expect(screen.getByText('Ferretería Suárez')).toBeInTheDocument()
  expect(screen.queryByText('Panadería del Sol')).not.toBeInTheDocument()
})

// El teléfono NO es columna de esta tabla: si sólo se buscara lo que se ve,
// esta consulta no encontraría nada.
it('filtra por teléfono aunque no sea columna', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), '2324441122')

  expect(screen.getByText('Panadería del Sol')).toBeInTheDocument()
  expect(screen.queryByText('Ferretería Suárez')).not.toBeInTheDocument()
})

// Los nombres se cargan a mano y con acentos; nadie los teclea al buscar.
it('encuentra sin acentos', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'ferreteria suarez')

  expect(screen.getByText('Ferretería Suárez')).toBeInTheDocument()
  expect(screen.queryByText('Kiosco 24hs')).not.toBeInTheDocument()
})

// Buscar y no encontrar no es lo mismo que no tener clientes: el mensaje de
// vacío de la página haría pensar que se perdieron.
it('avisa que no hay resultados, no que no hay clientes', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'zzz')

  expect(screen.getByText(/Sin resultados para/)).toBeInTheDocument()
  expect(screen.queryByText('Sin clientes todavía.')).not.toBeInTheDocument()
})
