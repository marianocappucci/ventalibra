import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
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
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '@/components/ui/tabs'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Barcode, Package, Ruler } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** El botón "+ Nueva unidad" y su modal, misma forma que el de producto de acá
 *  abajo — ver el comentario de aquél para por qué el botón y el `Dialog` van
 *  en el mismo componente.
 *
 *  Las dos altas del catálogo empezaron distintas: la de producto pasó a modal
 *  el 2026-08-23 y ésta se quedó en tarjeta, con el argumento de que son tres
 *  campos que se cargan de a varios seguidos al arrancar. El humano lo decidió
 *  al revés el 2026-08-24, y la pantalla gana en que las dos pestañas se usan
 *  igual: el botón está en el mismo lugar y hace lo mismo. */
function UnitCreateDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [allowsFraction, setAllowsFraction] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Abrir SIEMPRE limpia, igual que el alta de producto. */
  function abrir() {
    setCode('')
    setName('')
    setAllowsFraction(false)
    setError(null)
    setOpen(true)
  }

  async function handleCreate() {
    if (!code.trim() || !name.trim()) {
      // 🔴 Antes esto era un `return` mudo. En una tarjeta a la vista se
      // perdonaba —los dos campos vacíos están ahí, delante—; detrás de un
      // modal es apretar "Crear" y que no pase nada, sin nada que mirar.
      setError('Código y nombre son obligatorios.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post('/catalog/units', {
        code: code.trim(), name: name.trim(), allows_fraction: allowsFraction,
        decimal_scale: allowsFraction ? 3 : 0,
      })
      setOpen(false)
      onCreated()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button onClick={abrir}>+ Nueva unidad</Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva unidad</DialogTitle>
          </DialogHeader>

          <div className="grid gap-3">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="grid gap-2">
              <Label htmlFor="unit-code">Código</Label>
              <Input id="unit-code" value={code} autoFocus onChange={(e) => setCode(e.target.value)} placeholder="u, kg…" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="unit-name">Nombre</Label>
              <Input id="unit-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Unidad, Kilogramo…" />
            </div>
            {/* El `<label>` envuelve a su casilla, así que no necesita
                `htmlFor`: la asociación la da el anidado. */}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={allowsFraction} onChange={(e) => setAllowsFraction(e.target.checked)} />
              Se vende por fracción (peso/volumen)
            </label>
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
              input sin nombre. Es el mismo par que usan el alta de unidad de
              acá arriba y las de Pos/CuentasCorrientes. La Categoría no lo
              necesita: se nombra sola con el `ariaLabel` de `SelectBuscable`. */}
          <div className="grid gap-3">
            {error && <p className="text-sm text-destructive">{error}</p>}
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

  // Mismo patron de anchos que la tabla de productos: fijos al contenido real
  // y Nombre elastica.
  const unitColumns = useMemo<ColumnDef<Unit>[]>(() => [
    { accessorKey: 'code', header: sortableHeader('Código'), size: 110, minSize: 90, cell: ({ row }) => <span className="font-medium">{row.original.code}</span> },
    { accessorKey: 'name', header: sortableHeader('Nombre'), size: 240, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate" title={row.original.name}>{row.original.name}</span> },
    {
      accessorKey: 'allows_fraction',
      // El rotulo largo ("se vende por fraccion") es el de la casilla del
      // formulario; en la tabla no entra, y la columna de al lado —los
      // decimales que esa casilla habilita— termina de decir de que se trata.
      header: 'Fracción',
      size: 110,
      minSize: 95,
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.allows_fraction ? 'ok' : 'neutro'}>
          {row.original.allows_fraction ? 'Sí' : 'No'}
        </BadgeEstado>
      ),
    },
    { accessorKey: 'decimal_scale', header: 'Decimales', size: 110, minSize: 95 },
  ], [])

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
          <Button size="icon" variant="outline" title="Gestionar códigos y variantes" aria-label="Gestionar códigos y variantes" onClick={() => setDetailItem(row.original)}><Barcode /></Button>
        </div>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Package}>Catálogo</TituloPantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Las dos mitades del catálogo, cada una con su listado y su alta.
          Unidades va primero porque un producto no se puede cargar sin una,
          pero la que abre es Productos: es lo que se mira todos los días, y es
          lo que esta pantalla mostraba antes de las pestañas.

          Las dos altas son un botón `+ Nueva …` en el encabezado de su tarjeta
          y un modal detrás: la de producto desde el 2026-08-23, la de unidad
          desde el 2026-08-24, las dos por pedido del humano. **Que sean iguales
          es la gracia**: el botón está en el mismo lugar en las dos pestañas y
          hace lo mismo, así que cambiar de pestaña no cambia cómo se opera.

          El nombre de la pestaña NO se repite en un `CardHeader` adentro —
          mismo criterio que la pantalla de Logs, que usa este mismo `Tabs`. */}
      <Tabs defaultValue="productos" className="gap-4">
        <TabsList>
          <TabsTrigger value="unidades">
            <Ruler className="size-4" />Unidades
          </TabsTrigger>
          <TabsTrigger value="productos">
            <Package className="size-4" />Productos
          </TabsTrigger>
        </TabsList>

        <TabsContent value="unidades" className="grid gap-4">
          <Card>
            {/* El botón va a la derecha, en la misma posición que el de
                Productos —que la tiene porque a su izquierda está el buscador—.
                Acá no hay buscador y el encabezado queda con el botón solo:
                eso es preferible a moverlo, porque el ojo lo busca donde
                estaba al cambiar de pestaña. */}
            <CardHeader>
              <div className="flex items-center justify-end">
                <UnitCreateDialog onCreated={loadAll} />
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
              ) : (
                <DataTable columns={unitColumns} data={units} emptyMessage="Sin unidades todavía." />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="productos" className="grid gap-4">
          <Card>
            {/* El alta va acá y no arriba del todo, al lado del título de la
                pantalla: el título es "Catálogo" y el botón es sólo de esta
                pestaña — en Unidades no tendría nada que hacer. */}
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
        </TabsContent>
      </Tabs>

      {detailItem && <ItemDetailDialog item={detailItem} onClose={() => setDetailItem(null)} />}
    </div>
  )
}
