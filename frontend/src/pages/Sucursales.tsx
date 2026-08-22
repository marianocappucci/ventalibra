import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Location } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Warehouse } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function Sucursales() {
  const [locations, setLocations] = useState<Location[]>([])
  const [name, setName] = useState('')
  const [locationType, setLocationType] = useState('warehouse')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setLocations(await api.get<Location[]>('/locations'))
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

  const columns = useMemo<ColumnDef<Location>[]>(() => [
    { accessorKey: 'name', header: sortableHeader('Nombre'), cell: ({ row }) => <span className="font-medium">{row.original.name}</span> },
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
  ], [])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Warehouse}>Sucursales / depósitos</TituloPantalla>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nueva sucursal</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label>Nombre</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
            </div>
            <div className="grid gap-1.5">
              <Label>Tipo</Label>
              <Input value={locationType} onChange={(e) => setLocationType(e.target.value)} className="w-32" placeholder="warehouse" />
            </div>
            <Button onClick={handleCreate} disabled={saving}>{saving ? 'Creando…' : 'Crear'}</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={locations} emptyMessage="Sin sucursales todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
