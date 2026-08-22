// Historial de ventas, con anulación y devolución.
//
// Antes no había forma de ver una venta ya cobrada: el POS la cerraba y
// desaparecía. Sin esta pantalla, deshacer la venta de ayer — que es cuando
// el cliente vuelve con el producto — era imposible.
import { useEffect, useState } from 'react'
import {
  api, ApiError, type Sale, type SaleListItem, type SaleStatus,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Ban, Printer, Undo2 } from 'lucide-react'

const ESTADOS: Record<SaleStatus, { label: string; tono: TonoEstado }> = {
  draft: { label: 'Borrador', tono: 'neutro' },
  confirmed: { label: 'Cobrada', tono: 'ok' },
  cancelled: { label: 'Anulada', tono: 'negativo' },
  partially_returned: { label: 'Devuelta en parte', tono: 'atencion' },
  returned: { label: 'Devuelta', tono: 'atencion' },
}

const MEDIOS_DEVOLUCION = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'transferencia', label: 'Transferencia' },
  { value: 'mercado_pago', label: 'Mercado Pago' },
  { value: 'cuenta_corriente', label: 'Cuenta corriente' },
]

function money(value: string | number): string {
  return Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

function cantidad(value: string): string {
  const n = Number(value)
  return Number.isInteger(n) ? String(n)
    : n.toLocaleString('es-AR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function Ventas() {
  const [ventas, setVentas] = useState<SaleListItem[]>([])
  const [busqueda, setBusqueda] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abierta, setAbierta] = useState<number | null>(null)

  useEffect(() => { cargar() }, [])

  async function cargar(search = '') {
    setLoading(true)
    try {
      setVentas(await api.get<SaleListItem[]>(
        `/sales?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`,
      ))
      setError(null)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Ventas</h2>

      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); cargar(busqueda) }}
      >
        <Input
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscar por número o cliente"
          className="max-w-sm"
        />
        <Button type="submit" variant="secondary">Buscar</Button>
      </form>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader><CardTitle className="text-base">Últimas ventas</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : ventas.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No hay ventas todavía.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="p-2">Número</th>
                    <th className="p-2">Fecha</th>
                    <th className="p-2">Cliente</th>
                    <th className="w-32 p-2 text-right">Total</th>
                    <th className="w-40 p-2">Estado</th>
                    <th className="w-24 p-2" />
                  </tr>
                </thead>
                <tbody>
                  {ventas.map((v) => (
                    <tr key={v.id} className="border-b last:border-0">
                      <td className="p-2 font-medium tabular-nums">{v.number}</td>
                      <td className="p-2 tabular-nums text-muted-foreground">
                        {(v.confirmed_at ?? '').slice(0, 10)}
                      </td>
                      <td className="p-2">{v.cliente || 'Consumidor final'}</td>
                      <td className="p-2 text-right tabular-nums">${money(v.total)}</td>
                      <td className="p-2">
                        <BadgeEstado tono={ESTADOS[v.status].tono}>
                          {ESTADOS[v.status].label}
                        </BadgeEstado>
                      </td>
                      <td className="p-2 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setAbierta(v.id)}>
                          Ver
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {abierta !== null && (
        <DetalleVenta
          saleId={abierta}
          onCerrar={() => setAbierta(null)}
          onCambio={() => cargar(busqueda)}
        />
      )}
    </div>
  )
}

function DetalleVenta({ saleId, onCerrar, onCambio }: {
  saleId: number
  onCerrar: () => void
  onCambio: () => void
}) {
  const [venta, setVenta] = useState<Sale | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [devolviendo, setDevolviendo] = useState(false)
  const [aDevolver, setADevolver] = useState<Record<number, string>>({})
  const [medio, setMedio] = useState('efectivo')
  const [locationId, setLocationId] = useState<string>('')

  useEffect(() => {
    api.get<Sale>(`/sales/${saleId}`).then(setVenta).catch((e) => setError(describeError(e)))
    api.get<{ id: number }[]>('/locations')
      .then((ls) => { if (ls.length > 0) setLocationId(String(ls[0].id)) })
      .catch(() => {})
  }, [saleId])

  async function anular() {
    setBusy(true)
    setError(null)
    try {
      setVenta(await api.post<Sale>(`/sales/${saleId}/cancel`, {}))
      onCambio()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function devolver() {
    const lineas = Object.entries(aDevolver)
      .filter(([, cant]) => Number(cant) > 0)
      .map(([index, cant]) => ({ index: Number(index), quantity: cant }))
    if (lineas.length === 0) return

    setBusy(true)
    setError(null)
    try {
      setVenta(await api.post<Sale>(`/sales/${saleId}/returns`, {
        lineas, location_id: Number(locationId), medio_pago: medio,
      }))
      setADevolver({})
      setDevolviendo(false)
      onCambio()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const puedeDeshacer = venta?.status === 'confirmed'
    || venta?.status === 'partially_returned'

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Venta {venta?.number ?? ''}
            {venta && (
              <BadgeEstado tono={ESTADOS[venta.status].tono} className="ml-2">
                {ESTADOS[venta.status].label}
              </BadgeEstado>
            )}
          </DialogTitle>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {venta && (
          <>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="p-2">Producto</th>
                    <th className="w-20 p-2 text-center">Cant.</th>
                    <th className="w-28 p-2 text-right">Importe</th>
                    {devolviendo && <th className="w-28 p-2 text-center">Devolver</th>}
                  </tr>
                </thead>
                <tbody>
                  {venta.items.map((linea, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="p-2">{linea.description_snapshot}</td>
                      <td className="p-2 text-center tabular-nums">{cantidad(linea.quantity)}</td>
                      <td className="p-2 text-right tabular-nums">${money(linea.line_total)}</td>
                      {devolviendo && (
                        <td className="p-2">
                          <Input
                            value={aDevolver[i] ?? ''}
                            onChange={(e) => setADevolver((a) => ({ ...a, [i]: e.target.value }))}
                            placeholder="0"
                            className="h-8 text-center tabular-nums"
                          />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-baseline justify-between border-t pt-3">
              <span className="text-sm text-muted-foreground">Total</span>
              <span className="text-2xl font-medium tabular-nums">${money(venta.total)}</span>
            </div>

            {devolviendo && (
              <div className="grid gap-2 rounded-md border p-3">
                <p className="text-sm">
                  Indicá cuánto vuelve de cada línea. Se repone el stock y se
                  reintegra el importe.
                </p>
                <div className="flex items-end gap-2">
                  <div className="grid gap-1">
                    <Label className="text-xs">Devolver por</Label>
                    <Select value={medio} onValueChange={setMedio}>
                      <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {MEDIOS_DEVOLUCION.map((m) => (
                          <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button onClick={devolver} disabled={busy}>
                    {busy ? 'Devolviendo…' : 'Confirmar devolución'}
                  </Button>
                  <Button variant="ghost" onClick={() => { setDevolviendo(false); setADevolver({}) }}>
                    Cancelar
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            variant="outline"
            onClick={() => window.open(`/sales/${saleId}/ticket`, '_blank')}
          >
            <Printer />Ticket
          </Button>
          <div className="flex gap-2">
            {puedeDeshacer && !devolviendo && (
              <>
                <Button variant="outline" onClick={() => setDevolviendo(true)}>
                  <Undo2 />Devolver productos
                </Button>
                <Button variant="destructive" onClick={anular} disabled={busy}>
                  <Ban />Anular venta
                </Button>
              </>
            )}
            <Button variant="secondary" onClick={onCerrar}>Cerrar</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
