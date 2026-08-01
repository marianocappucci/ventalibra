import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import {
  api, ApiError, ITEM_CODE_TYPE_LABELS, opcionesCategoria,
  type CatalogItem, type Category, type ItemCode, type ItemCodeType, type ItemVariant, type Unit,
} from '../api'
import { SelectBuscable } from 'libra-ui/SelectBuscable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Barcode } from 'lucide-react'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function UnitQuickCreate({ units, onCreated }: { units: Unit[]; onCreated: () => void }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [allowsFraction, setAllowsFraction] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    if (!code.trim() || !name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await api.post('/catalog/units', {
        code: code.trim(), name: name.trim(), allows_fraction: allowsFraction,
        decimal_scale: allowsFraction ? 3 : 0,
      })
      setCode('')
      setName('')
      setAllowsFraction(false)
      onCreated()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Unidades</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor="unit-code">Código</Label>
            <Input id="unit-code" value={code} onChange={(e) => setCode(e.target.value)} className="w-24" placeholder="u, kg…" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="unit-name">Nombre</Label>
            <Input id="unit-name" value={name} onChange={(e) => setName(e.target.value)} className="w-40" placeholder="Unidad, Kilogramo…" />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={allowsFraction} onChange={(e) => setAllowsFraction(e.target.checked)} />
            Se vende por fracción (peso/volumen)
          </label>
          <Button onClick={handleCreate} disabled={saving}>{saving ? 'Creando…' : 'Crear unidad'}</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex flex-wrap gap-2">
          {units.map((u) => <Badge key={u.code} variant="outline">{u.code} — {u.name}</Badge>)}
        </div>
      </CardContent>
    </Card>
  )
}

