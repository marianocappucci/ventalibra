// Cliente HTTP delgado sobre la API de VentaLibra. Cookie de sesion
// (vl_session) manejada por el browser via `credentials: "include"` --
// en dev el proxy de Vite (vite.config.ts) mantiene todo en el mismo
// origen (localhost:5173) para que la cookie funcione sin CORS; en
// produccion el build de este frontend se sirve desde el mismo proceso
// FastAPI (ver app/asgi.py), tambien mismo origen.
//
// Los campos monetarios/decimales (Decimal en el backend) llegan como
// STRING en el JSON, no number -- Pydantic serializa Decimal asi. Los
// tipos de aca lo reflejan tal cual; convertir con Number(...) recien
// al momento de mostrar/calcular en la UI.
//
// El cliente base (ApiError/request/api) y el tipo User viven en
// libra-ui/api-client desde el 2026-07-26 (era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).

export { api, ApiError, type User } from 'libra-ui/api-client'

import type { OpcionSelect } from 'libra-ui/SelectBuscable'

export type Category = {
  id: number
  name: string
  parent_id: number | null
  active: boolean
}

export type Unit = {
  code: string
  name: string
  allows_fraction: boolean
  decimal_scale: number
}

export type CatalogItem = {
  id: number
  item_type: 'product' | 'service'
  name: string
  description: string
  category_id: number | null
  unit_code: string
  active: boolean
  sellable: boolean
  purchasable: boolean
  default_sale_price: string
  default_cost: string
}

/** Un escaneo ya resuelto. Es más que el producto porque la etiqueta de una
 *  balanza trae adentro cuánto se pesó. */
export type ScanResult = {
  item: CatalogItem
  /** 1 para un código común; el peso, si la etiqueta lo traía. */
  quantity: string
  /** Solo si la balanza imprimió el importe ya calculado. */
  unit_price: string | null
  from_scale: boolean
}

export type ItemCodeType = 'internal' | 'barcode' | 'sku' | 'scale' | 'other'

export const ITEM_CODE_TYPE_LABELS: Record<ItemCodeType, string> = {
  internal: 'Interno',
  barcode: 'Código de barras',
  sku: 'SKU',
  scale: 'Balanza',
  other: 'Otro',
}

export type MovimientoCuenta = {
  fecha: string
  tipo: 'debito' | 'credito'
  concepto: string
  monto: string
  medio: string
  referencia: string
  /** Sólo los abonos lo tienen: un cargo no es plata que entró, así que no
   *  hay recibo que emitirle. */
  cc_pago_id: number | null
}

export type CuentaCorriente = {
  party_id: number
  /** Positivo: el cliente debe. Negativo: pagó de más y tiene a favor. */
  saldo: string
  movimientos: MovimientoCuenta[]
  /** Sólo viene en la respuesta de un cobro recién hecho, para abrir el
   *  recibo sin que haya que pedirlo. `null` si la emisión falló: el cobro es
   *  válido igual y el botón de la fila lo reintenta. */
  recibo_id: number | null
}

export type Deudor = {
  party_id: number
  nombre: string
  saldo: string
}

/** Cómo imprime el ticket este comercio. */
export type TicketConfig = {
  /** '58' u '80': los dos anchos de rollo del mercado. */
  ancho_mm: string
  fuente_size: number
  mostrar_logo: boolean
  linea_corte: boolean
  pie: string
}

/** Las credenciales del QR de la caja. Sólo las lee la pantalla de
 *  configuración, que es admin-only. */
export type MercadoPagoConfig = {
  access_token: string
  /** El collector id de la cuenta — el `id` de `GET /users/me` de MercadoPago. */
  user_id: string
  /** El **external_id** de la caja creada en MercadoPago, no su nombre. */
  pos_id: string
  /** Si al acreditarse el pago se emite la factura sola. */
  auto_facturar: boolean
  /** Lo calcula el backend con el mismo criterio que usa el POS. Sólo lectura. */
  configurado?: boolean
}

/** Lo que el POS necesita saber del QR sin ver ninguna credencial. */
export type MpDisponible = {
  disponible: boolean
  auto_facturar: boolean
}

