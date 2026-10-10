// La devolución parcial de VentaLibra, montada como `accionesExtra` de
// `VentaDetalle` (libra-ui) desde F4 (2026-09-15, DECISIONS.md ADR-025).
//
// Se prueba el componente solo (`DevolucionDeVenta`), no la pantalla entera:
// lo que hace falta cubrir es que manda `sale_item_id` -- no el índice de la
// línea, que era como indexaba el modelo viejo (`POST /sales/{id}/returns`,
// retirado) -- junto con `cantidad`, `deposito_id` y `medio_pago`, y que
// recarga el detalle al terminar.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DevolucionDeVenta } from '../pages/Ventas'
import { opcionesDe } from './buscable'
import { _resetCacheDeMedios } from '@/lib/medios-pago'
import type { Venta } from '../api'

const MEDIOS = [
  { id: 'efectivo', label: 'Efectivo' },
  { id: 'tarjeta_debito', label: 'Tarjeta de débito' },
]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const DETALLE: Venta = {
  id: 42, numero: 'POS-000042', fecha: '2026-09-15', estado: 'cobrada',
  items: [
    { id: 501, nombre: 'Yerba 1kg', qty: 5, precio: 1500, subtotal: 7500, producto_id: 3 },
  ],
  subtotal: 7500, descuento: 0, total: 7500,
  cliente_id: null, cliente_nombre: '', observaciones: '',
  pagos: [{ medio: 'efectivo', monto: 7500, referencia: '' }],
  factura_id: null, factura_display: null, remito_id: null,
  mp_order_id: '', mp_payment_id: '',
}

type Llamada = { metodo: string; url: string; body: unknown }

// Sucursal y depósito son entidades distintas: cada depósito tiene su `branch_id`, y la sucursal dice cuál es su
// depósito de venta. Los ids no coinciden a propósito (la sucursal 7 vende del depósito 12).
const dep = (id: number, nombre: string, branch_id: number, es_default = 0, activo = 1) => (
  { id, nombre, descripcion: '', branch_id, tipo: 'warehouse', activo, es_default, total_productos: 0 }
)
const DEPOSITOS = [
  dep(11, 'Salón Centro', 1, 1),
  dep(13, 'Bodega Centro', 1),
  dep(12, 'Salón Norte', 7),
  dep(14, 'Bodega vieja Norte', 7, 0, 0),
]
const sucursal = (id: number, nombre: string, deposito_predeterminado_id: number, es_default = false) => (
  { id, nombre, codigo: null, direccion: null, activa: true, es_default, deposito_predeterminado_id, depositos: 2 }
)
const SUCURSALES = [sucursal(1, 'Centro', 11, true), sucursal(7, 'Norte', 12)]

// Cómo contesta `POST /api/ventas/42/devolver`, en orden (la última se repite): `ok`, `repetida` (el motor ya había aplicado ese intento),
// `red` (se corta la conexión: no se sabe si escribió), `5xx` (error del servidor) o `409` (la clave ya se usó con otros datos).
type Respuesta = 'ok' | 'repetida' | 'red' | '5xx' | '409'

