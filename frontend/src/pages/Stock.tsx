/** Cuánto hay de cada producto, y en qué sucursal.
 *
 * `Reportes` ya tenía una tarjeta de stock, pero suma **todo el parque por
 * producto**: dice que hay 10 de algo y no dónde están esas 10. Con varias
 * sucursales ese total no alcanza para decidir nada — dos repartos muy
 * distintos dan el mismo número, y uno de los dos deja un local en cero.
 *
 * Los depósitos en cero se muestran a propósito: uno que falta de la fila es
 * indistinguible de uno que existe y está vacío, y la pregunta que se le hace
 * a esta pantalla es "¿de dónde saco esto?".
 */
import { useEffect, useMemo, useState } from 'react'
import type { ColumnDef } from 'libra-ui/data-table'
import { Boxes } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { api, ApiError, type StockPorDeposito, type StockPorDepositoItem } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function numero(valor: string | undefined): number {
  const n = Number(valor)
  return Number.isFinite(n) ? n : 0
}

/** Un número de stock, con el cero y el negativo marcados.
 *
 * El negativo no se esconde: significa que se vendió más de lo que el sistema
 * creía tener, y taparlo con un 0 borra justamente la señal de que el
 * inventario está mal cargado. */
function Cantidad({ valor }: { valor: string | undefined }) {
  const n = numero(valor)
  const tono = n < 0 ? 'text-destructive font-medium' : n === 0 ? 'text-muted-foreground' : ''
  return <span className={`tabular-nums ${tono}`}>{valor ?? '0'}</span>
}

export function Stock() {
  const [datos, setDatos] = useState<StockPorDeposito | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [soloConStock, setSoloConStock] = useState(false)
  const [busqueda, setBusqueda] = useState('')

  async function cargar() {
    setCargando(true)
    try {
      setDatos(await api.get<StockPorDeposito>('/stock/por-deposito/grilla'))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Error de conexión.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => { void cargar() }, [])

  const depositos = datos?.depositos ?? []

  const filas = useMemo(() => {
    let items = datos?.items ?? []
    if (soloConStock) items = items.filter((i) => numero(i.total) !== 0)
    const q = busqueda.trim().toLowerCase()
    if (q) items = items.filter((i) => i.nombre.toLowerCase().includes(q))
    return items
  }, [datos, soloConStock, busqueda])

  const columnas = useMemo<ColumnDef<StockPorDepositoItem>[]>(() => [
    {
      accessorKey: 'nombre',
      header: sortableHeader('Producto'),
      size: 260,
      minSize: 160,
      meta: { stretch: true },
      cell: ({ row }) => (
        <span className="block truncate font-medium" title={row.original.nombre}>
          {row.original.nombre}
        </span>
      ),
    },
    { accessorKey: 'unit_code', header: 'Unidad', size: 90, minSize: 70 },
    // Una columna por depósito. El `accessorFn` devuelve el NÚMERO y no el
    // texto para que ordenar por una sucursal ordene por cantidad y no
    // alfabéticamente ("10" antes que "9").
    ...depositos.map((d): ColumnDef<StockPorDepositoItem> => ({
      id: `dep-${d.id}`,
      header: sortableHeader(d.nombre),
      size: 120,
      minSize: 90,
      accessorFn: (item) => numero(item.por_deposito[String(d.id)]),
      cell: ({ row }) => <Cantidad valor={row.original.por_deposito[String(d.id)]} />,
    })),
    {
      id: 'total',
      header: sortableHeader('Total'),
      size: 110,
      minSize: 90,
      accessorFn: (item) => numero(item.total),
      cell: ({ row }) => (
        <span className="font-medium"><Cantidad valor={row.original.total} /></span>
      ),
    },
  ], [depositos])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <TituloPantalla icono={Boxes}>Stock</TituloPantalla>
        <Button variant="outline" onClick={() => void cargar()} disabled={cargando}>
          {cargando ? 'Actualizando…' : 'Actualizar'}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="grid gap-2">
              <Label htmlFor="stock-buscar">Buscar producto</Label>
              <Input
                id="stock-buscar"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                className="w-64"
              />
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={soloConStock}
                onChange={(e) => setSoloConStock(e.target.checked)}
                className="size-4"
              />
              Sólo los que tienen stock
            </label>
          </div>

          {cargando ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : depositos.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Todavía no hay sucursales ni depósitos cargados.
            </p>
          ) : (
            <DataTable
              columns={columnas}
              data={filas}
              emptyMessage="Ningún producto coincide."
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
