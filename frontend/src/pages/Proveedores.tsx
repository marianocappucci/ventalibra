import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Supplier } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Plus, Truck } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

type Form = { name: string; taxId: string; email: string; phone: string }

const FORM_VACIO: Form = { name: '', taxId: '', email: '', phone: '' }

export function Proveedores() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // El alta pasó de un formulario suelto arriba de la lista a un modal, igual
  // que Sucursales (#295): la pantalla se abre para MIRAR proveedores, y el
  // formulario permanente empujaba la lista hacia abajo en todas las visitas.
  const [abierto, setAbierto] = useState(false)
  const [form, setForm] = useState<Form>(FORM_VACIO)
  const [guardando, setGuardando] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

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

  function abrirAlta() {
    setForm(FORM_VACIO)
    setFormError(null)
    setAbierto(true)
  }

  function cerrar() {
    setAbierto(false)
    // 📌 Este `setForm(FORM_VACIO)` es la SEGUNDA de dos guardas para lo
    // mismo: `abrirAlta` también limpia, y es esa la que el test observa
    // —el formulario sólo se ve con el modal abierto—. Medido por mutación
    // el 2026-09-21: aflojando sólo una de las dos, `cancelar cierra el modal
    // y descarta lo escrito` sigue en VERDE; hay que voltear las dos. Se deja
    // igual para no dejar el borrador colgado en memoria, pero conviene saber
    // que ningún test lo custodia por separado.
    setForm(FORM_VACIO)
    setFormError(null)
  }

  async function guardar() {
    if (!form.name.trim()) {
      setFormError('El nombre es obligatorio.')
      return
    }
    setGuardando(true)
    setFormError(null)
    try {
      await api.post('/suppliers', {
        display_name: form.name.trim(),
        party_type: 'organization',
        tax_id: form.taxId || null,
        email: form.email || null,
        phone: form.phone || null,
      })
      cerrar()
      await load()
    } catch (err) {
      // El error se muestra DENTRO del modal y el modal no se cierra: si se
      // cerrara, lo escrito se pierde y el mensaje aparece detrás, sobre una
      // lista que no cambió.
      setFormError(describeError(err))
    } finally {
      setGuardando(false)
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
        <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
          {row.original.active ? 'Activo' : 'Inactivo'}
        </BadgeEstado>
      ),
    },
  ], [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <TituloPantalla icono={Truck}>Proveedores</TituloPantalla>
        <Button onClick={abrirAlta}>
          <Plus />Nuevo proveedor
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={suppliers}
              emptyMessage="Sin proveedores todavía."
              // Mismo buscador que Clientes, con los mismos campos: las dos
              // pantallas son la misma cosa con otro nombre, y quien aprende a
              // buscar en una aprende en la otra. El teléfono entra aunque
              // también sea columna acá; el CUIT es lo que se tiene del papel.
              search={{
                campos: (s) => [s.display_name, s.tax_id, s.email, s.phone],
                placeholder: 'Buscar por nombre, CUIT, email o teléfono',
                ariaLabel: 'Buscar proveedor',
              }}
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={abierto} onOpenChange={(open) => { if (!open) cerrar() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo proveedor</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor="proveedor-nombre">Nombre</Label>
              <Input
                id="proveedor-nombre" value={form.name} autoFocus
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="proveedor-cuit">CUIT</Label>
              <Input
                id="proveedor-cuit" value={form.taxId}
                onChange={(e) => setForm({ ...form, taxId: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="proveedor-email">Email</Label>
              <Input
                id="proveedor-email" type="email" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="proveedor-telefono">Teléfono</Label>
              <Input
                id="proveedor-telefono" value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </div>
            {formError && <p className="text-sm text-destructive" role="alert">{formError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={cerrar}>Cancelar</Button>
            <Button onClick={guardar} disabled={guardando}>
              {guardando ? 'Creando…' : 'Crear'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
