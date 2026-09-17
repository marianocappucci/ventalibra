// Categorías de producto, como sección de Configuración -- mismo lugar que
// Unidades de medida (`ConfigUnidades.tsx`, que sirvió de modelo de forma) y
// por el mismo motivo: se cargan una vez y casi no cambian, no es algo que se
// mire seguido como el listado de Productos.
//
// A diferencia de Unidades, acá SÍ hay edición (`PUT /catalog/categories/{id}`,
// ver `app/routers/catalog.py`): nombre y estado activa/inactiva. Por eso el
// modal de edición sigue el patrón de `ItemEditDialog` de `Productos.tsx`
// (precarga + `Switch` de estado) y no el de `UnitCreateDialog`, que sólo da
// de alta.
//
// `GET /catalog/categories` devuelve TODAS las categorías, activas e
// inactivas (ver `CatalogService.list_categories`): esta pantalla necesita
// ver -y poder reactivar- las inactivas. Que el alta/edición de producto sólo
// ofrezca las activas es un filtro que hace `Productos.tsx`, no el backend.
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Category } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Pencil } from 'lucide-react'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

/** El botón "+ Nueva categoría" y su modal -- misma forma que
 *  `UnitCreateDialog` de `ConfigUnidades.tsx`. */
function CategoryCreateDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Abrir SIEMPRE limpia, igual que el resto de los altas de la familia. */
  function abrir() {
    setName('')
    setError(null)
    setOpen(true)
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post('/catalog/categories', { name: name.trim() })
      setOpen(false)
      onCreated()
    } catch (err) {
      // El error se queda adentro del modal -- acá llega el 422 de nombre
      // repetido (services/catalog.py::_validar_category_name).
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button onClick={abrir}>+ Nueva categoría</Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva categoría</DialogTitle>
          </DialogHeader>

          <div className="grid gap-3">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="grid gap-2">
              <Label htmlFor="category-name">Nombre</Label>
              <Input id="category-name" value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="Bebidas, Almacén…" />
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

/** El botón de editar (ícono lápiz) y su modal: nombre y estado. Mismo
 *  criterio de armado que `ItemEditDialog` de `Productos.tsx` -- precarga
 *  desde `category` y manda `PUT` en vez de `POST`. */
function CategoryEditDialog({
  category, onSaved, onClose,
}: { category: Category; onSaved: () => void; onClose: () => void }) {
  const [name, setName] = useState(category.name)
  const [active, setActive] = useState(category.active)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    if (!name.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.put(`/catalog/categories/${category.id}`, { name: name.trim(), active })
      onSaved()
      onClose()
    } catch (err) {
      // Mismo criterio que el alta: el error se queda adentro del modal.
      // Acá llega también el 422 de nombre repetido contra otra categoría
      // activa.
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar categoría</DialogTitle>
        </DialogHeader>

        <div className="grid gap-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="grid gap-2">
            <Label htmlFor="category-edit-name">Nombre</Label>
            <Input id="category-edit-name" value={name} autoFocus onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="category-active" checked={active} onCheckedChange={setActive} />
            <Label htmlFor="category-active">Activa</Label>
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

export function ConfigCategorias() {
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editCategory, setEditCategory] = useState<Category | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setCategories(await api.get<Category[]>('/catalog/categories'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  // Mismo patron de anchos que ConfigUnidades: fijos al contenido real y
  // Nombre elastica.
  const columns = useMemo<ColumnDef<Category>[]>(() => [
    { accessorKey: 'name', header: sortableHeader('Nombre'), size: 240, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate" title={row.original.name}>{row.original.name}</span> },
    {
      accessorKey: 'active',
      header: 'Estado',
      size: 110,
      minSize: 95,
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
          {row.original.active ? 'Activa' : 'Inactiva'}
        </BadgeEstado>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Button size="icon" variant="outline" title="Editar categoría" aria-label="Editar categoría" onClick={() => setEditCategory(row.original)}><Pencil /></Button>
        </div>
      ),
    },
  ], [])

  return (
    <div className="grid max-w-3xl gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-end">
            <CategoryCreateDialog onCreated={load} />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={categories} emptyMessage="Sin categorías todavía." />
          )}
        </CardContent>
      </Card>

      {editCategory && (
        <CategoryEditDialog category={editCategory} onSaved={load} onClose={() => setEditCategory(null)} />
      )}
    </div>
  )
}
