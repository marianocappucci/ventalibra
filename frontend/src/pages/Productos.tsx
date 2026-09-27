// Productos: la pantalla del kit (`libra-ui/comercio/Productos`), la misma que monta Contalibra, sobre el router del
// motor (`/api/productos`, ADR-034).
//
// Variantes de VentaLibra, todas props del kit: **códigos y variantes** de cada producto (`conDetalle`: varios códigos
// —barras, SKU, balanza— y talle/color), el **stock total** (la suma de todas las sucursales, `conStockTotal`), y **sin
// eliminar** (un producto con historial se desactiva, `conEliminar={false}`). Producto o servicio (`conTipo`) se elige al
// crear. Las unidades las dice el backend (las de la instalación) y las categorías son las activas de Configuración.
import { Productos as ProductosComercio } from 'libra-ui/comercio/Productos'

export function Productos() {
  return <ProductosComercio conTipo conDetalle conStockTotal conEliminar={false} />
}
