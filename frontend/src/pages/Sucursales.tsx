import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Location } from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Pencil, Plus, Star, Warehouse } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

// `location_type` se guarda con el código de siempre (`store`/`warehouse`):
// es lo que ya tienen las bases de los clientes y lo que siembra el demo. En
// pantalla nunca se ve el código, sólo la palabra.
type Tipo = 'store' | 'warehouse'
const TIPOS: { value: string; label: string }[] = [
  { value: 'store', label: 'Sucursal' },
  { value: 'warehouse', label: 'Depósito' },
]

function etiquetaTipo(tipo: string): string {
  return TIPOS.find((t) => t.value === tipo)?.label ?? tipo
}

// Cualquier tipo que no sea `store` cae en "Depósitos": el default del
// backend es `warehouse`, y un valor viejo escrito a mano no tiene que
// desaparecer de la pantalla.
function pestanaDe(tipo: string): Tipo {
  return tipo === 'store' ? 'store' : 'warehouse'
}

type Form = {
  name: string
  location_type: string
  is_default: boolean
  active: boolean
}

function formDe(loc: Location): Form {
  return {
    // Un tipo viejo (ni `store` ni `warehouse`) se muestra como depósito, que
    // es donde la pantalla ya lo lista: se elige entre los dos y se guarda.
    name: loc.name, location_type: pestanaDe(loc.location_type),
    is_default: loc.is_default, active: loc.active,
  }
}

export function Sucursales() {
  // Alta y edición sólo para admin (el backend las rechaza con 403 a staff,
  // igual que las cajas): al cajero no se le ofrecen, sólo ve la lista.
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [locations, setLocations] = useState<Location[]>([])
  const [pestana, setPestana] = useState<Tipo>('store')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Un solo diálogo para alta y edición: abierto con `editando === null` es
  // un alta.
  const [abierto, setAbierto] = useState(false)
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

  function abrirAlta() {
    // El tipo arranca en el de la pestaña que se está mirando.
    setEditando(null)
    setForm({ name: '', location_type: pestana, is_default: false, active: true })
    setFormError(null)
    setAbierto(true)
  }

  function abrirEdicion(loc: Location) {
    setEditando(loc)
    setForm(formDe(loc))
    setFormError(null)
    setAbierto(true)
  }

  function cerrar() {
    setAbierto(false)
    setEditando(null)
    setForm(null)
  }

  async function guardar() {
    if (!form) return
    if (!form.name.trim()) { setFormError('El nombre es obligatorio.'); return }
    if (!form.location_type.trim()) { setFormError('El tipo es obligatorio.'); return }
    setGuardando(true)
    setFormError(null)
    try {
      if (editando) {
        await api.put(`/locations/${editando.id}`, {
          name: form.name.trim(), location_type: form.location_type.trim(),
          is_default: form.is_default, active: form.active,
        })
      } else {
        await api.post('/locations', { name: form.name.trim(), location_type: form.location_type })
      }
      // Lo recién creado o editado queda a la vista, en su pestaña.
      setPestana(pestanaDe(form.location_type))
      cerrar()
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

  const sucursales = locations.filter((l) => pestanaDe(l.location_type) === 'store')
  const depositos = locations.filter((l) => pestanaDe(l.location_type) === 'warehouse')


  function tabla(filas: Location[], vacio: string) {
    return (
      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={filas} emptyMessage={vacio} />
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <TituloPantalla icono={Warehouse}>Sucursales / depósitos</TituloPantalla>
        {esAdmin && (
          <Button onClick={abrirAlta}>
            <Plus />{pestana === 'store' ? 'Nueva sucursal' : 'Nuevo depósito'}
          </Button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Tabs value={pestana} onValueChange={(v) => setPestana(v as Tipo)}>
        <TabsList>
          <TabsTrigger value="store">Sucursales ({sucursales.length})</TabsTrigger>
          <TabsTrigger value="warehouse">Depósitos ({depositos.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="store">{tabla(sucursales, 'Sin sucursales todavía.')}</TabsContent>
        <TabsContent value="warehouse">{tabla(depositos, 'Sin depósitos todavía.')}</TabsContent>
      </Tabs>

      <Dialog open={abierto} onOpenChange={(open) => { if (!open) cerrar() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editando
                ? `Editar ${etiquetaTipo(editando.location_type).toLowerCase()}`
                : 'Nueva sucursal / depósito'}
            </DialogTitle>
          </DialogHeader>
          {form && (
            <div className="grid gap-3">
              <div className="grid gap-2">
                <Label htmlFor="location-name">Nombre</Label>
                <Input
                  id="location-name" value={form.name} autoFocus
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="location-type">Tipo</Label>
                <Select value={form.location_type} onValueChange={(v) => setForm({ ...form, location_type: v })}>
                  <SelectTrigger id="location-type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIPOS.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {editando && (
                <>
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
                </>
              )}
              {formError && <p className="text-sm text-destructive" role="alert">{formError}</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={cerrar}>Cancelar</Button>
            <Button onClick={guardar} disabled={guardando}>
              {guardando ? 'Guardando…' : editando ? 'Guardar' : 'Crear'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
