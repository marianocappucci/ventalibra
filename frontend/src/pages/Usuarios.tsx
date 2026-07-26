import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type User } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DataTable, sortableHeader } from '@/components/data-table'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

const EMPTY = { username: '', name: '', password: '', role: 'staff' }

export function Usuarios() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setUsers(await api.get<User[]>('/users'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setEditingId('new')
    setForm(EMPTY)
  }

  function startEdit(user: User) {
    setEditingId(user.id)
    setForm({ username: user.username, name: user.name, password: '', role: user.role })
  }

  function cancelEdit() {
    setEditingId(null)
    setForm(EMPTY)
  }

  async function handleSave() {
    if (!form.name.trim() || (editingId === 'new' && (!form.username.trim() || !form.password))) {
      setError('Completá los campos obligatorios.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (editingId === 'new') {
        await api.post('/users', {
          username: form.username.trim(), name: form.name.trim(),
          password: form.password, role: form.role,
        })
      } else if (editingId) {
        await api.put(`/users/${editingId}`, { name: form.name.trim(), role: form.role, active: true })
      }
      cancelEdit()
      await load()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDeactivate(user: User) {
    setError(null)
    try {
      await api.put(`/users/${user.id}`, { name: user.name, role: user.role, active: !user.active })
      await load()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<User>[]>(() => [
    { accessorKey: 'username', header: sortableHeader('Usuario') },
    { accessorKey: 'name', header: 'Nombre' },
    { accessorKey: 'role', header: 'Rol', cell: ({ row }) => <span className="capitalize">{row.original.role}</span> },
    {
      accessorKey: 'active',
      header: 'Estado',
      cell: ({ row }) => (
        <Badge variant={row.original.active ? 'default' : 'outline'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={() => startEdit(row.original)}>Editar</Button>
          <Button size="sm" variant="outline" onClick={() => handleDeactivate(row.original)}>
            {row.original.active ? 'Desactivar' : 'Activar'}
          </Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Usuarios</h2>
        {editingId === null && <Button onClick={startCreate}>+ Nuevo usuario</Button>}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nuevo usuario' : 'Editar usuario'}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-2">
            {editingId === 'new' && (
              <div className="grid gap-1.5">
                <Label>Usuario</Label>
                <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="w-40" />
              </div>
            )}
            <div className="grid gap-1.5">
              <Label>Nombre</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-48" />
            </div>
            {editingId === 'new' && (
              <div className="grid gap-1.5">
                <Label>Contraseña</Label>
                <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="w-40" />
              </div>
            )}
            <div className="grid gap-1.5">
              <Label>Rol</Label>
              <Select value={form.role} onValueChange={(role) => setForm({ ...form, role })}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="staff">Staff</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleSave} disabled={saving}>{saving ? 'Guardando…' : editingId === 'new' ? 'Crear' : 'Guardar'}</Button>
            <Button variant="outline" onClick={cancelEdit}>Cancelar</Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={users} emptyMessage="Sin usuarios todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
