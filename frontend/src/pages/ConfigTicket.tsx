// Cómo sale el ticket impreso.
//
// Es configuración de hardware, igual que la balanza: el ancho depende del
// rollo que tenga puesto la ticketeadora, y equivocarlo sólo se nota cuando
// sale el papel. Por eso hay una vista previa: se mira antes de gastar rollo.
import { useEffect, useState } from 'react'
import { api, ApiError, type TicketConfig } from '../api'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Printer } from 'lucide-react'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function ConfigTicket() {
  const [cfg, setCfg] = useState<TicketConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    api.get<TicketConfig>('/settings/ticket')
      .then(setCfg)
      .catch((err) => setError(describeError(err)))
  }, [])

  function cambiar<K extends keyof TicketConfig>(campo: K, valor: TicketConfig[K]) {
    setCfg((actual) => (actual ? { ...actual, [campo]: valor } : actual))
    setGuardado(false)
  }

  async function guardar() {
    if (!cfg) return
    setSaving(true)
    setError(null)
    setGuardado(false)
    try {
      setCfg(await api.put<TicketConfig>('/settings/ticket', cfg))
      setGuardado(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }

  return (
    <div className="grid max-w-2xl gap-4">
      <h2 className="text-lg font-semibold">Ticket</h2>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Printer className="size-4" /> Impresión del ticket
          </CardTitle>
          <CardDescription>
            El ticket se imprime desde la pantalla del cajero (F8 después de
            cobrar) a través del diálogo de impresión del sistema, que es el
            que conoce la ticketeadora.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>Ancho del papel</Label>
              <Select value={cfg.ancho_mm} onValueChange={(v) => cambiar('ancho_mm', v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="80">80 mm</SelectItem>
                  <SelectItem value="58">58 mm</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                El del rollo que usa la impresora. Si no coincide, el ticket
                sale cortado o con media hoja en blanco.
              </p>
            </div>

            <div className="grid gap-1.5">
              <Label>Tamaño de letra</Label>
              <Input
                type="number" min={6} max={14} value={cfg.fuente_size}
                onChange={(e) => cambiar('fuente_size', Number(e.target.value))}
                className="w-24 tabular-nums"
              />
              <p className="text-xs text-muted-foreground">Entre 6 y 14 puntos.</p>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="pie">Texto al pie</Label>
            <Input
              id="pie" value={cfg.pie} placeholder="¡Gracias por su compra!"
              onChange={(e) => cambiar('pie', e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox" className="size-4"
              checked={cfg.mostrar_logo}
              onChange={(e) => cambiar('mostrar_logo', e.target.checked)}
            />
            Imprimir el logo del comercio
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox" className="size-4"
              checked={cfg.linea_corte}
              onChange={(e) => cambiar('linea_corte', e.target.checked)}
            />
            Marcar la línea de corte al final
          </label>

          <div className="flex items-center gap-3">
            <Button onClick={guardar} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
            {guardado && <span className="text-sm text-emerald-600">Guardado.</span>}
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cómo va a salir</CardTitle>
          <CardDescription>
            Aproximación en pantalla del ancho elegido, para no tener que
            gastar rollo probando.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Vista cfg={cfg} />
        </CardContent>
      </Card>
    </div>
  )
}

/** Maqueta del ticket. El PDF real lo arma el backend; esto sólo ayuda a
 *  decidir el ancho y el cuerpo de letra. */
function Vista({ cfg }: { cfg: TicketConfig }) {
  // 80mm ≈ 302px, 58mm ≈ 219px a 96dpi.
  const anchoPx = cfg.ancho_mm === '58' ? 219 : 302
  return (
    <div
      className="mx-auto border bg-white p-2 font-mono text-black shadow-sm"
      style={{ width: anchoPx, fontSize: cfg.fuente_size }}
    >
      {cfg.mostrar_logo && (
        <p className="text-center opacity-40">[logo]</p>
      )}
      <p className="text-center font-bold">MI COMERCIO</p>
      <p className="text-center">CUIT: 20-11111111-2</p>
      <p>{'-'.repeat(cfg.ancho_mm === '58' ? 24 : 32)}</p>
      <p className="text-center font-bold">TICKET DE VENTA</p>
      <p className="text-center">N° POS-000123</p>
      <p>{'-'.repeat(cfg.ancho_mm === '58' ? 24 : 32)}</p>
      <p>Yerba 1kg</p>
      <div className="flex justify-between"><span>&nbsp;&nbsp;2 x $1.500,00</span><span>$3.000,00</span></div>
      <p>Queso cremoso</p>
      <div className="flex justify-between"><span>&nbsp;&nbsp;0,750 x $8.500,00</span><span>$6.375,00</span></div>
      <p>{'-'.repeat(cfg.ancho_mm === '58' ? 24 : 32)}</p>
      <div className="flex justify-between font-bold"><span>TOTAL:</span><span>$9.375,00</span></div>
      {cfg.pie && (
        <>
          <p>{'-'.repeat(cfg.ancho_mm === '58' ? 24 : 32)}</p>
          <p className="text-center">{cfg.pie}</p>
        </>
      )}
      {cfg.linea_corte && (
        <p className="mt-2 text-center opacity-60">- - - - CORTE - - - -</p>
      )}
    </div>
  )
}