/** `approved`, `pending`, `rejected`, `cancelled`, `in_process` -- el estado
 *  crudo de MercadoPago. `payment_id`/`factura_id` sólo vienen cuando hay algo
 *  que informar (el motor omite la clave, no manda `null` a secas). */
export type MpEstado = {
  status: string
  payment_id?: string | null
  factura_id?: number | null
}

export type ScaleValueKind = 'weight' | 'amount'

/** Cómo leer las etiquetas de la balanza de este comercio. `null` = sin balanza. */
export type ScaleFormat = {
  prefix: string
  code_digits: number
  value_digits: number
  value_kind: ScaleValueKind
  divisor: number
  total_digits: number
}

export type ItemCode = {
  id: number
  item_id: number
  code_type: ItemCodeType
  code: string
  is_primary: boolean
}

export type ItemVariant = {
  id: number
  item_id: number
  sku: string
  name: string
  attributes: Record<string, string>
  active: boolean
}

export type PriceList = {
  id: number
  name: string
  description: string
  active: boolean
  is_default: boolean
}

export type Location = {
  id: number
  name: string
  branch_id: number | null
  location_type: string
  active: boolean
  /** El depósito del que descuenta una venta que no declara `deposito_id`
   *  (F4, ADR-025) -- en este producto un "location" ES un depósito del
   *  motor, mismo `id` (ver `app/services/locations.py`). */
  is_default: boolean
}

export type ShiftCaja = { id: number; nombre: string; punto_venta: number | null }
export type ShiftSucursal = { id: number; nombre: string }

export type Shift = {
  id: number
  usuario_id: number
  usuario_nombre: string
  apertura: string
  cierre: string | null
  monto_inicial: number
  monto_declarado_cierre: number | null
  monto_esperado_cierre: number | null
  estado: 'abierto' | 'cerrado'
  notas: string
  caja_id: number | null
  /** `null` en un turno viejo, de antes de la feature de cajas por sucursal
   *  (2026-09-16), o sin caja asignada. */
  caja: ShiftCaja | null
  sucursal: ShiftSucursal | null
}

// ── Cajas por sucursal (2026-09-16) ───────────────────────────────────────

export type Caja = {
  id: number
  nombre: string
  descripcion: string
  medios_pago: string[]
  punto_venta: number | null
  activo: boolean
  es_default: boolean
  sucursal_id: number | null
  /** Si ya hay un turno abierto en esta caja (de cualquier usuario) -- el POS
   *  la excluye del selector al abrir turno. */
  tiene_turno_abierto: boolean
}

export type CajaEntrada = {
  nombre: string
  descripcion?: string
  medios_pago: string[]
  punto_venta?: number | null
}

export type CajaAlta = CajaEntrada & { sucursal_id: number }
export type CajaEdicion = CajaEntrada & { activo: boolean }

// ── Cierre diario (2026-09-16) ─────────────────────────────────────────────

export type CierreDiarioMedio = { medio_pago: string; ingresos: number; egresos: number; neto: number }

export type CierreDiarioTurnoPreview = {
  id: number
  usuario_id: number
  usuario_nombre: string
  caja_id: number | null
  caja_nombre: string | null
  apertura: string
  cierre: string | null
  estado: 'abierto' | 'cerrado'
  monto_inicial: number
  monto_esperado_cierre: number | null
  monto_declarado_cierre: number | null
  diferencia: number
  medios: CierreDiarioMedio[]
}

export type CierreDiarioPreview = {
  fecha: string
  sucursal_id: number | null
  turnos_abiertos: CierreDiarioTurnoPreview[]
  turnos: CierreDiarioTurnoPreview[]
  medios: CierreDiarioMedio[]
  monto_esperado_total: number
  monto_declarado_total: number
  diferencia_total: number
  puede_cerrar: boolean
  ya_cerrado: boolean
}

export type CierreDiario = {
  id: number
  sucursal_id: number | null
  numero: number
  fecha: string
  usuario_id: number
  cerrado_por_nombre: string
  monto_esperado_total: number
  monto_declarado_total: number
  diferencia_total: number
  notas: string
  created_at: string
}

