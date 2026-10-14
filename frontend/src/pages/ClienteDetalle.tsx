// La ficha del cliente: la pantalla del kit (`libra-ui/comercio/ClienteDetalle`), la misma que monta
// Contalibra, sobre el router del motor (`/api/clientes/:id`, ADR-029).
//
// Variantes de VentaLibra: todavía no tiene los módulos de facturación (facturas, presupuestos,
// remitos) ni el de MercadoPago (auto-facturar y alias de la bandeja); la ficha no ofrece lo que no
// puede atender. `conConsultaCuit` sí pasa a su default (`true`) desde la fase 14 (ADR-040): el motor
// ya tiene `build_consultar_cuit_router`.
//
// 🔑 **`conListaDePrecio` NO se prende (ADR-084, 2026-10-14).** La tarjeta «Lista de precios» deja
// asignarle una lista a un cliente, pero el POS y la validación del precio del servidor sólo usan la lista
// predeterminada: la asignada no cambiaba ningún precio. Una pantalla que parece activa y no hace nada
// es peor que no tenerla. El router del motor sigue montado (`app/main.py`) y el gancho
// `lista_de_precio_para` está listo en `libracommerce`: se vuelve a prender cuando el POS cotice con
// la lista del cliente y el servidor la valide con la misma (ver ADR-084).
import { ClienteDetalle as ClienteDetalleComercio } from 'libra-ui/comercio/ClienteDetalle'

export function ClienteDetalle() {
  return <ClienteDetalleComercio conMercadoPago={false} conComprobantes={false} />
}
