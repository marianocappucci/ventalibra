// Productos: la pantalla del kit (`libra-ui/comercio/Productos`), la misma que monta Contalibra, sobre el router del
// motor (`/api/productos`, ADR-034).
//
// Variantes de VentaLibra, todas props del kit: **códigos y variantes** de cada producto (`conDetalle`: varios códigos
// —barras, SKU, balanza— y talle/color), el **stock total** (la suma de todas las sucursales, `conStockTotal`), y **sin
// eliminar** (un producto con historial se desactiva, `conEliminar={false}`). Producto o servicio (`conTipo`) se elige al
// crear. Las unidades las dice el backend (las de la instalación) y las categorías son las activas de Configuración.
//
// **El interruptor «Vence»** (vencimientos y lotes, ADR-053; kit v0.92.0): el backend ya trae y acepta `vence` en los productos
// (`OpcionesCatalogo.con_vencimientos`), pero marcar un producto como perecedero es de quien tiene `vencimientos.marcar` (el
// encargado y el admin), no de todo el que edita productos (el staff heredado también edita). `conVencimientos` lo decide por esa
// capacidad: con ella, el interruptor se fuerza aunque el catálogo todavía esté vacío (el kit lo deduce de los datos y una lista
// vacía no tiene de dónde); sin ella, no se ofrece (el backend igual contesta 403 a quien intente cambiar la marca).
import { Productos as ProductosComercio } from 'libra-ui/comercio/Productos'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Productos() {
  const { user } = useAuth()
  return (
    <ProductosComercio
      conTipo conDetalle conStockTotal conEliminar={false}
      conVencimientos={puede(user, 'vencimientos.marcar')}
    />
  )
}
