// Historial de ventas: la pantalla del kit (F4, ADR-025, P9-M3), con la
// devolución por línea como acción propia de este producto.
//
// Hasta F4 esto era una pantalla entera escrita acá, contra `/sales` (el
// listado y el detalle con anular/devolver a mano). El listado y el detalle
// pasan a `libra-ui/comercio/Ventas`/`VentaDetalle`, que hablan con
// `/api/ventas` -- lo que sigue siendo propio de VentaLibra es la devolución
// parcial, que el kit no implementa (cada producto la resuelve distinto), así
// que se monta como `accionesExtra`.
import { useEffect, useState } from 'react'
import { Ventas as VentasComercio } from 'libra-ui/comercio/Ventas'
import type { VentaDetalleAccionesExtraCtx } from 'libra-ui/comercio/VentaDetalle'
import {
  api, ApiError, type Deposito, type ShiftState, type Sucursal, type VentaDevuelto,
} from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Undo2 } from 'lucide-react'
import { useMediosPago } from '@/lib/medios-pago'

// La sesión de este producto siempre puede anular/devolver (F4, corrección
// del orquestador): `app/main.py` no le pasa `solo_admin` al motor -- hasta
// hoy un cajero podía hacer las dos cosas, y restringirlo sería una
// decisión que nadie tomó. Constante y no `user.role === 'admin'` a
// propósito: acá NO hay chequeo de rol que replicar.
const PUEDE_ANULAR = true

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function Ventas() {
  return (
    <VentasComercio
      puedeAnular={PUEDE_ANULAR}
      // `permitirAlta={false}`: este producto carga las ventas desde el POS
      // (Pos.tsx); el alta manual del kit queda para Contalibra/Restolibra.
      permitirAlta={false}
      // `null` (libra-ui v0.72.1, nullable desde acá): VentaLibra no tiene
      // pantalla de facturas ni de recibos -- el dato de la factura queda
      // como texto (`factura_display`), sin link, y el botón de recibo no se
      // ofrece. El ticket sigue con su ruta de siempre
      // (`/ventas/{id}/ticket`, la del backend): esa no es prop, el kit la
      // tiene fija.
      rutaDeFactura={null}
      rutaDeRecibo={null}
    />
  )
}

/** La devolución parcial de líneas, montada como `accionesExtra` de
 *  `VentaDetalle` (libra-ui). Sólo se ofrece con la venta cobrada o
 *  parcialmente devuelta -- lo decide el propio kit (no renderiza
 *  `accionesExtra` fuera de esos estados). */
