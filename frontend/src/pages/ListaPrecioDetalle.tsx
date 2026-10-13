// El detalle de una lista de precio: los precios de cada producto, el ajuste porcentual, la importación y —variante de
// VentaLibra— los **quiebres por cantidad** (`conQuiebres`; `build_quiebres_router` está montado), las **promociones con vigencia**
// (`conVigencias`, ADR-042) y, desde libra-ui 0.147.0, la **sucursal** del precio vigente (`conSucursal`: el select «Sucursal», que
// el kit ofrece con dos o más sucursales activas). 🔴 `conSucursal` exige libracommerce >= 0.59.0: sólo desde ahí la validación de la
// venta respeta el precio de la sucursal (ADR-058 del motor; ADR-083 de este repo).
import { ListaPrecioDetalle as ListaPrecioDetalleComercio } from 'libra-ui/comercio/ListaPrecioDetalle'

export function ListaPrecioDetalle() {
  return <ListaPrecioDetalleComercio conQuiebres conVigencias conSucursal />
}
