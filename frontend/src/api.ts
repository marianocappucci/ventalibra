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

/** Encabezado de venta para el listado: sin líneas ni pagos. */
export type SaleListItem = {
  id: number
  number: string
  status: SaleStatus
  total: string
  confirmed_at: string | null
  cliente: string
}

export type DevolucionLinea = {
  /** Posición de la línea en la venta, no un id. */
  index: number
  quantity: string
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

/** `approved`, `pending`, `sin_orden`, o el estado crudo de MercadoPago
 *  (`rejected`, `cancelled`, `in_process`). */
export type MpEstado = {
  status: string
  payment_id: string | null
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
}

export type SaleStatus = 'draft' | 'confirmed' | 'cancelled' | 'partially_returned' | 'returned'

export type SaleItem = {
  kind: 'product' | 'service'
  item_id: number | null
  variant_id: number | null
  description_snapshot: string
  quantity: string
  unit_price: string
  discount_amount: string
  tax_amount: string
  line_total: string
}

export type Factura = {
  id: number
  tipo: number
  punto_venta: number
  numero: number
  cae: string
} | null

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

export type SalePayment = {
  medio: string
  monto: string
  // Solo en efectivo: cuanto entrego el cliente. En los demas medios va null.
  recibido: string | null
  vuelto: string
  referencia: string
}

export type Sale = {
  id: number
  number: string
  status: SaleStatus
  items: SaleItem[]
  pagos: SalePayment[]
  vuelto_total: string
  subtotal: string
  discount_total: string
  tax_total: string
  total: string
  confirmed_at: string | null
  factura: Factura
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
