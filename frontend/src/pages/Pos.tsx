// Pantalla del cajero. Optimizada para despensa/autoservicio con lector de
// codigo de barras y teclado -- sin mouse: el foco vive en el campo de
// escaneo y vuelve solo, y todo lo demas son atajos de teclado.
//
// La regla de fondo: escanear AGREGA. No hay paso de confirmacion, porque el
// cajero mira el producto, no la pantalla; el acuse de que entro es la linea
// resaltada un segundo en el ticket.
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  api, ApiError, type CatalogItem, type ItemVariant, type Location, type Sale,
  type ScanResult, type Shift, type ShiftState, type ShiftSummary,
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
import { Ban, LockKeyhole, Plus, Scan, Trash2 } from 'lucide-react'

const MEDIOS_PAGO = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'tarjeta_debito', label: 'Tarjeta de débito' },
  { value: 'tarjeta_credito', label: 'Tarjeta de crédito' },
  { value: 'transferencia', label: 'Transferencia' },
  { value: 'mercado_pago', label: 'Mercado Pago' },
]

const ATAJOS = [
  ['F2', 'cobrar'], ['F3', 'dividir pago'], ['F4', 'quitar línea'],
  ['F6', 'cantidad'], ['F9', 'factura'], ['Esc', 'cancelar venta'],
]

// La sucursal se elige una vez y queda: en el mostrador no cambia entre
// ventas, y preguntarla en cada uno era ruido puro.
const LOCATION_KEY = 'ventalibra.pos.location'

