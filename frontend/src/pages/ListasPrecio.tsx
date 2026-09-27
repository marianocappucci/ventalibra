// Listas de precio: la pantalla del kit (`libra-ui/comercio/ListasPrecio`), la misma que monta Contalibra, sobre los
// routers del motor (`/api/listas-precio`, ADR-034). Las ve el admin: configurar precios es de admin.
import { ListasPrecio as ListasPrecioComercio } from 'libra-ui/comercio/ListasPrecio'

export function ListasPrecio() {
  return <ListasPrecioComercio />
}
