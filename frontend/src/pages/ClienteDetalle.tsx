// La ficha del cliente: la pantalla del kit (`libra-ui/comercio/ClienteDetalle`), la misma que monta
// Contalibra, sobre el router del motor (`/api/clientes/:id`, ADR-029).
//
// Variantes de VentaLibra: todavía no tiene los módulos de facturación (facturas, presupuestos,
// remitos), de MercadoPago (auto-facturar y alias de la bandeja) ni la consulta del CUIT en ARCA;
// la ficha no ofrece lo que no puede atender. Ver `inventario-adopcion-motores` en el wiki.
import { ClienteDetalle as ClienteDetalleComercio } from 'libra-ui/comercio/ClienteDetalle'

export function ClienteDetalle() {
  return (
    <ClienteDetalleComercio conMercadoPago={false} conComprobantes={false} conConsultaCuit={false} />
  )
}
