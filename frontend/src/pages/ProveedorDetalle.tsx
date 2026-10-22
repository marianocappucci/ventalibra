// La ficha del proveedor: la pantalla del kit (`libra-ui/comercio/ProveedorDetalle`), la misma que monta
// Contalibra, sobre el router del motor (ADR-030).
//
// Variante de VentaLibra: sin egresos (`conEgresos={false}`): este producto no tiene el módulo de egresos
// (registra órdenes y recepciones de compra, en Compras). La baja se rechaza si el proveedor tiene compras.
//
// En un nodo offline (ADR-093) el proveedor se edita en la versión web (ver `Proveedores`).
import { ProveedorDetalle as ProveedorDetalleComercio } from 'libra-ui/comercio/ProveedorDetalle'
import { AvisoComprasEnElNodo } from '../components/aviso-compras-en-el-nodo'

export function ProveedorDetalle() {
  return (
    <>
      <AvisoComprasEnElNodo />
      <ProveedorDetalleComercio conEgresos={false} />
    </>
  )
}
