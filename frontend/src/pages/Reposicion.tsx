// Reposición sugerida: la pantalla del kit (`libra-ui/comercio/Reposicion`) sobre el router del motor (`/api/reportes/reposicion`, ADR-051):
// por producto, cuánto conviene pedir según lo que se vende, lo que hay y lo que ya viene en órdenes abiertas, con export CSV.
//
// Sin variantes de pantalla: la cuenta es del motor. Dos cosas dependen de quién mira:
// - **Generar órdenes en borrador** (kit v0.105.0, ADR-057): una orden por proveedor habitual con lo que hay que pedir. Escribe órdenes de compra, así que el botón
//   es de quien tiene `compras.escribir` (el encargado y el admin); el número de cada orden creada lleva a su detalle en Compras. Nunca envía ni confirma.
// - El filtro y la columna de proveedor aparecen solos si el motor los maneja (ADR-056).
// - En un nodo offline (ADR-093) tampoco se ofrece: las órdenes de compra se cargan en la versión web (el backend contestaría 409).
import { Reposicion as ReposicionComercio } from 'libra-ui/comercio/Reposicion'
import { useConexionDelNodo } from 'libra-ui/nodo-offline'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Reposicion() {
  const { user } = useAuth()
  const { esNodo } = useConexionDelNodo()
  // El visitante de la demo (`demo_readonly`) «puede» todo para ver (ver `puede`), pero el backend le abre sólo la lectura: a él no se le ofrece una acción que escribe.
  const soloLectura = (user as { demo_readonly?: unknown } | null)?.demo_readonly === true
  return <ReposicionComercio conGenerarOrdenes={puede(user, 'compras.escribir') && !soloLectura && !esNodo} rutaDeOrden={(id) => `/compras/${id}`} />
}
