// El catálogo de productos. Hasta el 2026-09-17 esta pantalla se llamaba
// "Catálogo" y tenía una segunda pestaña de Unidades; el humano pidió
// renombrarla a "Productos" y mover Unidades a Configuración (ver
// `ConfigUnidades.tsx`, montada como su propia sección) -- el alta de un
// producto sigue necesitando las unidades, así que esta pantalla las sigue
// cargando (`/catalog/units`), sólo que ya no las muestra ni las da de alta.
//
// Los endpoints `/catalog/*` no cambiaron: sólo el nombre de la pantalla y su
// ruta (`/catalogo` redirige a `/productos`, ver `rutas-viejas.ts`).
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import {
  api, ApiError, ITEM_CODE_TYPE_LABELS, opcionesCategoria,
  type CatalogItem, type Category, type ItemCode, type ItemCodeType, type ItemVariant, type Unit,
} from '../api'
import { SelectBuscable } from 'libra-ui/SelectBuscable'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Barcode, Package, Pencil } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Parsea un precio/costo tipeado a mano. `null` si no es un número válido o
 *  es negativo -- nunca cae a 0 en silencio, a diferencia de `Number(x) || 0`
 *  (que el alta tampoco usa hoy: manda el string tal cual escrito, sin
 *  validar nada -- ver `ItemCreateDialog.handleCreate`, que sólo chequea
 *  nombre y unidad no vacíos). Misma regla de parseo que `parseMonto` de
 *  `Pos.tsx` (coma decimal, punto de miles), documentada ahí porque no hay
 *  un lugar compartido entre pantallas para ponerla -- no se importa de ahí
 *  porque esa función no está exportada y es específica del turno de caja. */
