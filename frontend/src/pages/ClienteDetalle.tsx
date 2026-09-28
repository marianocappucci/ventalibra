// La ficha del cliente: la pantalla del kit (`libra-ui/comercio/ClienteDetalle`), la misma que monta
// Contalibra, sobre el router del motor (`/api/clientes/:id`, ADR-029).
//
// Variantes de VentaLibra: todavía no tiene los módulos de facturación (facturas, presupuestos,
// remitos) ni el de MercadoPago (auto-facturar y alias de la bandeja); la ficha no ofrece lo que no
// puede atender. `conConsultaCuit` sí pasa a su default (`true`) desde la fase 14 (ADR-040): el motor
// ya tiene `build_consultar_cuit_router`. Ver `inventario-adopcion-motores` en el wiki.
import { ClienteDetalle as ClienteDetalleComercio } from 'libra-ui/comercio/ClienteDetalle'

export function ClienteDetalle() {
  return <ClienteDetalleComercio conMercadoPago={false} conComprobantes={false} />
}
