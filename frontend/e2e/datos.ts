import { randomUUID } from 'node:crypto'
import { expect, type APIRequestContext, type APIResponse } from '@playwright/test'

// Lo que cada spec necesita sembrar, por la API: los mismos endpoints que usa la pantalla. **Cada spec arma lo suyo con
// nombres únicos** (`unico`): no depende del orden, ni de lo que dejó otro, ni de la semilla de la demo (que además deja
// el turno cerrado).

/** Un nombre que no se repite entre corridas ni entre specs: la instancia de prueba (o dev, de noche) acumula datos. */
export function unico(base: string): string {
  return `${base} ${randomUUID().slice(0, 8)}`
}

/** Un monto como lo muestra la SPA (`es-AR`): `$12.000,00`. */
export function pesos(monto: number): string {
  return '$' + monto.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export async function json<T = Record<string, unknown>>(respuesta: APIResponse, contexto: string): Promise<T> {
  const cuerpo = await respuesta.text()
  expect(respuesta.ok(), `${contexto} -> ${respuesta.status()}: ${cuerpo.slice(0, 300)}`).toBe(true)
  return (cuerpo ? JSON.parse(cuerpo) : null) as T
}

export type Producto = { id: number; nombre: string; precio: number; unidad: string }

// Las lecturas que un spec repite DESPUÉS de varios segundos de navegador llevan `maxRetries`: Playwright reintenta sólo ECONNRESET («socket hang up»),
// que apareció una vez, suelto, en una repetición. Un GET se puede repetir sin efecto; las escrituras no llevan reintento.
export async function depositoPredeterminado(api: APIRequestContext): Promise<number> {
  const depositos = await json<Array<{ id: number; es_default?: boolean }>>(await api.get('/api/depositos', { maxRetries: 3 }), 'GET /api/depositos')
  const deposito = depositos.find((d) => d.es_default)
  expect(deposito, 'la instancia no tiene un depósito predeterminado').toBeTruthy()
  return deposito!.id
}

/** Un producto por unidad (o por la que se pida) con stock en el depósito predeterminado, que es del que descuenta el POS. */
export async function crearProducto(
  api: APIRequestContext,
  { nombre = unico('Producto e2e'), precio, stock = 100, unidad = 'UN', stockMinimo = 0 }: {
    nombre?: string; precio: number; stock?: number; unidad?: string; stockMinimo?: number
  },
): Promise<Producto> {
  const creado = await json<{ id: number }>(
    await api.post('/api/productos', {
      data: { nombre, unidad, precio_venta: precio, precio_costo: Math.round(precio / 2), stock_minimo: stockMinimo },
    }),
    'POST /api/productos',
  )
  if (stock > 0) {
    await json(
      await api.post(`/api/stock/${creado.id}/ajuste`, {
        data: { modo: 'entrada', cantidad: stock, deposito_id: await depositoPredeterminado(api), referencia: 'e2e' },
      }),
      'POST /api/stock/{id}/ajuste',
    )
  }
  return { id: creado.id, nombre, precio, unidad }
}

/** Le saca el stock mínimo a un producto. Un spec que deja productos por debajo de su mínimo los deja en el reporte de stock bajo de `/reportes`,
 *  y esa tabla se ensancha con cada nombre largo: a 390 px el spec de desbordes de otra corrida (o de otro spec) se pondría rojo. */
export async function quitarMinimo(api: APIRequestContext, producto: Producto): Promise<void> {
  await json(
    await api.put(`/api/productos/${producto.id}`, { data: { nombre: producto.nombre, unidad: producto.unidad, precio_venta: producto.precio, stock_minimo: 0 } }),
    'PUT /api/productos/{id}',
  )
}

export async function cambiarPrecio(api: APIRequestContext, producto: Producto, precio: number): Promise<Producto> {
  await json(await api.put(`/api/productos/${producto.id}`, { data: { nombre: producto.nombre, unidad: producto.unidad, precio_venta: precio } }), 'PUT /api/productos/{id}')
  return { ...producto, precio }
}

/** El stock que hay en el depósito predeterminado. */
export async function stockDe(api: APIRequestContext, producto: { id: number }): Promise<number> {
  const deposito = await depositoPredeterminado(api)
  const datos = await json<{ stock_deposito: number }>(
    await api.get(`/api/stock/${producto.id}`, { params: { deposito_id: deposito }, maxRetries: 3 }), 'GET /api/stock/{id}',
  )
  return Number(datos.stock_deposito)
}

// ── Lotes y vencimientos ────────────────────────────────────────────────────

/** La fecha ISO (`AAAA-MM-DD`) de hoy más `dias` (negativos: ya pasó), en Buenos Aires, que es la fecha con la que el motor decide qué está vencido. */
export function enDias(dias: number): string {
  const fecha = new Date(Date.now() + dias * 86_400_000)
  return fecha.toLocaleDateString('en-CA', { timeZone: 'America/Argentina/Buenos_Aires' })
}

/** Un producto de los que vencen (lo marca el admin) con un lote por cada `{ lote, vence, cantidad }`, en el depósito predeterminado.
 *  El stock del producto es la suma de los lotes: entran por `POST /api/vencimientos/entrada`, la misma carga con lote de la pantalla. */
export async function crearPerecedero(
  admin: APIRequestContext,
  { lotes, precio = 1_000, stockMinimo = 0 }: { lotes: Array<{ lote: string; vence: string; cantidad: number }>; precio?: number; stockMinimo?: number },
): Promise<Producto> {
  const producto = await crearProducto(admin, { nombre: unico('Yogur e2e'), precio, stock: 0, stockMinimo })
  await json(await admin.put(`/api/vencimientos/productos/${producto.id}`, { data: { vence: true } }), 'PUT /api/vencimientos/productos/{id}')
  const deposito = await depositoPredeterminado(admin)
  for (const { lote, vence, cantidad } of lotes) {
    await json(
      await admin.post('/api/vencimientos/entrada', {
        data: { producto_id: producto.id, deposito_id: deposito, lote, vence, cantidad, clave_operacion: randomUUID() },
      }),
      'POST /api/vencimientos/entrada',
    )
  }
  return producto
}

/** El saldo de cada lote de un producto en el depósito predeterminado, por código de lote (los lotes con saldo 0 no vienen). */
export async function saldosPorLote(api: APIRequestContext, producto: { id: number }): Promise<Record<string, number>> {
  const deposito = await depositoPredeterminado(api)
  const datos = await json<{ lotes: Array<{ lote: string | null; saldo: number }> }>(
    await api.get(`/api/vencimientos/productos/${producto.id}/lotes`, { params: { deposito_id: deposito }, maxRetries: 3 }),
    'GET /api/vencimientos/productos/{id}/lotes',
  )
  return Object.fromEntries(datos.lotes.map((l) => [l.lote ?? '', Number(l.saldo)]))
}

// ── La balanza ──────────────────────────────────────────────────────────────

/** La balanza configurada como en los tests del backend (`tests/test_validar_precio_de_venta.py`): etiqueta EAN-13 de 13
 *  dígitos, prefijo 20, 5 de producto y 5 de valor, que es el PESO en gramos (divisor 1000). Es global a la instancia, pero
 *  todos los specs la quieren igual. */
export async function asegurarBalanza(admin: APIRequestContext): Promise<void> {
  await json(
    await admin.put('/settings/scale', {
      data: { prefix: '20', code_digits: 5, value_digits: 5, value_kind: 'weight', divisor: 1000, total_digits: 13 },
    }),
    'PUT /settings/scale',
  )
}

/** Un producto por kilo con su código de balanza (PLU). El PLU va sin ceros a la izquierda: el parser de la etiqueta
 *  los descarta y el código del producto se busca sin ellos. */
export async function crearPesable(
  admin: APIRequestContext,
  { precioKg, stockKg = 20 }: { precioKg: number; stockKg?: number },
): Promise<Producto & { plu: string }> {
  // La unidad KG la crea la semilla; si falta (instancia vacía) se crea, y si ya está el alta repetida es 409.
  const unidad = await admin.post('/catalog/units', { data: { code: 'KG', name: 'Kilogramo', allows_fraction: true, decimal_scale: 3 } })
  expect([200, 201, 409], `POST /catalog/units -> ${unidad.status()}`).toContain(unidad.status())
  const producto = await crearProducto(admin, { nombre: unico('Queso e2e'), precio: precioKg, stock: stockKg, unidad: 'KG' })
  // Un PLU de 5 dígitos al azar; si ya lo tiene otro producto de una corrida anterior, se prueba con otro.
  for (let intento = 0; intento < 10; intento++) {
    const plu = String(10_000 + Math.floor(Math.random() * 89_999))
    const alta = await admin.post(`/api/productos/${producto.id}/codigos`, { data: { tipo: 'scale', codigo: plu } })
    if (alta.ok()) return { ...producto, plu }
  }
  throw new Error('no se pudo asignar un código de balanza libre')
}

/** La etiqueta EAN-13 de la balanza para `kilos` de un producto: `20` + PLU (5) + gramos (5) + dígito verificador. */
export function etiquetaDeBalanza(plu: string, kilos: number): string {
  const cuerpo = '20' + plu.padStart(5, '0') + String(Math.round(kilos * 1000)).padStart(5, '0')
  const suma = [...cuerpo].reduce((acc, d, i) => acc + Number(d) * (i % 2 === 0 ? 1 : 3), 0)
  return cuerpo + String((10 - (suma % 10)) % 10)
}

// ── La caja y el turno ──────────────────────────────────────────────────────

type Turno = { id: number; estado: string }
type ListaDeTurnos = { turnos: Turno[] }

/** Cierra todo turno abierto de la instancia, de quien sea. La sucursal de la instancia de prueba tiene UNA caja y un turno
 *  es por usuario y por caja: un turno que dejó abierto un spec anterior (o la semilla, o una corrida cortada) le
 *  impediría abrir el suyo a quien sigue. Lo hace el admin, que puede cerrar los de todos. */
export async function liberarCaja(admin: APIRequestContext): Promise<void> {
  const { turnos } = await json<ListaDeTurnos>(await admin.get('/api/turnos'), 'GET /api/turnos')
  for (const turno of turnos.filter((t) => t.estado === 'abierto')) {
    await json(await admin.post(`/api/turnos/${turno.id}/cerrar`, { data: { monto_declarado: 0, notas: 'e2e: la caja se libera' } }), 'cerrar turno ajeno')
  }
}

/** Abre el turno de quien llama (`api`) en la caja predeterminada, dejándola libre antes. Devuelve el id del turno. */
export async function abrirTurno(api: APIRequestContext, admin: APIRequestContext): Promise<number> {
  await liberarCaja(admin)
  // 🔴 La caja predeterminada DE LA SUCURSAL predeterminada: cada sucursal tiene la suya con `es_default`, y la semilla de la
  // demo agrega una sucursal más. Con la de otra, el POS vendería (y descontaría stock) en el depósito de esa otra sucursal.
  const sucursales = await json<Array<{ id: number; es_default?: boolean }>>(await api.get('/api/sucursales'), 'GET /api/sucursales')
  const sucursal = sucursales.find((s) => s.es_default) ?? sucursales[0]
  const cajas = await json<Array<{ id: number; es_default?: boolean }>>(
    await api.get('/api/cajas', { params: { sucursal_id: sucursal.id } }), 'GET /api/cajas',
  )
  const caja = cajas.find((c) => c.es_default) ?? cajas[0]
  const turno = await json<{ id: number }>(
    await api.post('/api/turnos/abrir', { data: { monto_inicial: 0, notas: 'e2e', caja_id: caja.id } }),
    'POST /api/turnos/abrir',
  )
  return turno.id
}

/** Cierra el turno abierto de quien llama, si tiene uno. Para el `finally` de cada spec: la caja queda libre aunque el test falle. */
export async function cerrarTurno(api: APIRequestContext): Promise<void> {
  const actual = await json<{ turno: { id: number } | null }>(await api.get('/api/turnos/actual'), 'GET /api/turnos/actual')
  if (!actual.turno) return
  await api.post(`/api/turnos/${actual.turno.id}/cerrar`, { data: { monto_declarado: 0, notas: 'e2e: cierre' } })
}

// ── Ventas ──────────────────────────────────────────────────────────────────

export type LineaDeVenta = { producto_id: number; qty: number; precio: number }
export type Venta = { id: number; numero: string; total: number; estado: string; turno_id: number; items: LineaDeVenta[] }

/** Una venta de contado y en efectivo por la API (el turno tiene que estar abierto). */
export async function venderPorApi(api: APIRequestContext, producto: Producto, cantidad = 1): Promise<Venta> {
  const total = producto.precio * cantidad
  return json<Venta>(
    await api.post('/api/ventas', {
      data: {
        fecha: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Argentina/Buenos_Aires' }),
        items: [{ nombre: producto.nombre, qty: cantidad, precio: producto.precio, producto_id: producto.id }],
        pagos: [{ medio: 'efectivo', monto: total }],
      },
    }),
    'POST /api/ventas',
  )
}

/** Las ventas que ve quien llama. Con `turnoId`, sólo las de ese turno: la instancia acumula las de corridas anteriores y
 *  «cuántas ventas hizo este spec» se cuenta en SU turno, que es nuevo. */
export async function ventasVisibles(api: APIRequestContext, turnoId?: number): Promise<Venta[]> {
  const datos = await json<Venta[] | { items: Venta[] }>(await api.get('/api/ventas'), 'GET /api/ventas')
  const ventas = Array.isArray(datos) ? datos : datos.items
  return turnoId === undefined ? ventas : ventas.filter((v) => v.turno_id === turnoId)
}

// ── Compras ─────────────────────────────────────────────────────────────────

/** Un proveedor nuevo con una orden de compra de `cantidad` unidades del producto (en borrador, lista para recibir). */
export async function crearOrdenDeCompra(
  admin: APIRequestContext,
  producto: Producto,
  { cantidad, costo }: { cantidad: number; costo: number },
): Promise<{ id: number; numero: string }> {
  const proveedor = await json<{ id: number }>(
    await admin.post('/api/proveedores', { data: { nombre: unico('Proveedor e2e') } }), 'POST /api/proveedores',
  )
  const orden = await json<{ id: number; number: string }>(
    await admin.post('/api/purchase-orders', { data: { proveedor_id: proveedor.id } }), 'POST /api/purchase-orders',
  )
  await json(
    await admin.post(`/api/purchase-orders/${orden.id}/items`, {
      data: { item_id: producto.id, quantity_ordered: cantidad, unit_cost: costo, tax_rate: 0.21 },
    }),
    'POST /api/purchase-orders/{id}/items',
  )
  return { id: orden.id, numero: orden.number }
}

/** Las recepciones registradas contra una orden. */
export async function recepcionesDe(api: APIRequestContext, ordenId: number): Promise<Array<{ id: number; status?: string }>> {
  return json(await api.get('/api/purchase-receipts', { params: { purchase_order_id: ordenId } }), 'GET /api/purchase-receipts')
}