function montarRed(opciones: {
  yaDevuelto?: number; depositoId?: number | null; turnoEnSucursal?: number | null; respuestas?: Respuesta[]
} = {}) {
  const llamadas: Llamada[] = []
  const respuestas = [...(opciones.respuestas ?? ['ok'])]
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    llamadas.push({ metodo, url: u, body })

    if (u.includes('/api/cajas/medios-disponibles')) return Promise.resolve(json(MEDIOS))
    if (u.includes('/ventas/42/devuelto')) {
      return Promise.resolve(json({
        por_clave: opciones.yaDevuelto
          ? [{ producto_id: 3, variante_id: null, cantidad: opciones.yaDevuelto }]
          : [],
        deposito_id: opciones.depositoId === undefined ? 11 : opciones.depositoId,
      }))
    }
    if (u.includes('/api/turnos/actual')) {
      const sucursalId = opciones.turnoEnSucursal
      return Promise.resolve(json({
        turno: sucursalId == null ? null : {
          id: 5, usuario_id: 1, usuario_nombre: 'Ana', apertura: '2026-09-16T10:00:00', cierre: null,
          monto_inicial: 0, estado: 'abierto', notas: '', caja_id: 10,
          caja: { id: 10, nombre: 'Caja 1', punto_venta: null },
          sucursal: { id: sucursalId, nombre: 'Sucursal' },
        },
      }))
    }
    if (u.includes('/api/sucursales')) return Promise.resolve(json(SUCURSALES))
    if (u.includes('/api/depositos')) return Promise.resolve(json(DEPOSITOS))
    if (u.includes('/api/ventas/42/devolver')) {
      const cual = respuestas.length > 1 ? respuestas.shift()! : respuestas[0]
      if (cual === 'red') return Promise.reject(new TypeError('Failed to fetch'))
      if (cual === '5xx') return Promise.resolve(json({ detail: 'Error interno' }, 502))
      if (cual === '409') return Promise.resolve(json({ detail: 'la clave_operacion ya se usó en esta venta con otras cantidades' }, 409))
      return Promise.resolve(json({ ...DETALLE, repetida: cual === 'repetida' }))
    }
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return { llamadas }
}

beforeEach(() => {
  localStorage.clear()
  _resetCacheDeMedios()
})

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {}

