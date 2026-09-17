// Cierre diario por sucursal (2026-09-16): acto registrado y numerado, con
// ticket de 80 mm. Lo puede hacer admin o cajero (staff) -- ver
// DECISIONS.md, feature de cajas por sucursal.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, type CierreDiario as CierreDiarioRow, type CierreDiarioPreview, type Location, type ShiftState } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { CalendarCheck, Printer } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { fecha, fechaHora, hora } from '@/lib/fechas'
import { abrirTicket } from '@/lib/tickets'
import { money, pesos } from '@/lib/dinero'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function CierreDiario() {
  const [locations, setLocations] = useState<Location[]>([])
  const [sucursalId, setSucursalId] = useState<string>('')
  const [preview, setPreview] = useState<CierreDiarioPreview | null>(null)
  const [historial, setHistorial] = useState<CierreDiarioRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [cerrando, setCerrando] = useState(false)
  const [notas, setNotas] = useState('')
  // Separado de `error`: los dos se muestran a la vez si un 422/409 del
  // cierre reusara `error` -- el diálogo sigue abierto y la tarjeta de atrás
  // quedaría mostrando el mismo texto, duplicado en el DOM.
  const [errorCierre, setErrorCierre] = useState<string | null>(null)

  // Preselecciona la sucursal del turno/caja del usuario, si tiene uno.
  useEffect(() => {
    (async () => {
      try {
        const [locs, estado] = await Promise.all([
          api.get<Location[]>('/locations'),
          api.get<ShiftState>('/shifts/current').catch(() => ({ turno: null }) as ShiftState),
        ])
        setLocations(locs)
        const sucursalDelTurno = estado.turno?.sucursal?.id
        const porDefecto = locs.find((l) => l.is_default)
        setSucursalId(String(sucursalDelTurno ?? porDefecto?.id ?? locs[0]?.id ?? ''))
      } catch (err) {
        setError(describeError(err))
      }
    })()
  }, [])

  const cargar = useCallback(async () => {
    if (!sucursalId) return
    setLoading(true)
    setError(null)
    try {
      const [prev, lista] = await Promise.all([
        api.get<CierreDiarioPreview>(`/api/cierre-diario/preview?sucursal_id=${sucursalId}`),
        api.get<CierreDiarioRow[]>(`/api/cierre-diario?sucursal_id=${sucursalId}`),
      ])
      setPreview(prev)
      setHistorial(lista)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }, [sucursalId])

  useEffect(() => { cargar() }, [cargar])

  const nombreSucursal = useMemo(() => {
    const m = new Map(locations.map((l) => [l.id, l.name]))
    return (id: number | null) => (id !== null ? m.get(id) ?? `Sucursal #${id}` : 'Sin sucursal')
  }, [locations])

  async function confirmarCierre() {
    setCerrando(true)
    setErrorCierre(null)
    try {
      await api.post('/api/cierre-diario/cerrar', {
        sucursal_id: sucursalId ? Number(sucursalId) : null, notas: notas.trim(),
      })
      setConfirmando(false)
      setNotas('')
      await cargar()
    } catch (err) {
      setErrorCierre(describeError(err))
    } finally {
      setCerrando(false)
    }
  }

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={CalendarCheck}>Cierre diario</TituloPantalla>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Vista previa del día</CardTitle>
          <Select value={sucursalId} onValueChange={setSucursalId}>
            <SelectTrigger className="h-8 w-56"><SelectValue placeholder="Elegí una sucursal…" /></SelectTrigger>
            <SelectContent>
              {locations.map((l) => (
                <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent className="grid gap-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : preview ? (
            <>
              <p className="text-sm text-muted-foreground">
                Día operativo: <span className="font-medium text-foreground">{fecha(preview.fecha)}</span>
                {preview.ya_cerrado && (
                  <BadgeEstado tono="ok" className="ml-2">Ya cerrado</BadgeEstado>
                )}
              </p>

              {preview.turnos_abiertos.length > 0 && (
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950">
                  <p className="font-medium text-amber-800 dark:text-amber-300">
                    Hay {preview.turnos_abiertos.length} turno{preview.turnos_abiertos.length === 1 ? '' : 's'} abierto{preview.turnos_abiertos.length === 1 ? '' : 's'}: hay que cerrarlo{preview.turnos_abiertos.length === 1 ? '' : 's'} antes.
                  </p>
                  <ul className="mt-1 list-inside list-disc text-amber-700 dark:text-amber-400">
                    {preview.turnos_abiertos.map((t) => (
                      <li key={t.id}>
                        #{t.id} · {t.usuario_nombre} · {t.caja_nombre ?? 'sin caja'} · desde {hora(t.apertura)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid gap-1 rounded-md border p-3 text-sm">
                {preview.medios.map((m) => (
                  <div key={m.medio_pago} className="flex justify-between">
                    <span className="text-muted-foreground">{m.medio_pago.replace(/_/g, ' ')}</span>
                    <span className="tabular-nums">${money(m.neto)}</span>
                  </div>
                ))}
                <div className="mt-1 flex justify-between border-t pt-2 font-medium">
                  <span>Esperado</span>
                  <span className="tabular-nums">${money(preview.monto_esperado_total)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Declarado</span>
                  <span className="tabular-nums">${money(preview.monto_declarado_total)}</span>
                </div>
                <div className="flex justify-between font-medium">
                  <span>Diferencia</span>
                  {/* Puede ser negativa (faltante): el signo va antes del
                      `$`, no `$-500,00` -- ver `lib/dinero.ts::pesos`. */}
                  <span className="tabular-nums">{pesos(preview.diferencia_total)}</span>
                </div>
              </div>

              <Button
                className="justify-self-start"
                disabled={!preview.puede_cerrar || preview.ya_cerrado || preview.turnos.length === 0}
                onClick={() => setConfirmando(true)}
              >
                Cerrar el día
              </Button>
              {!preview.puede_cerrar && preview.turnos_abiertos.length === 0 && preview.turnos.length === 0 && (
                <p className="text-xs text-muted-foreground">No hubo turnos hoy en esta sucursal.</p>
              )}
            </>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">Elegí una sucursal.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Cierres anteriores</CardTitle></CardHeader>
        <CardContent className="grid gap-2">
          {historial.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">Sin cierres todavía.</p>
          )}
          {historial.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-md border p-3 text-sm">
              <div>
                <span className="font-medium">Cierre #{c.numero}</span>
                <span className="ml-2 text-muted-foreground">{fecha(c.fecha)} · {nombreSucursal(c.sucursal_id)}</span>
                <p className="text-xs text-muted-foreground">
                  Cerrado por {c.cerrado_por_nombre} el {fechaHora(c.created_at)}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="tabular-nums">${money(c.monto_declarado_total)}</span>
                <Button size="sm" variant="outline" onClick={() => abrirTicket(`/api/cierre-diario/${c.id}/ticket`)}>
                  <Printer />Imprimir ticket
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Dialog
        open={confirmando}
        onOpenChange={(o) => { setConfirmando(o); if (!o) setErrorCierre(null) }}
      >
        <DialogContent>
          <DialogHeader><DialogTitle>Confirmar cierre del día</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            Se cierra {fecha(preview?.fecha ?? '')} para {nombreSucursal(sucursalId ? Number(sucursalId) : null)}.
            No se puede deshacer.
          </p>
          <textarea
            className="min-h-16 rounded-md border p-2 text-sm"
            placeholder="Notas (opcional)"
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />
          {errorCierre && <p className="text-sm text-destructive">{errorCierre}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmando(false)}>Cancelar</Button>
            <Button onClick={confirmarCierre} disabled={cerrando}>
              {cerrando ? 'Cerrando…' : 'Confirmar cierre'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
