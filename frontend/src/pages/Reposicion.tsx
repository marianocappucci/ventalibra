// Reposición sugerida: la pantalla del kit (`libra-ui/comercio/Reposicion`) sobre el router del motor (`/api/reportes/reposicion`, ADR-051):
// por producto, cuánto conviene pedir según lo que se vende, lo que hay y lo que ya viene en órdenes abiertas. Sólo lectura, con export CSV.
//
// Sin variantes de pantalla: la cuenta es del motor. Sólo sugiere: no genera la orden de compra.
import { Reposicion as ReposicionComercio } from 'libra-ui/comercio/Reposicion'

export function Reposicion() {
  return <ReposicionComercio />
}