function money(value: string | number): string {
  return Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

/** Las cantidades enteras se ven como enteros ("3"); las pesadas, con los
 *  tres decimales del kilo ("0,750") -- que es como el cajero lee la
 *  etiqueta de la balanza y puede compararla contra la pantalla. */
function cantidadLegible(value: string): string {
  const n = Number(value)
  return Number.isInteger(n)
    ? String(n)
    : n.toLocaleString('es-AR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

/** `3 * 7790123456` => cantidad 3, codigo 7790123456. Es el gesto que el
 *  cajero ya conoce de cualquier supermercado: multiplicador y despues el
 *  producto, sin tocar un campo aparte. */
function parseMultiplicador(texto: string): { cantidad: string; resto: string } {
  const m = /^\s*(\d+(?:[.,]\d+)?)\s*[*x]\s*(.+)$/i.exec(texto)
  if (!m) return { cantidad: '1', resto: texto.trim() }
  return { cantidad: m[1].replace(',', '.'), resto: m[2].trim() }
}

export function Pos() {
  const [locations, setLocations] = useState<Location[]>([])
  const [locationId, setLocationId] = useState<string>(
    () => localStorage.getItem(LOCATION_KEY) ?? '',
  )

  const [sale, setSale] = useState<Sale | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmada, setConfirmada] = useState<Sale | null>(null)

  // Linea marcada: sobre ella actuan F4 (quitar) y F6 (cantidad). Arranca en
  // la ultima agregada, que es la que el cajero suele querer corregir.
  const [marcada, setMarcada] = useState<number | null>(null)
  const [reciente, setReciente] = useState<number | null>(null)

  const [candidatos, setCandidatos] = useState<CatalogItem[]>([])
  const [variantes, setVariantes] = useState<ItemVariant[]>([])
  const [pendiente, setPendiente] = useState<{ item: CatalogItem; cantidad: string } | null>(null)

  const [cobroOpen, setCobroOpen] = useState(false)
  const [cantidadOpen, setCantidadOpen] = useState(false)
  const escaneoRef = useRef<HTMLInputElement>(null)

  // Sin turno abierto el backend rechaza el cobro (409), asi que la pantalla
  // pide la apertura antes de dejar vender en vez de esperar al error.
  const [turno, setTurno] = useState<Shift | null>(null)
  const [turnoCargado, setTurnoCargado] = useState(false)
  const [cierreOpen, setCierreOpen] = useState(false)

  const cargarTurno = useCallback(async () => {
    try {
      const estado = await api.get<ShiftState>('/shifts/current')
      setTurno(estado.turno)
    } catch {
      setTurno(null)
    } finally {
      setTurnoCargado(true)
    }
  }, [])

  useEffect(() => { cargarTurno() }, [cargarTurno])

  const hayDialogo = cobroOpen || cantidadOpen || cierreOpen || !turno
    || candidatos.length > 0 || variantes.length > 0

  const enfocarEscaneo = useCallback(() => {
    if (hayDialogo) return
    escaneoRef.current?.focus()
  }, [hayDialogo])

  useEffect(() => {
    api.get<Location[]>('/locations')
      .then((items) => {
        setLocations(items)
        setLocationId((actual) => {
          if (actual && items.some((l) => String(l.id) === actual)) return actual
          return items.length > 0 ? String(items[0].id) : ''
        })
      })
      .catch(() => setLocations([]))
  }, [])

  useEffect(() => {
    if (locationId) localStorage.setItem(LOCATION_KEY, locationId)
  }, [locationId])

  // El foco vuelve al campo de escaneo apenas se cierra lo que lo saco: el
  // cajero nunca tiene que ir a buscarlo con el mouse.
  useEffect(() => { enfocarEscaneo() }, [enfocarEscaneo, sale, confirmada])

  useEffect(() => {
    if (reciente === null) return
    const t = setTimeout(() => setReciente(null), 1000)
    return () => clearTimeout(t)
  }, [reciente])

  async function conVenta(): Promise<Sale> {
    if (sale) return sale
    const creada = await api.post<Sale>('/sales', {})
    setSale(creada)
    return creada
  }

  async function agregar(
    item: CatalogItem, cantidad: string, variantId?: number, precioUnitario?: string | null,
  ) {
    setBusy(true)
    setError(null)
    try {
      const actual = await conVenta()
      const actualizada = await api.post<Sale>(`/sales/${actual.id}/items`, {
        item_id: item.id, variant_id: variantId ?? null, quantity: cantidad,
        // Solo lo manda la balanza configurada para imprimir el importe ya
        // calculado: ahi se cobra lo que dice la etiqueta pegada al producto
        // y no el precio de la lista, que pudo cambiar despues de pesar.
        ...(precioUnitario ? { unit_price: precioUnitario } : {}),
      })
      setSale(actualizada)
      setReciente(actualizada.items.length - 1)
      setMarcada(actualizada.items.length - 1)
      setQuery('')
      setCandidatos([])
      setVariantes([])
      setPendiente(null)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
      enfocarEscaneo()
    }
  }

  async function elegirItem(
    item: CatalogItem, cantidad: string, precioUnitario?: string | null,
  ) {
    // Un item con variantes no se puede vender sin elegir cual: se pregunta
    // solo en ese caso, no en cada producto.
    try {
      const vs = await api.get<ItemVariant[]>(`/catalog/items/${item.id}/variants`)
      if (vs.length > 0) {
        setPendiente({ item, cantidad })
        setVariantes(vs)
        setCandidatos([])
        return
      }
    } catch {
      // sin variantes accesibles: se vende el item pelado
    }
    await agregar(item, cantidad, undefined, precioUnitario)
  }

  async function buscar(event: FormEvent) {
    event.preventDefault()
    const texto = query.trim()
    if (!texto) return
    const { cantidad, resto } = parseMultiplicador(texto)
    if (!resto) return

    setBusy(true)
    setError(null)
    try {
      // Primero por codigo exacto: es lo que manda el lector, y tiene que
      // entrar sin intervencion.
      const escaneado = await api.get<ScanResult>(
        `/catalog/items/scan?code=${encodeURIComponent(resto)}`,
      )
      // Una etiqueta de balanza ya trae cuanto se peso, y el multiplicador
      // no aplica: cada etiqueta es de un paquete concreto, no de N iguales.
      await elegirItem(
        escaneado.item,
        escaneado.from_scale ? escaneado.quantity : cantidad,
        escaneado.unit_price,
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        try {
          const encontrados = await api.get<CatalogItem[]>(
            `/catalog/items?search=${encodeURIComponent(resto)}`,
          )
          if (encontrados.length === 0) setError(`Sin resultados para "${resto}".`)
          else if (encontrados.length === 1) await elegirItem(encontrados[0], cantidad)
          else { setCandidatos(encontrados); setPendiente({ item: encontrados[0], cantidad }) }
        } catch (e2) {
          setError(describeError(e2))
        }
      } else {
        setError(describeError(err))
      }
    } finally {
      setBusy(false)
    }
  }

  async function quitarLinea(index: number) {
    if (!sale) return
    setBusy(true)
    setError(null)
    try {
      const actualizada = await api.del<Sale>(`/sales/${sale.id}/items/${index}`)
      setSale(actualizada)
      setMarcada(actualizada.items.length > 0 ? actualizada.items.length - 1 : null)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
      enfocarEscaneo()
    }
  }

  async function cambiarCantidad(index: number, cantidad: string) {
    if (!sale) return
    setBusy(true)
    setError(null)
    try {
      const actualizada = await api.patch<Sale>(`/sales/${sale.id}/items/${index}`, {
        quantity: cantidad,
      })
      setSale(actualizada)
      setCantidadOpen(false)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
      enfocarEscaneo()
    }
  }

  function cancelarVenta() {
    setSale(null)
    setMarcada(null)
    setQuery('')
    setCandidatos([])
    setVariantes([])
    setPendiente(null)
    setError(null)
    enfocarEscaneo()
  }

  const puedeCobrar = Boolean(sale && sale.items.length > 0 && locationId)

  // Atajos globales. preventDefault en las F porque el navegador se las
  // queda (F3 abre buscar, F6 mueve el foco a la barra de direcciones).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'F2') { e.preventDefault(); if (puedeCobrar) setCobroOpen(true) }
      else if (e.key === 'F3') { e.preventDefault(); if (puedeCobrar) setCobroOpen(true) }
      else if (e.key === 'F4') {
        e.preventDefault()
        if (marcada !== null && sale?.items.length) quitarLinea(marcada)
      } else if (e.key === 'F6') {
        e.preventDefault()
        if (marcada !== null && sale?.items.length) setCantidadOpen(true)
      } else if (e.key === 'Escape' && !hayDialogo) {
        e.preventDefault()
        if (sale) cancelarVenta()
      } else if (e.key === 'ArrowUp' && sale?.items.length) {
        e.preventDefault()
        setMarcada((i) => (i === null ? sale.items.length - 1 : Math.max(0, i - 1)))
      } else if (e.key === 'ArrowDown' && sale?.items.length) {
        e.preventDefault()
        setMarcada((i) => (i === null ? 0 : Math.min(sale.items.length - 1, i + 1)))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // Nada de POS hasta que haya turno: es la misma regla que aplica el
  // backend, mostrada antes de que el cajero cargue una venta que no va a
  // poder cobrar.
  if (turnoCargado && !turno) {
    return <AbrirTurno onAbierto={(t) => setTurno(t)} />
  }

  if (confirmada) {
    return (
      <VentaCobrada
        venta={confirmada}
        onNueva={() => { setConfirmada(null); setSale(null); setMarcada(null); setQuery('') }}
      />
    )
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span className="flex items-center gap-2">
          <Scan className="size-4 text-primary" />
          {sale ? `Venta ${sale.number}` : 'Nueva venta'}
        </span>
        <div className="flex items-center gap-2">
          {turno && (
            <>
              <span className="rounded border px-2 py-0.5 text-xs">
                Turno #{turno.id} · desde {turno.apertura.slice(11, 16)} · inicial ${money(turno.monto_inicial)}
              </span>
              <Button size="sm" variant="outline" onClick={() => setCierreOpen(true)}>
                Cerrar turno
              </Button>
            </>
          )}
          <span className="text-xs">Sucursal</span>
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger className="h-8 w-48"><SelectValue placeholder="Elegí una sucursal…" /></SelectTrigger>
            <SelectContent>
              {locations.map((loc) => (
                <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <form onSubmit={buscar} className="flex items-center gap-2">
        <Scan className="size-5 shrink-0 text-primary" aria-hidden="true" />
        <Input
          ref={escaneoRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Escaneá o escribí código / nombre…    (3 * código para 3 unidades)"
          className="h-11 flex-1 text-base"
          autoFocus
          aria-label="Código o nombre del producto"
        />
        <Button type="submit" disabled={busy} className="h-11">Agregar</Button>
      </form>

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Ticket
          sale={sale}
          marcada={marcada}
          reciente={reciente}
          onMarcar={setMarcada}
          onQuitar={quitarLinea}
        />

        <div className="grid content-start gap-2">
          <div className="rounded-md border p-4">
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="text-4xl font-medium tabular-nums">${money(sale?.total ?? 0)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {sale?.items.length ?? 0} producto{(sale?.items.length ?? 0) === 1 ? '' : 's'}
            </p>
          </div>
          <Button
            className="h-14 text-base"
            disabled={!puedeCobrar || busy}
            onClick={() => setCobroOpen(true)}
          >
            Cobrar <span className="ml-2 text-xs opacity-70">F2</span>
          </Button>
          {sale && (
            <Button variant="outline" onClick={cancelarVenta} disabled={busy}>
              <Ban />Cancelar venta <span className="ml-1 text-xs opacity-70">Esc</span>
            </Button>
          )}
          {locations.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No hay sucursales creadas todavía: sin una, no se puede cobrar.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {ATAJOS.map(([tecla, que]) => (
          <span key={tecla} className="rounded border px-2 py-0.5 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{tecla}</span> {que}
          </span>
        ))}
      </div>

      <ElegirCandidato
        candidatos={candidatos}
        onElegir={(item) => elegirItem(item, pendiente?.cantidad ?? '1')}
        onCerrar={() => { setCandidatos([]); setPendiente(null); enfocarEscaneo() }}
      />

      <ElegirVariante
        variantes={variantes}
        onElegir={(v) => pendiente && agregar(pendiente.item, pendiente.cantidad, v.id)}
        onCerrar={() => { setVariantes([]); setPendiente(null); enfocarEscaneo() }}
      />

      {cantidadOpen && marcada !== null && sale?.items[marcada] && (
        <CambiarCantidad
          linea={sale.items[marcada]}
          onAceptar={(cant) => cambiarCantidad(marcada, cant)}
          onCerrar={() => { setCantidadOpen(false); enfocarEscaneo() }}
        />
      )}

      {cierreOpen && turno && (
        <CerrarTurno
          turno={turno}
          onCerrado={() => { setCierreOpen(false); setTurno(null); setSale(null) }}
          onCancelar={() => { setCierreOpen(false); enfocarEscaneo() }}
        />
      )}

      {cobroOpen && sale && (
        <Cobro
          total={sale.total}
          busy={busy}
          onCerrar={() => { setCobroOpen(false); enfocarEscaneo() }}
          onCobrar={async (pagos, factura) => {
            setBusy(true)
            setError(null)
            try {
              const cobrada = await api.post<Sale>(`/sales/${sale.id}/confirm`, {
                location_id: Number(locationId), pagos, invoice: factura,
              })
              setCobroOpen(false)
              setConfirmada(cobrada)
              setSale(null)
            } catch (err) {
              setError(describeError(err))
            } finally {
              setBusy(false)
            }
          }}
        />
      )}
    </div>
  )
}


function Ticket({ sale, marcada, reciente, onMarcar, onQuitar }: {
  sale: Sale | null
  marcada: number | null
  reciente: number | null
  onMarcar: (i: number) => void
  onQuitar: (i: number) => void
}) {
  if (!sale || sale.items.length === 0) {
    return (
      <div className="flex min-h-56 items-center justify-center rounded-md border border-dashed p-6 text-sm text-muted-foreground">
        Escaneá el primer producto para empezar la venta.
      </div>
    )
  }
  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <th className="w-8 p-2 text-left">#</th>
            <th className="p-2 text-left">Producto</th>
            <th className="w-16 p-2 text-center">Cant.</th>
            <th className="w-24 p-2 text-right">P. unit.</th>
            <th className="w-28 p-2 text-right">Importe</th>
            <th className="w-12 p-2" />
          </tr>
        </thead>
        <tbody>
          {sale.items.map((linea, i) => (
            <tr
              key={i}
              onClick={() => onMarcar(i)}
              className={[
                'cursor-pointer border-b last:border-0',
                i === marcada ? 'bg-accent' : '',
                // El resaltado del escaneo pisa al de seleccion: es el acuse
                // de que la linea entro, y dura un segundo.
                i === reciente ? 'bg-emerald-100 dark:bg-emerald-950' : '',
              ].join(' ')}
            >
              <td className="p-2 text-muted-foreground">{i + 1}</td>
              <td className="p-2">{linea.description_snapshot}</td>
              <td className="p-2 text-center tabular-nums">{cantidadLegible(linea.quantity)}</td>
              <td className="p-2 text-right tabular-nums">${money(linea.unit_price)}</td>
              <td className="p-2 text-right tabular-nums">${money(linea.line_total)}</td>
              <td className="p-2 text-right">
                <Button
                  size="icon" variant="ghost" title="Quitar línea" aria-label="Quitar línea"
                  className="text-destructive hover:text-destructive"
                  onClick={(e) => { e.stopPropagation(); onQuitar(i) }}
                >
                  <Trash2 />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ElegirCandidato({ candidatos, onElegir, onCerrar }: {
  candidatos: CatalogItem[]
  onElegir: (item: CatalogItem) => void
  onCerrar: () => void
}) {
  if (candidatos.length === 0) return null
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader><DialogTitle>¿Cuál de estos?</DialogTitle></DialogHeader>
        <div className="grid max-h-80 gap-1 overflow-y-auto">
          {candidatos.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onElegir(item)}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <span>{item.name}</span>
              <span className="tabular-nums text-muted-foreground">${money(item.default_sale_price)}</span>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ElegirVariante({ variantes, onElegir, onCerrar }: {
  variantes: ItemVariant[]
  onElegir: (v: ItemVariant) => void
  onCerrar: () => void
}) {
  if (variantes.length === 0) return null
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Elegí la variante</DialogTitle></DialogHeader>
        <div className="grid max-h-80 gap-1 overflow-y-auto">
          {variantes.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => onElegir(v)}
              className="rounded-md border px-3 py-2 text-left text-sm hover:bg-accent"
            >
              {v.name}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CambiarCantidad({ linea, onAceptar, onCerrar }: {
  linea: { description_snapshot: string; quantity: string }
  onAceptar: (cantidad: string) => void
  onCerrar: () => void
}) {
  const [valor, setValor] = useState(String(Number(linea.quantity)))
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>{linea.description_snapshot}</DialogTitle></DialogHeader>
        <form
          onSubmit={(e) => { e.preventDefault(); onAceptar(valor) }}
          className="grid gap-3"
        >
          <div className="grid gap-1.5">
            <Label htmlFor="cantidad-nueva">Cantidad</Label>
            <Input
              id="cantidad-nueva" value={valor} autoFocus
              onChange={(e) => setValor(e.target.value)}
              onFocus={(e) => e.target.select()}
              className="h-12 text-lg"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
            <Button type="submit">Aceptar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}


type PagoForm = { medio: string; monto: string; recibido: string }

/** Cobro. El numero que importa es el vuelto: es lo que el cajero mira
 *  mientras cuenta el cambio, asi que se calcula en vivo y se muestra
 *  grande. Si lo entregado no alcanza, lo dice en vez de mostrar un vuelto
 *  negativo. */
function Cobro({ total, busy, onCobrar, onCerrar }: {
  total: string
  busy: boolean
  onCobrar: (pagos: { medio: string; monto: string; recibido?: string }[], factura: boolean) => void
  onCerrar: () => void
}) {
  const totalNum = Number(total)
  const [pagos, setPagos] = useState<PagoForm[]>([
    { medio: 'efectivo', monto: total, recibido: '' },
  ])
  const [factura, setFactura] = useState(false)
  const mixto = pagos.length > 1

  const cubierto = pagos.reduce((acc, p) => acc + (Number(p.monto) || 0), 0)
  const falta = totalNum - cubierto
  const vuelto = pagos.reduce((acc, p) => {
    const recibido = Number(p.recibido)
    const monto = Number(p.monto) || 0
    if (!p.recibido || isNaN(recibido) || recibido <= monto) return acc
    return acc + (recibido - monto)
  }, 0)
  const faltaEfectivo = pagos.some(
    (p) => p.recibido !== '' && Number(p.recibido) < (Number(p.monto) || 0),
  )
  const puedeCobrar = falta <= 0.009 && !faltaEfectivo && !busy

  function actualizar(i: number, campo: keyof PagoForm, valor: string) {
    setPagos((prev) => prev.map((p, idx) => (idx === i ? { ...p, [campo]: valor } : p)))
  }

  function agregarMedio() {
    const restante = Math.max(0, totalNum - cubierto)
    setPagos((prev) => [...prev, { medio: 'tarjeta_debito', monto: restante.toFixed(2), recibido: '' }])
  }

  function enviar() {
    if (!puedeCobrar) return
    onCobrar(
      pagos
        .filter((p) => Number(p.monto) > 0)
        .map((p) => ({
          medio: p.medio,
          monto: p.monto,
          ...(p.medio === 'efectivo' && p.recibido ? { recibido: p.recibido } : {}),
        })),
      factura,
    )
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Cobrar ${money(total)}</DialogTitle></DialogHeader>

        <form onSubmit={(e) => { e.preventDefault(); enviar() }} className="grid gap-3">
          {pagos.map((pago, i) => (
            <div key={i} className="grid gap-2 rounded-md border p-3">
              <div className="flex items-center gap-2">
                <Select value={pago.medio} onValueChange={(v) => actualizar(i, 'medio', v)}>
                  <SelectTrigger className="h-9 flex-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MEDIOS_PAGO.map((m) => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {mixto && (
                  <Button
                    type="button" size="icon" variant="ghost"
                    title="Quitar medio" aria-label="Quitar medio"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setPagos((prev) => prev.filter((_, idx) => idx !== i))}
                  >
                    <Trash2 />
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <Label className="text-xs" htmlFor={`monto-${i}`}>Monto</Label>
                  <Input
                    id={`monto-${i}`} value={pago.monto} className="h-10 tabular-nums"
                    onChange={(e) => actualizar(i, 'monto', e.target.value)}
                    onFocus={(e) => e.target.select()}
                  />
                </div>
                {pago.medio === 'efectivo' && (
                  <div className="grid gap-1">
                    <Label className="text-xs" htmlFor={`recibido-${i}`}>Recibe</Label>
                    <Input
                      id={`recibido-${i}`} value={pago.recibido} className="h-10 tabular-nums"
                      placeholder="opcional"
                      autoFocus={i === 0}
                      onChange={(e) => actualizar(i, 'recibido', e.target.value)}
                      onFocus={(e) => e.target.select()}
                    />
                  </div>
                )}
              </div>
            </div>
          ))}

          <Button type="button" variant="outline" size="sm" onClick={agregarMedio}>
            <Plus />Dividir en otro medio
          </Button>

          <div className="rounded-md border p-3">
            {falta > 0.009 ? (
              <p className="text-sm text-destructive">
                Falta cubrir ${money(falta)} para llegar al total.
              </p>
            ) : faltaEfectivo ? (
              <p className="text-sm text-destructive">
                Lo recibido es menor que el monto de ese pago.
              </p>
            ) : (
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-muted-foreground">Vuelto</span>
                <span className="text-3xl font-medium tabular-nums text-emerald-600 dark:text-emerald-500">
                  ${money(vuelto)}
                </span>
              </div>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={factura} onChange={(e) => setFactura(e.target.checked)} />
            Emitir factura
          </label>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
            <Button type="submit" disabled={!puedeCobrar} className="min-w-32">
              {busy ? 'Cobrando...' : 'Cobrar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Pantalla de cierre: lo unico que el cajero necesita ver es cuanto vuelto
 *  dar. El numero de venta y la factura quedan como dato secundario. */
function VentaCobrada({ venta, onNueva }: { venta: Sale; onNueva: () => void }) {
  const vuelto = Number(venta.vuelto_total)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Enter' || e.key === 'F2' || e.key === 'Escape') {
        e.preventDefault()
        onNueva()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNueva])

  return (
    <div className="grid gap-4">
      <div className="rounded-md border p-6 text-center">
        <p className="text-sm text-muted-foreground">Venta {venta.number} cobrada</p>
        <p className="mt-1 text-2xl font-medium tabular-nums">${money(venta.total)}</p>
        {vuelto > 0 && (
          <div className="mt-5 border-t pt-5">
            <p className="text-sm text-muted-foreground">Vuelto</p>
            <p className="text-5xl font-medium tabular-nums text-emerald-600 dark:text-emerald-500">
              ${money(vuelto)}
            </p>
          </div>
        )}
        {venta.pagos.length > 1 && (
          <p className="mt-4 text-xs text-muted-foreground">
            {venta.pagos.map((p) => `${p.medio} $${money(p.monto)}`).join(' - ')}
          </p>
        )}
        {venta.factura && (
          <p className="mt-3 text-xs text-muted-foreground">
            Factura {venta.factura.punto_venta}-{venta.factura.numero} - CAE {venta.factura.cae}
          </p>
        )}
      </div>
      <Button className="h-14 text-base" onClick={onNueva} autoFocus>
        Nueva venta
      </Button>
    </div>
  )
}


/** Apertura del turno. Bloquea el POS: sin turno el backend rechaza el cobro
 *  (409), y descubrirlo recien al cobrar significa haber cargado la venta
 *  entera al pedo. */
function AbrirTurno({ onAbierto }: { onAbierto: (t: Shift) => void }) {
  const [monto, setMonto] = useState('0')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function abrir(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const abierto = await api.post<{ turno: Shift }>('/shifts/open', {
        monto_inicial: Number(monto) || 0,
      })
      onAbierto(abierto.turno)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto grid max-w-md gap-4 pt-10">
      <div className="rounded-md border p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <LockKeyhole className="size-5" />
          <span className="text-sm">No hay ningún turno de caja abierto</span>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Para poder cobrar hace falta abrir el turno. Contá lo que hay en el
          cajón ahora: es la base contra la que se arquea al cerrar.
        </p>
        <form onSubmit={abrir} className="mt-5 grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="monto-inicial">Efectivo inicial en caja</Label>
            <Input
              id="monto-inicial" value={monto} autoFocus className="h-12 text-lg tabular-nums"
              onChange={(e) => setMonto(e.target.value)}
              onFocus={(e) => e.target.select()}
            />
          </div>
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          <Button type="submit" className="h-12 text-base" disabled={busy}>
            {busy ? 'Abriendo...' : 'Abrir turno'}
          </Button>
        </form>
      </div>
    </div>
  )
}

/** Cierre con arqueo. Lo que importa es la diferencia: se calcula en vivo
 *  mientras el cajero tipea lo que conto, para que la vea antes de confirmar
 *  y no despues. */
function CerrarTurno({ turno, onCerrado, onCancelar }: {
  turno: Shift
  onCerrado: () => void
  onCancelar: () => void
}) {
  const [resumen, setResumen] = useState<ShiftSummary | null>(null)
  const [declarado, setDeclarado] = useState('')
  const [notas, setNotas] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<ShiftState>(`/shifts/${turno.id}/summary`)
      .then((r) => setResumen(r.resumen ?? null))
      .catch(() => setResumen(null))
  }, [turno.id])

  const esperado = resumen ? turno.monto_inicial + resumen.efectivo_ventas : null
  const contado = Number(declarado)
  const diferencia = esperado !== null && declarado !== '' && !isNaN(contado)
    ? contado - esperado
    : null

  async function cerrar(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.post(`/shifts/${turno.id}/close`, {
        monto_declarado: Number(declarado) || 0, notas,
      })
      onCerrado()
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onCancelar()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Cerrar turno #{turno.id}</DialogTitle></DialogHeader>
        <form onSubmit={cerrar} className="grid gap-3">
          <div className="grid gap-1 rounded-md border p-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Efectivo inicial</span>
              <span className="tabular-nums">${money(turno.monto_inicial)}</span>
            </div>
            {resumen && Object.entries(resumen.pagos_por_medio).map(([medio, total]) => (
              <div key={medio} className="flex justify-between">
                <span className="text-muted-foreground">{medio.replace(/_/g, ' ')}</span>
                <span className="tabular-nums">${money(total)}</span>
              </div>
            ))}
            <div className="mt-1 flex justify-between border-t pt-2 font-medium">
              <span>Efectivo esperado en caja</span>
              <span className="tabular-nums">
                {esperado === null ? '—' : `$${money(esperado)}`}
              </span>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="declarado">Efectivo contado</Label>
            <Input
              id="declarado" value={declarado} autoFocus className="h-12 text-lg tabular-nums"
              placeholder="0,00"
              onChange={(e) => setDeclarado(e.target.value)}
              onFocus={(e) => e.target.select()}
            />
          </div>

          {diferencia !== null && (
            <div className="flex items-baseline justify-between rounded-md border p-3">
              <span className="text-sm text-muted-foreground">Diferencia</span>
              <span
                className={[
                  'text-2xl font-medium tabular-nums',
                  Math.abs(diferencia) < 0.005
                    ? 'text-emerald-600 dark:text-emerald-500'
                    : 'text-destructive',
                ].join(' ')}
              >
                {/* el signo va antes del $: un faltante se lee -$500,00, no
                    $-500,00, que es como sale al formatear el negativo */}
                {diferencia < 0 ? '-' : diferencia > 0 ? '+' : ''}${money(Math.abs(diferencia))}
              </span>
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="notas-cierre">Notas</Label>
            <Input
              id="notas-cierre" value={notas} placeholder="opcional"
              onChange={(e) => setNotas(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancelar}>Cancelar</Button>
            <Button type="submit" disabled={busy || declarado === ''}>
              {busy ? 'Cerrando...' : 'Cerrar turno'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
