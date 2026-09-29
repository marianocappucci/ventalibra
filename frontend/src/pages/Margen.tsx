// Margen y rotación: la pantalla del kit (`libra-ui/comercio/Margen`) sobre el router del motor (`/api/reportes/margen`, ADR-046):
// ingreso, costo, margen ($ y %) y unidades por producto y por período, ordenable y con export CSV.
//
// Sin variantes de pantalla: la cuenta es del motor. Una venta anulada o pendiente de cobro no cuenta y las devoluciones se restan.
import { Margen as MargenComercio } from 'libra-ui/comercio/Margen'

export function Margen() {
  return <MargenComercio />
}
