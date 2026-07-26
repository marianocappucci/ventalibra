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

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await response.json() : undefined

  if (!response.ok) {
    const detail = (data && typeof data === 'object' && 'detail' in data)
      ? String((data as { detail: unknown }).detail)
      : response.statusText
    throw new ApiError(response.status, detail)
  }

  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

export type User = {
  id: string
  username: string
  name: string
  role: 'admin' | 'staff'
  active: boolean
}

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

export type Sale = {
  id: number
  number: string
  status: SaleStatus
  items: SaleItem[]
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
