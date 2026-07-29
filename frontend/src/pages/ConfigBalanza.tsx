// Configuracion de la balanza de mostrador.
//
// El formato de la etiqueta lo define la marca y como este configurado el
// equipo, asi que no se puede adivinar. La pantalla trae un probador: se
// escanea una etiqueta real y se ve al instante que producto y que peso
// entendio el sistema -- que es la unica forma honesta de saber si la
// configuracion quedo bien sin arriesgar un cobro equivocado.
import { useEffect, useState } from 'react'
import {
  api, ApiError, type ScanResult, type ScaleFormat, type ScaleValueKind,
} from '../api'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Scale } from 'lucide-react'

const POR_DEFECTO: ScaleFormat = {
  prefix: '20',
  code_digits: 5,
  value_digits: 5,
  value_kind: 'weight',
  divisor: 1000,
  total_digits: 13,
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function ConfigBalanza() {
  const [activa, setActiva] = useState(false)
  const [fmt, setFmt] = useState<ScaleFormat>(POR_DEFECTO)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => { cargar() }, [])

  async function cargar() {
    setLoading(true)
    try {
      const actual = await api.get<ScaleFormat | null>('/settings/scale')
      setActiva(actual !== null)
      if (actual) setFmt(actual)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function cambiar<K extends keyof ScaleFormat>(campo: K, valor: ScaleFormat[K]) {
    setFmt((actual) => ({ ...actual, [campo]: valor }))
    setGuardado(false)
  }

  async function guardar() {
    setSaving(true)
    setError(null)
    setGuardado(false)
    try {
      if (activa) await api.put('/settings/scale', fmt)
      else await api.del('/settings/scale')
      setGuardado(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }

  const usados = fmt.prefix.length + fmt.code_digits + fmt.value_digits
  const sobran = fmt.total_digits - usados

  return (
    <div className="grid max-w-2xl gap-4">
      <h2 className="text-lg font-semibold">Balanza</h2>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Scale className="size-4" /> Etiquetas de la balanza de mostrador
          </CardTitle>
          <CardDescription>
            La balanza imprime un código de barras que además del producto lleva
            adentro cuánto se pesó. El formato depende del equipo: si no sabés
            cuál usa el tuyo, dejá los valores por defecto y probá una etiqueta
            real acá abajo.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={activa}
              onChange={(e) => { setActiva(e.target.checked); setGuardado(false) }}
              className="size-4"
            />
            El local usa balanza con etiquetas
          </label>

          {activa && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>Prefijo</Label>
                  <Input
                    value={fmt.prefix}
                    onChange={(e) => cambiar('prefix', e.target.value.replace(/\D/g, ''))}
                    className="w-24 tabular-nums"
                  />
                  <p className="text-xs text-muted-foreground">
                    Con qué empiezan las etiquetas de la balanza. Casi siempre 20.
                  </p>
                </div>

                <div className="grid gap-1.5">
                  <Label>Qué trae la etiqueta</Label>
                  <Select
                    value={fmt.value_kind}
                    onValueChange={(v) => cambiar('value_kind', v as ScaleValueKind)}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="weight">El peso</SelectItem>
                      <SelectItem value="amount">El importe ya calculado</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {fmt.value_kind === 'weight'
                      ? 'El importe lo calcula el sistema con el precio por kilo vigente.'
                      : 'Se cobra lo que dice la etiqueta, aunque el precio del sistema haya cambiado.'}
                  </p>
                </div>

                <div className="grid gap-1.5">
                  <Label>Dígitos del código de producto</Label>
                  <Input
                    type="number" min={1} value={fmt.code_digits}
                    onChange={(e) => cambiar('code_digits', Number(e.target.value))}
                    className="w-24 tabular-nums"
                  />
                </div>

                <div className="grid gap-1.5">
                  <Label>Dígitos del {fmt.value_kind === 'weight' ? 'peso' : 'importe'}</Label>
                  <Input
                    type="number" min={1} value={fmt.value_digits}
                    onChange={(e) => cambiar('value_digits', Number(e.target.value))}
                    className="w-24 tabular-nums"
                  />
                </div>

                <div className="grid gap-1.5">
                  <Label>Largo total del código</Label>
                  <Input
                    type="number" min={1} value={fmt.total_digits}
                    onChange={(e) => cambiar('total_digits', Number(e.target.value))}
                    className="w-24 tabular-nums"
                  />
                  <p className="text-xs text-muted-foreground">13 en un EAN-13, 8 en un EAN-8.</p>
                </div>

                <div className="grid gap-1.5">
                  <Label>Unidad mínima</Label>
                  <Select
                    value={String(fmt.divisor)}
                    onValueChange={(v) => cambiar('divisor', Number(v))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1000">Milésimos (gramos)</SelectItem>
                      <SelectItem value="100">Centésimos (centavos)</SelectItem>
                      <SelectItem value="10">Décimos</SelectItem>
                      <SelectItem value="1">Enteros</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {fmt.divisor === 1000 && fmt.value_kind === 'weight'
                      ? 'Un valor de 00750 se lee como 0,750 kg.'
                      : `Los dígitos se dividen por ${fmt.divisor}.`}
                  </p>
                </div>
              </div>

              <p className="text-xs text-muted-foreground">
                {sobran >= 0
                  ? `${fmt.prefix.length} + ${fmt.code_digits} + ${fmt.value_digits} = ${usados} dígitos usados,
                     ${sobran} para el verificador.`
                  : `No entra: ${usados} dígitos no caben en ${fmt.total_digits}.`}
              </p>
            </>
          )}

          <div className="flex items-center gap-3">
            <Button onClick={guardar} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
            {guardado && <span className="text-sm text-emerald-600">Guardado.</span>}
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {activa && <Probador />}
    </div>
  )
}

/** Escanea una etiqueta contra la configuración YA GUARDADA y muestra qué
 *  entendió el sistema. Es la verificación que evita descubrir un formato mal
 *  configurado recién cuando se cobró de menos. */
function Probador() {
  const [codigo, setCodigo] = useState('')
  const [resultado, setResultado] = useState<ScanResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [probando, setProbando] = useState(false)

  async function probar() {
    const texto = codigo.trim()
    if (!texto) return
    setProbando(true)
    setError(null)
    setResultado(null)
    try {
      setResultado(await api.get<ScanResult>(`/catalog/items/scan?code=${encodeURIComponent(texto)}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setProbando(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Probar una etiqueta</CardTitle>
        <CardDescription>
          Pesá algo en la balanza y escaneá la etiqueta acá. No registra ninguna venta.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex gap-2">
          <Input
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); probar() } }}
            placeholder="Escaneá o escribí el código"
            className="tabular-nums"
            autoFocus
          />
          <Button variant="secondary" onClick={probar} disabled={probando}>Probar</Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {resultado && (
          <div className="rounded-md border p-3 text-sm">
            <p className="font-medium">{resultado.item.name}</p>
            {resultado.from_scale ? (
              <p className="text-muted-foreground">
                {resultado.unit_price
                  ? `Importe impreso en la etiqueta: $${Number(resultado.unit_price)
                      .toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
                  : `Peso leído: ${Number(resultado.quantity)
                      .toLocaleString('es-AR', { minimumFractionDigits: 3 })} kg`}
              </p>
            ) : (
              <p className="text-muted-foreground">
                Se leyó como código de barras común, no como etiqueta de balanza.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
