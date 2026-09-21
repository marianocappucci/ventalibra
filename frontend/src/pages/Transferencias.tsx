/** Mover mercadería entre sucursales o depósitos.
 *
 * El caso que la motivó: dos locales del mismo dueño que se reponen entre sí.
 * Antes de esto sólo se podía con dos ajustes sueltos, que no quedan como
 * transferencia y pierden mercadería si el segundo falla.
 *
 * ⚠️ **No hay estado "en tránsito".** Al confirmar, el sistema ya cuenta la
 * mercadería en el destino; la pantalla lo dice de frente para que nadie
 * suponga que hay una recepción pendiente del otro lado.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { ArrowRightLeft } from 'lucide-react'
import { SelectBuscable, type OpcionSelect } from 'libra-ui/SelectBuscable'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { api, ApiError, type CatalogItem, type Location } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export type Transferencia = {
  id: number
  item_id: number
  item: string
  variant_id: number | null
  cantidad: string
  origen_id: number
  origen: string
  destino_id: number
  destino: string
  fecha: string
  nota: string
  usuario_id: number | null
}

type Resultado = {
  origen: { id: number; nombre: string; stock: string }
  destino: { id: number; nombre: string; stock: string }
  cantidad: string
}

export function Transferencias() {
  const [locations, setLocations] = useState<Location[]>([])
  const [items, setItems] = useState<CatalogItem[]>([])
  const [historial, setHistorial] = useState<Transferencia[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [itemId, setItemId] = useState('')
  const [origenId, setOrigenId] = useState('')
  const [destinoId, setDestinoId] = useState('')
  const [cantidad, setCantidad] = useState('')
  const [nota, setNota] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<Resultado | null>(null)

  async function cargar() {
    setCargando(true)
    try {
      const [locs, its, hist] = await Promise.all([
        api.get<Location[]>('/locations'),
        api.get<CatalogItem[]>('/catalog/items'),
        api.get<Transferencia[]>('/stock/transferencias/historial'),
      ])
      setLocations(locs)
      setItems(its)
      setHistorial(hist)
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Error de conexión.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => { void cargar() }, [])

  const opcionesItem: OpcionSelect[] = useMemo(
    () => items.map((i) => ({ value: String(i.id), label: i.name })),
    [items],
  )

  // La cantidad no se parsea con `Number(x) || 0`: eso manda un 0 en
  // silencio, y acá sería una transferencia de nada que igual queda escrita
  // en el ledger. Mismo criterio que el POS y el cierre de turno.
  const limpia = cantidad.trim().replace(',', '.')
  const numero = limpia === '' ? NaN : Number(limpia)
  const cantidadValida = Number.isFinite(numero) && numero > 0
  const cantidadInvalida = cantidad.trim() !== '' && !cantidadValida
  const mismoDeposito = origenId !== '' && origenId === destinoId
  const puedeGuardar =
    itemId !== '' && origenId !== '' && destinoId !== '' &&
    !mismoDeposito && cantidadValida && !guardando

  async function transferir() {
    if (!puedeGuardar) return
    setGuardando(true)
    setFormError(null)
    try {
      const r = await api.post<Resultado>('/stock/transferir', {
        item_id: Number(itemId),
        origen_id: Number(origenId),
        destino_id: Number(destinoId),
        cantidad: String(numero),
        nota,
      })
      setResultado(r)
      setCantidad('')
      setNota('')
      setHistorial(await api.get<Transferencia[]>('/stock/transferencias/historial'))
    } catch (e) {
      setFormError(e instanceof ApiError ? e.detail : 'Error de conexión.')
      setResultado(null)
    } finally {
      setGuardando(false)
    }
  }

  const columnas: ColumnDef<Transferencia>[] = [
    { accessorKey: 'item', header: sortableHeader('Producto') },
    {
      accessorKey: 'cantidad',
      header: 'Cantidad',
      cell: ({ row }) => <span className="tabular-nums">{row.original.cantidad}</span>,
    },
    { accessorKey: 'origen', header: sortableHeader('Desde') },
    { accessorKey: 'destino', header: sortableHeader('Hasta') },
    { accessorKey: 'nota', header: 'Nota' },
  ]

  function selectDeposito(
    id: string, valor: string, onChange: (v: string) => void, etiqueta: string,
  ) {
    return (
      <div className="grid gap-2">
        <Label htmlFor={id}>{etiqueta}</Label>
        <Select value={valor} onValueChange={onChange}>
          <SelectTrigger id={id} className="w-full">
            <SelectValue placeholder="Elegí una sucursal o depósito…" />
          </SelectTrigger>
          <SelectContent>
            {locations.map((l) => (
              <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <TituloPantalla icono={ArrowRightLeft}>Transferencias</TituloPantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mover mercadería</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <Label>Producto</Label>
            <SelectBuscable
              value={itemId}
              onChange={setItemId}
              opciones={opcionesItem}
              placeholder="Buscá un producto…"
              ariaLabel="Producto"
              className="w-full"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {selectDeposito('origen', origenId, setOrigenId, 'Desde')}
            {selectDeposito('destino', destinoId, setDestinoId, 'Hasta')}
          </div>
          {mismoDeposito && (
            <p className="text-sm text-destructive">
              El origen y el destino son el mismo: la transferencia no movería nada.
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="cantidad">Cantidad</Label>
              <Input
                id="cantidad"
                inputMode="decimal"
                value={cantidad}
                onChange={(e) => setCantidad(e.target.value)}
              />
              {cantidadInvalida && (
                <p className="text-sm text-destructive">Escribí una cantidad mayor que cero.</p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="nota">Nota (opcional)</Label>
              <Input id="nota" value={nota} onChange={(e) => setNota(e.target.value)} />
            </div>
          </div>

          {/* Se dice en la pantalla y no sólo en la documentación: al
              confirmar, el destino ya cuenta la mercadería. */}
          <p className="text-sm text-muted-foreground">
            Al confirmar, el destino cuenta la mercadería en el acto: no queda
            pendiente de recepción.
          </p>

          {formError && <p className="text-sm text-destructive">{formError}</p>}
          {resultado && (
            <p className="text-sm">
              Listo: {resultado.cantidad} de {resultado.origen.nombre} a{' '}
              {resultado.destino.nombre}. Quedan {resultado.origen.stock} en el
              origen y {resultado.destino.stock} en el destino.
            </p>
          )}

          <Button onClick={() => void transferir()} disabled={!puedeGuardar}>
            {guardando ? 'Transfiriendo…' : 'Transferir'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Historial</CardTitle>
        </CardHeader>
        <CardContent>
          {cargando ? (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          ) : historial.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Todavía no se transfirió mercadería.
            </p>
          ) : (
            <DataTable columns={columnas} data={historial} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
