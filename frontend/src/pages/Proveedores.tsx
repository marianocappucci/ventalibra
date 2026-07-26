import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Supplier } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { DataTable, sortableHeader } from '@/components/data-table'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function Proveedores() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [name, setName] = useState('')
  const [taxId, setTaxId] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setSuppliers(await api.get<Supplier[]>('/suppliers'))
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
      await api.post('/suppliers', {
        display_name: name.trim(), party_type: 'organization',
        tax_id: taxId || null, email: email || null, phone: phone || null,
      })
      setName('')
      setTaxId('')
      setEmail('')
      setPhone('')
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const columns = useMemo<ColumnDef<Supplier>[]>(() => [
    { accessorKey: 'display_name', header: sortableHeader('Nombre'), cell: ({ row }) => <span className="font-medium">{row.original.display_name}</span> },
    { accessorKey: 'tax_id', header: 'CUIT', cell: ({ row }) => row.original.tax_id ?? '—' },
    { accessorKey: 'email', header: 'Email', cell: ({ row }) => row.original.email ?? '—' },
    { accessorKey: 'phone', header: 'Teléfono', cell: ({ row }) => row.original.phone ?? '—' },
    {
      accessorKey: 'active',
      header: 'Estado',
      cell: ({ row }) => (
        <Badge variant={row.original.active ? 'default' : 'outline'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </Badge>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Proveedores</h2>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nuevo proveedor</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label>Nombre</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
            </div>
            <div className="grid gap-1.5">
              <Label>CUIT</Label>
              <Input value={taxId} onChange={(e) => setTaxId(e.target.value)} className="w-36" />
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
            <DataTable columns={columns} data={suppliers} emptyMessage="Sin proveedores todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
