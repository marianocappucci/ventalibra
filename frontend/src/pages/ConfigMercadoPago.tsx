// Con qué cuenta de MercadoPago cobra el QR del mostrador.
//
// 🔑 **El QR es el cartel impreso de la caja, no una imagen que salga en
// pantalla.** Es el modelo de QR fijo por punto de venta: el cartel no cambia
// nunca y lo que el sistema cambia es cuánto cobra cuando alguien lo escanea.
// Por eso hacen falta los tres datos y no sólo el token — el collector id y el
// external_id de la caja van en la URL de la orden.
import { useEffect, useState } from 'react'
import { api, ApiError, type MercadoPagoConfig } from '../api'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { QrCode } from 'lucide-react'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function ConfigMercadoPago() {
  const [cfg, setCfg] = useState<MercadoPagoConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    api.get<MercadoPagoConfig>('/settings/mercadopago')
      .then(setCfg)
      .catch((err) => setError(describeError(err)))
  }, [])

  function cambiar<K extends keyof MercadoPagoConfig>(campo: K, valor: MercadoPagoConfig[K]) {
    setCfg((actual) => (actual ? { ...actual, [campo]: valor } : actual))
    setGuardado(false)
  }

  async function guardar() {
    if (!cfg) return
    setSaving(true)
    setError(null)
    setGuardado(false)
    try {
      setCfg(await api.put<MercadoPagoConfig>('/settings/mercadopago', {
        access_token: cfg.access_token,
        user_id: cfg.user_id,
        pos_id: cfg.pos_id,
        auto_facturar: cfg.auto_facturar,
      }))
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
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <QrCode className="size-4" /> Cobro con QR
          </CardTitle>
          <CardDescription>
            El cajero pone el total de la venta en el QR impreso del mostrador
            y el cliente lo escanea. No hay ninguna imagen que mostrar en
            pantalla: el cartel es siempre el mismo y lo que cambia es cuánto
            cobra.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="mp-token">Access Token</Label>
            <Input
              id="mp-token" type="password" autoComplete="off"
              value={cfg.access_token}
              placeholder="APP_USR-…"
              onChange={(e) => cambiar('access_token', e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              El de la aplicación de MercadoPago del comercio, en «Tus
              integraciones → Credenciales de producción».
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="mp-user">User ID</Label>
              <Input
                id="mp-user" value={cfg.user_id}
                placeholder="123456789"
                onChange={(e) => cambiar('user_id', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                El número de la cuenta vendedora, el mismo que muestra el
                perfil de MercadoPago.
              </p>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="mp-pos">POS ID</Label>
              <Input
                id="mp-pos" value={cfg.pos_id}
                placeholder="CAJA01"
                onChange={(e) => cambiar('pos_id', e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                El <strong>identificador externo</strong> de la caja, no su
                nombre. Una caja sin ese campo cargado en MercadoPago no se
                puede direccionar y el cobro falla con «404».
              </p>
            </div>
          </div>

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox" className="mt-0.5 size-4"
              checked={cfg.auto_facturar}
              onChange={(e) => cambiar('auto_facturar', e.target.checked)}
            />
            <span>
              Emitir la factura automáticamente al acreditarse el pago
              <span className="block text-xs text-muted-foreground">
                Sólo para las ventas cobradas con este QR. Las demás siguen
                facturándose cuando el cajero lo pide.
              </span>
            </span>
          </label>

          <div className="flex items-center gap-3">
            <Button onClick={guardar} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
            {guardado && <span className="text-sm text-emerald-600">Guardado.</span>}
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>

          {!cfg.configurado && (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
              Faltan datos: el POS no va a ofrecer el cobro con QR hasta que
              los tres estén cargados.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
