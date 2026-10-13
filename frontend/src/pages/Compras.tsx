// Las órdenes de compra: la pantalla del kit (`libra-ui/comercio/Compras`) sobre el router del motor.
//
// `puedeEscribir` (libra-ui 0.146.0, ADR-058 del kit; ADR-083 de este repo): el depósito tiene `compras.ver` pero no
// `compras.escribir`, así que no se le ofrece «Nueva compra» (el backend le contestaría 403). El kit además oculta solo los
// importes que el backend no le manda (`app/costos.py`): sin `$NaN`.
import { Compras as ComprasComercio } from 'libra-ui/comercio/Compras'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Compras() {
  const { user } = useAuth()
  return <ComprasComercio puedeEscribir={puede(user, 'compras.escribir')} />
}