function ItemCreateForm({
  units, categories, onCreated,
}: { units: Unit[]; categories: Category[]; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [unitCode, setUnitCode] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [salePrice, setSalePrice] = useState('0')
  const [cost, setCost] = useState('0')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    if (!name.trim() || !unitCode) {
      setError('Nombre y unidad son obligatorios.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post('/catalog/items', {
        name: name.trim(), unit_code: unitCode,
        category_id: categoryId ? Number(categoryId) : null,
        default_sale_price: salePrice, default_cost: cost,
      })
      setName('')
      setSalePrice('0')
      setCost('0')
      onCreated()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Nuevo item</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label>Nombre</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
          </div>
          <div className="grid gap-1.5">
            <Label>Unidad</Label>
            <Select value={unitCode} onValueChange={setUnitCode}>
              <SelectTrigger className="w-32"><SelectValue placeholder="Unidad…" /></SelectTrigger>
              <SelectContent>
                {units.map((u) => <SelectItem key={u.code} value={u.code}>{u.code}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>Categoría</Label>
            <SelectBuscable
              value={categoryId}
              onChange={setCategoryId}
              opciones={opcionesCategoria(categories)}
              placeholder="Sin categoría"
              ariaLabel="Categoría"
              className="w-40"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Precio de venta</Label>
            <Input value={salePrice} onChange={(e) => setSalePrice(e.target.value)} className="w-28" />
          </div>
          <div className="grid gap-1.5">
            <Label>Costo</Label>
            <Input value={cost} onChange={(e) => setCost(e.target.value)} className="w-28" />
          </div>
          <Button onClick={handleCreate} disabled={saving}>{saving ? 'Creando…' : 'Crear item'}</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}

function ItemDetailDialog({ item, onClose }: { item: CatalogItem; onClose: () => void }) {
  const [codes, setCodes] = useState<ItemCode[]>([])
  const [variants, setVariants] = useState<ItemVariant[]>([])
  const [error, setError] = useState<string | null>(null)

  const [codeType, setCodeType] = useState<ItemCodeType>('barcode')
  const [codeValue, setCodeValue] = useState('')
  const [savingCode, setSavingCode] = useState(false)

  const [variantSku, setVariantSku] = useState('')
  const [variantName, setVariantName] = useState('')
  const [savingVariant, setSavingVariant] = useState(false)

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id])

  async function load() {
    try {
      const [codeList, variantList] = await Promise.all([
        api.get<ItemCode[]>(`/catalog/items/${item.id}/codes`),
        api.get<ItemVariant[]>(`/catalog/items/${item.id}/variants`),
      ])
      setCodes(codeList)
      setVariants(variantList)
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function addCode() {
    if (!codeValue.trim()) return
    setSavingCode(true)
    setError(null)
    try {
      await api.post(`/catalog/items/${item.id}/codes`, { code_type: codeType, code: codeValue.trim() })
      setCodeValue('')
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSavingCode(false)
    }
  }

  async function addVariant() {
    if (!variantSku.trim() || !variantName.trim()) return
    setSavingVariant(true)
    setError(null)
    try {
      await api.post(`/catalog/items/${item.id}/variants`, { sku: variantSku.trim(), name: variantName.trim() })
      setVariantSku('')
      setVariantName('')
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSavingVariant(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item.name}</DialogTitle>
        </DialogHeader>
        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="grid gap-2">
          <h4 className="text-sm font-medium">Códigos</h4>
          <div className="flex flex-wrap gap-2">
            {codes.length === 0 && <p className="text-sm text-muted-foreground">Sin códigos todavía.</p>}
            {codes.map((c) => (
              <Badge key={c.id} variant={c.is_primary ? 'default' : 'outline'}>
                {ITEM_CODE_TYPE_LABELS[c.code_type]}: {c.code}
              </Badge>
            ))}
          </div>
          <div className="flex items-end gap-2">
            <div className="grid gap-1.5">
              <Label>Tipo</Label>
              <Select value={codeType} onValueChange={(v) => setCodeType(v as ItemCodeType)}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(ITEM_CODE_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5 flex-1">
              <Label>Código</Label>
              <Input value={codeValue} onChange={(e) => setCodeValue(e.target.value)} />
            </div>
            <Button onClick={addCode} disabled={savingCode}>Agregar</Button>
          </div>
        </div>

        <div className="grid gap-2 border-t pt-4">
          <h4 className="text-sm font-medium">Variantes (talle/color)</h4>
          <div className="flex flex-wrap gap-2">
            {variants.length === 0 && <p className="text-sm text-muted-foreground">Sin variantes todavía.</p>}
            {variants.map((v) => <Badge key={v.id} variant="outline">{v.sku} — {v.name}</Badge>)}
          </div>
          <div className="flex items-end gap-2">
            <div className="grid gap-1.5">
              <Label>SKU</Label>
              <Input value={variantSku} onChange={(e) => setVariantSku(e.target.value)} className="w-32" />
            </div>
            <div className="grid gap-1.5 flex-1">
              <Label>Nombre (ej. M / Azul)</Label>
              <Input value={variantName} onChange={(e) => setVariantName(e.target.value)} />
            </div>
            <Button onClick={addVariant} disabled={savingVariant}>Agregar</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function Catalogo() {
  const [items, setItems] = useState<CatalogItem[]>([])
  const [units, setUnits] = useState<Unit[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [detailItem, setDetailItem] = useState<CatalogItem | null>(null)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [itemList, unitList, categoryList] = await Promise.all([
        api.get<CatalogItem[]>('/catalog/items'),
        api.get<Unit[]>('/catalog/units'),
        api.get<Category[]>('/catalog/categories'),
      ])
      setItems(itemList)
      setUnits(unitList)
      setCategories(categoryList)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function runSearch() {
    setLoading(true)
    try {
      const itemList = await api.get<CatalogItem[]>(`/catalog/items${search ? `?search=${encodeURIComponent(search)}` : ''}`)
      setItems(itemList)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  // Anchos fijos al contenido real + Nombre elastica, mismo patron que el
  // resto de la familia. La columna de acciones no declara ancho: la mide
  // `libra-ui` sola (ver wiki/entities/libra-ui.md v0.4.0).
  const columns = useMemo<ColumnDef<CatalogItem>[]>(() => [
    { accessorKey: 'name', header: sortableHeader('Nombre'), size: 240, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate font-medium" title={row.original.name}>{row.original.name}</span> },
    { accessorKey: 'unit_code', header: 'Unidad', size: 100, minSize: 80 },
    {
      accessorKey: 'default_sale_price',
      header: 'Precio',
      size: 120,
      minSize: 100,
      cell: ({ row }) => `$${money(row.original.default_sale_price)}`,
    },
    {
      accessorKey: 'active',
      header: 'Estado',
      size: 100,
      minSize: 85,
      cell: ({ row }) => (
        <Badge variant={row.original.active ? 'default' : 'outline'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      // El header decia "Códigos / variantes" (era el unico de la familia que
      // no decia "Acciones"). Al unificarlo, lo que ese rotulo explicaba pasa
      // al tooltip del boton para no perder el significado.
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Gestionar códigos y variantes" aria-label="Gestionar códigos y variantes" onClick={() => setDetailItem(row.original)}><Barcode /></Button>
        </div>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Catálogo</h2>

      <UnitQuickCreate units={units} onCreated={loadAll} />
      <ItemCreateForm units={units} categories={categories} onCreated={loadAll} />

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Input
              placeholder="Buscar por nombre…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runSearch()}
              className="max-w-xs"
            />
            <Button variant="outline" onClick={runSearch}>Buscar</Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={items} emptyMessage="Sin items todavía." />
          )}
        </CardContent>
      </Card>

      {detailItem && <ItemDetailDialog item={detailItem} onClose={() => setDetailItem(null)} />}
    </div>
  )
}
