import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ColumnDef } from 'libra-ui/data-table'
import { api, ApiError, type Customer } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Plus, Users } from 'lucide-react'
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

type Form = { name: string; cuit: string; condicionIva: string; email: string; phone: string }

const FORM_VACIO: Form = { name: '', cuit: '', condicionIva: '', email: '', phone: '' }

export function Clientes() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // El alta pasó de un formulario suelto arriba de la lista a un modal, igual
  // que Proveedores y Sucursales: la pantalla se abre para MIRAR clientes, y
  // el formulario permanente empujaba la lista hacia abajo en todas las
  // visitas, incluso cuando no se iba a dar de alta nada.
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
      setCustomers(await api.get<Customer[]>('/customers'))
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
      await api.post('/customers', {
        display_name: form.name.trim(),
        party_type: 'person',
        email: form.email || null,
        phone: form.phone || null,
        cuit: form.cuit || null,
        condicion_iva: form.condicionIva || null,
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

  const columns = useMemo<ColumnDef<Customer>[]>(() => [
    {
      accessorKey: 'display_name', header: sortableHeader('Nombre'),
      cell: ({ row }) => <Link className="font-medium underline-offset-4 hover:underline" to={`/clientes/${row.original.id}`}>{row.original.display_name}</Link>,
    },
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
      <div className="flex items-center justify-between">
        <TituloPantalla icono={Users}>Clientes</TituloPantalla>
        <Button onClick={abrirAlta}>
          <Plus />Nuevo cliente
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
              data={customers}
              emptyMessage="Sin clientes todavía."
              // La tabla no pagina: sin buscador, llegar a un cliente entre
              // cientos es scrollear. El teléfono entra en la búsqueda aunque
              // no sea columna -- es lo que queda anotado del mostrador; el
              // CUIT, lo que se tiene del papel.
              search={{
                campos: (c) => [c.display_name, c.cuit, c.email, c.phone],
                placeholder: 'Buscar por nombre, CUIT, email o teléfono',
                ariaLabel: 'Buscar cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={abierto} onOpenChange={(open) => { if (!open) cerrar() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo cliente</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor="cliente-nombre">Nombre</Label>
              <Input
                id="cliente-nombre" value={form.name} autoFocus
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cliente-cuit">CUIT</Label>
              <Input
                id="cliente-cuit" value={form.cuit}
                onChange={(e) => setForm({ ...form, cuit: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cliente-iva">Condición de IVA</Label>
              <Select
                value={form.condicionIva}
                onValueChange={(v) => setForm({ ...form, condicionIva: v })}
              >
                <SelectTrigger id="cliente-iva" className="w-full">
                  <SelectValue placeholder="Condición de IVA…" />
                </SelectTrigger>
                <SelectContent>
                  {CONDICIONES_IVA.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cliente-email">Email</Label>
              <Input
                id="cliente-email" type="email" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cliente-telefono">Teléfono</Label>
              <Input
                id="cliente-telefono" value={form.phone}
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
