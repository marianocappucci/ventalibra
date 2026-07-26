import { useEffect, useState, type FormEvent } from 'react'
import {
  api, ApiError, type CatalogItem, type ItemVariant, type Location, type Sale,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const MEDIOS_PAGO = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'tarjeta_debito', label: 'Tarjeta de débito' },
  { value: 'tarjeta_credito', label: 'Tarjeta de crédito' },
  { value: 'transferencia', label: 'Transferencia' },
  { value: 'mercado_pago', label: 'Mercado Pago' },
]

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function Pos() {
  const [locations, setLocations] = useState<Location[]>([])
  const [locationId, setLocationId] = useState<string>('')
  const [medioPago, setMedioPago] = useState<string>('efectivo')
  const [invoice, setInvoice] = useState(false)

  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<CatalogItem[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [pickedItem, setPickedItem] = useState<CatalogItem | null>(null)
  const [variants, setVariants] = useState<ItemVariant[]>([])
  const [variantId, setVariantId] = useState<string>('')
  const [quantity, setQuantity] = useState('1')

  const [sale, setSale] = useState<Sale | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState<Sale | null>(null)

  useEffect(() => {
    api.get<Location[]>('/locations')
      .then((items) => {
        setLocations(items)
        if (items.length > 0) setLocationId(String(items[0].id))
      })
      .catch(() => setLocations([]))
  }, [])

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setSearchError(null)
    setSearchResults([])
    setPickedItem(null)
    try {
      const scanned = await api.get<CatalogItem>(`/catalog/items/scan?code=${encodeURIComponent(query.trim())}`)
      await pickItem(scanned)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        try {
          const found = await api.get<CatalogItem[]>(`/catalog/items?search=${encodeURIComponent(query.trim())}`)
          if (found.length === 0) setSearchError('Sin resultados.')
          setSearchResults(found)
        } catch (searchErr) {
          setSearchError(describeError(searchErr))
        }
      } else {
        setSearchError(describeError(err))
      }
    } finally {
      setSearching(false)
    }
  }

  async function pickItem(item: CatalogItem) {
    setPickedItem(item)
    setSearchResults([])
    setVariantId('')
    setQuantity('1')
    try {
      const itemVariants = await api.get<ItemVariant[]>(`/catalog/items/${item.id}/variants`)
      setVariants(itemVariants)
    } catch {
      setVariants([])
    }
  }

  async function ensureDraftSale(): Promise<Sale> {
    if (sale) return sale
    const created = await api.post<Sale>('/sales', {})
    setSale(created)
    return created
  }

  async function handleAddItem() {
    if (!pickedItem) return
    if (variants.length > 0 && !variantId) {
      setError('Elegí una variante antes de agregar.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const current = await ensureDraftSale()
      const updated = await api.post<Sale>(`/sales/${current.id}/items`, {
        item_id: pickedItem.id,
        variant_id: variantId ? Number(variantId) : null,
        quantity,
      })
      setSale(updated)
      setPickedItem(null)
      setVariants([])
      setQuery('')
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirm() {
    if (!sale || !locationId) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.post<Sale>(`/sales/${sale.id}/confirm`, {
        location_id: Number(locationId),
        medio_pago: medioPago,
        invoice,
      })
      setConfirmed(result)
      setSale(null)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  function startNewSale() {
    setConfirmed(null)
    setSale(null)
    setError(null)
    setQuery('')
    setPickedItem(null)
    setSearchResults([])
  }

  if (confirmed) {
    return (
      <div className="grid gap-4 max-w-xl">
        <Card>
          <CardHeader>
            <CardTitle>Venta {confirmed.number} confirmada</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-2xl font-semibold">${money(confirmed.total)}</p>
            {confirmed.factura ? (
              <p className="text-sm text-muted-foreground">
                Factura {confirmed.factura.punto_venta}-{confirmed.factura.numero} · CAE {confirmed.factura.cae}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Sin factura.</p>
            )}
            <Button onClick={startNewSale}>Nueva venta</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Buscar producto</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <form className="flex gap-2" onSubmit={handleSearch}>
              <Input
                placeholder="Código de barras o nombre…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
              />
              <Button type="submit" disabled={searching}>{searching ? 'Buscando…' : 'Buscar'}</Button>
            </form>
            {searchError && <p className="text-sm text-destructive">{searchError}</p>}

            {searchResults.length > 0 && (
              <div className="grid gap-1">
                {searchResults.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm hover:bg-accent"
                    onClick={() => pickItem(item)}
                  >
                    <span>{item.name}</span>
                    <span className="text-muted-foreground">${money(item.default_sale_price)}</span>
                  </button>
                ))}
              </div>
            )}

            {pickedItem && (
              <div className="grid gap-3 rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{pickedItem.name}</span>
                  <span className="text-muted-foreground">${money(pickedItem.default_sale_price)}</span>
                </div>
                {variants.length > 0 && (
                  <div className="grid gap-2">
                    <Label>Variante</Label>
                    <Select value={variantId} onValueChange={setVariantId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Elegí una variante…" />
                      </SelectTrigger>
                      <SelectContent>
                        {variants.map((v) => (
                          <SelectItem key={v.id} value={String(v.id)}>{v.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="grid gap-2">
                  <Label htmlFor="quantity">Cantidad</Label>
                  <Input
                    id="quantity"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    className="w-28"
                  />
                </div>
                <Button onClick={handleAddItem} disabled={busy}>Agregar a la venta</Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Venta en curso</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {error && <p className="text-sm text-destructive">{error}</p>}

            {!sale || sale.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">Todavía no agregaste ningún producto.</p>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Producto</TableHead>
                      <TableHead>Cant.</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sale.items.map((line, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{line.description_snapshot}</TableCell>
                        <TableCell>{line.quantity}</TableCell>
                        <TableCell className="text-right">${money(line.line_total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="flex items-center justify-between border-t pt-3">
                  <span className="font-medium">Total</span>
                  <span className="text-xl font-semibold">${money(sale.total)}</span>
                </div>
              </>
            )}

            <div className="grid gap-3 border-t pt-3">
              <div className="grid gap-2">
                <Label>Sucursal / depósito</Label>
                <Select value={locationId} onValueChange={setLocationId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Elegí una sucursal…" />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map((loc) => (
                      <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {locations.length === 0 && (
                  <p className="text-xs text-muted-foreground">No hay sucursales creadas todavía.</p>
                )}
              </div>
              <div className="grid gap-2">
                <Label>Medio de pago</Label>
                <Select value={medioPago} onValueChange={setMedioPago}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MEDIOS_PAGO.map((m) => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={invoice} onChange={(e) => setInvoice(e.target.checked)} />
                Emitir factura
              </label>
              <Button
                onClick={handleConfirm}
                disabled={busy || !sale || sale.items.length === 0 || !locationId}
              >
                {busy ? 'Confirmando…' : 'Confirmar venta'}
              </Button>
            </div>
          </CardContent>
        </Card>
        {sale && <Badge variant="outline">Borrador {sale.number}</Badge>}
      </div>
    </div>
  )
}
