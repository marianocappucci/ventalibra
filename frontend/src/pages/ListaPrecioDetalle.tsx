// El detalle de una lista de precio: los precios de cada producto, el ajuste porcentual, la importación y —variante de
// VentaLibra— los **quiebres por cantidad** (`conQuiebres`; `build_quiebres_router` está montado).
import { ListaPrecioDetalle as ListaPrecioDetalleComercio } from 'libra-ui/comercio/ListaPrecioDetalle'

export function ListaPrecioDetalle() {
  return <ListaPrecioDetalleComercio conQuiebres />
}
