// El quiebre por cantidad de la lista cuenta POR PRODUCTO (ADR-078): dos talles de una remera, de a uno, llegan juntos a un
// quiebre de 2, y un producto sin variantes escaneado dos veces en dos líneas también -- igual que las promociones (ADR-074).
// La cuenta la hace el motor (`POST /api/listas-precio/{id}/precios`, libracommerce ADR-048); el POS le manda TODAS las
// líneas cada vez que cambia lo que decide un precio (agregar, cantidad, quitar) y pone lo que vuelve en cada línea.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Pos } from '../pages/Pos'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import { lineasDelPedido, responderPrecios } from './precios-de-lista'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const TURNO = {
  id: 1, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-08-23T10:00:00', cierre: null,
  monto_inicial: 0, monto_declarado_cierre: null, monto_esperado_cierre: null, estado: 'abierto', notas: '',
}
const REMERA = { id: 3, nombre: 'Remera', sku: 'REM', barcode: '779000001', unidad: 'u', precio_venta: 3000, activo: 1 }
const CAFE = { id: 4, nombre: 'Café', sku: 'CAF', barcode: '779000002', unidad: 'u', precio_venta: 1500, activo: 1 }
const VARIANTES = [
  { id: 31, producto_id: 3, sku: 'REM-M', nombre: 'Talle M', atributos: {}, activa: true },
  { id: 32, producto_id: 3, sku: 'REM-L', nombre: 'Talle L', atributos: {}, activa: true },
]
const LISTA = { id: 5, nombre: 'Default', descripcion: '', es_default: 1, activa: 1, created_at: '2026-09-28' }
const LOCATIONS = [{
  id: 1, nombre: 'Salón', codigo: null, direccion: null, activa: true, es_default: true,
  deposito_predeterminado_id: 11, depositos: 1,
}]

/** La lista del test: la remera cuesta 2.500 y 2.000 desde 2 unidades; el café, 1.200 y 1.000 desde 2 (los productos no se
 *  suman entre sí). Cada pedido de precios se anota en `pedidos`; `frenar` deja el próximo sin contestar hasta `soltar()`. */
function montarRed({ precioBalanza = null }: { precioBalanza?: number | null } = {}) {
  const pedidos: { producto_id: number; variante_id: number | null; cantidad: number }[][] = []
  let soltar: () => void = () => {}
  let frenado: Promise<void> | null = null
  const frenar = () => { frenado = new Promise<void>((resolver) => { soltar = () => { frenado = null; resolver() } }) }
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u === '/api/listas-precio/5/precios') {
      pedidos.push(lineasDelPedido(init))
      if (frenado) await frenado
      return responderPrecios(init, (n, productoId) => (productoId === 4 ? (n >= 2 ? 1000 : 1200) : (n >= 2 ? 2000 : 2500)))
    }
    if (u.includes('/api/promociones/calcular')) return json({ aplicadas: [], ahorro: 0 })
    if (u === '/api/listas-precio') return json([LISTA])
    if (u.includes('/api/cajas/medios-disponibles')) return json([{ id: 'efectivo', label: 'Efectivo' }])
    if (u.includes('/pos/mp-estado')) return json({ disponible: false, auto_facturar: false })
    if (u.includes('/api/turnos/actual')) return json({ turno: TURNO })
    if (u.includes('/api/sucursales')) return json(LOCATIONS)
    if (u.includes('/customers')) return json([])
    if (u.includes('/api/productos/3/variantes')) return json(VARIANTES)
    if (u.includes('/api/productos/4/variantes')) return json([])
    if (u.includes('/api/productos/escanear')) {
      const code = new URL(u, 'http://x').searchParams.get('code')
      const base = { cantidad: 1, precio_unitario: precioBalanza, de_balanza: precioBalanza !== null }
      if (code === 'REM-M') return json({ producto: REMERA, variante: VARIANTES[0], ...base })
      if (code === 'REM-L') return json({ producto: REMERA, variante: VARIANTES[1], ...base })
      if (code === '779000002') return json({ producto: CAFE, ...base })
      return json({ detail: 'No hay ningún ítem con ese código.' }, 404)
    }
    return json([])
  }))
  return { pedidos, frenar, soltar: () => soltar() }
}

async function montar(opciones: { precioBalanza?: number | null } = {}) {
  const red = montarRed(opciones)
  const user = userEvent.setup()
  render(<MemoryRouter><Pos /></MemoryRouter>)
  await screen.findByText(/Turno #/)
  // La lista predeterminada tiene que estar cargada antes de escanear: sin ella no se pide precio.
  await new Promise((r) => setTimeout(r, 0))
  return { ...red, user }
}

async function escanear(user: ReturnType<typeof userEvent.setup>, texto: string) {
  const campo = await screen.findByPlaceholderText(/scane|Escane|código|codigo/i)
  await user.type(campo, `${texto}{Enter}`)
}

/** La fila del ticket de la `n`-ésima línea (desde 0). */
function fila(nombre: RegExp | string, n = 0) {
  return screen.getAllByText(nombre)[n].closest('tr') as HTMLElement
}

/** El precio unitario de una fila del ticket (la 4.ª columna: el importe repite el número cuando la cantidad es 1). */
function precioDe(filaDelTicket: HTMLElement) {
  return filaDelTicket.querySelectorAll('td')[3].textContent ?? ''
}

beforeEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  _resetCacheDeMedios()
})

