// Cuánto hay de cada producto, y en qué sucursal: la pantalla del kit (`libra-ui/comercio/Stock`), la misma que
// monta Contalibra, sobre el router del motor (`/api/stock`, ADR-033).
//
// Variantes de VentaLibra: el backend devuelve `depositos` y el stock de cada producto en cada uno (`por_deposito`),
// con lo que la pantalla trae una columna por sucursal/depósito, el ajuste elige en cuál va y el historial dice
// cuál; `conFiltros` suma el buscador y «sólo los que tienen stock», que es lo que esta pantalla tenía antes. Los
// depósitos en cero se muestran a propósito: la pregunta que se le hace es «¿de dónde saco esto?».
import { Stock as StockComercio } from 'libra-ui/comercio/Stock'

export function Stock() {
  return <StockComercio conFiltros rutaDeProductos="/productos" />
}
