// Listado de órdenes de compra, al 100% del ancho -- misma forma que Ventas
// del kit y las pantallas propias del producto (Clientes, Productos): título
// a la izquierda, "Nueva compra" arriba a la derecha, tabla completa abajo y
// el detalle en su propia ruta (`CompraDetalle.tsx`).
//
// Hasta acá el listado ocupaba la mitad de la pantalla y el detalle se
// desplegaba al costado en un segundo `Card`, con un panel de recepciones
// suelto debajo, sin ligarse a una orden en particular. El humano pidió las
// dos cosas: la tabla a todo el ancho con click a la fila para el detalle, y
// que "recibir mercadería" pase a hacerse DENTRO de la orden -- ver
// `CompraDetalle.tsx`.
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ColumnDef } from 'libra-ui/data-table'
import {
  api, ApiError, opcionesProveedor, PURCHASE_ORDER_STATUS_LABELS, PURCHASE_ORDER_STATUS_TONO,
  type PurchaseOrder, type Supplier,
} from '../api'
import { SelectBuscable } from 'libra-ui/SelectBuscable'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Plus, ShoppingBag } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: number): string {
  return value.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function totalDe(order: PurchaseOrder): number {
  return order.items.reduce((acc, linea) => acc + Number(linea.subtotal), 0)
}

/** El botón "Nueva compra" y su modal: sólo elige proveedor y crea la orden
 *  vacía -- las líneas se cargan recién en el detalle, al que se navega
 *  apenas se crea (mismo criterio que "Nueva venta" del kit). */
function NuevaCompraDialog({
  suppliers, onCreada,
}: { suppliers: Supplier[]; onCreada: (orden: PurchaseOrder) => void }) {
  const [open, setOpen] = useState(false)
  const [supplierId, setSupplierId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function abrir() {
    setSupplierId('')
    setError(null)
    setOpen(true)
  }

  async function crear() {
    if (!supplierId) return
    setSaving(true)
    setError(null)
    try {
      const creada = await api.post<PurchaseOrder>('/purchase-orders', {
        supplier_party_id: Number(supplierId),
      })
      setOpen(false)
      onCreada(creada)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button onClick={abrir}><Plus />Nueva compra</Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva compra</DialogTitle>
          </DialogHeader>

          <div className="grid gap-3">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="grid gap-2">
              <Label>Proveedor</Label>
              <SelectBuscable
                value={supplierId}
                onChange={setSupplierId}
                opciones={opcionesProveedor(suppliers)}
                placeholder="Elegí un proveedor…"
                ariaLabel="Proveedor"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button onClick={crear} disabled={saving || !supplierId}>{saving ? 'Creando…' : 'Crear'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export function Compras() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cargar()
  }, [])

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const [o, s] = await Promise.all([
        api.get<PurchaseOrder[]>('/purchase-orders'),
        api.get<Supplier[]>('/suppliers'),
      ])
      setOrders(o)
      setSuppliers(s)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function supplierName(supplierId: number): string {
    return suppliers.find((s) => s.id === supplierId)?.display_name ?? `#${supplierId}`
  }

  function irAlDetalle(orden: PurchaseOrder) {
    navigate(`/compras/${orden.id}`)
  }

  // Anchos fijos al contenido real + Proveedor elastica, mismo patron que el
  // resto de la familia (ver Catalogo/Productos.tsx).
  const columns = useMemo<ColumnDef<PurchaseOrder>[]>(() => [
    { accessorKey: 'number', header: sortableHeader('Número'), size: 130, minSize: 100, cell: ({ row }) => <span className="font-medium">{row.original.number}</span> },
    {
      id: 'proveedor',
      header: 'Proveedor',
      minSize: 140,
      meta: { stretch: true },
      cell: ({ row }) => <span className="block truncate">{supplierName(row.original.supplier_party_id)}</span>,
    },
    {
      accessorKey: 'status',
      header: 'Estado',
      size: 140,
      minSize: 110,
      cell: ({ row }) => (
        <BadgeEstado tono={PURCHASE_ORDER_STATUS_TONO[row.original.status] ?? 'neutro'}>
          {PURCHASE_ORDER_STATUS_LABELS[row.original.status] ?? row.original.status}
        </BadgeEstado>
      ),
    },
    { id: 'lineas', header: 'Líneas', size: 90, minSize: 80, cell: ({ row }) => row.original.items.length },
    { id: 'total', header: 'Total', size: 130, minSize: 100, cell: ({ row }) => `$${money(totalDe(row.original))}` },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [suppliers])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <TituloPantalla icono={ShoppingBag}>Compras</TituloPantalla>
        <NuevaCompraDialog suppliers={suppliers} onCreada={irAlDetalle} />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={orders}
              emptyMessage="Sin órdenes de compra todavía."
              onRowClick={irAlDetalle}
              // Mismo buscador que Clientes/Proveedores/Productos.
              search={{
                campos: (o) => [o.number, supplierName(o.supplier_party_id)],
                placeholder: 'Buscar por número o proveedor',
                ariaLabel: 'Buscar orden de compra',
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
