import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type Customer } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { ArrowLeft, Users } from 'lucide-react'

export function ClienteDetalle() {
  const { id } = useParams<{ id: string }>()
  const [cliente, setCliente] = useState<Customer | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true
    setCargando(true)
    setCliente(null)
    setError(null)
    api.get<Customer>(`/customers/${id}`)
      .then((datos) => { if (vigente) setCliente(datos) })
      .catch((err: unknown) => {
        if (vigente) setError(err instanceof ApiError ? err.detail : 'No se pudo cargar el cliente.')
      })
      .finally(() => { if (vigente) setCargando(false) })
    return () => { vigente = false }
  }, [id])

  return (
    <div className="grid gap-4">
      <Link className="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:underline" to="/clientes">
        <ArrowLeft className="size-4" /> Volver a clientes
      </Link>
      <TituloPantalla icono={Users}>Ficha cliente</TituloPantalla>
      {cargando && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {cliente && (
        <Card>
          <CardHeader><CardTitle>{cliente.display_name}</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div><dt className="text-sm text-muted-foreground">Estado</dt><dd><BadgeEstado tono={cliente.active ? 'ok' : 'neutro'}>{cliente.active ? 'Activo' : 'Inactivo'}</BadgeEstado></dd></div>
              <div><dt className="text-sm text-muted-foreground">Tipo</dt><dd>{cliente.party_type === 'organization' ? 'Organización' : 'Persona'}</dd></div>
              <div><dt className="text-sm text-muted-foreground">CUIT</dt><dd>{cliente.cuit || '—'}</dd></div>
              <div><dt className="text-sm text-muted-foreground">Condición de IVA</dt><dd>{cliente.condicion_iva || '—'}</dd></div>
              <div><dt className="text-sm text-muted-foreground">Email</dt><dd>{cliente.email || '—'}</dd></div>
              <div><dt className="text-sm text-muted-foreground">Teléfono</dt><dd>{cliente.phone || '—'}</dd></div>
            </dl>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