// Arqueo del turno: se calcula sobre los movimientos de caja, no sobre las
// ventas (ver wiki/entities/ventalibra.md).
export type ShiftSummary = {
  movimientos: {
    id: number
    fecha: string
    tipo: string
    concepto: string
    monto: number
    medio_pago: string
    referencia: string
  }[]
  pagos_por_medio: Record<string, number>
  total_ventas: number
  // Lo unico que se cuenta a mano al cerrar: lo demas queda en el resumen de
  // la terminal o del banco.
  efectivo_ventas: number
}

export type ShiftState = { turno: Shift | null; resumen?: ShiftSummary }

// ── La venta (F4, ADR-025): la capa ERP de LibraCommerce ──────────────────
//
// `Venta`/`VentaItem`/`VentaPago` son los tipos del kit (`libra-ui/comercio/
// tipos`), el contrato de `libracommerce.web.ventas_router` +
// `libracore.ventas_cobro_router` (montados como `/api/ventas` en
// `app/main.py`). Re-exportados acá para que las pantallas de este producto
// los importen desde `../api` como todo lo demás, sin acordarse de cuál
// paquete los declara.
//
// 🔴 A diferencia del `Sale` viejo (con montos `string`, por el `Decimal` de
// Pydantic), acá los montos son `number`: ni `crear()` ni `obtener_venta()`
// pasan por un `response_model` -- son dicts de Python con floats, que FastAPI
// serializa como número JSON directo.
export type { Venta, VentaItem, VentaPago } from 'libra-ui/comercio/tipos'
import type { VentaPago as _VentaPago } from 'libra-ui/comercio/tipos'

/** Un pago con el vuelto ya calculable (D4, ADR-025): `recibido` no está en
 *  el tipo compartido del kit -- ni Contalibra ni Restolibra lo mandan -- pero
 *  `ventas_pagos.recibido` sí viaja en el JSON de este producto (columna de
 *  LibraCore, ver `libracommerce.erp.ventas.agregar_pago`). El vuelto es
 *  `recibido - monto`, a cargo de quien lea (no lo precalcula la API). */
export type VentaPagoConRecibido = _VentaPago & {
  /** `null` en cualquier medio que no sea efectivo, o si no se mandó. */
  recibido: number | null
}

/** El body de `POST /api/ventas` (`libracommerce.web.ventas_router.
 *  VentaPayload`). Los montos van en `number`, no `string`: el backend valida
 *  con Pydantic (`float`), a diferencia de las lecturas (`Decimal`-como-string
 *  del modelo viejo). */
export type VentaItemPayload = {
  nombre: string
  qty: number
  precio: number
  producto_id: number | null
  variante_id?: number | null
}

export type VentaPagoPayload = {
  medio: string
  monto: number
  referencia?: string
  /** `true`: "le voy a cobrar", nace pendiente y lo acredita el poll del QR.
   *  Sólo aplica al medio `mercadopago` (el motor lo valida). */
  cobrar_con_qr?: boolean
  /** Cuánto entregó el cliente (D4). Sólo tiene sentido en efectivo. */
  recibido?: number
}

export type VentaPayload = {
  fecha: string
  items: VentaItemPayload[]
  cliente_id?: number | null
  observaciones?: string
  pagos: VentaPagoPayload[]
  /** El depósito de la sucursal elegida en el POS (F4, VentaLibra
   *  multisucursal). Sin mandarlo, el motor descuenta del default de siempre. */
  deposito_id?: number | null
}

/** El body de `POST /api/ventas/{vid}/devolver`
 *  (`libracommerce.web.ventas_router.DevolucionPayload`). Indexa por
 *  `sale_item_id` -- el id de `sale_items`, no la posición de la línea, que
 *  es como indexaba el modelo viejo (`DevolucionLinea`, retirado). */
export type DevolucionLineaPayload = {
  sale_item_id: number
  cantidad: number
}

export type DevolucionPayload = {
  lineas: DevolucionLineaPayload[]
  deposito_id: number
  medio_pago?: string
}

/** Cuánto se devolvió ya de una venta, por (producto, variante) -- lo que
 *  `GET /api/ventas/{id}` no trae (`app/routers/ventas_extra.py`). Sirve para
 *  topear la cantidad a devolver y proponer el depósito por default. */
export type VentaDevueltoPorClave = {
  producto_id: number
  variante_id: number | null
  cantidad: number
}

export type VentaDevuelto = {
  por_clave: VentaDevueltoPorClave[]
  deposito_id: number | null
}

