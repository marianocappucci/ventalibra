// Quién debe, cuánto, y el registro del pago cuando viene a saldar.
//
// Es el reemplazo del cuaderno: la lista es lo primero que se ve porque la
// pregunta del comercio es "¿quién me debe?", no "¿cuál es el detalle de la
// cuenta de fulano?" -- eso viene después, al abrir una fila.
import { useEffect, useState } from 'react'
import {
  api, ApiError, type CuentaCorriente, type Deudor,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ReceiptText, Wallet } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { fecha } from '@/lib/fechas'

const MEDIOS_PAGO = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'tarjeta_debito', label: 'Tarjeta de débito' },
  { value: 'transferencia', label: 'Transferencia' },
  { value: 'mercado_pago', label: 'Mercado Pago' },
]

function money(value: string | number): string {
  return Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

/** El signo va afuera del importe: `-$500,00`, nunca `$-500,00`. */
function conSigno(value: string | number): string {
  const n = Number(value)
  return `${n < 0 ? '-' : ''}$${money(Math.abs(n))}`
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function CuentasCorrientes() {
  const [deudores, setDeudores] = useState<Deudor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abierta, setAbierta] = useState<Deudor | null>(null)

  useEffect(() => { cargar() }, [])

  async function cargar() {
    setLoading(true)
    try {
      setDeudores(await api.get<Deudor[]>('/accounts'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const totalFiado = deudores.reduce((acc, d) => acc + Math.max(0, Number(d.saldo)), 0)

  if (loading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-baseline justify-between">
        <TituloPantalla icono={Wallet}>Cuentas corrientes</TituloPantalla>
        {deudores.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Fiado total: <strong className="tabular-nums text-foreground">${money(totalFiado)}</strong>
          </p>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Wallet className="size-4" /> Quién debe
          </CardTitle>
        </CardHeader>
        <CardContent>
          {deudores.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nadie tiene cuenta corriente abierta.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="p-2">Cliente</th>
                    <th className="w-32 p-2 text-right">Saldo</th>
                    <th className="w-28 p-2" />
                  </tr>
                </thead>
                <tbody>
                  {deudores.map((d) => (
                    <tr key={d.party_id} className="border-b last:border-0">
                      <td className="p-2">{d.nombre}</td>
                      <td
                        className={[
                          'p-2 text-right tabular-nums',
                          Number(d.saldo) < 0 ? 'text-emerald-600 dark:text-emerald-500' : '',
                        ].join(' ')}
                      >
                        {conSigno(d.saldo)}
                      </td>
                      <td className="p-2 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setAbierta(d)}>
                          Ver cuenta
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

      {abierta && (
        <DetalleCuenta
          deudor={abierta}
          onCerrar={() => setAbierta(null)}
          onCobrado={() => { cargar() }}
        />
      )}
    </div>
  )
}

function DetalleCuenta({ deudor, onCerrar, onCobrado }: {
  deudor: Deudor
  onCerrar: () => void
  onCobrado: () => void
}) {
  const [cuenta, setCuenta] = useState<CuentaCorriente | null>(null)
  const [monto, setMonto] = useState('')
  const [medio, setMedio] = useState('efectivo')
  const [concepto, setConcepto] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { cargar() }, [deudor.party_id])

  async function cargar() {
    try {
      setCuenta(await api.get<CuentaCorriente>(`/accounts/${deudor.party_id}`))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function cobrar() {
    const importe = Number(monto)
    if (!importe || importe <= 0) return
    setBusy(true)
    setError(null)
    // La ventana se abre ANTES del await: abrirla con la respuesta ya en mano
    // la vuelve un popup no pedido por el usuario y el navegador la bloquea.
    const ventana = window.open('', '_blank')
    try {
      const actualizada = await api.post<CuentaCorriente>(
        `/accounts/${deudor.party_id}/payments`, { monto, medio_pago: medio, concepto },
      )
      setCuenta(actualizada)
      setMonto('')
      setConcepto('')
      onCobrado()
      // El cobro ya está registrado aunque el recibo no haya salido. Si no
      // vino id se cierra la ventana en vez de dejarla en blanco: el botón de
      // la fila lo reintenta.
      if (actualizada.recibo_id) {
        ventana!.location.href = `/accounts/receipts/${actualizada.recibo_id}/pdf`
      } else {
        ventana?.close()
      }
    } catch (err) {
      ventana?.close()
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function verRecibo(ccPagoId: number) {
    const ventana = window.open('', '_blank')
    setError(null)
    try {
      // Idempotente: emite si el pago todavía no tiene recibo, y devuelve el
      // que ya existía si lo tiene. Por eso alcanza un solo botón.
      const recibo = await api.post<{ id: number }>(`/accounts/receipts/${ccPagoId}`, {})
      ventana!.location.href = `/accounts/receipts/${recibo.id}/pdf`
    } catch (err) {
      ventana?.close()
      setError(describeError(err))
    }
  }

  const saldo = Number(cuenta?.saldo ?? deudor.saldo)

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>{deudor.nombre}</DialogTitle></DialogHeader>

        <div className="rounded-md border p-3">
          <p className="text-xs text-muted-foreground">
            {saldo < 0 ? 'Saldo a favor' : 'Debe'}
          </p>
          <p className="text-3xl font-medium tabular-nums">{conSigno(saldo)}</p>
        </div>

        <div className="grid gap-2 rounded-md border p-3">
          <p className="text-sm font-medium">Registrar un pago</p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1">
              <Label className="text-xs" htmlFor="monto">Monto</Label>
              <Input
                id="monto" value={monto} className="w-32 tabular-nums"
                onChange={(e) => setMonto(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); cobrar() } }}
                autoFocus
              />
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Medio</Label>
              <Select value={medio} onValueChange={setMedio}>
                <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MEDIOS_PAGO.map((m) => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid flex-1 gap-1">
              <Label className="text-xs" htmlFor="concepto">Concepto</Label>
              <Input
                id="concepto" value={concepto} placeholder="opcional"
                onChange={(e) => setConcepto(e.target.value)}
              />
            </div>
            <Button onClick={cobrar} disabled={busy || !Number(monto)}>
              {busy ? 'Registrando…' : 'Cobrar'}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            El pago entra a la caja del turno abierto. Si no hay turno, no se
            puede registrar.
          </p>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-background">
              <tr className="border-b text-left text-muted-foreground">
                <th className="p-2">Fecha</th>
                <th className="p-2">Concepto</th>
                <th className="w-28 p-2 text-right">Debe</th>
                <th className="w-28 p-2 text-right">Haber</th>
                <th className="w-12 p-2" />
              </tr>
            </thead>
            <tbody>
              {(cuenta?.movimientos ?? []).map((m, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="p-2 tabular-nums text-muted-foreground">{fecha(m.fecha)}</td>
                  <td className="p-2">
                    {m.concepto}
                    {m.medio && <span className="ml-1 text-xs text-muted-foreground">({m.medio})</span>}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {m.tipo === 'debito' ? `$${money(m.monto)}` : ''}
                  </td>
                  <td className="p-2 text-right tabular-nums text-emerald-600 dark:text-emerald-500">
                    {m.tipo === 'credito' ? `$${money(m.monto)}` : ''}
                  </td>
                  <td className="p-2 text-right">
                    {/* Sólo los abonos: un cargo no es plata que entró, no hay
                        recibo que emitirle. */}
                    {m.cc_pago_id && (
                      <Button
                        size="icon" variant="ghost" title="Ver recibo" aria-label="Ver recibo"
                        onClick={() => verRecibo(m.cc_pago_id!)}
                      >
                        <ReceiptText className="size-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {(cuenta?.movimientos ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-muted-foreground">
                    Sin movimientos.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onCerrar}>Cerrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
