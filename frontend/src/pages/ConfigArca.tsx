import { useEffect, useState } from 'react'
import { api, ApiError, type ArcaConfig } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

export function ConfigArca() {
  const [cuit, setCuit] = useState('')
  const [puntoVenta, setPuntoVenta] = useState('1')
  const [certificadoPath, setCertificadoPath] = useState('')
  const [clavePath, setClavePath] = useState('')
  const [ambiente, setAmbiente] = useState('homologacion')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const cfg = await api.get<ArcaConfig | null>('/config/arca')
      if (cfg) {
        setCuit(cfg.cuit)
        setPuntoVenta(String(cfg.punto_venta))
        setCertificadoPath(cfg.certificado_path)
        setClavePath(cfg.clave_path)
        setAmbiente(cfg.ambiente)
      }
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await api.put('/config/arca', {
        cuit, punto_venta: Number(puntoVenta),
        certificado_path: certificadoPath, clave_path: clavePath, ambiente,
      })
      setSaved(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }

  return (
    <div className="grid gap-4 max-w-lg">
      <h2 className="text-lg font-semibold">Configuración ARCA</h2>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Facturación electrónica</CardTitle>
          <CardDescription>
            Certificado y clave se referencian por path en el filesystem del servidor —
            subir el archivo real es una tarea manual todavía.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>CUIT</Label>
            <Input value={cuit} onChange={(e) => setCuit(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label>Punto de venta</Label>
            <Input value={puntoVenta} onChange={(e) => setPuntoVenta(e.target.value)} className="w-32" />
          </div>
          <div className="grid gap-1.5">
            <Label>Ambiente</Label>
            <Select value={ambiente} onValueChange={setAmbiente}>
              <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="homologacion">Homologación</SelectItem>
                <SelectItem value="produccion">Producción</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>Path del certificado</Label>
            <Input value={certificadoPath} onChange={(e) => setCertificadoPath(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label>Path de la clave privada</Label>
            <Input value={clavePath} onChange={(e) => setClavePath(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {saved && <p className="text-sm text-muted-foreground">Guardado.</p>}
          <Button onClick={handleSave} disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Button>
        </CardContent>
      </Card>
    </div>
  )
}