async function abrirDialogo(user: ReturnType<typeof userEvent.setup>) {
  render(<DevolucionDeVenta detalle={DETALLE} recargar={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
}

describe('La devolución de una venta', () => {
  it('bajo `lg` el botón y los del diálogo miden 44 px de alto (como el resto del detalle, libra-ui ADR-022)', async () => {
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={vi.fn()} />)
    // Antes de abrir: con el diálogo abierto Radix lo saca del árbol accesible.
    const boton = screen.getByRole('button', { name: /Devolver productos/ })
    expect(boton.className).toContain('max-lg:h-11')
    await user.click(boton)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByRole('button', { name: 'Cancelar' }).className).toContain('max-lg:h-11')
    // Los dos selectores y la X de cierre (el componente `Dialog` del producto, que usan todos sus diálogos) también: medían 36 y 16 px.
    // Son `SelectBuscable`: el campo de texto fija su alto con `h-9` y el componente no admite clase propia en el input, así que el 44 va en
    // el contenedor, sobre el input de adentro (`max-lg:[&_input]:h-11`). Un `max-lg:h-11` en el contenedor no alcanzaba al campo.
    for (const etiqueta of ['Depósito', 'Devolver por']) {
      const clase = within(dialogo).getByLabelText(etiqueta).parentElement!.className
      expect(clase).toContain('max-lg:[&_input]:h-11')
    }
    // Las cantidades a devolver, también 44 (medían 32).
    for (const campo of within(dialogo).getAllByPlaceholderText(/máx\./)) expect(campo.className).toContain('max-lg:h-11')
    expect(within(dialogo).getByRole('button', { name: 'Close' }).className).toContain('max-lg:size-11')
  })

  it('manda sale_item_id, cantidad, deposito_id y medio_pago, y recarga', async () => {
    const { llamadas } = montarRed()
    const recargar = vi.fn()
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={recargar} />)

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    const cantidad = await screen.findByPlaceholderText(/máx\. 5/)
    await user.type(cantidad, '2')

    await user.click(await screen.findByRole('button', { name: /Confirmar devolución/ }))

    const devolucion = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.url.includes('/api/ventas/42/devolver'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(devolucion.body).toMatchObject({
      lineas: [{ sale_item_id: 501, cantidad: 2 }],
      deposito_id: 11,
      medio_pago: 'efectivo',
    })
    // Nada de `index`: la forma vieja del payload (`POST /sales/{id}/returns`,
    // retirado) indexaba por posición de línea.
    expect(devolucion.body).not.toHaveProperty('lineas.0.index')
    await waitFor(() => expect(recargar).toHaveBeenCalled())
  })

  it('propone el depósito de la venta original', async () => {
    montarRed({ depositoId: 13 })
    const user = userEvent.setup()
    await abrirDialogo(user)

    // El combobox de depósito (no el de "Devolver por") tiene que mostrar
    // "Bodega Centro" como valor ya elegido -- no hace falta abrirlo.
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Depósito' })).toHaveValue('Bodega Centro')
    })
  })

  it('sin turno ofrece todos los depósitos activos, y sin depósito de la venta propone el de venta de la sucursal predeterminada', async () => {
    montarRed({ depositoId: null })
    const user = userEvent.setup()
    await abrirDialogo(user)

    const combo = await screen.findByRole('combobox', { name: 'Depósito' })
    await waitFor(() => expect(combo).toHaveValue('Salón Centro'))
    expect(await opcionesDe(user, combo)).toEqual(['Salón Centro', 'Bodega Centro', 'Salón Norte'])
  })

  it('con turno en una sucursal ofrece sólo los depósitos activos de ésa, y manda el elegido', async () => {
    // El turno es de la sucursal 7. La venta original salió del depósito 11 (otra sucursal): no es opción, así que
    // se propone el depósito de venta de la 7 (el 12), que es el que el backend acepta.
    const { llamadas } = montarRed({ turnoEnSucursal: 7, depositoId: 11 })
    const user = userEvent.setup()
    await abrirDialogo(user)

    const combo = await screen.findByRole('combobox', { name: 'Depósito' })
    await waitFor(() => expect(combo).toHaveValue('Salón Norte'))
    // Ni los depósitos de la sucursal 1 ni el dado de baja de la 7.
    expect(await opcionesDe(user, combo)).toEqual(['Salón Norte'])

    await user.type(await screen.findByPlaceholderText(/máx\. 5/), '1')
    await user.click(await screen.findByRole('button', { name: /Confirmar devolución/ }))
    const devolucion = await waitFor(() => {
      const encontrada = llamadas.find((l) => l.url.includes('/api/ventas/42/devolver'))
      expect(encontrada).toBeDefined()
      return encontrada!
    })
    expect(devolucion.body).toMatchObject({ deposito_id: 12 })
  })

  it('con turno, el depósito de la venta original se propone si es de la sucursal del turno', async () => {
    montarRed({ turnoEnSucursal: 1, depositoId: 13 })
    const user = userEvent.setup()
    await abrirDialogo(user)

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Depósito' })).toHaveValue('Bodega Centro')
    })
  })

  it('topea la cantidad a lo que todavía no se devolvió', async () => {
    montarRed({ yaDevuelto: 4 })
    const user = userEvent.setup()
    await abrirDialogo(user)

    // Vendido 5, ya devuelto 4: queda 1 disponible.
    await screen.findByPlaceholderText(/máx\. 1/)
  })

  // ── ADR-041: la `clave_operacion` distingue un reintento de una segunda devolución ──

  const devoluciones = (llamadas: Llamada[]) => llamadas.filter((l) => l.metodo === 'POST' && l.url.includes('/api/ventas/42/devolver'))
  const claveDe = (l: Llamada) => (l.body as { clave_operacion?: string }).clave_operacion

  async function devolverCon(user: ReturnType<typeof userEvent.setup>, cantidad: string) {
    const campo = await screen.findByPlaceholderText(/máx\. 5/)
    await user.clear(campo)
    await user.type(campo, cantidad)
    await user.click(await screen.findByRole('button', { name: /Confirmar devolución/ }))
  }

  it('manda una clave_operacion (un UUID) en el body', async () => {
    const { llamadas } = montarRed()
    const user = userEvent.setup()
    await abrirDialogo(user)
    await devolverCon(user, '2')

    await waitFor(() => expect(devoluciones(llamadas)).toHaveLength(1))
    expect(claveDe(devoluciones(llamadas)[0])).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
  })

  it.each<Respuesta>(['red', '5xx'])('tras un error (%s) el reintento con los mismos datos reusa la misma clave', async (falla) => {
    const { llamadas } = montarRed({ respuestas: [falla, 'ok'] })
    const recargar = vi.fn()
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={recargar} />)
    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    await devolverCon(user, '2')

    await screen.findByRole('alert')                       // el error a la vista, el diálogo sigue abierto
    expect(recargar).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /Confirmar devolución/ }))

    await waitFor(() => expect(devoluciones(llamadas)).toHaveLength(2))
    const [primera, segunda] = devoluciones(llamadas)
    expect(claveDe(primera)).toBeTruthy()
    expect(claveDe(segunda)).toBe(claveDe(primera))
    expect(segunda.body).toEqual(primera.body)             // exactamente lo mismo
    await waitFor(() => expect(recargar).toHaveBeenCalled())
  })

  it('si cambian las cantidades es otro pedido: otra clave', async () => {
    const { llamadas } = montarRed({ respuestas: ['red', 'ok'] })
    const user = userEvent.setup()
    await abrirDialogo(user)
    await devolverCon(user, '2')
    await screen.findByRole('alert')

    await devolverCon(user, '3')                           // cambia la cantidad y vuelve a confirmar
    await waitFor(() => expect(devoluciones(llamadas)).toHaveLength(2))
    const [primera, segunda] = devoluciones(llamadas)
    expect(claveDe(segunda)).toBeTruthy()
    expect(claveDe(segunda)).not.toBe(claveDe(primera))
    expect(segunda.body).toMatchObject({ lineas: [{ sale_item_id: 501, cantidad: 3 }] })
  })

  it('al cerrar el diálogo se descarta la clave: la próxima devolución es otro intento', async () => {
    const { llamadas } = montarRed({ respuestas: ['red', 'ok'] })
    const user = userEvent.setup()
    await abrirDialogo(user)
    await devolverCon(user, '2')
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    await devolverCon(user, '2')                           // mismos datos, pero otro diálogo
    await waitFor(() => expect(devoluciones(llamadas)).toHaveLength(2))
    const [primera, segunda] = devoluciones(llamadas)
    expect(claveDe(segunda)).not.toBe(claveDe(primera))
  })

  it('al terminar bien se descarta la clave: otra devolución de lo mismo lleva otra', async () => {
    const { llamadas } = montarRed({ respuestas: ['ok'] })
    const user = userEvent.setup()
    await abrirDialogo(user)
    await devolverCon(user, '1')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    await devolverCon(user, '1')
    await waitFor(() => expect(devoluciones(llamadas)).toHaveLength(2))
    const [primera, segunda] = devoluciones(llamadas)
    expect(claveDe(segunda)).not.toBe(claveDe(primera))
  })

  it('una respuesta `repetida: true` es el mismo resultado: cierra y recarga, sin aviso de error', async () => {
    montarRed({ respuestas: ['repetida'] })
    const recargar = vi.fn()
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={recargar} />)
    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    await devolverCon(user, '2')

    await waitFor(() => expect(recargar).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('un 409 (clave usada con otros datos) se muestra como error y el diálogo sigue abierto', async () => {
    montarRed({ respuestas: ['409'] })
    const recargar = vi.fn()
    const user = userEvent.setup()
    render(<DevolucionDeVenta detalle={DETALLE} recargar={recargar} />)
    await user.click(screen.getByRole('button', { name: /Devolver productos/ }))
    await devolverCon(user, '2')

    expect((await screen.findByRole('alert')).textContent).toContain('clave_operacion')
    expect(recargar).not.toHaveBeenCalled()
  })
})
