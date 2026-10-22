// Las órdenes de compra: la pantalla del kit (`libra-ui/comercio/Compras`) sobre el router del motor.
//
// `puedeEscribir` (libra-ui 0.146.0, ADR-058 del kit; ADR-083 de este repo): el depósito tiene `compras.ver` pero no
// `compras.escribir`, así que no se le ofrece «Nueva compra» (el backend le contestaría 403). El kit además oculta solo los
// importes que el backend no le manda (`app/costos.py`): sin `$NaN`.
//
// En un nodo offline (ADR-093) tampoco se ofrece «Nueva compra»: las órdenes se cargan en la versión web y bajan al equipo del
// local (el backend contestaría 409 `solo_en_el_central`). Acá sólo se las ve y, en su detalle, se recibe contra ellas.
import { Compras as ComprasComercio } from 'libra-ui/comercio/Compras'
import { useConexionDelNodo } from 'libra-ui/nodo-offline'
import { AvisoComprasEnElNodo } from '../components/aviso-compras-en-el-nodo'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Compras() {
  const { user } = useAuth()
  const { esNodo } = useConexionDelNodo()
  return (
    <>
      <AvisoComprasEnElNodo>Para recibir mercadería, abrí la orden y usá «Recibir mercadería».</AvisoComprasEnElNodo>
      <ComprasComercio puedeEscribir={puede(user, 'compras.escribir') && !esNodo} />
    </>
  )
}