export type CurrentStock = {
  item_id: number
  location_id: number
  variant_id: number | null
  quantity: string
}

export type Party = {
  id: number
  party_type: 'person' | 'organization'
  display_name: string
  email: string | null
  phone: string | null
  active: boolean
}

export type Supplier = Party & {
  legal_name: string | null
  tax_id: string | null
}

export type Customer = Party & {
  cuit: string | null
  condicion_iva: string | null
}

export type ArcaConfig = {
  empresa: string
  cuit: string
  punto_venta: number
  ambiente: string
  certificado_path: string
  clave_path: string
}

export type PurchaseOrderStatus = 'draft' | 'sent' | 'partial' | 'received' | 'cancelled'

export type PurchaseOrderItem = {
  item_id: number
  quantity_ordered: string
  quantity_received: string
  pending_quantity: string
  unit_cost: string
  tax_rate: string
  subtotal: string
}

export type PurchaseOrder = {
  id: number
  number: string
  supplier_party_id: number
  status: PurchaseOrderStatus
  items: PurchaseOrderItem[]
  is_fully_received: boolean
}

export type PurchaseReceiptStatus = 'draft' | 'confirmed'

export type PurchaseReceiptItem = {
  item_id: number
  quantity: string
  unit_cost: string
  lot_code: string | null
  expires_at: string | null
}

export type PurchaseReceipt = {
  id: number
  supplier_party_id: number
  purchase_order_id: number | null
  status: PurchaseReceiptStatus
  items: PurchaseReceiptItem[]
  received_at: string | null
  document_reference: string | null
}

export type SalesReport = {
  date_from: string
  date_to: string
  total_ventas: number
  total_facturado: string
  por_dia: { day: string; cantidad: number; total: string }[]
  top_items: { item_id: number; descripcion: string; cantidad: string; total: string }[]
}

export type CajaReport = {
  date_from: string
  date_to: string
  ingresos: string
  egresos: string
  saldo_periodo: string
  saldo_total: string
}

export type StockReportItem = {
  item_id: number
  name: string
  unit_code: string
  stock: string
}

export type StockReport = {
  items: StockReportItem[]
  low_stock: StockReportItem[]
}

// --- opciones para los selects con busqueda (libra-ui/SelectBuscable) ------
//
// Viven aca, junto a los tipos, para que las pantallas que eligen un
// proveedor o un producto lo muestren y lo busquen igual. El `hint` no es
// decorativo: ademas de desambiguar dos nombres parecidos, **entra en la
// busqueda**.
//
// Es el producto de la familia donde mas hace falta: una despensa real tiene
// cientos de items en el catalogo, y elegirlos a ojo en una lista ordenada
// era el caso que motivo el componente.

export function opcionesProveedor(proveedores: Supplier[]): OpcionSelect[] {
  return proveedores.map((s) => ({
    value: String(s.id),
    label: s.display_name,
    // El CUIT es lo que figura en la factura del proveedor, que es el papel
    // que se tiene a mano al cargar una compra.
    hint: [s.tax_id, s.active ? null : 'inactivo'].filter(Boolean).join(' · ') || undefined,
  }))
}

export function opcionesItem(items: CatalogItem[]): OpcionSelect[] {
  return items.map((i) => ({
    value: String(i.id),
    label: i.name,
    hint: [i.unit_code, i.active ? null : 'inactivo'].filter(Boolean).join(' · ') || undefined,
  }))
}

export function opcionesOrdenCompra(ordenes: PurchaseOrder[]): OpcionSelect[] {
  return ordenes.map((o) => ({
    value: String(o.id),
    label: o.number,
    hint: PURCHASE_ORDER_STATUS_HINT[o.status],
  }))
}

const PURCHASE_ORDER_STATUS_HINT: Record<PurchaseOrderStatus, string> = {
  draft: 'borrador',
  sent: 'enviada',
  partial: 'recibida parcial',
  received: 'recibida',
  cancelled: 'cancelada',
}

export function opcionesCategoria(categorias: Category[]): OpcionSelect[] {
  return categorias.map((c) => ({
    value: String(c.id),
    label: c.name,
    hint: c.active ? undefined : 'inactiva',
  }))
}
