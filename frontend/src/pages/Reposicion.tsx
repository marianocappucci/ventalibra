// Reposición sugerida: la pantalla del kit (`libra-ui/comercio/Reposicion`) sobre el router del motor (`/api/reportes/reposicion`, ADR-051):
// por producto, cuánto conviene pedir según lo que se vende, lo que hay y lo que ya viene en órdenes abiertas, con export CSV.
//
// Sin variantes de pantalla: la cuenta es del motor. Dos cosas dependen de quién mira:
// - **Generar órdenes en borrador** (kit v0.105.0, ADR-057): una orden por proveedor habitual con lo que hay que pedir. Escribe órdenes de compra, así que el botón
//   es de quien tiene `compras.escribir` (el encargado y el admin); el número de cada orden creada lleva a su detalle en Compras. Nunca envía ni confirma.
// - El filtro y la columna de proveedor aparecen solos si el motor los maneja (ADR-056).
import { Reposicion as ReposicionComercio } from 'libra-ui/comercio/Reposicion'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Reposicion() {
  const { user } = useAuth()
  return <ReposicionComercio conGenerarOrdenes={puede(user, 'compras.escribir')} rutaDeOrden={(id) => `/compras/${id}`} />
}
