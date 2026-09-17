// El detalle de una orden de compra: líneas, alta de línea (mientras la orden
// admite), y "Recibir mercadería" -- la recepción pasa a hacerse DENTRO de la
// orden (pedido del humano), y ya no en un panel suelto de Compras.tsx.
//
// La confirmación de una recepción (con el depósito de destino) también vive
// acá, en la sección "Recepciones de esta orden": si "Recibir mercadería" se
// corta a mitad de camino, la recepción que quedó en borrador aparece ahí con
// su botón "Confirmar" -- no queda un estado sin salida.
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  api, ApiError, opcionesItem, PURCHASE_ORDER_STATUS_LABELS, PURCHASE_ORDER_STATUS_TONO,
  PURCHASE_RECEIPT_STATUS_LABELS, PURCHASE_RECEIPT_STATUS_TONO,
  type CatalogItem, type Location, type PurchaseOrder, type PurchaseReceipt, type Supplier,
} from '../api'
import { fechaHora } from '@/lib/fechas'
import { SelectBuscable } from 'libra-ui/SelectBuscable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ArrowLeft, PackageCheck, ShoppingBag } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string | number): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function CompraDetalle() {
  const { id } = useParams<{ id: string }>()
  const orderId = Number(id)

  const [order, setOrder] = useState<PurchaseOrder | null>(null)
  const [items, setItems] = useState<CatalogItem[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [receipts, setReceipts] = useState<PurchaseReceipt[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [lineItemId, setLineItemId] = useState('')
  const [lineQuantity, setLineQuantity] = useState('1')
  const [lineCost, setLineCost] = useState('0')
  const [savingLine, setSavingLine] = useState(false)

  const [recibirOpen, setRecibirOpen] = useState(false)

  useEffect(() => {
    cargarTodo()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId])

  async function cargarTodo() {
    setLoading(true)
    setError(null)
    try {
      const [o, i, s, l, r] = await Promise.all([
        api.get<PurchaseOrder>(`/purchase-orders/${orderId}`),
        api.get<CatalogItem[]>('/catalog/items'),
        api.get<Supplier[]>('/suppliers'),
        api.get<Location[]>('/locations'),
        api.get<PurchaseReceipt[]>('/purchase-receipts'),
      ])
      setOrder(o)
      setItems(i)
      setSuppliers(s)
      setLocations(l)
      setReceipts(r)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function cargarOrden() {
    setOrder(await api.get<PurchaseOrder>(`/purchase-orders/${orderId}`))
  }

  async function cargarRecepciones() {
    setReceipts(await api.get<PurchaseReceipt[]>('/purchase-receipts'))
  }

  function itemName(itemId: number): string {
    return items.find((i) => i.id === itemId)?.name ?? `#${itemId}`
  }

  function supplierName(supplierId: number): string {
    return suppliers.find((s) => s.id === supplierId)?.display_name ?? `#${supplierId}`
  }

  async function agregarLinea() {
    if (!order || !lineItemId) return
    setSavingLine(true)
    setError(null)
    try {
      const updated = await api.post<PurchaseOrder>(`/purchase-orders/${order.id}/items`, {
        item_id: Number(lineItemId), quantity_ordered: lineQuantity, unit_cost: lineCost,
      })
      setOrder(updated)
      setLineItemId('')
      setLineQuantity('1')
      setLineCost('0')
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSavingLine(false)
    }
  }

  const recepcionesDeLaOrden = useMemo(
    () => receipts.filter((r) => r.purchase_order_id === orderId),
    [receipts, orderId],
  )

  const pendientes = order?.items.filter((l) => Number(l.pending_quantity) > 0) ?? []
  const puedeRecibir = !!order
    && pendientes.length > 0
    && order.status !== 'received' && order.status !== 'cancelled'
  // `is_fully_received()` da vacuamente `true` para una orden sin líneas
  // (`all()` sobre una colección vacía) -- el gate real de "se pueden seguir
  // agregando líneas" es el status, mismo criterio que valida
  // `PurchasingService.add_order_item()` del lado del backend.
  const puedeAgregarLinea = order?.status === 'draft' || order?.status === 'sent'

  if (loading || !order) {
    return (
      <div className="grid gap-4">
        <TituloPantalla icono={ShoppingBag}>Orden de compra</TituloPantalla>
        {error ? <p className="text-sm text-destructive">{error}</p> : (
          <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
        )}
      </div>
    )
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TituloPantalla icono={ShoppingBag}>
          Orden {order.number}{' '}
          <BadgeEstado tono={PURCHASE_ORDER_STATUS_TONO[order.status] ?? 'neutro'}>
            {PURCHASE_ORDER_STATUS_LABELS[order.status] ?? order.status}
          </BadgeEstado>
        </TituloPantalla>
        <div className="flex flex-wrap gap-2">
          {puedeRecibir && (
            <Button size="sm" onClick={() => setRecibirOpen(true)}>
              <PackageCheck />Recibir mercadería
            </Button>
          )}
          <Button asChild size="sm" variant="outline">
            <Link to="/compras"><ArrowLeft />Volver</Link>
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Proveedor</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{supplierName(order.supplier_party_id)}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Líneas</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Producto</TableHead>
                <TableHead>Pedido</TableHead>
                <TableHead>Recibido</TableHead>
                <TableHead>Pendiente</TableHead>
                <TableHead>Costo unitario</TableHead>
                <TableHead>Subtotal</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {order.items.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground">Sin líneas todavía.</TableCell></TableRow>
              )}
              {order.items.map((line, idx) => (
                <TableRow key={idx}>
                  <TableCell>{itemName(line.item_id)}</TableCell>
                  <TableCell>{line.quantity_ordered}</TableCell>
                  <TableCell>{line.quantity_received}</TableCell>
                  <TableCell>{line.pending_quantity}</TableCell>
                  <TableCell>${money(line.unit_cost)}</TableCell>
                  <TableCell>${money(line.subtotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {puedeAgregarLinea && (
            <div className="flex flex-wrap items-end gap-2 border-t pt-3">
              <div className="grid gap-2">
                <Label>Producto</Label>
                <SelectBuscable
                  value={lineItemId}
                  onChange={setLineItemId}
                  opciones={opcionesItem(items)}
                  placeholder="Producto…"
                  ariaLabel="Producto"
                  className="w-48"
                />
              </div>
              <div className="grid gap-2">
                <Label>Cantidad</Label>
                <Input value={lineQuantity} onChange={(e) => setLineQuantity(e.target.value)} className="w-24" />
              </div>
              <div className="grid gap-2">
                <Label>Costo unitario</Label>
                <Input value={lineCost} onChange={(e) => setLineCost(e.target.value)} className="w-28" />
              </div>
              <Button onClick={agregarLinea} disabled={savingLine || !lineItemId}>Agregar línea</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <RecepcionesDeLaOrden
        receipts={recepcionesDeLaOrden}
        locations={locations}
        onConfirmada={async () => { await Promise.all([cargarOrden(), cargarRecepciones()]) }}
      />

      {recibirOpen && order && (
        <RecibirMercaderiaDialog
          order={order}
          locations={locations}
          itemName={itemName}
          onCerrar={() => setRecibirOpen(false)}
          onRecibida={async () => {
            setRecibirOpen(false)
            await Promise.all([cargarOrden(), cargarRecepciones()])
          }}
          onRecargarRecepciones={cargarRecepciones}
        />
      )}
    </div>
  )
}

/** El modal de "Recibir mercadería": una fila por línea pendiente, con la
 *  cantidad y el costo precargados y editables, el depósito de destino y un
 *  remito opcional. Al confirmar hace los tres pasos del backend en orden
 *  (crear recepción → cargar líneas → confirmar) -- si alguno falla a mitad de
 *  camino, la recepción que quedó en borrador sigue viendose y confirmable
 *  desde "Recepciones de esta orden" (por eso, ante un error, se recargan las
 *  recepciones con `onRecargarRecepciones` — y NO con `onRecibida`, que cierra
 *  el modal y se llevaría el mensaje de error antes de que se lea). */
function RecibirMercaderiaDialog({
  order, locations, itemName, onCerrar, onRecibida, onRecargarRecepciones,
}: {
  order: PurchaseOrder
  locations: Location[]
  itemName: (itemId: number) => string
  onCerrar: () => void
  onRecibida: () => void | Promise<void>
  onRecargarRecepciones: () => void | Promise<void>
}) {
  const pendientes = useMemo(
    () => order.items.filter((l) => Number(l.pending_quantity) > 0),
    [order],
  )

  const [cantidades, setCantidades] = useState<Record<number, string>>(
    () => Object.fromEntries(pendientes.map((l) => [l.item_id, l.pending_quantity])),
  )
  const [costos, setCostos] = useState<Record<number, string>>(
    () => Object.fromEntries(pendientes.map((l) => [l.item_id, l.unit_cost])),
  )
  const [locationId, setLocationId] = useState(() => {
    const porDefecto = locations.find((l) => l.is_default)
    return porDefecto ? String(porDefecto.id) : (locations[0] ? String(locations[0].id) : '')
  })
  const [documentReference, setDocumentReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function errorDeLinea(itemId: number, pendiente: string): string | null {
    const valor = cantidades[itemId] ?? ''
    if (valor === '') return null
    const n = Number(valor)
    if (Number.isNaN(n) || n < 0) return 'Tiene que ser un número igual o mayor a 0.'
    if (n > Number(pendiente)) return `No puede superar lo pendiente (${pendiente}).`
    return null
  }

  const hayErrores = pendientes.some((l) => errorDeLinea(l.item_id, l.pending_quantity) !== null)
  const hayAlgunaCantidad = pendientes.some((l) => Number(cantidades[l.item_id]) > 0)
  const puedeConfirmar = hayAlgunaCantidad && !hayErrores && !!locationId && !busy

  async function recibir() {
    if (!puedeConfirmar) return
    setBusy(true)
    setError(null)
    try {
      const receipt = await api.post<PurchaseReceipt>('/purchase-receipts', {
        supplier_party_id: order.supplier_party_id,
        purchase_order_id: order.id,
        document_reference: documentReference.trim() || null,
      })
      for (const linea of pendientes) {
        const cantidad = cantidades[linea.item_id]
        if (!cantidad || Number(cantidad) <= 0) continue
        await api.post(`/purchase-receipts/${receipt.id}/items`, {
          item_id: linea.item_id,
          quantity: cantidad,
          unit_cost: costos[linea.item_id] ?? linea.unit_cost,
        })
      }
      await api.post(`/purchase-receipts/${receipt.id}/confirm`, { location_id: Number(locationId) })
      await onRecibida()
    } catch (err) {
      // La recepción puede haber quedado creada (en borrador, con algunas o
      // ninguna línea): se avisa el error y se recarga igual, para que quede
      // visible en "Recepciones de esta orden" -- no queda un estado sin
      // salida al que sólo se llega recargando la página a mano.
      setError(describeError(err))
      await Promise.resolve(onRecargarRecepciones()).catch(() => {})
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Recibir mercadería — Orden {order.number}</DialogTitle>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="max-h-72 overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Producto</TableHead>
                <TableHead>Pendiente</TableHead>
                <TableHead>Recibir</TableHead>
                <TableHead>Costo unitario</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pendientes.map((linea) => {
                const err = errorDeLinea(linea.item_id, linea.pending_quantity)
                return (
                  <TableRow key={linea.item_id}>
                    <TableCell>{itemName(linea.item_id)}</TableCell>
                    <TableCell className="tabular-nums">{linea.pending_quantity}</TableCell>
                    <TableCell>
                      <Input
                        value={cantidades[linea.item_id] ?? ''}
                        onChange={(e) => setCantidades((prev) => ({ ...prev, [linea.item_id]: e.target.value }))}
                        aria-label={`Cantidad a recibir de ${itemName(linea.item_id)}`}
                        className="w-24 tabular-nums"
                      />
                      {err && <p className="text-xs text-destructive">{err}</p>}
                    </TableCell>
                    <TableCell>
                      <Input
                        value={costos[linea.item_id] ?? ''}
                        onChange={(e) => setCostos((prev) => ({ ...prev, [linea.item_id]: e.target.value }))}
                        aria-label={`Costo unitario de ${itemName(linea.item_id)}`}
                        className="w-28 tabular-nums"
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-2">
            <Label htmlFor="recepcion-deposito">Depósito de destino</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger id="recepcion-deposito" className="w-48"><SelectValue placeholder="Depósito…" /></SelectTrigger>
              <SelectContent>
                {locations.map((loc) => <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="recepcion-remito">Remito / comprobante</Label>
            <Input
              id="recepcion-remito" value={documentReference}
              onChange={(e) => setDocumentReference(e.target.value)}
              placeholder="Opcional" className="w-48"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={busy}>Cancelar</Button>
          <Button onClick={recibir} disabled={!puedeConfirmar}>
            {busy ? 'Recibiendo…' : 'Recibir'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Las recepciones de ESTA orden (`GET /purchase-receipts` filtrado del lado
 *  del cliente -- el backend no ofrece el filtro por orden, ver
 *  `app/routers/purchasing.py::list_receipts`). Una recepción en borrador
 *  -la que puede haber quedado de un "Recibir mercadería" cortado a mitad de
 *  camino- ofrece acá su propio "Confirmar", con el depósito. */
function RecepcionesDeLaOrden({
  receipts, locations, onConfirmada,
}: { receipts: PurchaseReceipt[]; locations: Location[]; onConfirmada: () => void | Promise<void> }) {
  const [confirmando, setConfirmando] = useState<PurchaseReceipt | null>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recepciones de esta orden</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead>Remito</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Líneas</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {receipts.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground">Sin recepciones todavía.</TableCell></TableRow>
            )}
            {receipts.map((receipt) => (
              <TableRow key={receipt.id}>
                <TableCell>#{receipt.id}</TableCell>
                <TableCell>{receipt.received_at ? fechaHora(receipt.received_at) : '—'}</TableCell>
                <TableCell>{receipt.document_reference ?? '—'}</TableCell>
                <TableCell>
                  <BadgeEstado tono={PURCHASE_RECEIPT_STATUS_TONO[receipt.status] ?? 'neutro'}>
                    {PURCHASE_RECEIPT_STATUS_LABELS[receipt.status] ?? receipt.status}
                  </BadgeEstado>
                </TableCell>
                <TableCell>{receipt.items.length}</TableCell>
                <TableCell>
                  {/* Sin líneas el backend rechaza la confirmación ("no se
                      puede confirmar una recepcion sin lineas"): ofrecer el
                      botón sería mandar a un error seguro. */}
                  {receipt.status === 'draft' && receipt.items.length > 0 && (
                    <Button size="sm" variant="outline" onClick={() => setConfirmando(receipt)}>Confirmar</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      {confirmando && (
        <ConfirmarRecepcionDialog
          receipt={confirmando}
          locations={locations}
          onCerrar={() => setConfirmando(null)}
          onConfirmada={async () => { setConfirmando(null); await onConfirmada() }}
        />
      )}
    </Card>
  )
}

function ConfirmarRecepcionDialog({
  receipt, locations, onCerrar, onConfirmada,
}: {
  receipt: PurchaseReceipt
  locations: Location[]
  onCerrar: () => void
  onConfirmada: () => void | Promise<void>
}) {
  const [locationId, setLocationId] = useState(() => {
    const porDefecto = locations.find((l) => l.is_default)
    return porDefecto ? String(porDefecto.id) : (locations[0] ? String(locations[0].id) : '')
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function confirmar() {
    if (!locationId) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/purchase-receipts/${receipt.id}/confirm`, { location_id: Number(locationId) })
      await onConfirmada()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirmar recepción #{receipt.id}</DialogTitle>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="grid gap-2">
          <Label htmlFor="confirmar-deposito">Depósito de destino</Label>
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger id="confirmar-deposito" className="w-48"><SelectValue placeholder="Depósito…" /></SelectTrigger>
            <SelectContent>
              {locations.map((loc) => <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={busy}>Cancelar</Button>
          <Button onClick={confirmar} disabled={busy || !locationId}>
            {busy ? 'Confirmando…' : 'Confirmar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
