// Reportes: la pantalla del kit (`libra-ui/comercio/Reportes`), la misma que monta Contalibra, sobre el router del motor
// (`/api/reportes`, ADR-035): ventas por período, medios de pago, productos más vendidos, caja y stock bajo, con los exports CSV.
//
// Sin variantes de pantalla: las de VentaLibra viven en el backend. Una venta anulada o pendiente de cobro no cuenta como venta, y la
// cuenta corriente no es ingreso de caja («fiar no es cobrar»), como en el arqueo del turno.
import { Reportes as ReportesComercio } from 'libra-ui/comercio/Reportes'

export function Reportes() {
  return <ReportesComercio />
}
