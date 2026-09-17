import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Location } from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Pencil, Star, Warehouse } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

type Form = {
  name: string
  location_type: string
  is_default: boolean
  active: boolean
}

function formDe(loc: Location): Form {
  return {
    name: loc.name, location_type: loc.location_type,
    is_default: loc.is_default, active: loc.active,
  }
}

export function Sucursales() {
  // Alta y edición sólo para admin (el backend las rechaza con 403 a staff,
  // igual que las cajas): al cajero no se le ofrecen, sólo ve la lista.
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [locations, setLocations] = useState<Location[]>([])
  const [name, setName] = useState('')
  const [locationType, setLocationType] = useState('warehouse')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [editando, setEditando] = useState<Location | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      // `incluir_inactivas`: a diferencia del POS (que sólo necesita ver las
      // activas para vender), esta pantalla es la única forma de REACTIVAR
      // una sucursal dada de baja -- sin esto, apenas se desactiva una
      // desaparece de la lista y no hay cómo volver atrás.
      setLocations(await api.get<Location[]>('/locations?incluir_inactivas=true'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate() {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await api.post('/locations', { name: name.trim(), location_type: locationType })
      setName('')
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  function abrirEdicion(loc: Location) {
    setEditando(loc)
    setForm(formDe(loc))
    setFormError(null)
  }

  async function guardarEdicion() {
    if (!editando || !form) return
    if (!form.name.trim()) { setFormError('El nombre es obligatorio.'); return }
    if (!form.location_type.trim()) { setFormError('El tipo es obligatorio.'); return }
    setGuardando(true)
    setFormError(null)
    try {
      await api.put(`/locations/${editando.id}`, {
        name: form.name.trim(), location_type: form.location_type.trim(),
        is_default: form.is_default, active: form.active,
      })
      setEditando(null)
      setForm(null)
      await load()
    } catch (err) {
      // El 409 (default/turno abierto) y el 422 (nombre/tipo vacío) del
      // backend se muestran tal cual -- son mensajes pensados para leerse.
      setFormError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  const columns = useMemo<ColumnDef<Location>[]>(() => [
    {
      accessorKey: 'name',
      header: sortableHeader('Nombre'),
      cell: ({ row }) => (
        <span className="flex items-center gap-1.5 font-medium">
          {row.original.is_default && <Star className="size-3.5 fill-amber-400 text-amber-400" />}
          {row.original.name}
        </span>
      ),
    },
    { accessorKey: 'location_type', header: 'Tipo' },
    {
      accessorKey: 'active',
      header: 'Estado',
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
          {row.original.active ? 'Activa' : 'Inactiva'}
        </BadgeEstado>
      ),
    },
    {
      id: 'acciones',
      header: '',
      cell: ({ row }) => esAdmin ? (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => abrirEdicion(row.original)}>
            <Pencil />Editar
          </Button>
        </div>
      ) : null,
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [esAdmin])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Warehouse}>Sucursales / depósitos</TituloPantalla>

      {esAdmin && (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nueva sucursal</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-2">
              <Label>Nombre</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
            </div>
            <div className="grid gap-2">
              <Label>Tipo</Label>
              <Input value={locationType} onChange={(e) => setLocationType(e.target.value)} className="w-32" placeholder="warehouse" />
            </div>
            <Button onClick={handleCreate} disabled={saving}>{saving ? 'Creando…' : 'Crear'}</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>
      )}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={locations} emptyMessage="Sin sucursales todavía." />
          )}
        </CardContent>
      </Card>

      <Dialog open={editando !== null} onOpenChange={(open) => { if (!open) { setEditando(null); setForm(null) } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar sucursal</DialogTitle>
          </DialogHeader>
          {form && (
            <div className="grid gap-3">
              <div className="grid gap-2">
                <Label htmlFor="edit-location-name">Nombre</Label>
                <Input
                  id="edit-location-name" value={form.name} autoFocus
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="edit-location-type">Tipo</Label>
                <Input
                  id="edit-location-type"
                  value={form.location_type}
                  onChange={(e) => setForm({ ...form, location_type: e.target.value })}
                  placeholder="warehouse"
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                  className="size-4"
                />
                Predeterminada
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })}
                  className="size-4"
                />
                Activa
              </label>
              {formError && <p className="text-sm text-destructive" role="alert">{formError}</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditando(null); setForm(null) }}>Cancelar</Button>
            <Button onClick={guardarEdicion} disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
