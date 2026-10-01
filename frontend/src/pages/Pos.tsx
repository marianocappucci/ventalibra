// Pantalla del cajero. Optimizada para despensa/autoservicio con lector de
// codigo de barras y teclado -- sin mouse: el foco vive en el campo de
// escaneo y vuelve solo, y todo lo demas son atajos de teclado.
//
// La regla de fondo: escanear AGREGA. No hay paso de confirmacion, porque el
// cajero mira el producto, no la pantalla; el acuse de que entro es la linea
// resaltada un segundo en el ticket.
//
// F4 del plan ERP (2026-09-15, DECISIONS.md ADR-025, D1): el carrito vive
// ENTERO en el navegador -- ya no hay un borrador en el backend que se llena
// de a una línea (`POST /sales` + `.../items`, retirados). Recién al cobrar
// se manda TODO junto en un solo `POST /api/ventas`. Lo que cambia respecto
// del modelo viejo:
// - No existe más "la venta" del lado del servidor hasta que se cobra: lo que
//   antes era `sale` (con su `id`, su `number`) ahora es `cart`, un array
//   local sin id.
// - Agregar/quitar/corregir una línea es una mutación de estado de React, sin
//   ida y vuelta a la red -- por eso `agregar`/`quitarLinea`/`cambiarCantidad`
//   dejaron de ser async.
// - El QR ya no es "poner el monto en un borrador que ya existe": la venta
//   nace PENDIENTE recién cuando se aprieta "Cobrar con QR" (D2, el modelo de
//   la familia). Cancelar ese cobro es anular esa venta pendiente -- no hay
//   "bajar del QR" en el modelo nuevo.
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { hoyISO } from 'libra-ui/fechas'
import { hora } from '@/lib/fechas'
import type { CalculoPromociones, ListaPrecio } from 'libra-ui/comercio/tipos'
import {
  api, ApiError, type Caja, type Cliente, type Escaneo, type Producto, type Sucursal, type VarianteProducto,
  type MpDisponible, type MpEstado, type Venta, type VentaPagoConRecibido,
  type Shift, type ShiftState, type ShiftSummary,
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
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Ban, FileText, Hash, LockKeyhole, Plus, Printer, QrCode, Scan, Split, Trash2, User } from 'lucide-react'
import type { ComponentType } from 'react'
import { useMediosPago } from '@/lib/medios-pago'
import { abrirTicket } from '@/lib/tickets'
import { money } from '@/lib/dinero'
import { EmitirFactura } from '../components/emitir-factura'
import { DialogoAvisosDeVencimiento } from '../components/avisos-de-vencimiento'
import { consultarAvisosDeSalida, describirAviso, type AvisoDeVencimiento } from '../lib/avisos-de-vencimiento'
import { FACTURACION, useTieneModulo } from '../lib/modulos'

/** El medio que representa el fiado. No es plata: no entra al arqueo del
 *  turno y genera deuda en la cuenta del cliente. */
const CUENTA_CORRIENTE = 'cuenta_corriente'

/** El medio que se cobra escaneando el QR impreso de la caja.
 *
 *  Es la clave canonica de la familia (`libracore.medios_pago.ELEGIBLES`).
 *  Hasta esta version este POS escribia `mercado_pago`, con guion bajo, y era
 *  la ultima divergencia de grafia del vocabulario: cambiarla exigio migrar
 *  antes las filas ya escritas, porque un selector nuevo sobre datos viejos
 *  parte cada reporte en dos lineas para la misma cosa. La normalizacion vive
 *  en `app/normalizacion_medios.py` y corre en cada arranque. */
const MERCADO_PAGO = 'mercadopago'

/** Cuanto esperar sin tipeo antes de pedir sugerencias por nombre. Ni tan
 *  corto que dispare una request por tecla (el lector tipea rapidisimo, asi
 *  que cada caracter del codigo dispararia una), ni tan largo que se sienta
 *  lento para un humano escribiendo a mano. */
const SUGERENCIAS_DEBOUNCE_MS = 250
/** Con menos, el LIKE por nombre trae casi todo el catalogo -- no aporta y
 *  es ruido en pantalla mientras el cajero recien empieza a escribir. */
const SUGERENCIAS_MIN_CHARS = 2

const QR_POLL_MS = 3000
/** Cinco minutos: pasado eso el cliente ya se fue del mostrador. Cortar el
 *  poll anula la venta pendiente -- no hay "bajar del QR" sin anular en el
 *  modelo nuevo (D2). */
const QR_ESPERA_MAXIMA_MS = 5 * 60 * 1000

/** Dos notas cortas, sintetizadas. Sin archivo de audio a proposito: no hay
 *  nada que descargar ni que sirva el backend, y suena igual sin internet.
 *
 *  El `AudioContext` se crea con el click de "Cobrar con QR" y no al
 *  acreditar: los navegadores bloquean el audio que no nace de un gesto del
 *  usuario, y la acreditacion llega desde un `setInterval`, que no cuenta como
 *  gesto. Mismo mecanismo que Contalibra. */
function crearAudio(): AudioContext | null {
  try {
    const Ctor = window.AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    return Ctor ? new Ctor() : null
  } catch {
    return null
  }
}

function sonarCampanita(ctx: AudioContext | null) {
  if (!ctx) return
  if (ctx.state === 'suspended') void ctx.resume()
  for (const { hz, en } of [{ hz: 1318.5, en: 0 }, { hz: 1760.0, en: 0.13 }]) {
    const osc = ctx.createOscillator()
    const vol = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = hz
    const t = ctx.currentTime + en
    vol.gain.setValueAtTime(0.0001, t)
    vol.gain.exponentialRampToValueAtTime(0.28, t + 0.01)
    vol.gain.exponentialRampToValueAtTime(0.0001, t + 0.42)
    osc.connect(vol).connect(ctx.destination)
    osc.start(t)
    osc.stop(t + 0.45)
  }
}

/** 🔴 Acá había una lista propia de seis medios, y el backend no validaba:
 *  la lista era lo único que decía qué se podía cobrar, y no ofrecía Cuenta
 *  DNI, otras billeteras ni cheque, que la familia sí. Ahora sale del motor
 *  (`useMediosPago`), como en Contalibra y Restolibra. Lo único propio del
 *  mostrador es cómo se llama el fiado. El QR sigue siendo sólo de Mercado
 *  Pago: los otros medios electrónicos se registran como un cobro manual. */
function etiquetaEnElPos(medio: { id: string; label: string }): string {
  return medio.id === CUENTA_CORRIENTE ? 'Cuenta corriente (fiado)' : medio.label
}

/** Un botón de la grilla de funciones del POS: la misma acción que su tecla, grande y de color (pedido del humano, 2026-10-01). */
function BotonFuncion({ tecla, etiqueta, detalle, icono: Icono, color, onClick, disabled, className = '' }: {
  tecla: string
  etiqueta: string
  detalle?: string
  icono: ComponentType<{ className?: string }>
  color: string
  onClick: () => void
  disabled?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`relative flex h-20 min-w-0 flex-col items-center justify-center gap-1 rounded-lg border-2 px-2 text-sm font-semibold shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-40 ${color} ${className}`}
    >
      <span className="absolute right-1.5 top-1 text-[10px] font-bold opacity-70">{tecla}</span>
      <Icono className="size-6" />
      <span className="max-w-full truncate leading-none">{etiqueta}</span>
      {detalle && <span className="max-w-full truncate text-[11px] font-normal leading-none opacity-80">{detalle}</span>}
    </button>
  )
}


// La sucursal se elige una vez y queda: en el mostrador no cambia entre
// ventas, y preguntarla en cada uno era ruido puro.
const LOCATION_KEY = 'ventalibra.pos.location'

/** Antepone la etiqueta salvo que el nombre ya la traiga -- evita "Sucursal
 *  Sucursal Centro" cuando el nombre del registro ya viene con el prefijo
 *  (comparación sin distinguir mayúsculas). */
