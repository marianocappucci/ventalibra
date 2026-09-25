// ABM de cajas por sucursal (2026-09-16). Admin: alta, edición, baja y
// marcar predeterminada. La lectura (staff y admin) vive en el POS, al abrir
// turno -- acá es la pantalla de configuración del local.
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Caja, type Location } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Landmark, Star } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { useMediosPago } from '@/lib/medios-pago'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

type Form = {
  nombre: string
  descripcion: string
  medios_pago: string[]
  punto_venta: string
  mp_pos_id: string
  sucursal_id: string
  activo: boolean
}

const FORM_VACIO: Form = {
  nombre: '', descripcion: '', medios_pago: [], punto_venta: '', mp_pos_id: '', sucursal_id: '', activo: true,
}

export function Cajas() {
  const [locations, setLocations] = useState<Location[]>([])
  const [cajas, setCajas] = useState<Caja[]>([])
  const [sucursalFiltro, setSucursalFiltro] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Caja | null>(null)
  const [form, setForm] = useState<Form>(FORM_VACIO)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const { medios } = useMediosPago()

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [locs, cjs] = await Promise.all([
        api.get<Location[]>('/locations'),
        api.get<Caja[]>('/api/cajas'),
      ])
      setLocations(locs)
      setCajas(cjs)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const nombreSucursal = useMemo(() => {
    const m = new Map(locations.map((l) => [l.id, l.name]))
    return (id: number | null) => (id !== null ? m.get(id) ?? `#${id}` : 'Sin sucursal')
  }, [locations])

  const filtradas = useMemo(
    () => (sucursalFiltro ? cajas.filter((c) => String(c.sucursal_id) === sucursalFiltro) : cajas),
    [cajas, sucursalFiltro],
  )

  function abrirAlta() {
    setEditando(null)
    setForm({ ...FORM_VACIO, sucursal_id: sucursalFiltro || String(locations[0]?.id ?? '') })
    setFormError(null)
    setDialogOpen(true)
  }

  function abrirEdicion(caja: Caja) {
    setEditando(caja)
    setForm({
      nombre: caja.nombre, descripcion: caja.descripcion, medios_pago: caja.medios_pago,
      punto_venta: caja.punto_venta !== null ? String(caja.punto_venta) : '',
      mp_pos_id: caja.mp_pos_id ?? '',
      sucursal_id: String(caja.sucursal_id ?? ''), activo: caja.activo,
    })
    setFormError(null)
    setDialogOpen(true)
  }

  function alternarMedio(id: string) {
    setForm((f) => ({
      ...f,
      medios_pago: f.medios_pago.includes(id)
        ? f.medios_pago.filter((m) => m !== id)
        : [...f.medios_pago, id],
    }))
  }

  async function guardar() {
    if (!form.nombre.trim()) { setFormError('El nombre es obligatorio.'); return }
    setSaving(true)
    setFormError(null)
    const puntoVenta = form.punto_venta.trim() ? Number(form.punto_venta.trim()) : null
    try {
      if (editando) {
        await api.put(`/api/cajas/${editando.id}`, {
          nombre: form.nombre.trim(), descripcion: form.descripcion.trim(),
          medios_pago: form.medios_pago, punto_venta: puntoVenta, activo: form.activo,
          mp_pos_id: form.mp_pos_id.trim() || null,
        })
      } else {
        await api.post('/api/cajas', {
          nombre: form.nombre.trim(), descripcion: form.descripcion.trim(),
          medios_pago: form.medios_pago, punto_venta: puntoVenta,
          mp_pos_id: form.mp_pos_id.trim() || null,
          sucursal_id: Number(form.sucursal_id),
        })
      }
      setDialogOpen(false)
      await load()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function marcarPredeterminada(caja: Caja) {
    try {
      await api.post(`/api/cajas/${caja.id}/predeterminada`, {})
      await load()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function borrar(caja: Caja) {
    if (!confirm(`¿Dar de baja la caja "${caja.nombre}"?`)) return
    try {
      await api.del(`/api/cajas/${caja.id}`)
      await load()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Caja>[]>(() => [
    {
      accessorKey: 'nombre',
      header: sortableHeader('Nombre'),
      cell: ({ row }) => (
        <span className="flex items-center gap-1.5 font-medium">
          {row.original.es_default && <Star className="size-3.5 fill-amber-400 text-amber-400" />}
          {row.original.nombre}
        </span>
      ),
    },
    {
      accessorKey: 'sucursal_id',
      header: 'Sucursal',
      cell: ({ row }) => nombreSucursal(row.original.sucursal_id),
    },
    {
      accessorKey: 'punto_venta',
      header: 'Punto de venta',
      cell: ({ row }) => row.original.punto_venta ?? <span className="text-muted-foreground">de la empresa</span>,
    },
    {
      accessorKey: 'activo',
      header: 'Estado',
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.activo ? 'ok' : 'neutro'}>
          {row.original.activo ? 'Activa' : 'Inactiva'}
        </BadgeEstado>
      ),
    },
    {
      id: 'acciones',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end gap-2">
          {!row.original.es_default && (
            <Button size="sm" variant="ghost" onClick={() => marcarPredeterminada(row.original)}>
              Marcar predeterminada
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => abrirEdicion(row.original)}>Editar</Button>
          <Button size="sm" variant="outline" className="text-destructive" onClick={() => borrar(row.original)}>
            Baja
          </Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nombreSucursal])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Landmark}>Cajas</TituloPantalla>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Mostradores</CardTitle>
          <div className="flex items-center gap-2">
            <Select value={sucursalFiltro || 'todas'} onValueChange={(v) => setSucursalFiltro(v === 'todas' ? '' : v)}>
              <SelectTrigger className="h-8 w-56" aria-label="Filtrar por sucursal">
                <SelectValue placeholder="Todas las sucursales" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas las sucursales</SelectItem>
                {locations.map((l) => (
                  <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={abrirAlta} disabled={locations.length === 0}>Nueva caja</Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={filtradas} emptyMessage="Sin cajas para esta sucursal." />
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editando ? 'Editar caja' : 'Nueva caja'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            {!editando && (
              <div className="grid gap-2">
                <Label>Sucursal</Label>
                <Select value={form.sucursal_id} onValueChange={(v) => setForm((f) => ({ ...f, sucursal_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Elegí una sucursal…" /></SelectTrigger>
                  <SelectContent>
                    {locations.map((l) => (
                      <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="grid gap-2">
              <Label>Nombre</Label>
              <Input value={form.nombre} onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label>Descripción</Label>
              <Input value={form.descripcion} onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label>Punto de venta de ARCA (opcional)</Label>
              <Input
                value={form.punto_venta}
                onChange={(e) => setForm((f) => ({ ...f, punto_venta: e.target.value }))}
                placeholder="Vacío = el de la empresa"
                inputMode="numeric"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="caja-mp-pos-id">ID del POS de MercadoPago (opcional)</Label>
              <Input
                id="caja-mp-pos-id"
                value={form.mp_pos_id}
                onChange={(e) => setForm((f) => ({ ...f, mp_pos_id: e.target.value }))}
                placeholder="Ej.: BIOKOCAJA01"
              />
            </div>
            <div className="grid gap-2">
              <Label>Medios de pago</Label>
              <div className="grid grid-cols-2 gap-2">
                {medios.map((m) => (
                  <label key={m.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.medios_pago.includes(m.id)}
                      onChange={() => alternarMedio(m.id)}
                      className="size-4"
                    />
                    {m.label}
                  </label>
                ))}
              </div>
            </div>
            {editando && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                  className="size-4"
                />
                Activa
              </label>
            )}
            {formError && <p className="text-sm text-destructive">{formError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button onClick={guardar} disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
