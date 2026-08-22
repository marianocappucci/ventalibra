import { useEffect, useState } from 'react'
import {
  api, ApiError, opcionesItem, opcionesOrdenCompra, opcionesProveedor,
  type CatalogItem, type Location, type PurchaseOrder, type PurchaseReceipt, type Supplier,
} from '../api'
import { SelectBuscable } from 'libra-ui/SelectBuscable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador', sent: 'Enviada', partial: 'Recibida parcial',
  received: 'Recibida', cancelled: 'Cancelada',
}

const ORDER_STATUS_TONO: Record<string, TonoEstado> = {
  draft: 'neutro', sent: 'curso', partial: 'atencion',
  received: 'ok', cancelled: 'negativo',
}

const RECEIPT_STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador', confirmed: 'Confirmada',
}

const RECEIPT_STATUS_TONO: Record<string, TonoEstado> = {
  draft: 'neutro', confirmed: 'ok',
}

function OrdersPanel({ suppliers, items }: { suppliers: Supplier[]; items: CatalogItem[] }) {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [supplierId, setSupplierId] = useState('')
  const [selected, setSelected] = useState<PurchaseOrder | null>(null)
  const [lineItemId, setLineItemId] = useState('')
  const [lineQuantity, setLineQuantity] = useState('1')
  const [lineCost, setLineCost] = useState('0')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    loadOrders()
  }, [])

  async function loadOrders() {
    try {
      setOrders(await api.get<PurchaseOrder[]>('/purchase-orders'))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function createOrder() {
    if (!supplierId) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.post<PurchaseOrder>('/purchase-orders', { supplier_party_id: Number(supplierId) })
      await loadOrders()
      setSelected(created)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function addItem() {
    if (!selected || !lineItemId) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api.post<PurchaseOrder>(`/purchase-orders/${selected.id}/items`, {
        item_id: Number(lineItemId), quantity_ordered: lineQuantity, unit_cost: lineCost,
      })
      setSelected(updated)
      await loadOrders()
      setLineItemId('')
      setLineQuantity('1')
      setLineCost('0')
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  function itemName(itemId: number): string {
    return items.find((i) => i.id === itemId)?.name ?? `#${itemId}`
  }

  function supplierName(supplierId: number): string {
    return suppliers.find((s) => s.id === supplierId)?.display_name ?? `#${supplierId}`
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Órdenes de compra</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex items-end gap-2">
            <div className="grid gap-1.5 flex-1">
              <Label>Proveedor</Label>
              <SelectBuscable
                value={supplierId}
                onChange={setSupplierId}
                opciones={opcionesProveedor(suppliers)}
                placeholder="Elegí un proveedor…"
                ariaLabel="Proveedor"
              />
            </div>
            <Button onClick={createOrder} disabled={busy || !supplierId}>Nueva orden</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Table>
            <TableHeader>
              <TableRow><TableHead>Número</TableHead><TableHead>Proveedor</TableHead><TableHead>Estado</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {orders.length === 0 && (
                <TableRow><TableCell colSpan={3} className="text-center text-sm text-muted-foreground">Sin órdenes todavía.</TableCell></TableRow>
              )}
              {orders.map((order) => (
                <TableRow key={order.id} className="cursor-pointer hover:bg-accent" onClick={() => setSelected(order)}>
                  <TableCell>{order.number}</TableCell>
                  <TableCell>{supplierName(order.supplier_party_id)}</TableCell>
                  <TableCell><BadgeEstado tono={ORDER_STATUS_TONO[order.status] ?? 'neutro'}>{ORDER_STATUS_LABELS[order.status] ?? order.status}</BadgeEstado></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Orden {selected.number}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Item</TableHead><TableHead>Pedido</TableHead><TableHead>Recibido</TableHead><TableHead>Costo</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {selected.items.length === 0 && (
                  <TableRow><TableCell colSpan={4} className="text-center text-sm text-muted-foreground">Sin líneas todavía.</TableCell></TableRow>
                )}
                {selected.items.map((line, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{itemName(line.item_id)}</TableCell>
                    <TableCell>{line.quantity_ordered}</TableCell>
                    <TableCell>{line.quantity_received}</TableCell>
                    <TableCell>${Number(line.unit_cost).toLocaleString('es-AR')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {/* is_fully_received() da vacuamente true para una orden sin lineas
                (all() sobre una coleccion vacia) -- el gate real de "se pueden
                seguir agregando items" es el status, mismo criterio que
                PurchasingService.add_order_item() valida del lado del backend. */}
            {(selected.status === 'draft' || selected.status === 'sent') && (
              <div className="flex flex-wrap items-end gap-2 border-t pt-3">
                <div className="grid gap-1.5">
                  <Label>Item</Label>
                  <SelectBuscable
                    value={lineItemId}
                    onChange={setLineItemId}
                    opciones={opcionesItem(items)}
                    placeholder="Item…"
                    ariaLabel="Item"
                    className="w-40"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>Cantidad</Label>
                  <Input value={lineQuantity} onChange={(e) => setLineQuantity(e.target.value)} className="w-24" />
                </div>
                <div className="grid gap-1.5">
                  <Label>Costo unitario</Label>
                  <Input value={lineCost} onChange={(e) => setLineCost(e.target.value)} className="w-28" />
                </div>
                <Button onClick={addItem} disabled={busy || !lineItemId}>Agregar línea</Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ReceiptsPanel({
  suppliers, items, locations, orders,
}: { suppliers: Supplier[]; items: CatalogItem[]; locations: Location[]; orders: PurchaseOrder[] }) {
  const [receipts, setReceipts] = useState<PurchaseReceipt[]>([])
  const [supplierId, setSupplierId] = useState('')
  const [orderId, setOrderId] = useState('')
  const [selected, setSelected] = useState<PurchaseReceipt | null>(null)
  const [lineItemId, setLineItemId] = useState('')
  const [lineQuantity, setLineQuantity] = useState('1')
  const [lineCost, setLineCost] = useState('0')
  const [locationId, setLocationId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    loadReceipts()
    if (locations.length > 0) setLocationId(String(locations[0].id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations])

  async function loadReceipts() {
    try {
      setReceipts(await api.get<PurchaseReceipt[]>('/purchase-receipts'))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function createReceipt() {
    if (!supplierId) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.post<PurchaseReceipt>('/purchase-receipts', {
        supplier_party_id: Number(supplierId),
        purchase_order_id: orderId ? Number(orderId) : null,
      })
      await loadReceipts()
      setSelected(created)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function addItem() {
    if (!selected || !lineItemId) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api.post<PurchaseReceipt>(`/purchase-receipts/${selected.id}/items`, {
        item_id: Number(lineItemId), quantity: lineQuantity, unit_cost: lineCost,
      })
      setSelected(updated)
      await loadReceipts()
      setLineItemId('')
      setLineQuantity('1')
      setLineCost('0')
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function confirmReceipt() {
    if (!selected || !locationId) return
    setBusy(true)
    setError(null)
    try {
      const confirmed = await api.post<PurchaseReceipt>(`/purchase-receipts/${selected.id}/confirm`, {
        location_id: Number(locationId),
      })
      setSelected(confirmed)
      await loadReceipts()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  function itemName(itemId: number): string {
    return items.find((i) => i.id === itemId)?.name ?? `#${itemId}`
  }

  function supplierName(supplierId: number): string {
    return suppliers.find((s) => s.id === supplierId)?.display_name ?? `#${supplierId}`
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recepciones</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5 flex-1">
              <Label>Proveedor</Label>
              <SelectBuscable
                value={supplierId}
                onChange={setSupplierId}
                opciones={opcionesProveedor(suppliers)}
                placeholder="Elegí un proveedor…"
                ariaLabel="Proveedor"
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Orden vinculada (opcional)</Label>
              <SelectBuscable
                value={orderId}
                onChange={setOrderId}
                opciones={opcionesOrdenCompra(orders)}
                placeholder="Sin orden"
                ariaLabel="Orden vinculada"
                className="w-40"
              />
            </div>
            <Button onClick={createReceipt} disabled={busy || !supplierId}>Nueva recepción</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Table>
            <TableHeader>
              <TableRow><TableHead>ID</TableHead><TableHead>Proveedor</TableHead><TableHead>Estado</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {receipts.length === 0 && (
                <TableRow><TableCell colSpan={3} className="text-center text-sm text-muted-foreground">Sin recepciones todavía.</TableCell></TableRow>
              )}
              {receipts.map((receipt) => (
                <TableRow key={receipt.id} className="cursor-pointer hover:bg-accent" onClick={() => setSelected(receipt)}>
                  <TableCell>#{receipt.id}</TableCell>
                  <TableCell>{supplierName(receipt.supplier_party_id)}</TableCell>
                  <TableCell><BadgeEstado tono={RECEIPT_STATUS_TONO[receipt.status] ?? 'neutro'}>{RECEIPT_STATUS_LABELS[receipt.status] ?? receipt.status}</BadgeEstado></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recepción #{selected.id}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Item</TableHead><TableHead>Cant.</TableHead><TableHead>Costo</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {selected.items.length === 0 && (
                  <TableRow><TableCell colSpan={3} className="text-center text-sm text-muted-foreground">Sin líneas todavía.</TableCell></TableRow>
                )}
                {selected.items.map((line, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{itemName(line.item_id)}</TableCell>
                    <TableCell>{line.quantity}</TableCell>
                    <TableCell>${Number(line.unit_cost).toLocaleString('es-AR')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {selected.status === 'draft' && (
              <>
                <div className="flex flex-wrap items-end gap-2 border-t pt-3">
                  <div className="grid gap-1.5">
                    <Label>Item</Label>
                    <SelectBuscable
                      value={lineItemId}
                      onChange={setLineItemId}
                      opciones={opcionesItem(items)}
                      placeholder="Item…"
                      ariaLabel="Item"
                      className="w-40"
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label>Cantidad</Label>
                    <Input value={lineQuantity} onChange={(e) => setLineQuantity(e.target.value)} className="w-24" />
                  </div>
                  <div className="grid gap-1.5">
                    <Label>Costo unitario</Label>
                    <Input value={lineCost} onChange={(e) => setLineCost(e.target.value)} className="w-28" />
                  </div>
                  <Button onClick={addItem} disabled={busy || !lineItemId}>Agregar línea</Button>
                </div>
                <div className="flex items-end gap-2 border-t pt-3">
                  <div className="grid gap-1.5">
                    <Label>Depósito de destino</Label>
                    <Select value={locationId} onValueChange={setLocationId}>
                      <SelectTrigger className="w-48"><SelectValue placeholder="Depósito…" /></SelectTrigger>
                      <SelectContent>
                        {locations.map((loc) => <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button onClick={confirmReceipt} disabled={busy || selected.items.length === 0 || !locationId}>
                    Confirmar recepción
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function Compras() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [items, setItems] = useState<CatalogItem[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<Supplier[]>('/suppliers'),
      api.get<CatalogItem[]>('/catalog/items'),
      api.get<Location[]>('/locations'),
      api.get<PurchaseOrder[]>('/purchase-orders'),
    ])
      .then(([s, i, l, o]) => {
        setSuppliers(s)
        setItems(i)
        setLocations(l)
        setOrders(o)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-semibold">Compras</h2>
      <OrdersPanel suppliers={suppliers} items={items} />
      <ReceiptsPanel suppliers={suppliers} items={items} locations={locations} orders={orders} />
    </div>
  )
}