function conPrefijo(etiqueta: string, nombre: string): string {
  return nombre.toLowerCase().startsWith(etiqueta.toLowerCase()) ? nombre : `${etiqueta} ${nombre}`
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

/** Parsea un monto que el CAJERO tipeó a mano (efectivo inicial de un turno,
 *  efectivo contado al cerrarlo) -- nunca el de una línea del carrito, que
 *  sale del catálogo. `null` si no es un monto válido: nunca cae a 0 en
 *  silencio, a diferencia de `Number(x) || 0`. Quien llama tiene que mostrar
 *  el error y frenar el envío en vez de mandar `null` al backend.
 *
 *  Regla de parseo (la mínima que pide un cajero argentino, documentada acá
 *  porque no hay otro lugar donde buscarla):
 *  - Con coma: la coma es decimal y los puntos, si hay, separan miles en
 *    grupos de a tres -- "500,50", "1.500,50", "1.250.000,5".
 *  - Sin coma, con puntos en grupos de a tres: son separadores de miles --
 *    "1.500" es MIL QUINIENTOS. 🔴 Leerlo como decimal (1,5) sería el mismo
 *    error silencioso que se vino a arreglar, con otra cara: es como se
 *    escribe un monto en Argentina.
 *  - Sin coma y con un punto que no forma grupos de a tres: decimal --
 *    "500.5", "500.25".
 *  - Nunca negativo (un cajón no tiene "menos plata"): cualquier signo lo
 *    rechaza, no lo trunca. Cualquier otra forma ("1.5.0,50", "a500") es
 *    inválida. */
function parseMonto(texto: string): number | null {
  const t = texto.trim()
  let normalizado: string
  if (/^(\d{1,3}(\.\d{3})+|\d+),\d+$/.test(t)) {
    normalizado = t.replace(/\./g, '').replace(',', '.')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(t)) {
    normalizado = t.replace(/\./g, '')
  } else if (/^\d+(\.\d+)?$/.test(t)) {
    normalizado = t
  } else {
    return null
  }
  const n = Number(normalizado)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** Parsea la cantidad que el cajero tipea a mano para una línea del carrito.
 *  Mismo criterio que `parseMonto` —`null` antes que un 0 silencioso—, con
 *  una regla propia: la cantidad puede ser un peso (`1,250` kg), así que la
 *  coma o el punto son siempre decimales y NO hay separador de miles (nadie
 *  vende "1.500" unidades tipeándolas; "1.500" kg es un kilo y medio). Tiene
 *  que ser mayor a 0: para sacar un producto está «Quitar».
 *
 *  Devuelve la cantidad normalizada con punto, que es como la guarda
 *  `CartLine.qty`. */
function parseCantidad(texto: string): string | null {
  const t = texto.trim()
  if (!/^\d+([.,]\d+)?$/.test(t)) return null
  const normalizada = t.replace(',', '.')
  return Number(normalizada) > 0 ? normalizada : null
}

/** `3 * 7790123456` => cantidad 3, codigo 7790123456. Es el gesto que el
 *  cajero ya conoce de cualquier supermercado: multiplicador y despues el
 *  producto, sin tocar un campo aparte. */
function parseMultiplicador(texto: string): { cantidad: string; resto: string } {
  const m = /^\s*(\d+(?:[.,]\d+)?)\s*[*x]\s*(.+)$/i.exec(texto)
  if (!m) return { cantidad: '1', resto: texto.trim() }
  return { cantidad: m[1].replace(',', '.'), resto: m[2].trim() }
}

/** Una línea del carrito, ANTES de registrarse (D1): todavía no tiene `id`
 *  de `sale_items` -- eso lo pone el backend recién en `POST /api/ventas`. */
type CartLine = {
  nombre: string
  qty: string
  precio: string
  producto_id: number | null
  variante_id: number | null
}

function lineaVacia(item: Producto, cantidad: string, variante?: VarianteProducto, precioUnitario?: string | null): CartLine {
  return {
    nombre: variante ? `${item.nombre} (${variante.nombre})` : item.nombre,
    qty: cantidad,
    precio: precioUnitario ?? String(item.precio_venta),
    producto_id: item.id,
    variante_id: variante?.id ?? null,
  }
}

export function Pos() {
  // Las sucursales activas (`/api/sucursales`); `locationId` es el id de la SUCURSAL elegida. El depósito del que
  // descuenta la venta es otro id: el de venta de esa sucursal (`depositoDeVenta`, más abajo).
  const [locations, setLocations] = useState<Sucursal[]>([])
  const [locationId, setLocationId] = useState<string>(
    () => localStorage.getItem(LOCATION_KEY) ?? '',
  )

  const [cart, setCart] = useState<CartLine[]>([])
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmada, setConfirmada] = useState<Venta | null>(null)
  const [facturaError, setFacturaError] = useState<string | null>(null)
  const [avisoQr, setAvisoQr] = useState<string | null>(null)

  // Linea marcada: sobre ella actuan F4 (quitar) y F6 (cantidad). Arranca en
  // la ultima agregada, que es la que el cajero suele querer corregir.
  const [marcada, setMarcada] = useState<number | null>(null)
  const [reciente, setReciente] = useState<number | null>(null)

  const [candidatos, setCandidatos] = useState<Producto[]>([])
  const [variantes, setVariantes] = useState<VarianteProducto[]>([])
  const [pendiente, setPendiente] = useState<{ item: Producto; cantidad: string } | null>(null)

  // Sugerencias mientras se tipea (sin Enter) -- distintas de `candidatos`,
  // que es el modal que dispara `buscar()` cuando el Enter no matcheo un
  // codigo exacto y la busqueda por nombre trajo mas de un resultado. Las
  // dos conviven: esta es la busqueda en vivo, esa sigue andando igual que
  // siempre.
  const [sugerencias, setSugerencias] = useState<Producto[]>([])
  // Guarda por secuencia (no AbortController: `api.get` de libra-ui no
  // acepta AbortSignal, y no se toca ese paquete desde aca) -- si una
  // respuesta vieja llega despues de una mas nueva, se descarta en vez de
  // pisarla. Arranca en 0 y se incrementa recien al DISPARAR el fetch (no en
  // cada tecla), para que dos pedidos en vuelo a la vez comparen bien.
  const secuenciaSugerenciasRef = useRef(0)

  const [cobroOpen, setCobroOpen] = useState(false)
  // F3 abre el cobro ya dividido en dos medios; F2 lo abre con uno solo.
  const [cobroDividido, setCobroDividido] = useState(false)
  const [cantidadOpen, setCantidadOpen] = useState(false)
  const escaneoRef = useRef<HTMLInputElement>(null)

  // Cliente de la venta. La mayoría son a consumidor final y no lo necesitan;
  // fiar sí, porque una deuda tiene que ser de alguien.
  const [cliente, setCliente] = useState<Cliente | null>(null)
  const [clienteOpen, setClienteOpen] = useState(false)

  // Sin turno abierto el backend rechaza el cobro (409), asi que la pantalla
  // pide la apertura antes de dejar vender en vez de esperar al error.
  const [turno, setTurno] = useState<Shift | null>(null)
  const [turnoCargado, setTurnoCargado] = useState(false)
  const [cierreOpen, setCierreOpen] = useState(false)
  // Confirmación de «cancelar venta» (Esc o el botón): con muchos ítems cargados, un Esc sin querer no puede tirar todo.
  const [cancelarOpen, setCancelarOpen] = useState(false)
  // La última venta cobrada: F8 reimprime su ticket y F9 abre su detalle (donde se factura) sin salir del POS.
  const [ultimaVentaId, setUltimaVentaId] = useState<number | null>(null)
  const navigate = useNavigate()
  const facturacionActiva = useTieneModulo(FACTURACION)

  // Si este mostrador puede cobrar por QR, y si eso factura solo. Se pregunta
  // una vez al abrir la pantalla: son dos booleanos de configuración, no algo
  // que cambie entre una venta y la siguiente. `null` mientras carga — con eso
  // el diálogo de cobro no parpadea mostrando el botón y sacándolo.
  //
  // 🔑 No trae ninguna credencial: la pantalla que las carga es admin y esto
  // lo lee el cajero.
  const [mp, setMp] = useState<MpDisponible | null>(null)

  // La lista de precios predeterminada (roadmap de producto, 2026-09-28): si la
  // instalación tiene una marcada, cada línea se cobra al precio que resulte de
  // aplicar cantidad y vigencia (`libracommerce.erp.listas_precio.resolve_price`)
  // en vez del precio plano del producto. `null` mientras carga o si no hay
  // ninguna marcada -- en los dos casos el POS sigue vendiendo al precio de
  // siempre, sin bloquear nada (mismo criterio que `mp-estado`, arriba).
  const [listaPrecioDefaultId, setListaPrecioDefaultId] = useState<number | null>(null)

  useEffect(() => {
    api.get<MpDisponible>('/pos/mp-estado')
      .then(setMp)
      // Sin respuesta, el POS sigue cobrando por los medios de siempre: el QR
      // es una forma más de cobrar, no un requisito para vender.
      .catch(() => setMp({ disponible: false, auto_facturar: false }))
  }, [])

  useEffect(() => {
    api.get<ListaPrecio[]>('/api/listas-precio')
      .then((listas) => setListaPrecioDefaultId(listas.find((l) => l.es_default && l.activa)?.id ?? null))
      // Sin lista (instalación que no configuró ninguna) el POS vende al
      // precio plano de siempre, no rompe nada.
      .catch(() => setListaPrecioDefaultId(null))
  }, [])

  const cargarTurno = useCallback(async () => {
    try {
      const estado = await api.get<ShiftState>('/api/turnos/actual')
      setTurno(estado.turno)
    } catch {
      setTurno(null)
    } finally {
      setTurnoCargado(true)
    }
  }, [])

  useEffect(() => { cargarTurno() }, [cargarTurno])

  const hayDialogo = cobroOpen || cantidadOpen || cierreOpen || clienteOpen || cancelarOpen || !turno
    || candidatos.length > 0 || variantes.length > 0

  const enfocarEscaneo = useCallback(() => {
    if (hayDialogo) return
    escaneoRef.current?.focus()
  }, [hayDialogo])

  // Busqueda en vivo mientras se tipea -- sin apretar Enter. El multiplicador
  // ("3 * cono") se pela antes de buscar, para que "cono" traiga sugerencias
  // igual que si no hubiera multiplicador delante.
  //
  // 🔴 A proposito NO cancela con `busy`/Enter en vuelo: ese flujo
  // (`buscar()`) limpia `query` apenas resuelve (via `agregar()`) o marca el
  // error, y eso por si solo vacia `resto` y esconde las sugerencias -- no
  // hace falta una segunda guarda cruzada, que solo agregaria una carrera
  // mas para pisar.
  useEffect(() => {
    const { resto } = parseMultiplicador(query)
    if (hayDialogo || resto.length < SUGERENCIAS_MIN_CHARS) {
      setSugerencias([])
      return
    }
    const temporizador = window.setTimeout(() => {
      // La secuencia se actualiza recien ACA, al disparar el pedido -- no en
      // cada tecla -- para que dos fetches realmente en vuelo a la vez (no
      // dos teclas que el debounce ya absorbio) sean los que se comparan.
      const secuencia = ++secuenciaSugerenciasRef.current
      api.get<Producto[]>(`/api/productos?solo_activos=true&q=${encodeURIComponent(resto)}`)
        .then((encontrados) => {
          // Llego una respuesta mas nueva mientras esta viajaba: la vieja se
          // descarta en vez de pisarle el resultado a la de recien.
          if (secuenciaSugerenciasRef.current === secuencia) setSugerencias(encontrados)
        })
        .catch(() => {
          if (secuenciaSugerenciasRef.current === secuencia) setSugerencias([])
        })
    }, SUGERENCIAS_DEBOUNCE_MS)
    return () => window.clearTimeout(temporizador)
  }, [query, hayDialogo])

  useEffect(() => {
    // Sólo vende una sucursal activa (`/api/sucursales` ya trae sólo esas); los depósitos no se ofrecen.
    api.get<Sucursal[]>('/api/sucursales')
      .then((items) => {
        setLocations(items)
        setLocationId((actual) => {
          if (actual && items.some((l) => String(l.id) === actual)) return actual
          // La sucursal default del sistema -- no "la primera de la
          // lista", que puede no ser la que el motor usa cuando el POS no
          // manda `deposito_id`.
          const porDefecto = items.find((l) => !!l.es_default)
          if (porDefecto) return String(porDefecto.id)
          return items.length > 0 ? String(items[0].id) : ''
        })
      })
      .catch(() => setLocations([]))
  }, [])

  // Con turno abierto EN UNA CAJA, la sucursal de la venta queda atada a la
  // de esa caja -- no a lo último elegido a mano ni a lo que haya en
  // localStorage. Esto es lo que garantiza, del lado del POS, que
  // `deposito_id` viaje siempre de un depósito de la sucursal del turno.
  // El backend además lo valida (`app/ganchos.py::validar_deposito`): un
  // depósito de otra sucursal es un 422.
  useEffect(() => {
    if (turno?.sucursal) setLocationId(String(turno.sucursal.id))
  }, [turno])

  useEffect(() => {
    if (locationId) localStorage.setItem(LOCATION_KEY, locationId)
  }, [locationId])

  // El foco vuelve al campo de escaneo apenas se cierra lo que lo saco: el
  // cajero nunca tiene que ir a buscarlo con el mouse.
  useEffect(() => { enfocarEscaneo() }, [enfocarEscaneo, cart, confirmada])

  useEffect(() => {
    if (reciente === null) return
    const t = setTimeout(() => setReciente(null), 1000)
    return () => clearTimeout(t)
  }, [reciente])

  /** El cliente se elige en cualquier momento de la venta, incluso con líneas
   *  ya cargadas (que es lo habitual: el cajero se entera de que va fiado
   *  recién al cobrar). Ya no hay ningún borrador al que avisarle (D1): el
   *  cliente viaja recién en `POST /api/ventas`. */
  function elegirCliente(elegido: Cliente | null) {
    setCliente(elegido)
    setClienteOpen(false)
    enfocarEscaneo()
  }

  function agregar(
    item: Producto, cantidad: string, variante?: VarianteProducto, precioUnitario?: string | null,
  ) {
    setCart((prev) => {
      const nueva = [...prev, lineaVacia(item, cantidad, variante, precioUnitario)]
      setReciente(nueva.length - 1)
      setMarcada(nueva.length - 1)
      return nueva
    })
    setQuery('')
    setCandidatos([])
    setVariantes([])
    setPendiente(null)
    setSugerencias([])
    enfocarEscaneo()
  }

  /** El precio de `productoId` para `cantidad`, AHORA, según la lista
   *  predeterminada (cantidad y vigencia por fecha/hora -- roadmap de
   *  producto). `null` si no hay lista default, no hay precio para ese
   *  producto, o la consulta falla: en los tres casos el llamador cae al
   *  precio plano de siempre, nunca bloquea la venta por esto. */
  async function resolverPrecioEfectivo(productoId: number, cantidad: string): Promise<string | null> {
    if (listaPrecioDefaultId === null) return null
    try {
      const { precio } = await api.get<{ precio: number | null }>(
        `/api/listas-precio/${listaPrecioDefaultId}/precio?producto_id=${productoId}`
        + `&cantidad=${encodeURIComponent(cantidad || '1')}&en=${encodeURIComponent(new Date().toISOString())}`,
      )
      return precio === null ? null : String(precio)
    } catch {
      return null
    }
  }

  async function elegirItem(
    item: Producto, cantidad: string, precioUnitario?: string | null,
  ) {
    // Un item con variantes no se puede vender sin elegir cual: se pregunta
    // solo en ese caso, no en cada producto.
    try {
      const vs = (await api.get<VarianteProducto[]>(`/api/productos/${item.id}/variantes`)).filter((v) => v.activa)
      if (vs.length > 0) {
        setPendiente({ item, cantidad })
        setVariantes(vs)
        setCandidatos([])
        return
      }
    } catch {
      // sin variantes accesibles: se vende el item pelado
    }
    // `precioUnitario` sólo viene definido cuando una etiqueta de balanza trae el
    // suyo: ese no se pisa. En cualquier otro caso (`undefined`) se consulta la
    // lista predeterminada.
    const efectivo = precioUnitario === undefined ? await resolverPrecioEfectivo(item.id, cantidad) : precioUnitario
    agregar(item, cantidad, undefined, efectivo)
  }

  /** Elegir una sugerencia de la busqueda en vivo -- mismo camino que
   *  cualquier otra forma de resolver un item (`elegirItem`: respeta
   *  variantes y termina en `agregar`, que limpia el campo y devuelve el
   *  foco). El multiplicador tipeado antes del nombre ("3 * cono") se
   *  respeta igual que en el flujo de Enter. */
  async function elegirSugerencia(item: Producto) {
    const { cantidad } = parseMultiplicador(query)
    // Se esconde ACA, antes del await: `elegirItem` puede tardar (pide las
    // variantes), y la lista no tiene por que seguir visible mientras tanto.
    setSugerencias([])
    await elegirItem(item, cantidad)
  }

  async function buscar(event: FormEvent) {
    event.preventDefault()
    // Las sugerencias en vivo son de un flujo aparte (ver el useEffect de
    // arriba) -- el Enter siempre resuelve por su cuenta, codigo exacto
    // primero, y no tiene por que esperarlas ni convivir con ellas en
    // pantalla mientras resuelve.
    setSugerencias([])
    const texto = query.trim()
    if (!texto) return
    const { cantidad, resto } = parseMultiplicador(texto)
    if (!resto) return
    // `0 * 7790123456` pasaba el regex y entraba una línea con cantidad 0,
    // que viajaba así al registrar la venta.
    if (Number(cantidad) <= 0) {
      setError('La cantidad tiene que ser mayor a 0.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      // Primero por codigo exacto: es lo que manda el lector, y tiene que
      // entrar sin intervencion.
      const escaneado = await api.get<Escaneo>(
        `/api/productos/escanear?code=${encodeURIComponent(resto)}`,
      )
      // Una etiqueta de balanza ya trae cuanto se peso, y el multiplicador
      // no aplica: cada etiqueta es de un paquete concreto, no de N iguales.
      await elegirItem(
        escaneado.producto,
        escaneado.de_balanza ? String(escaneado.cantidad) : cantidad,
        escaneado.precio_unitario === null ? undefined : String(escaneado.precio_unitario),
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        try {
          const encontrados = await api.get<Producto[]>(
            `/api/productos?solo_activos=true&q=${encodeURIComponent(resto)}`,
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

  function quitarLinea(index: number) {
    setCart((prev) => {
      const nuevo = prev.filter((_, i) => i !== index)
      setMarcada(nuevo.length > 0 ? nuevo.length - 1 : null)
      return nuevo
    })
    enfocarEscaneo()
  }

  async function cambiarCantidad(index: number, cantidad: string) {
    const productoId = cart[index]?.producto_id
    setCart((prev) => prev.map((linea, i) => (i === index ? { ...linea, qty: cantidad } : linea)))
    setCantidadOpen(false)
    enfocarEscaneo()
    // El nuevo precio (si cambia el quiebre de cantidad alcanzado) llega
    // después, sin bloquear el cierre del diálogo ni el resto de la venta --
    // la cantidad ya quedó cargada aunque esto tarde o falle.
    if (productoId !== null && productoId !== undefined) {
      const efectivo = await resolverPrecioEfectivo(productoId, cantidad)
      if (efectivo !== null) {
        setCart((prev) => prev.map((linea, i) => (i === index && linea.producto_id === productoId ? { ...linea, precio: efectivo } : linea)))
      }
    }
  }

  function cancelarVenta() {
    setCart([])
    setMarcada(null)
    setQuery('')
    setCandidatos([])
    setVariantes([])
    setPendiente(null)
    setError(null)
    enfocarEscaneo()
  }

  const total = cart.reduce((acc, l) => acc + (Number(l.qty) || 0) * (Number(l.precio) || 0), 0)

  // Las promociones (roadmap de producto, 2026-09-28: «llevá N pagá M» y combos): el
  // ahorro lo calcula el motor (`POST /api/promociones/calcular`) y es el mismo que el
  // servidor suma al descuento al registrar la venta (`OpcionesVentas.promociones`),
  // así que lo que el cajero cobra es lo que el servidor espera. Se consulta después
  // de cada cambio del carrito (agregar, cantidad, quitar: son acciones discretas, no
  // teclas), sin demora, y `Cobrar` espera esa respuesta para no abrir el cobro con
  // un total viejo. Si la consulta falla se vende sin descuento, sin bloquear.
  const [promos, setPromos] = useState<CalculoPromociones | null>(null)
  const [calculandoPromos, setCalculandoPromos] = useState(false)
  const secuenciaPromosRef = useRef(0)
  useEffect(() => {
    if (cart.length === 0) {
      setPromos(null)
      setCalculandoPromos(false)
      return
    }
    const secuencia = ++secuenciaPromosRef.current
    setCalculandoPromos(true)
    api.post<CalculoPromociones>('/api/promociones/calcular', {
      items: cart.map((l) => ({
        producto_id: l.producto_id, qty: Number(l.qty) || 0, precio: Number(l.precio) || 0,
      })),
      en: new Date().toISOString(),
    })
      .then((r) => { if (secuenciaPromosRef.current === secuencia) setPromos(r) })
      .catch(() => { if (secuenciaPromosRef.current === secuencia) setPromos(null) })
      .finally(() => { if (secuenciaPromosRef.current === secuencia) setCalculandoPromos(false) })
  }, [cart])
  const promosAplicadas = Array.isArray(promos?.aplicadas) ? promos.aplicadas : []
  const ahorro = promosAplicadas.length > 0 ? Number(promos?.ahorro) || 0 : 0
  const totalConPromos = Math.max(0, Math.round((total - ahorro) * 100) / 100)
  const puedeCobrar = cart.length > 0 && Boolean(locationId) && !calculandoPromos
  // 🔴 El `deposito_id` de la venta NO es el id de la sucursal: es su depósito de venta. Son entidades distintas
  // (la sucursal 7 puede vender del depósito 12) y el backend rechaza con 422 un depósito de otra sucursal.
  const depositoDeVenta = locations.find((l) => String(l.id) === locationId)?.deposito_predeterminado_id ?? null

  // Atajos globales. preventDefault en las F porque el navegador se las
  // queda (F3 abre buscar, F6 mueve el foco a la barra de direcciones).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'F2') { e.preventDefault(); if (puedeCobrar) { setCobroDividido(false); setCobroOpen(true) } }
      else if (e.key === 'F3') { e.preventDefault(); if (puedeCobrar) { setCobroDividido(true); setCobroOpen(true) } }
      else if (e.key === 'F4') {
        e.preventDefault()
        if (marcada !== null && cart.length) quitarLinea(marcada)
      } else if (e.key === 'F6') {
        e.preventDefault()
        if (marcada !== null && cart.length) setCantidadOpen(true)
      } else if (e.key === 'F7') {
        e.preventDefault()
        setClienteOpen(true)
      } else if (e.key === 'F8' && !confirmada) {
        e.preventDefault()
        if (ultimaVentaId !== null) imprimirTicket(ultimaVentaId)
      } else if (e.key === 'F9' && !confirmada) {
        e.preventDefault()
        // Sólo con el carrito vacío y sin diálogos: ir al detalle de la venta anterior desmonta el POS y perdería la venta en curso.
        if (ultimaVentaId !== null && facturacionActiva && cart.length === 0 && !hayDialogo) navigate(`/ventas/${ultimaVentaId}`)
      } else if (e.key === 'Escape' && !hayDialogo) {
        e.preventDefault()
        if (cart.length) setCancelarOpen(true)
      } else if (e.key === 'ArrowUp' && cart.length) {
        e.preventDefault()
        setMarcada((i) => (i === null ? cart.length - 1 : Math.max(0, i - 1)))
      } else if (e.key === 'ArrowDown' && cart.length) {
        e.preventDefault()
        setMarcada((i) => (i === null ? 0 : Math.min(cart.length - 1, i + 1)))
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
        facturaError={facturaError}
        aviso={avisoQr}
        onNueva={() => {
          setConfirmada(null); setFacturaError(null); setAvisoQr(null)
          setCart([]); setMarcada(null); setQuery('')
        }}
      />
    )
  }

  return (
    // En pantallas anchas la pantalla mide lo que la ventana (menos el padding de `Layout`): el que scrollea es el listado
    // de productos y NO la página, así que el total y «Cobrar» quedan siempre a la vista (pedido del humano, 2026-10-01).
    <div className="grid gap-3 lg:flex lg:h-[calc(100svh-3rem)] lg:flex-col">
      {/* Color (ADR-054, pedido del humano 2026-10-01): el POS es la pantalla que el cajero mira todo el día y no tiene que
          parecerse al resto. Encabezado azul, total sobre fondo de marca y «Cobrar» verde; el resto de la app queda sobrio. */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gradient-to-r from-sky-600 to-indigo-600 px-4 py-2.5 text-sm text-sky-50 shadow-sm">
        <span className="flex items-center gap-2">
          <Scan className="size-4 text-white" />
          {/* Identificación sobria de la pantalla (pedido del humano,
              2026-09-17): sin bloque propio -- éste es el único renglón de
              encabezado que tiene el POS, y robarle alto es justo lo que no
              hay que hacer acá (ver TituloPantalla, que sí lo haría). */}
          <span className="text-base font-semibold text-white">POS (Caja)</span>
          <span aria-hidden="true">·</span>
          Nueva venta
        </span>
        <div className="flex items-center gap-2">
          {/* Orden pedido por el humano (2026-09-17): turno, después
              sucursal/caja, y "Cerrar turno" al final -- el más a la
              derecha, porque es la acción y no una etiqueta. */}
          {turno && (
            <span className="rounded border border-white/30 bg-white/15 px-2 py-0.5 text-xs text-white">
              Turno #{turno.id} · desde {hora(turno.apertura)} · inicial ${money(turno.monto_inicial)}
            </span>
          )}
          {/* Con turno abierto EN UNA CAJA, la sucursal queda fija a la de esa
              caja: la venta tiene que salir del depósito de esa sucursal, y
              dejar elegir otra la desalinearía sin que nadie lo note (ver el
              pendiente de motor documentado en `AbrirTurno` de este archivo).
              Un turno viejo sin caja (de antes de esta feature) conserva el
              selector, con un aviso para migrarlo. */}
          {turno?.sucursal ? (
            // Sin selector, a propósito (ver el comentario de arriba): el
            // `title` es la forma más sobria de decir CÓMO se cambia de
            // sucursal sin agregar un segundo botón que haga lo mismo que
            // "Cerrar turno" -- ya está ahí, a un click. Pedido del
            // humano (2026-09-17): "un botón «Cambiar»... o un tooltip".
            <span
              className="rounded border border-white/30 bg-white/15 px-2 py-0.5 text-xs text-white"
              title="Para trabajar en otra sucursal, cerrá el turno."
            >
              {conPrefijo('Sucursal', turno.sucursal.nombre)}
              {turno.caja?.nombre && <> · {conPrefijo('Caja', turno.caja.nombre)}</>}
            </span>
          ) : (
            <>
              <span className="text-xs">Sucursal</span>
              <Select value={locationId} onValueChange={setLocationId}>
                <SelectTrigger className="h-8 w-48" aria-label="Sucursal"><SelectValue placeholder="Elegí una sucursal…" /></SelectTrigger>
                <SelectContent>
                  {locations.map((loc) => (
                    <SelectItem key={loc.id} value={String(loc.id)}>{loc.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {turno && !turno.caja && (
                <span className="text-xs text-amber-600 dark:text-amber-500">
                  Turno sin caja asignada: convendría cerrarlo y abrir uno nuevo en una caja.
                </span>
              )}
            </>
          )}
          {turno && (
            <Button size="sm" variant="secondary" onClick={() => setCierreOpen(true)}>
              Cerrar turno
            </Button>
          )}
        </div>
      </div>

      <form onSubmit={buscar} className="flex items-center gap-2">
        <Scan className="size-6 shrink-0 text-sky-600" aria-hidden="true" />
        <div className="relative flex-1">
          <Input
            ref={escaneoRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Escaneá o escribí código / nombre…    (3 * código para 3 unidades)"
            className="h-12 w-full border-2 border-sky-300 bg-sky-50/60 text-base focus-visible:border-sky-500 dark:border-sky-800 dark:bg-sky-950/30"
            autoFocus
            autoComplete="off"
            aria-label="Código o nombre del producto"
            role="combobox"
            aria-expanded={sugerencias.length > 0}
            aria-controls="pos-sugerencias"
          />
          {/* Busqueda en vivo (sin Enter). NO es el modal `ElegirCandidato`
              de mas abajo a proposito: un Dialog de Radix atrapa el foco al
              abrirse, y el lector de codigo de barras necesita que el foco
              siga siempre en este input mientras tipea. Un desplegable
              comun, que solo aparece por estado y nunca llama a `.focus()`,
              no le roba nada -- y clickear una opcion es un gesto explicito
              del cajero, no algo que pase mientras tipea. */}
          {sugerencias.length > 0 && (
            <ul
              id="pos-sugerencias"
              role="listbox"
              aria-label="Sugerencias"
              className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
            >
              {sugerencias.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => elegirSugerencia(item)}
                    className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                  >
                    <span>{item.nombre}</span>
                    <span className="tabular-nums text-muted-foreground">${money(String(item.precio_venta))}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Button type="submit" disabled={busy} className="h-12 bg-sky-600 px-6 text-white hover:bg-sky-700">Agregar</Button>
      </form>

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

      <div className="grid gap-3 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
        <Ticket
          items={cart}
          marcada={marcada}
          reciente={reciente}
          onMarcar={setMarcada}
          onQuitar={quitarLinea}
        />

        <div className="grid content-start gap-2">
          <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
            {ahorro > 0 && (
              <div className="mb-2 grid gap-0.5 border-b pb-2 text-sm">
                <p className="flex justify-between text-muted-foreground">
                  <span>Subtotal</span><span className="tabular-nums">${money(total)}</span>
                </p>
                {promosAplicadas.map((a) => (
                  <p key={`${a.promocion_id}-${a.nombre}`} className="flex justify-between text-emerald-700 dark:text-emerald-400">
                    <span>{a.nombre}{a.veces > 1 ? ` × ${a.veces}` : ''}</span>
                    <span className="tabular-nums">−${money(a.ahorro)}</span>
                  </p>
                ))}
              </div>
            )}
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">Total</p>
            <p className="text-5xl font-bold tabular-nums text-emerald-700 dark:text-emerald-400">${money(totalConPromos)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {cart.length} producto{cart.length === 1 ? '' : 's'}
            </p>
          </div>
          <Button
            className="h-16 bg-emerald-600 text-lg font-semibold text-white shadow hover:bg-emerald-700 disabled:bg-emerald-600/40"
            disabled={!puedeCobrar || busy}
            onClick={() => { setCobroDividido(false); setCobroOpen(true) }}
          >
            Cobrar <span className="ml-2 text-xs opacity-70">F2</span>
          </Button>
          {/* Las teclas de función como botones: la misma acción que el teclado, grandes y de color (dos filas de 3 y «Cancelar venta» a todo el ancho). F2 es el «Cobrar» grande de arriba: no se repite. */}
          <div className="grid grid-cols-6 gap-2">
            <BotonFuncion tecla="F3" etiqueta="Dividir pago" icono={Split} className="col-span-2"
              color="border-sky-300 bg-sky-50 text-sky-800 hover:bg-sky-100 focus-visible:ring-sky-500 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300"
              disabled={!puedeCobrar || busy} onClick={() => { setCobroDividido(true); setCobroOpen(true) }} />
            <BotonFuncion tecla="F4" etiqueta="Quitar línea" icono={Trash2} className="col-span-2"
              color="border-red-300 bg-red-50 text-red-800 hover:bg-red-100 focus-visible:ring-red-500 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
              disabled={marcada === null || cart.length === 0 || busy} onClick={() => marcada !== null && quitarLinea(marcada)} />
            <BotonFuncion tecla="F6" etiqueta="Cantidad" icono={Hash} className="col-span-2"
              color="border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 focus-visible:ring-amber-500 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
              disabled={marcada === null || cart.length === 0 || busy} onClick={() => setCantidadOpen(true)} />
            <BotonFuncion tecla="F7" etiqueta="Cliente" detalle={cliente ? cliente.name : 'Consumidor final'} icono={User} className="col-span-2"
              color="border-violet-300 bg-violet-50 text-violet-800 hover:bg-violet-100 focus-visible:ring-violet-500 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300"
              disabled={busy} onClick={() => setClienteOpen(true)} />
            <BotonFuncion tecla="F8" etiqueta="Imprimir" detalle="última venta" icono={Printer} className="col-span-2"
              color="border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 focus-visible:ring-cyan-500 dark:border-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-300"
              disabled={ultimaVentaId === null} onClick={() => ultimaVentaId !== null && imprimirTicket(ultimaVentaId)} />
            <BotonFuncion tecla="F9" etiqueta="Factura" detalle="última venta" icono={FileText} className="col-span-2"
              color="border-teal-300 bg-teal-50 text-teal-800 hover:bg-teal-100 focus-visible:ring-teal-500 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300"
              disabled={ultimaVentaId === null || !facturacionActiva || cart.length > 0} onClick={() => ultimaVentaId !== null && navigate(`/ventas/${ultimaVentaId}`)} />
            <BotonFuncion tecla="Esc" etiqueta="Cancelar venta" icono={Ban} className="col-span-6"
              color="border-rose-400 bg-white text-rose-700 hover:bg-rose-50 focus-visible:ring-rose-500 dark:border-rose-800 dark:bg-transparent dark:text-rose-300"
              disabled={cart.length === 0 || busy} onClick={() => setCancelarOpen(true)} />
          </div>
          {locations.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No hay sucursales creadas todavía: sin una, no se puede cobrar.
            </p>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={cancelarOpen}
        onOpenChange={(abierto) => { setCancelarOpen(abierto); if (!abierto) enfocarEscaneo() }}
        title="¿Cancelar la venta?"
        description={`Vas a descartar ${cart.length} producto${cart.length === 1 ? '' : 's'} por $${money(totalConPromos)}. Esta acción no se puede deshacer.`}
        confirmLabel="Sí, cancelar venta"
        onConfirm={cancelarVenta}
      />

      <ElegirCandidato
        candidatos={candidatos}
        onElegir={(item) => elegirItem(item, pendiente?.cantidad ?? '1')}
        onCerrar={() => { setCandidatos([]); setPendiente(null); enfocarEscaneo() }}
      />

      <ElegirVariante
        variantes={variantes}
        onElegir={(v) => pendiente && agregar(pendiente.item, pendiente.cantidad, v)}
        onCerrar={() => { setVariantes([]); setPendiente(null); enfocarEscaneo() }}
      />

      {cantidadOpen && marcada !== null && cart[marcada] && (
        <CambiarCantidad
          linea={cart[marcada]}
          onAceptar={(cant) => cambiarCantidad(marcada, cant)}
          onCerrar={() => { setCantidadOpen(false); enfocarEscaneo() }}
        />
      )}

      {cierreOpen && turno && (
        <CerrarTurno
          turno={turno}
          onCerrado={() => { setCierreOpen(false); setTurno(null); setCart([]) }}
          onCancelar={() => { setCierreOpen(false); enfocarEscaneo() }}
        />
      )}

      {clienteOpen && (
        <ElegirCliente
          actual={cliente}
          onElegir={elegirCliente}
          onCerrar={() => { setClienteOpen(false); enfocarEscaneo() }}
        />
      )}

      {cobroOpen && (
        <Cobro
          dividir={cobroDividido}
          cart={cart}
          total={totalConPromos}
          depositoId={depositoDeVenta}
          cliente={cliente}
          mp={mp}
          onPedirCliente={() => setClienteOpen(true)}
          onCerrar={() => { setCobroOpen(false); enfocarEscaneo() }}
          onRegistrado={(venta, errorFactura, aviso) => {
            setCobroOpen(false)
            setCart([])
            setMarcada(null)
            setFacturaError(errorFactura)
            setAvisoQr(aviso ?? null)
            setUltimaVentaId(venta.id)
            setConfirmada(venta)
          }}
        />
      )}
    </div>
  )
}


function Ticket({ items, marcada, reciente, onMarcar, onQuitar }: {
  items: CartLine[]
  marcada: number | null
  reciente: number | null
  onMarcar: (i: number) => void
  onQuitar: (i: number) => void
}) {
  if (items.length === 0) {
    return (
      <div className="flex min-h-56 items-center justify-center rounded-lg border-2 border-dashed border-sky-300 bg-sky-50/50 p-6 text-sm text-sky-800 dark:border-sky-800 dark:bg-sky-950/20 dark:text-sky-300">
        Escaneá el primer producto para empezar la venta.
      </div>
    )
  }
  return (
    <div className="overflow-hidden rounded-lg border-2 border-sky-200 lg:max-h-full lg:self-start lg:overflow-y-auto dark:border-sky-900">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 border-b bg-sky-100 text-xs font-semibold text-sky-900 dark:bg-sky-950 dark:text-sky-200">
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
          {items.map((linea, i) => (
            <tr
              key={i}
              onClick={() => onMarcar(i)}
              className={[
                'cursor-pointer border-b last:border-0',
                i === marcada ? 'bg-sky-100 dark:bg-sky-900/40' : '',
                // El resaltado del escaneo pisa al de seleccion: es el acuse
                // de que la linea entro, y dura un segundo.
                i === reciente ? 'bg-emerald-100 dark:bg-emerald-950' : '',
              ].join(' ')}
            >
              <td className="p-2 text-muted-foreground">{i + 1}</td>
              <td className="p-2">{linea.nombre}</td>
              <td className="p-2 text-center tabular-nums">{cantidadLegible(linea.qty)}</td>
              <td className="p-2 text-right tabular-nums">${money(linea.precio)}</td>
              <td className="p-2 text-right tabular-nums">
                ${money((Number(linea.qty) || 0) * (Number(linea.precio) || 0))}
              </td>
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
  candidatos: Producto[]
  onElegir: (item: Producto) => void
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
              <span>{item.nombre}</span>
              <span className="tabular-nums text-muted-foreground">${money(String(item.precio_venta))}</span>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ElegirVariante({ variantes, onElegir, onCerrar }: {
  variantes: VarianteProducto[]
  onElegir: (v: VarianteProducto) => void
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
              {v.nombre}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CambiarCantidad({ linea, onAceptar, onCerrar }: {
  linea: { nombre: string; qty: string }
  onAceptar: (cantidad: string) => void
  onCerrar: () => void
}) {
  const [valor, setValor] = useState(String(Number(linea.qty)))
  // 🔴 Antes se aceptaba cualquier texto: «a3» quedaba en el carrito y
  // `itemsPayload` lo mandaba como `qty: 0` (`Number(x) || 0`), en silencio.
  // Mismo defecto que el «Efectivo contado» del cierre de turno.
  const cantidad = parseCantidad(valor)
  const invalida = valor.trim() !== '' && cantidad === null
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>{linea.nombre}</DialogTitle></DialogHeader>
        <form
          onSubmit={(e) => { e.preventDefault(); if (cantidad !== null) onAceptar(cantidad) }}
          className="grid gap-3"
        >
          <div className="grid gap-2">
            <Label htmlFor="cantidad-nueva">Cantidad</Label>
            <Input
              id="cantidad-nueva" value={valor} autoFocus
              aria-invalid={invalida || undefined}
              onChange={(e) => setValor(e.target.value)}
              onFocus={(e) => e.target.select()}
              className="h-12 text-lg"
            />
            {invalida && (
              <p className="text-sm text-destructive" role="alert">
                Cantidad inválida: tiene que ser un número mayor a 0 (ej. 3 o 1,250).
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCerrar}>Cancelar</Button>
            <Button type="submit" disabled={cantidad === null}>Aceptar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}


type PagoForm = { medio: string; monto: string; recibido: string }

/** Elegir a quién se le vende. Sólo hace falta para fiar y para facturar; el
 *  resto de las ventas son a consumidor final y no pasan por acá. */
function ElegirCliente({ actual, onElegir, onCerrar }: {
  actual: Cliente | null
  onElegir: (cliente: Cliente | null) => void
  onCerrar: () => void
}) {
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [filtro, setFiltro] = useState('')

  useEffect(() => {
    // El listado del motor trae también a los inactivos (la pantalla los marca): el POS sólo ofrece los activos.
    api.get<Cliente[]>('/api/clientes').then((todos) => setClientes(todos.filter((c) => c.activo))).catch(() => setClientes([]))
  }, [])

  const visibles = filtro
    ? clientes.filter((c) => c.name.toLowerCase().includes(filtro.toLowerCase()))
    : clientes

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Cliente de la venta</DialogTitle></DialogHeader>
        <Input
          autoFocus
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          placeholder="Buscar por nombre"
        />
        <div className="max-h-72 overflow-y-auto">
          {visibles.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              {clientes.length === 0 ? 'No hay clientes cargados.' : 'Sin resultados.'}
            </p>
          )}
          {visibles.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => onElegir(c)}
              className={[
                'flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent',
                actual?.id === c.id ? 'bg-accent' : '',
              ].join(' ')}
            >
              <span>{c.name}</span>
              {c.cuit_dni && <span className="text-xs text-muted-foreground">{c.cuit_dni}</span>}
            </button>
          ))}
        </div>
        <DialogFooter>
          {actual && (
            <Button variant="ghost" onClick={() => onElegir(null)}>
              Quitar cliente
            </Button>
          )}
          <Button variant="secondary" onClick={onCerrar}>Cancelar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type QrEstado = 'idle' | 'creando' | 'esperando' | 'acreditado'

/** Cobro. El numero que importa es el vuelto: es lo que el cajero mira
 *  mientras cuenta el cambio, asi que se calcula en vivo y se muestra
 *  grande. Si lo entregado no alcanza, lo dice en vez de mostrar un vuelto
 *  negativo.
 *
 *  Es EL lugar donde la venta se registra (D1: `POST /api/ventas`, una sola
 *  vez, con todo el carrito adentro). Dos caminos llegan a esa llamada:
 *  - El submit normal (`confirmar`): un solo pago o varios, todos ya
 *    acreditados -- la venta vuelve `cobrada` en la misma respuesta.
 *  - "Cobrar con QR" (`cobrarConQr`): registra con `cobrar_con_qr: true`
 *    (nace `pendiente`, D2), pone el monto en el QR de la caja y pollea hasta
 *    que MercadoPago avisa. */
function Cobro({ cart, total, depositoId, cliente, mp, dividir = false, onCerrar, onPedirCliente, onRegistrado }: {
  cart: CartLine[]
  total: number
  depositoId: number | null
  cliente: Cliente | null
  mp: MpDisponible | null
  /** Arranca con el pago ya dividido en dos medios (la mitad en efectivo y el resto en tarjeta; se editan): es el F3. */
  dividir?: boolean
  onCerrar: () => void
  onPedirCliente: () => void
  /** `aviso` es sólo para el caso de `verificarYAnular`: el pago se acreditó
   *  justo en el hueco antes de anular. No es un error -- es información
   *  sobre CÓMO se cerró la venta. */
  onRegistrado: (venta: Venta, facturaError: string | null, aviso?: string | null) => void
}) {
  const { medios } = useMediosPago()
  const [pagos, setPagos] = useState<PagoForm[]>(() => {
    if (dividir) {
      const mitad = Math.floor((total / 2) * 100) / 100
      return [
        { medio: 'efectivo', monto: mitad.toFixed(2), recibido: '' },
        { medio: 'tarjeta_debito', monto: Math.max(0, total - mitad).toFixed(2), recibido: '' },
      ]
    }
    // Con dos decimales y no `String(total)`: un total de pesada como 125.125
    // se leería con `parseMonto` como 125.125 pesos con puntos de miles.
    return [{ medio: 'efectivo', monto: total.toFixed(2), recibido: '' }]
  })
  const [factura, setFactura] = useState(false)
  // La facturación ARCA es del plan Premium (ADR-048): sin el módulo el backend contesta 403 a `/facturar`, así que
  // el casillero se ofrece apagado y con el motivo en vez de dejar la venta cobrada con un error de factura.
  const facturacion = useTieneModulo(FACTURACION)
  const [registrando, setRegistrando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mixto = pagos.length > 1
  // Guarda re-entrancia SINCRÓNICA: dos clicks casi simultáneos (doble click
  // de mouse, Enter repetido) no tienen que disparar dos `POST /api/ventas`.
  // El `disabled` del botón (que cuelga de `registrando`/`qrEstado`, estado
  // de React) ya alcanza para eso en la práctica -- verificado con la
  // mutación de este archivo -- pero es una operación que cobra plata, y acá
  // se quiere el guardia explícito además del `disabled`: un `useRef`, no
  // estado, porque tiene que valer YA, antes de que el evento termine de
  // procesarse, sin esperar al próximo render.
  const enviandoRef = useRef(false)

  // «¿Vender igual?» (ADR-053): los avisos de lote vencido o por vencer que dejó el plan de salida, mientras el cajero decide. La
  // venta espera la respuesta (`resolver`), con el guardia de arriba tomado, así que un doble clic no registra dos.
  const [avisosPendientes, setAvisosPendientes] = useState<
    { avisos: AvisoDeVencimiento[]; resolver: (seguir: boolean) => void } | null
  >(null)

  const [qrEstado, setQrEstado] = useState<QrEstado>('idle')
  const [qrError, setQrError] = useState<string | null>(null)
  const [confirmarCancelarQr, setConfirmarCancelarQr] = useState(false)
  const pollRef = useRef<number | null>(null)
  const audioRef = useRef<AudioContext | null>(null)
  // La venta pendiente de un cobro por QR en curso -- para que "cancelar", el
  // timeout y una acreditación tardía actúen sobre la MISMA venta que se
  // registró (y para poder nombrarla si hace falta anularla a mano). Guarda
  // el objeto entero, no sólo el id: `numero` hace falta para el aviso de
  // "no se pudo anular sola", y si el refresco final falla es lo único que
  // queda para mostrar como cobrada.
  const ventaQrRef = useRef<Venta | null>(null)
  // La promesa del tick del poll que esté corriendo AHORA, si hay uno.
  // `cancelarCobroQr` lo espera antes de decidir: sin esto, cancelar podía
  // pisarse con un tick que ya estaba a mitad de camino de acreditar.
  const pollEnVueloRef = useRef<Promise<void> | null>(null)

  // Los montos del cobro se leen con `parseMonto`, la misma regla que el
  // efectivo del turno: «1.500» es mil quinientos y «1.500,50» lleva coma
  // decimal. Antes era `Number(x) || 0`: «1.500» valía 1,5 y «1500,50» valía
  // 0, y el cajero quedaba bloqueado en «Falta cubrir» sin saber por qué.
  // Un monto que no se puede leer no cuenta como 0: se marca en el campo y
  // frena el cobro.
  const montos = pagos.map((p) => parseMonto(p.monto))
  const recibidos = pagos.map((p) => (p.recibido.trim() === '' ? null : parseMonto(p.recibido)))
  const montoInvalido = pagos.map((p, i) => p.monto.trim() !== '' && montos[i] === null)
  const recibidoInvalido = pagos.map((p, i) => p.recibido.trim() !== '' && recibidos[i] === null)
  const hayMontoInvalido = montoInvalido.some(Boolean) || recibidoInvalido.some(Boolean)
  const cubierto = montos.reduce<number>((acc, m) => acc + (m ?? 0), 0)
  const falta = total - cubierto
  const vuelto = pagos.reduce((acc, _p, i) => {
    const recibido = recibidos[i]
    const monto = montos[i] ?? 0
    if (recibido === null || recibido <= monto) return acc
    return acc + (recibido - monto)
  }, 0)
  const faltaEfectivo = pagos.some(
    (_p, i) => recibidos[i] !== null && (recibidos[i] as number) < (montos[i] ?? 0),
  )
  // Fiar sin cliente lo rechaza el backend (422). Se frena antes para que el
  // cajero no descubra el problema recien al apretar Cobrar, con la fila
  // esperando.
  const fia = pagos.some((p, i) => p.medio === CUENTA_CORRIENTE && (montos[i] ?? 0) > 0)
  const fiaSinCliente = fia && !cliente
  const puedeCobrar = !hayMontoInvalido && falta <= 0.009 && !faltaEfectivo && !fiaSinCliente && !registrando

  function actualizar(i: number, campo: keyof PagoForm, valor: string) {
    setPagos((prev) => prev.map((p, idx) => (idx === i ? { ...p, [campo]: valor } : p)))
  }

  function agregarMedio() {
    const restante = Math.max(0, total - cubierto)
    setPagos((prev) => [...prev, { medio: 'tarjeta_debito', monto: restante.toFixed(2), recibido: '' }])
  }

  function itemsPayload() {
    return cart.map((l) => ({
      nombre: l.nombre, qty: Number(l.qty) || 0, precio: Number(l.precio) || 0,
      producto_id: l.producto_id, variante_id: l.variante_id,
    }))
  }

  /** Antes de registrar la venta: si el plan de salida dice que el carrito lleva mercadería de un lote vencido o por vencer,
   *  pregunta «¿Vender igual?». `true` = seguir. **Opt-in y sin riesgo:** sin avisos, con el endpoint caído, inexistente (404/405) o
   *  lento (más de ~1,5 s) no muestra nada y devuelve `true`: se cobra como siempre (`consultarAvisosDeSalida` nunca rechaza). */
  async function confirmarAvisosDeVencimiento(): Promise<boolean> {
    const avisos = await consultarAvisosDeSalida(cart, depositoId)
    if (avisos.length === 0) return true
    return new Promise<boolean>((resolver) => setAvisosPendientes({ avisos, resolver }))
  }

  /** Si se pidió factura y todavía no la tiene, la pide DESPUÉS de
   *  registrada (nunca antes ni en el mismo POST): si falla, la venta queda
   *  igual -- el error se muestra y el detalle de la venta tiene el botón
   *  para reintentar. */
  async function conFacturaSiHaceFalta(venta: Venta): Promise<[Venta, string | null]> {
    if (!factura || !facturacion || venta.factura_id) return [venta, null]
    let mensaje: string | null = null
    try {
      await api.post(`/api/ventas/${venta.id}/facturar`)
    } catch (err) {
      mensaje = describeError(err)
    }
    try {
      return [await api.get<Venta>(`/api/ventas/${venta.id}`), mensaje]
    } catch {
      return [venta, mensaje]
    }
  }

  async function confirmar() {
    if (enviandoRef.current) return
    enviandoRef.current = true
    setRegistrando(true)
    setError(null)
    try {
      if (!(await confirmarAvisosDeVencimiento())) return  // «Volver»: nada se registró; el `finally` suelta el guardia
      const pagosPayload = pagos
        .map((p, i) => ({ p, monto: montos[i], recibido: recibidos[i] }))
        .filter(({ monto }) => monto !== null && monto > 0)
        .map(({ p, monto, recibido }) => ({
          medio: p.medio,
          monto: monto as number,
          ...(p.medio === 'efectivo' && recibido !== null ? { recibido } : {}),
        }))
      const venta = await api.post<Venta>('/api/ventas', {
        fecha: hoyISO(),
        items: itemsPayload(),
        cliente_id: cliente?.id ?? null,
        pagos: pagosPayload,
        deposito_id: depositoId,
      })
      const [final, facturaErr] = await conFacturaSiHaceFalta(venta)
      onRegistrado(final, facturaErr)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setRegistrando(false)
      enviandoRef.current = false
    }
  }

  function enviar() {
    if (!puedeCobrar) return
    confirmar()
  }

  // ── El cobro con QR ────────────────────────────────────────────────────
  //
  // 🔑 **Primero la plata, después la venta queda cerrada.** Se registra la
  // venta como PENDIENTE con el pago `mercadopago` en `cobrar_con_qr: true`
  // (D2), se pone el total en el QR de la caja, se espera a que MercadoPago
  // diga que se acreditó, y recién ahí se muestra el ticket. La venta YA
  // existe desde el primer paso -- a diferencia del modelo viejo, acá no hay
  // un "confirmar" aparte: `acreditar_pago_qr` (el poll) hace ese trabajo del
  // lado del motor.
  //
  // Sólo cuando Mercado Pago cubre el total con una única línea: la orden que
  // se pone en el QR es por el total, así que en un cobro mixto le estaría
  // pidiendo al cliente la venta entera y no su parte.
  const soloMercadoPago = pagos.length === 1
    && pagos[0].medio === MERCADO_PAGO
    && montos[0] !== null
    && Math.abs(montos[0] - total) <= 0.009
  const aplicaQr = !!mp?.disponible && soloMercadoPago && total > 0

  function frenarPoll() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  // Sin esto el poll sigue corriendo contra una venta que ya no está en
  // pantalla: cada 3 segundos sale un request contra una venta pendiente
  // que nadie mira.
  useEffect(() => frenarPoll, [])

  /** Anula la venta pendiente de un cobro por QR que no se pudo cerrar
   *  cobrada -- cancelar a mano, el timeout, un rechazo de MercadoPago, o que
   *  la orden ni se haya podido poner en el QR (D2: no hay "bajar del QR",
   *  cualquiera de esos casos anula).
   *
   *  🔴 Si el anular EN SÍ falla, no se calla: el mensaje nombra el número de
   *  la venta para que el cajero la anule a mano desde el historial. Una
   *  venta pendiente con el stock ya descontado, sin ticket y de la que el
   *  POS no vuelve a hablar, es peor que un cartel de error. */
  async function anularPendiente(mensaje: string) {
    const pendiente = ventaQrRef.current
    ventaQrRef.current = null
    setQrEstado('idle')
    if (pendiente == null) {
      setQrError(mensaje)
      return
    }
    try {
      await api.post(`/api/ventas/${pendiente.id}/anular`)
      setQrError(mensaje)
    } catch {
      setQrError(
        `${mensaje} No se pudo anular sola: anulá la venta ${pendiente.numero} `
        + 'desde el historial.',
      )
    }
  }

  /** El pago se acreditó: refresca la venta, factura si hace falta, y la
   *  muestra como cobrada. `aviso` es para cuando esto lo dispara
   *  `verificarYAnular` (el pago entró justo en el hueco entre "se decidió
   *  cancelar/anular" y la última pregunta antes de hacerlo) -- en el cobro
   *  normal por QR no hay nada que avisar. */
  async function cerrarComoAcreditada(aviso: string | null = null) {
    const pendiente = ventaQrRef.current
    if (pendiente == null) return
    ventaQrRef.current = null
    setQrEstado('acreditado')
    sonarCampanita(audioRef.current)
    try {
      const actualizada = await api.get<Venta>(`/api/ventas/${pendiente.id}`)
      const [final, facturaErr] = await conFacturaSiHaceFalta(actualizada)
      onRegistrado(final, facturaErr, aviso)
    } catch (err) {
      // La plata ya entró y la venta ya está cobrada del lado del servidor:
      // un error acá es sólo de refrescar la pantalla, no de la venta -- se
      // muestra igual con lo que se tenía.
      onRegistrado(pendiente, describeError(err), aviso)
    }
  }

  /** Antes de anular, vuelve a preguntar -- el pago pudo entrar justo en el
   *  hueco entre el último poll y la decisión de anular (el cajero cancela
   *  en el mismo instante en que el cliente termina de escanear; el timeout
   *  se cumple con el pago ya en camino; un "rechazado" que en realidad ya
   *  quedó viejo). Sin este último chequeo, D2 podía anular una venta que el
   *  cliente ya había pagado -- la plata quedaría en MercadoPago y la venta,
   *  cancelada.
   *
   *  🔴 **Residuo que queda, sin resolver acá.** Si HAY otra pantalla con el
   *  detalle de esta misma venta abierta y pollea por su cuenta, un anular
   *  que arranca ANTES de esta pregunta final puede terminar corriendo
   *  igual -- dos pestañas, la misma carrera, dos decisiones. libracore
   *  v1.101.0 ya cubre esa carrera del lado del motor: `venta_mp_status`
   *  sobre una venta YA anulada responde `estado: "anulada"` con el pago
   *  igual sellado y sin facturar, para que alguien la revise y devuelva a
   *  mano -- no autofactura ni resucita la venta. Ver, del lado del backend,
   *  `test_mp_status_sobre_una_venta_anulada_no_factura`. */
  async function verificarYAnular(mensajeSiAnula: string) {
    const pendiente = ventaQrRef.current
    if (pendiente == null) return
    let estado: string | null = null
    try {
      estado = (await api.get<MpEstado>(`/api/ventas/${pendiente.id}/mp-status`)).status
    } catch {
      // Sin poder confirmar el estado final, se sigue con la decisión de
      // anular: es la misma incertidumbre que ya asumía la versión anterior.
    }
    if (estado === 'approved') {
      await cerrarComoAcreditada(
        'El pago se acreditó justo ahora: la venta quedó cobrada, no se anuló.',
      )
      return
    }
    await anularPendiente(mensajeSiAnula)
  }

  /** El botón "Cancelar el cobro por QR", ya confirmado. Frena el poll,
   *  espera a que termine el tick que estuviera en vuelo (si el cajero
   *  cancela justo cuando el poll ya está a mitad de camino de leer
   *  `mp-status`, no hay que pisarlo) y recién ahí pregunta una última vez. */
  async function cancelarCobroQr() {
    frenarPoll()
    if (pollEnVueloRef.current) await pollEnVueloRef.current.catch(() => {})
    await verificarYAnular('Cobro por QR cancelado: la venta se anuló.')
  }

  function cerrar() {
    frenarPoll()
    if (qrEstado === 'esperando' || qrEstado === 'creando') {
      setConfirmarCancelarQr(true)
      return
    }
    onCerrar()
  }

  async function cobrarConQr() {
    if (enviandoRef.current) return
    enviandoRef.current = true
    try {
      // Acá, con el click todavía en curso, es el único momento en que el
      // navegador deja abrir el audio.
      audioRef.current = audioRef.current ?? crearAudio()
      setQrError(null)
      setError(null)
      setQrEstado('creando')
      if (!(await confirmarAvisosDeVencimiento())) {  // «Volver»: nada se registró
        setQrEstado('idle')
        return
      }
      let venta: Venta
      try {
        venta = await api.post<Venta>('/api/ventas', {
          fecha: hoyISO(),
          items: itemsPayload(),
          cliente_id: cliente?.id ?? null,
          pagos: [{ medio: MERCADO_PAGO, monto: total, cobrar_con_qr: true }],
          deposito_id: depositoId,
        })
      } catch (err) {
        setQrError(describeError(err))
        setQrEstado('idle')
        return
      }
      ventaQrRef.current = venta
      try {
        await api.post(`/api/ventas/${venta.id}/mp-qr`)
      } catch (err) {
        // 🔴 La venta YA existe (PENDIENTE, con el stock ya descontado)
        // aunque ponerle el monto en el QR haya fallado: sin anularla acá
        // queda huérfana -- nadie la vuelve a mencionar, y no tiene ticket
        // ni aparece como cobrada. Mismo camino que cualquier otra salida
        // sin acreditar.
        const detalle = describeError(err)
        await anularPendiente(`No se pudo poner el monto en el QR: ${detalle} La venta se anuló.`)
        return
      }
      setQrEstado('esperando')
      const hasta = Date.now() + QR_ESPERA_MAXIMA_MS
      pollRef.current = window.setInterval(() => {
        // La promesa de ESTE tick queda guardada para que `cancelarCobroQr`
        // pueda esperarla antes de decidir -- ver el docstring de esa función.
        pollEnVueloRef.current = (async () => {
          let estado: string
          try {
            estado = (await api.get<MpEstado>(`/api/ventas/${venta.id}/mp-status`)).status
          } catch (err) {
            frenarPoll()
            setQrEstado('idle')
            setQrError(describeError(err))
            return
          }
          if (estado === 'approved') {
            frenarPoll()
            await cerrarComoAcreditada()
            return
          }
          if (estado === 'rejected' || estado === 'cancelled') {
            frenarPoll()
            await verificarYAnular(
              'El pago fue rechazado o cancelado en MercadoPago: la venta se anuló.',
            )
            return
          }
          if (Date.now() > hasta) {
            frenarPoll()
            await verificarYAnular(
              'Se agotó la espera y la venta se anuló. Si el cliente pagó igual, '
              + 'fijate en MercadoPago antes de volver a cobrar.',
            )
          }
        })()
      }, QR_POLL_MS)
    } finally {
      enviandoRef.current = false
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Cobrar ${money(total)}</DialogTitle></DialogHeader>

        <form onSubmit={(e) => { e.preventDefault(); enviar() }} className="grid gap-3">
          {pagos.map((pago, i) => (
            <div key={i} className="grid gap-2 rounded-md border p-3">
              <div className="flex items-center gap-2">
                <Select value={pago.medio} onValueChange={(v) => actualizar(i, 'medio', v)}>
                  <SelectTrigger className="h-9 flex-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {medios.map((m) => (
                      <SelectItem key={m.id} value={m.id}>{etiquetaEnElPos(m)}</SelectItem>
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
                    aria-invalid={montoInvalido[i] || undefined}
                    onChange={(e) => actualizar(i, 'monto', e.target.value)}
                    onFocus={(e) => e.target.select()}
                  />
                  {montoInvalido[i] && (
                    <p className="text-xs text-destructive" role="alert">Monto inválido (ej. 1.500 o 1.500,50)</p>
                  )}
                </div>
                {pago.medio === 'efectivo' && (
                  <div className="grid gap-1">
                    <Label className="text-xs" htmlFor={`recibido-${i}`}>Recibe</Label>
                    <Input
                      id={`recibido-${i}`} value={pago.recibido} className="h-10 tabular-nums"
                      placeholder="opcional"
                      autoFocus={i === 0}
                      aria-invalid={recibidoInvalido[i] || undefined}
                      onChange={(e) => actualizar(i, 'recibido', e.target.value)}
                      onFocus={(e) => e.target.select()}
                    />
                    {recibidoInvalido[i] && (
                      <p className="text-xs text-destructive" role="alert">Monto inválido</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          <Button type="button" variant="outline" size="sm" onClick={agregarMedio}>
            <Plus />Dividir en otro medio
          </Button>

          {aplicaQr && (
            <div className="grid gap-2 rounded-md border p-3">
              {qrEstado === 'esperando' || qrEstado === 'acreditado' ? (
                <>
                  <p className="text-sm">
                    {qrEstado === 'acreditado' ? (
                      <span className="font-medium text-emerald-600 dark:text-emerald-500">
                        Pago acreditado. Cerrando la venta…
                      </span>
                    ) : (
                      <>
                        El QR de la caja ya está cobrando{' '}
                        <strong className="tabular-nums">${money(total)}</strong>.
                        Pedile al cliente que lo escanee.
                      </>
                    )}
                  </p>
                  {qrEstado === 'esperando' && (
                    <Button
                      type="button" size="sm" variant="ghost"
                      className="justify-self-start text-destructive hover:text-destructive"
                      onClick={() => { frenarPoll(); setConfirmarCancelarQr(true) }}
                    >
                      Cancelar el cobro por QR
                    </Button>
                  )}
                </>
              ) : (
                <>
                  <Button
                    type="button" size="sm" variant="secondary"
                    disabled={qrEstado === 'creando' || registrando}
                    onClick={cobrarConQr}
                  >
                    <QrCode />
                    {qrEstado === 'creando' ? 'Preparando el QR…' : 'Cobrar con QR'}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Registra la venta, pone el total en el QR impreso del mostrador
                    y espera a que MercadoPago avise. La venta se cierra sola cuando
                    se acredita
                    {mp?.auto_facturar ? ', con la factura emitida' : ''}. Cancelar
                    anula la venta.
                  </p>
                </>
              )}
              {qrError && <p className="text-sm text-destructive">{qrError}</p>}
            </div>
          )}

          {fia && (
            <div className="rounded-md border border-amber-500/50 bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
              {cliente ? (
                <p>
                  Queda como deuda de <strong>{cliente.name}</strong>. No
                  entra a la caja: el movimiento aparece cuando venga a pagar.
                </p>
              ) : (
                <div className="grid gap-2">
                  <p className="text-destructive">
                    Para fiar hace falta saber a quién: elegí el cliente.
                  </p>
                  <Button type="button" size="sm" variant="secondary" onClick={onPedirCliente}>
                    Elegir cliente (F7)
                  </Button>
                </div>
              )}
            </div>
          )}

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

          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

          <EmitirFactura marcado={factura} disponible={facturacion} onChange={setFactura} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={cerrar}>Cancelar</Button>
            {/* Mientras el QR está esperando, cerrar la venta a mano dejaría
                el monto puesto en el cartel de la caja cobrándole al próximo
                que escanee. El camino de salida es "Cancelar el cobro por
                QR" (con confirmación), que además anula la venta pendiente. */}
            <Button
              type="submit"
              disabled={!puedeCobrar || qrEstado === 'esperando' || qrEstado === 'creando'}
              className="min-w-32"
            >
              {registrando ? 'Cobrando...' : 'Cobrar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>

      {avisosPendientes && (
        <DialogoAvisosDeVencimiento
          avisos={avisosPendientes.avisos}
          onDecidir={(seguir) => {
            const { resolver } = avisosPendientes
            setAvisosPendientes(null)
            resolver(seguir)
          }}
        />
      )}

      <ConfirmDialog
        open={confirmarCancelarQr}
        onOpenChange={setConfirmarCancelarQr}
        title="¿Cancelar el cobro por QR?"
        description="Se vuelve a preguntar antes de anular: si el pago ya se acreditó, la venta queda cobrada igual. Si no, se anula -- se repone el stock y el cartel de la caja deja de cobrar este monto."
        confirmLabel="Anular la venta"
        onConfirm={() => {
          setConfirmarCancelarQr(false)
          void cancelarCobroQr()
        }}
      />
    </Dialog>
  )
}

/** Pantalla de cierre: lo unico que el cajero necesita ver es cuanto vuelto
 *  dar. El numero de venta y la factura quedan como dato secundario. */
function VentaCobrada({ venta, facturaError, aviso, onNueva }: {
  venta: Venta
  facturaError: string | null
  /** No es un error: es información sobre cómo se cerró la venta (p. ej. el
   *  pago por QR se acreditó justo cuando el cajero la estaba cancelando). */
  aviso?: string | null
  onNueva: () => void
}) {
  const pagos = venta.pagos as VentaPagoConRecibido[]
  const vuelto = pagos.reduce((acc, p) => {
    if (p.recibido == null || p.recibido <= p.monto) return acc
    return acc + (p.recibido - p.monto)
  }, 0)
  // Los avisos de vencimiento (ADR-053): `POST /api/ventas` y `GET /api/ventas/{id}` traen `avisos` sólo si hay alguno y el backend
  // tiene la opción; sin ella la clave no existe y no se muestra nada. Informan: un producto vencido se vende.
  const avisosDeLote = (venta as Venta & { avisos?: unknown }).avisos
  const avisosDeVencimiento = Array.isArray(avisosDeLote)
    ? (avisosDeLote as AvisoDeVencimiento[]).filter((a) => a && typeof a.nombre === 'string')
    : []

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'F8') {
        e.preventDefault()
        imprimirTicket(venta.id)
      } else if (e.key === 'Enter' || e.key === 'F2' || e.key === 'Escape') {
        e.preventDefault()
        onNueva()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNueva, venta.id])

  return (
    <div className="grid gap-4">
      <div className="rounded-md border p-6 text-center">
        <p className="text-sm text-muted-foreground">Venta {venta.numero} cobrada</p>
        <p className="mt-1 text-2xl font-medium tabular-nums">${money(venta.total)}</p>
        {(venta.promociones ?? []).length > 0 && (
          <div className="mt-2 grid gap-0.5 text-sm text-emerald-700 dark:text-emerald-400">
            {(venta.promociones ?? []).map((promo, i) => (
              <p key={i}>
                {promo.nombre}{promo.veces > 1 ? ` × ${promo.veces}` : ''}: ahorro ${money(promo.ahorro)}
              </p>
            ))}
          </div>
        )}
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
        {venta.factura_display && (
          <p className="mt-3 text-xs text-muted-foreground">
            Factura {venta.factura_display}
          </p>
        )}
      </div>

      {aviso && (
        <div className="rounded-md border border-amber-500/50 bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
          <p>{aviso}</p>
        </div>
      )}

      {avisosDeVencimiento.length > 0 && (
        <div role="note" aria-label="Avisos de vencimiento" className="rounded-md border border-amber-500/50 bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
          <p className="font-medium">Esta venta incluye mercadería con vencimiento a tener en cuenta:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {avisosDeVencimiento.map((a, i) => <li key={i}>{describirAviso(a)}</li>)}
          </ul>
        </div>
      )}

      {facturaError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm">
          <p className="text-destructive">No se pudo emitir la factura: {facturaError}</p>
          <p className="mt-1 text-muted-foreground">
            La venta quedó cobrada igual. Reintentá desde{' '}
            <Link to={`/ventas/${venta.id}`} className="font-medium text-primary hover:underline">
              el detalle de la venta
            </Link>.
          </p>
        </div>
      )}

      <Button className="h-14 text-base" onClick={onNueva} autoFocus>
        Nueva venta
      </Button>
      <Button variant="outline" onClick={() => imprimirTicket(venta.id)}>
        <Printer />Imprimir ticket <span className="ml-1 text-xs opacity-70">F8</span>
      </Button>
    </div>
  )
}

/** `/ventas/{id}/ticket` (F4, ADR-025) -- antes `/sales/{id}/ticket`, que ya
 *  no existe: `/sales` se retiró entero. Ver `lib/tickets.ts::abrirTicket`. */
function imprimirTicket(saleId: number) {
  abrirTicket(`/ventas/${saleId}/ticket`)
}


/** Apertura del turno. Bloquea el POS: sin turno el backend rechaza el cobro
 *  (409), y descubrirlo recien al cobrar significa haber cargado la venta
 *  entera al pedo.
 *
 *  🔴 Desde la feature de cajas por sucursal (2026-09-16) `caja_id` es
 *  obligatorio: el cajero elige primero la sucursal y después el mostrador
 *  -- sin las cajas que ya tienen un turno abierto, para no toparse con el
 *  409 recién al mandar el formulario. */
function AbrirTurno({ onAbierto }: { onAbierto: (t: Shift) => void }) {
  const [locations, setLocations] = useState<Sucursal[]>([])
  const [sucursalId, setSucursalId] = useState('')
  const [cajas, setCajas] = useState<Caja[]>([])
  const [cajaId, setCajaId] = useState('')
  const [monto, setMonto] = useState('0')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Igual que en `CerrarTurno`: "Efectivo inicial" tambien es dinero que
  // DECLARA el cajero (lo que cuenta en el cajon al abrir), asi que corre la
  // misma regla -- ver `parseMonto`. `null` sin haber tocado el campo
  // (arranca en "0", que es valido) no puede pasar, pero se cubre igual.
  const montoInicial = parseMonto(monto)
  const montoInvalido = monto !== '' && montoInicial === null

  useEffect(() => {
    api.get<Sucursal[]>('/api/sucursales').then((items) => {
      setLocations(items)
      const porDefecto = items.find((l) => !!l.es_default)
      setSucursalId(String((porDefecto ?? items[0])?.id ?? ''))
    }).catch(() => setLocations([]))
  }, [])

  useEffect(() => {
    if (!sucursalId) { setCajas([]); setCajaId(''); return }
    api.get<Caja[]>(`/api/cajas?sucursal_id=${sucursalId}`).then((todas) => {
      // Una caja dada de baja (inactiva) no se ofrece para abrir turno.
      const items = todas.filter((c) => !!c.activo)
      setCajas(items)
      const libre = items.find((c) => c.es_default && !c.tiene_turno_abierto)
        ?? items.find((c) => !c.tiene_turno_abierto)
      setCajaId(libre ? String(libre.id) : '')
    }).catch(() => setCajas([]))
  }, [sucursalId])

  async function abrir(e: FormEvent) {
    e.preventDefault()
    // Guardia defensiva: el boton ya queda disabled con un monto invalido,
    // esto es para no mandar el POST si igual llega a dispararse el submit
    // (Enter en un campo, por ejemplo).
    if (!cajaId || montoInicial === null) return
    setBusy(true)
    setError(null)
    try {
      const abierto = await api.post<Shift>('/api/turnos/abrir', {
        monto_inicial: montoInicial, caja_id: Number(cajaId),
      })
      onAbierto(abierto)
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
          Para poder cobrar hace falta abrir el turno en una caja. Contá lo
          que hay en el cajón ahora: es la base contra la que se arquea al
          cerrar.
        </p>
        <form onSubmit={abrir} className="mt-5 grid gap-3">
          <div className="grid gap-2">
            <Label>Sucursal</Label>
            {/* `v && ...`: el `<select>` nativo que Radix mantiene en sombra
                para accesibilidad dispara un `onChange` con valor vacío en
                cuanto sus `<option>` cambian (acá, cuando `locations` pasa
                de `[]` a la lista real) -- sin este guard, esa señal
                espuria pisaba la sucursal recién preseleccionada, antes de
                que el cajero llegara a tocar nada. Medido con la suite de
                este archivo (`pos-turno-por-caja.test.tsx`). */}
            <Select value={sucursalId} onValueChange={(v) => v && setSucursalId(v)}>
              <SelectTrigger aria-label="Sucursal"><SelectValue placeholder="Elegí una sucursal…" /></SelectTrigger>
              <SelectContent>
                {locations.map((l) => (
                  <SelectItem key={l.id} value={String(l.id)}>{l.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Caja</Label>
            <Select value={cajaId} onValueChange={(v) => v && setCajaId(v)} disabled={!sucursalId}>
              <SelectTrigger aria-label="Caja"><SelectValue placeholder="Elegí una caja…" /></SelectTrigger>
              <SelectContent>
                {cajas.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)} disabled={c.tiene_turno_abierto}>
                    {c.nombre}{c.tiene_turno_abierto ? ' (en uso)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {sucursalId && cajas.length > 0 && cajas.every((c) => c.tiene_turno_abierto) && (
              <p className="text-xs text-muted-foreground">
                Todas las cajas de esta sucursal tienen un turno abierto.
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="monto-inicial">Efectivo inicial en caja</Label>
            <Input
              id="monto-inicial" value={monto} className="h-12 text-lg tabular-nums"
              aria-invalid={montoInvalido || undefined}
              onChange={(e) => setMonto(e.target.value)}
              onFocus={(e) => e.target.select()}
            />
            {montoInvalido && (
              <p className="text-sm text-destructive" role="alert">
                Monto inválido: escribí sólo números, con coma o punto decimal
                (ej. 500 o 1.500,50).
              </p>
            )}
          </div>
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          <Button type="submit" className="h-12 text-base" disabled={busy || !cajaId || montoInicial === null}>
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
  // Turno recién cerrado: se queda en el diálogo un paso más para ofrecer el
  // ticket -- si `onCerrado()` corriera de una, la pantalla ya volvió al POS
  // (sin turno) y no hay dónde mostrar el botón.
  const [cerrado, setCerrado] = useState(false)

  useEffect(() => {
    api.get<ShiftState>(`/api/turnos/${turno.id}`)
      .then((r) => setResumen(r.resumen ?? null))
      .catch(() => setResumen(null))
  }, [turno.id])

  const esperado = resumen ? turno.monto_inicial + resumen.efectivo_ventas : null
  // 🔴 Acá guardaba `Number(declarado) || 0` en silencio: con un texto
  // inválido ("a500") `Number` da `NaN`, `|| 0` lo tapa, y el cierre se
  // registraba con $0 declarado sin ningún aviso (hallazgo del humano en la
  // prueba en pantalla, 2026-09-17). Ahora se parsea con la misma regla que
  // `AbrirTurno` (`parseMonto`) y, si no es válido, ni se calcula la
  // diferencia ni se deja enviar -- ver el botón, más abajo.
  const declaradoParseado = parseMonto(declarado)
  const declaradoInvalido = declarado !== '' && declaradoParseado === null
  const diferencia = esperado !== null && declaradoParseado !== null
    ? declaradoParseado - esperado
    : null

  async function cerrar(e: FormEvent) {
    e.preventDefault()
    // Guardia defensiva: el boton ya queda disabled sin un monto valido.
    if (declaradoParseado === null) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/api/turnos/${turno.id}/cerrar`, {
        monto_declarado: declaradoParseado, notas,
      })
      setCerrado(true)
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  if (cerrado) {
    return (
      <Dialog open onOpenChange={(o) => !o && onCerrado()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Turno #{turno.id} cerrado</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            El arqueo quedó registrado. Podés imprimir el ticket ahora.
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => abrirTicket(`/api/cierre-diario/turno/${turno.id}/ticket`)}
            >
              <Printer />Imprimir ticket
            </Button>
            <Button onClick={onCerrado}>Listo</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
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

          <div className="grid gap-2">
            <Label htmlFor="declarado">Efectivo contado</Label>
            <Input
              id="declarado" value={declarado} autoFocus className="h-12 text-lg tabular-nums"
              placeholder="0,00"
              aria-invalid={declaradoInvalido || undefined}
              onChange={(e) => setDeclarado(e.target.value)}
              onFocus={(e) => e.target.select()}
            />
            {declaradoInvalido && (
              <p className="text-sm text-destructive" role="alert">
                Monto inválido: escribí sólo números, con coma o punto decimal
                (ej. 500 o 1.500,50).
              </p>
            )}
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

          <div className="grid gap-2">
            <Label htmlFor="notas-cierre">Notas</Label>
            <Input
              id="notas-cierre" value={notas} placeholder="opcional"
              onChange={(e) => setNotas(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancelar}>Cancelar</Button>
            <Button type="submit" disabled={busy || declaradoParseado === null}>
              {busy ? 'Cerrando...' : 'Cerrar turno'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
