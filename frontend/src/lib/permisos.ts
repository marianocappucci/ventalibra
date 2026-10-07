// Qué puede hacer el usuario en sesión, tal como lo manda `/auth/me` (`capacidades`; ver `app/routers/auth.py` y
// `app/permisos.py`, ADR-049).
//
// 🔴 **Sólo decide qué se muestra: el que corta es el backend.** Cada endpoint contesta 403 con o sin este aviso. La
// matriz rol -> capacidad vive UNA vez, en `app/permisos.py`; acá no hay ninguna tabla de roles, sólo los NOMBRES de las
// capacidades (un test del backend, `tests/test_roles_matriz.py`, falla si esta lista y la de allá se separan) y la
// lectura de lo que llegó en el usuario. Antes la SPA miraba `user.role === 'admin'` y `adminOnly`, que con cinco
// roles no alcanza.
//
// Los roles y para qué sirve cada uno, en `DECISIONS.md` (ADR-049).
/** Los nombres de las capacidades. Tienen que ser EXACTAMENTE los de `app/permisos.py::CAPACIDADES`. */
export const CAPACIDADES = [
  'usuarios.admin',
  'config',
  'logs',
  'sucursales.admin',
  'caja.admin',
  'cierre_diario.reabrir',
  'facturas.nota_credito',
  'catalogo.ver',
  'productos.escribir',
  'catalogo.pantalla',
  'stock.pantalla',
  'proveedores.pantalla',
  'stock.ver',
  'stock.ajustar',
  'stock.transferir',
  'precios.consultar',
  'precios.escribir',
  'etiquetas',
  'ventas.pos',
  'ventas.todas',
  'caja.propia',
  'turnos.todos',
  'cierre_diario',
  'clientes.ver',
  'clientes.pantalla',
  'clientes.ficha',
  'clientes.alta',
  'clientes.escribir',
  'clientes.lista_precio',
  'cuenta_corriente',
  'cobranzas.anular',
  'compras.ver',
  'compras.escribir',
  'compras.recibir',
  'costos.ver',
  'egresos',
  'tesoreria',
  'libros_iva',
  'dashboard',
  'reportes',
  'margen',
  'reposicion.ver',
  'reposicion.parametros',
  'vencimientos.ver',
  'vencimientos.marcar',
  'vencimientos.mover',
] as const

export type Capacidad = (typeof CAPACIDADES)[number]

type ConCapacidades = { role?: unknown; capacidades?: unknown; demo_readonly?: unknown }

/** Si el usuario puede hacer lo que pide la capacidad (o CUALQUIERA de la lista, si se pasa una).
 *
 *  - Sin usuario: no.
 *  - **El visitante de la demo (`demo_readonly`) ve todo**, como hasta ahora: el backend le abre sólo la lectura
 *    (`json_api_require_role` de libraauth) y los botones de guardar de cada pantalla se siguen gateando por lo
 *    suyo, no por esto.
 *  - Si el backend no mandó `capacidades` (uno viejo) sólo el `admin` puede: es lo que hacía `role === 'admin'`, así
 *    que un backend sin roles nuevos se comporta como antes en vez de abrirle todo a cualquiera. */
export function puede(user: unknown, capacidad: Capacidad | readonly Capacidad[]): boolean {
  const datos = user as ConCapacidades | null | undefined
  if (!datos) return false
  if (datos.demo_readonly === true) return true
  const pedidas = typeof capacidad === 'string' ? [capacidad] : capacidad
  if (Array.isArray(datos.capacidades)) {
    const tiene = datos.capacidades as string[]
    return pedidas.some((c) => tiene.includes(c))
  }
  return datos.role === 'admin'
}

/** Para `hideFor` del menú del kit: esconde el ítem a quien NO tiene la capacidad. */
export function sinCapacidad(capacidad: Capacidad | readonly Capacidad[]) {
  return (user: unknown) => !puede(user, capacidad)
}

/** La pantalla a la que se lleva a quien entra a una ruta que no es suya, o a la raíz: el tablero para el encargado y el
 *  admin (ADR-054), el POS para quien vende y no administra (el cajero), el stock para el depósito. `null` si el usuario no tiene ninguna de las dos (un rol nuevo sin inicio: la app avisa en
 *  vez de rebotar en círculo). Cada destino exige justo la capacidad que se mira acá, así que nunca es una ruta que el
 *  propio usuario no pueda abrir. */
export function inicioDe(user: unknown): string | null {
  if (puede(user, 'dashboard')) return '/dashboard'
  if (puede(user, 'ventas.pos')) return '/pos'
  if (puede(user, 'stock.ver')) return '/stock'
  return null
}

/** Los roles que ofrece la pantalla de Usuarios, en el orden del Select. El PRIMERO es el que trae el alta: el de
 *  menos privilegio que sirve para trabajar (el cajero). `staff`, el de antes de los roles, se retiró (ADR-071). Tienen que coincidir con
 *  `app/permisos.py::ROLES` (`deposito` va sin tilde: es un valor de base). */
export const ROLES_DE_USUARIO: { value: string; label: string }[] = [
  { value: 'cajero', label: 'Cajero' },
  { value: 'vendedor', label: 'Vendedor' },
  { value: 'deposito', label: 'Depósito' },
  { value: 'encargado', label: 'Encargado' },
  { value: 'admin', label: 'Admin' },
]
