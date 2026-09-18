// Unidades de medida, como sección de Configuración. Hasta el 2026-09-17 esto
// era la pestaña "Unidades" de Catálogo (hoy `Productos.tsx`); el humano
// pidió moverla acá -- las unidades son un dato de configuración del negocio
// (se cargan una vez y casi no cambian), no algo que se mire seguido como el
// listado de productos. Los endpoints (`/catalog/units`) no cambiaron.
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Unit } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DataTable, sortableHeader } from '@/components/data-table'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

/** El botón "+ Nueva unidad" y su modal -- misma forma que el alta de
 *  producto de `Productos.tsx` (ver el comentario de aquél para por qué el
 *  botón y el `Dialog` van en el mismo componente). */
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

export function ConfigUnidades() {
  const [units, setUnits] = useState<Unit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setUnits(await api.get<Unit[]>('/catalog/units'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  // Mismo patron de anchos que la tabla de productos: fijos al contenido real
  // y Nombre elastica.
  const columns = useMemo<ColumnDef<Unit>[]>(() => [
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

  return (
    <div className="grid max-w-3xl gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-end">
            <UnitCreateDialog onCreated={load} />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={units} emptyMessage="Sin unidades todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