function parsePrecio(texto: string): number | null {
  const t = texto.trim()
  let normalizado: string
  if (/^(\d{1,3}(\.\d{3})+|\d+),\d+$/.test(t)) {
    normalizado = t.replace(/\./g, '').replace(',', '.')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(t)) {
    normalizado = t.replace(/\./g, '')
  } else if (/^\d+(\.\d+)?$/.test(t)) {
    normalizado = t
  } else {
    return null
  }
  const n = Number(normalizado)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** Los campos que comparten alta y edición: nombre, unidad, categoría,
 *  precio y costo. Extraído para no duplicar el JSX -- el switch «Activo»
 *  de la edición y los botones de cada modal quedan afuera, porque no
 *  existen en el alta. */
function ItemFormFields({
  units, categories, name, setName, unitCode, setUnitCode, categoryId, setCategoryId,
  salePrice, setSalePrice, cost, setCost,
}: {
  units: Unit[]
  categories: Category[]
  name: string
  setName: (v: string) => void
  unitCode: string
  setUnitCode: (v: string) => void
  categoryId: string
  setCategoryId: (v: string) => void
  salePrice: string
  setSalePrice: (v: string) => void
  cost: string
  setCost: (v: string) => void
}) {
  return (
    <>
      <div className="grid gap-2">
        <Label htmlFor="item-name">Nombre</Label>
        <Input id="item-name" value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="item-unit">Unidad</Label>
        <Select value={unitCode} onValueChange={setUnitCode}>
          <SelectTrigger id="item-unit" className="w-full"><SelectValue placeholder="Unidad…" /></SelectTrigger>
          <SelectContent>
            {units.map((u) => <SelectItem key={u.code} value={u.code}>{u.code} — {u.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-2">
        <Label>Categoría</Label>
        <SelectBuscable
          value={categoryId}
          onChange={setCategoryId}
          opciones={opcionesCategoria(categories)}
          placeholder="Sin categoría"
          ariaLabel="Categoría"
          className="w-full"
        />
      </div>
      {/* Precio y costo van a la par: son los dos numéricos y cortos, y
          apilarlos estiraría el modal por dos campos de 90 px. */}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2">
          <Label htmlFor="item-price">Precio de venta</Label>
          <Input id="item-price" value={salePrice} onChange={(e) => setSalePrice(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="item-cost">Costo</Label>
          <Input id="item-cost" value={cost} onChange={(e) => setCost(e.target.value)} />
        </div>
      </div>
    </>
  )
}

/** El botón "+ Nuevo producto" y su modal. Va junto, y no un botón acá y un
 *  `Dialog` allá, porque el estado que los une —si está abierto y qué se
 *  escribió— no le sirve a nadie más.
 *
 *  El alta era una tarjeta fija arriba de la tabla. Es el mismo cambio que se
 *  le hizo a `Usuarios` en `libra-ui` el 2026-08-15 y por el mismo motivo: la
 *  tarjeta empujaba la grilla hacia abajo y ocupaba la pantalla con un
 *  formulario que se usa de vez en cuando. */
function ItemCreateDialog({
  units, categories, onCreated,
}: { units: Unit[]; categories: Category[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [unitCode, setUnitCode] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [salePrice, setSalePrice] = useState('0')
  const [cost, setCost] = useState('0')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Abrir SIEMPRE limpia. Sin esto, cerrar a medio cargar y volver a abrir
   *  muestra el borrador anterior como si fuera un alta nueva. */
  function abrir() {
    setName('')
    setUnitCode('')
    setCategoryId('')
    setSalePrice('0')
    setCost('0')
    setError(null)
    setOpen(true)
  }

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
      setOpen(false)
      onCreated()
    } catch (err) {
      // El error se queda adentro del modal, que es donde está la vista: si
      // se cerrara para mostrarlo afuera, se perdería lo cargado.
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button onClick={abrir}>+ Nuevo producto</Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo producto</DialogTitle>
          </DialogHeader>

          {/* Los `htmlFor`/`id` no son decorativos: sin ellos el rótulo no
              queda asociado a su campo y un lector de pantalla anuncia el
              input sin nombre. Es el mismo par que usan el alta de unidad
              (ahora en Configuración) y las de Pos/CuentasCorrientes. La
              Categoría no lo necesita: se nombra sola con el `ariaLabel` de
              `SelectBuscable`. */}
          <div className="grid gap-3">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <ItemFormFields
              units={units} categories={categories}
              name={name} setName={setName}
              unitCode={unitCode} setUnitCode={setUnitCode}
              categoryId={categoryId} setCategoryId={setCategoryId}
              salePrice={salePrice} setSalePrice={setSalePrice}
              cost={cost} setCost={setCost}
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={saving}>{saving ? 'Creando…' : 'Crear'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** El botón de editar (ícono lápiz) y su modal, mismo criterio de armado que
 *  `ItemCreateDialog`: reutiliza `ItemFormFields` y agrega lo que el alta no
 *  tiene -- el switch «Activo» -- y lo que la edición sí necesita: precargar
 *  todo desde `item` y mandar `PUT` en vez de `POST`. */
function ItemEditDialog({
  item, units, categories, onSaved, onClose,
}: { item: CatalogItem; units: Unit[]; categories: Category[]; onSaved: () => void; onClose: () => void }) {
  const [name, setName] = useState(item.name)
  const [unitCode, setUnitCode] = useState(item.unit_code)
  const [categoryId, setCategoryId] = useState(item.category_id ? String(item.category_id) : '')
  const [salePrice, setSalePrice] = useState(item.default_sale_price)
  const [cost, setCost] = useState(item.default_cost)
  const [active, setActive] = useState(item.active)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    if (!name.trim() || !unitCode) {
      setError('Nombre y unidad son obligatorios.')
      return
    }
    const precioVenta = parsePrecio(salePrice)
    const costoValor = parsePrecio(cost)
    if (precioVenta === null || costoValor === null) {
      setError('Precio y costo tienen que ser números válidos, no negativos.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.put(`/catalog/items/${item.id}`, {
        name: name.trim(), unit_code: unitCode,
        category_id: categoryId ? Number(categoryId) : null,
        description: item.description, active,
        sellable: item.sellable, purchasable: item.purchasable,
        default_sale_price: String(precioVenta), default_cost: String(costoValor),
      })
      onSaved()
      onClose()
    } catch (err) {
      // Mismo criterio que el alta: el error se queda adentro del modal, que
      // es donde está lo que se estaba editando. Acá es también donde llega
      // el 409 de la unidad bloqueada por movimientos (services/catalog.py).
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar producto</DialogTitle>
        </DialogHeader>

        <div className="grid gap-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <ItemFormFields
            units={units} categories={categories}
            name={name} setName={setName}
            unitCode={unitCode} setUnitCode={setUnitCode}
            categoryId={categoryId} setCategoryId={setCategoryId}
            salePrice={salePrice} setSalePrice={setSalePrice}
            cost={cost} setCost={setCost}
          />
          <div className="flex items-center gap-2">
            <Switch id="item-active" checked={active} onCheckedChange={setActive} />
            <Label htmlFor="item-active">Activo</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
              <BadgeEstado key={c.id} tono={c.is_primary ? 'ok' : 'neutro'}>
                {ITEM_CODE_TYPE_LABELS[c.code_type]}: {c.code}
              </BadgeEstado>
            ))}
          </div>
          <div className="flex items-end gap-2">
            <div className="grid gap-2">
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
            <div className="grid gap-2 flex-1">
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
            <div className="grid gap-2">
              <Label>SKU</Label>
              <Input value={variantSku} onChange={(e) => setVariantSku(e.target.value)} className="w-32" />
            </div>
            <div className="grid gap-2 flex-1">
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

export function Productos() {
  const [items, setItems] = useState<CatalogItem[]>([])
  const [units, setUnits] = useState<Unit[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [detailItem, setDetailItem] = useState<CatalogItem | null>(null)
  const [editItem, setEditItem] = useState<CatalogItem | null>(null)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [itemList, unitList, categoryList] = await Promise.all([
        api.get<CatalogItem[]>('/catalog/items'),
        // Sigue cargándose acá aunque ya no se muestre: el alta de producto
        // la necesita (el `Select` de Unidad, más abajo). El listado y el
        // alta de unidades pasaron a Configuración -- ver ConfigUnidades.tsx.
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
        <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </BadgeEstado>
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
          <Button size="icon" variant="outline" title="Editar producto" aria-label="Editar producto" onClick={() => setEditItem(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" title="Gestionar códigos y variantes" aria-label="Gestionar códigos y variantes" onClick={() => setDetailItem(row.original)}><Barcode /></Button>
        </div>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Package}>Productos</TituloPantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
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
            <ItemCreateDialog units={units} categories={categories} onCreated={loadAll} />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={items} emptyMessage="Sin productos todavía." />
          )}
        </CardContent>
      </Card>

      {detailItem && <ItemDetailDialog item={detailItem} onClose={() => setDetailItem(null)} />}
      {editItem && (
        <ItemEditDialog
          item={editItem} units={units} categories={categories}
          onSaved={loadAll} onClose={() => setEditItem(null)}
        />
      )}
    </div>
  )
}
