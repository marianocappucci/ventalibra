// La ficha del cliente: la pantalla del kit (`libra-ui/comercio/ClienteDetalle`), la misma que monta
// Contalibra, sobre el router del motor (`/api/clientes/:id`, ADR-029).
//
// Variantes de VentaLibra: todavía no tiene los módulos de facturación (facturas, presupuestos,
// remitos) ni el de MercadoPago (auto-facturar y alias de la bandeja); la ficha no ofrece lo que no
// puede atender. `conConsultaCuit` sí pasa a su default (`true`) desde la fase 14 (ADR-040): el motor
// ya tiene `build_consultar_cuit_router`. `conListaDePrecio` se prende desde que
// `build_cliente_lista_router` del motor (ADR-010 de libracommerce) reemplaza al add-on mayorista de
// Contalibra: acá no hay add-on, listas de precio es un módulo siempre libre (fase 7). Ver
// `inventario-adopcion-motores` en el wiki.
import { ClienteDetalle as ClienteDetalleComercio } from 'libra-ui/comercio/ClienteDetalle'

export function ClienteDetalle() {
  return <ClienteDetalleComercio conListaDePrecio conMercadoPago={false} conComprobantes={false} />
}
