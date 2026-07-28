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

export type ItemCodeType = 'internal' | 'barcode' | 'sku' | 'other'

export const ITEM_CODE_TYPE_LABELS: Record<ItemCodeType, string> = {
  internal: 'Interno',
  barcode: 'Código de barras',
  sku: 'SKU',
  other: 'Otro',
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
