// Proveedores: la pantalla del kit (`libra-ui/comercio/Proveedores`), la misma que monta Contalibra,
// sobre el router del motor (`/api/proveedores`, ADR-030).
//
// En un nodo offline (ADR-093) los proveedores se cargan en la versión web y bajan al equipo: el aviso lo dice. La pantalla del
// kit todavía no tiene una prop de sólo lectura (`puedeEscribir`, como `Compras`), así que los botones siguen y el backend
// contesta 409 `solo_en_el_central` con el mismo texto del aviso.
import { Proveedores as ProveedoresComercio } from 'libra-ui/comercio/Proveedores'
import { AvisoComprasEnElNodo } from '../components/aviso-compras-en-el-nodo'

export function Proveedores() {
  return (
    <>
      <AvisoComprasEnElNodo />
      <ProveedoresComercio />
    </>
  )
}
