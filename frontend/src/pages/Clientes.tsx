import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Customer } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Users } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const CONDICIONES_IVA = [
  'Responsable Inscripto',
  'Monotributista',
  'IVA Exento',
  'Consumidor Final',
  'No Alcanzado',
]

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function Clientes() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [cuit, setCuit] = useState('')
  const [condicionIva, setCondicionIva] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setCustomers(await api.get<Customer[]>('/customers'))
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
      await api.post('/customers', {
        display_name: name.trim(), party_type: 'person',
        email: email || null, phone: phone || null,
        cuit: cuit || null, condicion_iva: condicionIva || null,
      })
      setName('')
      setEmail('')
      setPhone('')
      setCuit('')
      setCondicionIva('')
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const columns = useMemo<ColumnDef<Customer>[]>(() => [
    { accessorKey: 'display_name', header: sortableHeader('Nombre'), cell: ({ row }) => <span className="font-medium">{row.original.display_name}</span> },
    { accessorKey: 'cuit', header: 'CUIT', cell: ({ row }) => row.original.cuit ?? '—' },
    { accessorKey: 'condicion_iva', header: 'Condición IVA', cell: ({ row }) => row.original.condicion_iva ?? '—' },
    { accessorKey: 'email', header: 'Email', cell: ({ row }) => row.original.email ?? '—' },
    {
      accessorKey: 'active',
      header: 'Estado',
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </BadgeEstado>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Users}>Clientes</TituloPantalla>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nuevo cliente</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label>Nombre</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
            </div>
            <div className="grid gap-1.5">
              <Label>CUIT</Label>
              <Input value={cuit} onChange={(e) => setCuit(e.target.value)} className="w-36" />
            </div>
            <div className="grid gap-1.5">
              <Label>Condición de IVA</Label>
              <Select value={condicionIva} onValueChange={setCondicionIva}>
                <SelectTrigger className="w-52"><SelectValue placeholder="Condición de IVA…" /></SelectTrigger>
                <SelectContent>
                  {CONDICIONES_IVA.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>Email</Label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-52" />
            </div>
            <div className="grid gap-1.5">
              <Label>Teléfono</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="w-40" />
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
            <DataTable columns={columns} data={customers} emptyMessage="Sin clientes todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