describe('El quiebre cuenta por producto (ADR-078)', () => {
  it('dos talles de a una unidad llegan al quiebre de 2: los dos se cobran al precio del quiebre', async () => {
    const { pedidos, user } = await montar()
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await waitFor(() => expect(precioDe(fila(/Talle M/))).toMatch(/2\.500,00/))

    await escanear(user, 'REM-L')
    await screen.findByText(/Remera \(Talle L\)/)

    // Cada talle tiene UNA unidad, pero el producto lleva dos: las dos líneas van a 2.000, también la que ya estaba.
    await waitFor(() => {
      expect(precioDe(fila(/Talle M/))).toMatch(/2\.000,00/)
      expect(precioDe(fila(/Talle L/))).toMatch(/2\.000,00/)
    })
    expect(screen.queryByText(/2\.500,00/)).not.toBeInTheDocument()
    // El POS mandó las dos líneas juntas, con su variante.
    expect(pedidos.at(-1)).toEqual([
      { producto_id: 3, variante_id: 31, cantidad: 1 },
      { producto_id: 3, variante_id: 32, cantidad: 1 },
    ])
  })

  it('un producto sin variantes escaneado dos veces (dos líneas de a una unidad) llega al quiebre', async () => {
    const { user } = await montar()
    await escanear(user, '779000002')
    await screen.findByText('Café')
    await waitFor(() => expect(precioDe(fila('Café'))).toMatch(/1\.200,00/))
    await escanear(user, '779000002')

    await waitFor(() => {
      expect(screen.getAllByText('Café')).toHaveLength(2)
      expect(precioDe(fila('Café', 0))).toMatch(/1\.000,00/)
      expect(precioDe(fila('Café', 1))).toMatch(/1\.000,00/)
    })
  })

  it('productos distintos no se suman: cada uno decide su quiebre con lo suyo', async () => {
    const { pedidos, user } = await montar()
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await escanear(user, '779000002')
    await screen.findByText('Café')

    await waitFor(() => expect(pedidos.at(-1)).toHaveLength(2))
    await waitFor(() => {
      expect(precioDe(fila(/Talle M/))).toMatch(/2\.500,00/)
      expect(precioDe(fila('Café'))).toMatch(/1\.200,00/)
    })
  })

  it('cambiar la cantidad de un talle reprecia también al otro talle', async () => {
    const { pedidos, user } = await montar()
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await escanear(user, 'REM-L')
    await screen.findByText(/Remera \(Talle L\)/)
    await waitFor(() => expect(precioDe(fila(/Talle L/))).toMatch(/2\.000,00/))

    // El talle L (la línea marcada) pasa a 0: el producto vuelve a llevar una unidad y las dos líneas, al precio base.
    fireEvent.keyDown(window, { key: 'F6' })
    const dialogo = await screen.findByRole('dialog')
    const campo = within(dialogo).getByLabelText('Cantidad')
    await user.clear(campo)
    await user.type(campo, '1')
    await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(pedidos.at(-1)).toEqual([
      { producto_id: 3, variante_id: 31, cantidad: 1 },
      { producto_id: 3, variante_id: 32, cantidad: 1 },
    ])
  })

  it('al quitar un talle, el que queda vuelve al precio base', async () => {
    const { user } = await montar()
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await escanear(user, 'REM-L')
    await waitFor(() => expect(precioDe(fila(/Talle M/))).toMatch(/2\.000,00/))

    fireEvent.keyDown(window, { key: 'F4' }) // quita la línea marcada: el último talle agregado
    await waitFor(() => expect(screen.queryByText(/Remera \(Talle L\)/)).not.toBeInTheDocument())

    await waitFor(() => expect(precioDe(fila(/Talle M/))).toMatch(/2\.500,00/))
    expect(screen.queryByText(/2\.000,00/)).not.toBeInTheDocument()
  })

  it('no se puede cobrar hasta que llegan los precios, y el cobro abre con el total ya repreciado', async () => {
    const { frenar, soltar, user } = await montar()
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await waitFor(() => expect(precioDe(fila(/Talle M/))).toMatch(/2\.500,00/))

    frenar()
    await escanear(user, 'REM-L')
    await screen.findByText(/Remera \(Talle L\)/)
    // La respuesta no llegó: los talles siguen a lo que traían, y F2 (cobrar) no abre el cobro con un total viejo.
    fireEvent.keyDown(window, { key: 'F2' })
    expect(screen.queryByText(/^Cobrar \$/)).not.toBeInTheDocument()

    soltar()
    await waitFor(() => expect(precioDe(fila(/Talle M/))).toMatch(/2\.000,00/))
    expect(screen.getByText('Total').nextElementSibling).toHaveTextContent('$4.000,00')
    // Ya con los precios, F2 abre el cobro por el total del quiebre. 🔑 F2 se repite adentro del `waitFor`: el carrito
    // repreciado vuelve a calcular las promociones y `puedeCobrar` espera también a `calculandoPromos`; con el CI lento,
    // un F2 único caía en esa ventana, se ignoraba (bien) y el test daba rojo (falló así tres veces, 5,3 a 5,5 s).
    // Repetirlo es inocuo: con el cobro abierto, F2 sólo lo vuelve a abrir.
    await waitFor(() => {
      fireEvent.keyDown(window, { key: 'F2' })
      expect(screen.getByText('Cobrar $4.000,00')).toBeInTheDocument()
    })
  })

  it('una etiqueta de balanza suma sus kilos al producto pero conserva su precio', async () => {
    const { pedidos, user } = await montar({ precioBalanza: 4200 })
    await escanear(user, 'REM-M')
    await screen.findByText(/Remera \(Talle M\)/)
    await waitFor(() => expect(pedidos.length).toBeGreaterThan(0))
    expect(precioDe(fila(/Talle M/))).toMatch(/4\.200,00/)
    expect(screen.queryByText(/2\.500,00/)).not.toBeInTheDocument()
  })
})