export function DevolucionDeVenta({ detalle, recargar }: VentaDetalleAccionesExtraCtx) {
  const [open, setOpen] = useState(false)
  const [devuelto, setDevuelto] = useState<VentaDevuelto | null>(null)
  const [locations, setLocations] = useState<Deposito[]>([])
  const [locationId, setLocationId] = useState('')
  const [medio, setMedio] = useState('efectivo')
  const [cantidades, setCantidades] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { medios } = useMediosPago()

  useEffect(() => {
    if (!open) return
    setError(null)
    setCantidades({})
    Promise.all([
      api.get<VentaDevuelto>(`/ventas/${detalle.id}/devuelto`),
      api.get<Deposito[]>('/api/depositos'),
      // Sólo para saber cuál es el depósito de venta: si falla, la devolución sigue con el default del sistema.
      api.get<Sucursal[]>('/api/sucursales').catch(() => [] as Sucursal[]),
      api.get<ShiftState>('/api/turnos/actual').catch(() => ({ turno: null }) as ShiftState),
    ]).then(([d, ds, sucursales, estado]) => {
      setDevuelto(d)
      // Se repone stock en un depósito, y el backend rechaza (422, `app/ganchos.py::validar_deposito`) uno que no
      // sea de la sucursal del turno de quien devuelve: con turno en una caja, sólo se ofrecen los depósitos activos
      // de esa sucursal; sin turno, todos los activos.
      const sucursalDelTurno = estado.turno?.sucursal?.id
      const opciones = ds.filter((x) => !!x.activo && (sucursalDelTurno == null || x.branch_id === sucursalDelTurno))
      setLocations(opciones)
      // Default: el depósito de la venta original si se pudo saber y está entre las opciones; si no, el depósito de
      // venta de la sucursal (la del turno o, sin turno, la predeterminada); si tampoco, el default del sistema (o
      // el primero, si no hay uno marcado).
      const sucursal = sucursales.find((x) => x.id === sucursalDelTurno)
        ?? sucursales.find((x) => !!x.es_default)
      const esOpcion = (id: number | null | undefined) => id != null && opciones.some((x) => x.id === id)
      const sugerido = [d.deposito_id, sucursal?.deposito_predeterminado_id].find(esOpcion)
        ?? opciones.find((x) => !!x.es_default)?.id
        ?? opciones[0]?.id
      setLocationId(sugerido ? String(sugerido) : '')
    }).catch((err) => setError(describeError(err)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, detalle.id])

  // Vendido por (producto, variante): el pozo es compartido entre líneas
  // iguales -- mismo criterio que `libracommerce.erp.ventas.devolver_items`.
  function claveDe(it: { producto_id: number | null; variante_id?: number | null }) {
    return `${it.producto_id}:${it.variante_id ?? ''}`
  }
  const vendidoPorClave = new Map<string, number>()
  for (const it of detalle.items) {
    const k = claveDe(it)
    vendidoPorClave.set(k, (vendidoPorClave.get(k) ?? 0) + it.qty)
  }
  const devueltoPorClave = new Map<string, number>()
  for (const d of devuelto?.por_clave ?? []) {
    devueltoPorClave.set(claveDe(d), d.cantidad)
  }
  function disponibleDe(it: { producto_id: number | null; variante_id?: number | null; qty: number }): number {
    if (it.producto_id == null) return 0
    const k = claveDe(it)
    const pozo = (vendidoPorClave.get(k) ?? 0) - (devueltoPorClave.get(k) ?? 0)
    return Math.max(0, Math.min(it.qty, pozo))
  }

  const lineas = Object.entries(cantidades)
    .map(([id, cant]) => ({ sale_item_id: Number(id), cantidad: Number(cant) }))
    .filter((l) => l.cantidad > 0)

  async function devolver() {
    if (lineas.length === 0 || !locationId) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/api/ventas/${detalle.id}/devolver`, {
        lineas, deposito_id: Number(locationId), medio_pago: medio,
      })
      setOpen(false)
      recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {/* 44 px de alto bajo `lg`, como los demás botones del detalle de la venta (libra-ui ADR-022): en el teléfono medía 32. */}
      <Button size="sm" variant="outline" className="max-lg:h-11" onClick={() => setOpen(true)}>
        <Undo2 />Devolver productos
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Devolver productos de la venta {detalle.numero}</DialogTitle></DialogHeader>

          <p className="text-sm text-muted-foreground">
            Indicá cuánto vuelve de cada línea. Se repone el stock y se
            reintegra el importe.
          </p>

          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="p-2">Producto</th>
                  <th className="w-20 p-2 text-center">Vendido</th>
                  <th className="w-24 p-2 text-center">Devolver</th>
                </tr>
              </thead>
              <tbody>
                {detalle.items.map((it) => {
                  const disponible = disponibleDe(it)
                  const lineaId = it.id
                  return (
                    <tr key={lineaId ?? it.nombre} className="border-b last:border-0">
                      <td className="p-2">{it.nombre}</td>
                      <td className="p-2 text-center tabular-nums">{it.qty}</td>
                      <td className="p-2">
                        <Input
                          value={lineaId != null ? (cantidades[lineaId] ?? '') : ''}
                          disabled={lineaId == null || disponible <= 0 || busy}
                          onChange={(e) => {
                            if (lineaId == null) return
                            setCantidades((prev) => ({ ...prev, [lineaId]: e.target.value }))
                          }}
                          placeholder={disponible > 0 ? `máx. ${disponible}` : '0 disponible'}
                          className="h-8 text-center tabular-nums max-lg:h-11"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* `max-lg:data-[size=default]:h-11` y no `max-lg:h-11`: el `SelectTrigger` del kit fija su alto con `data-[size=default]:h-9`,
              que por el selector de atributo pesa más y le ganaba (medido en Chromium contra demo: seguían en 36 px). */}
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1">
              <Label className="text-xs">Depósito</Label>
              <Select value={locationId} onValueChange={setLocationId}>
                <SelectTrigger className="w-48 max-lg:data-[size=default]:h-11" aria-label="Depósito"><SelectValue placeholder="Elegí un depósito…" /></SelectTrigger>
                <SelectContent>
                  {locations.map((l) => (
                    <SelectItem key={l.id} value={String(l.id)}>{l.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Devolver por</Label>
              <Select value={medio} onValueChange={setMedio}>
                <SelectTrigger className="w-48 max-lg:data-[size=default]:h-11" aria-label="Devolver por"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {medios.map((m) => (
                    <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

          <DialogFooter>
            <Button variant="outline" className="max-lg:h-11" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button className="max-lg:h-11" onClick={devolver} disabled={busy || lineas.length === 0 || !locationId}>
              {busy ? 'Devolviendo…' : 'Confirmar devolución'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
