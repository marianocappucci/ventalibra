// Los turnos de caja: la pantalla del kit (`libra-ui/comercio/Turnos`), la misma que monta Contalibra, sobre
// el router del motor (`/api/turnos`, ADR-032). Cada uno ve los suyos; el encargado y el admin, los de todos (`turnos.todos`).
//
// Variante de VentaLibra: el turno se abre **sobre una caja** (`conCaja`); la caja y la sucursal salen de
// `enriquecer` en el backend. El POS sigue siendo donde el cajero abre y cierra su turno de todos los días.
import { Turnos as TurnosComercio } from 'libra-ui/comercio/Turnos'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Turnos() {
  const { user } = useAuth()
  return <TurnosComercio esAdmin={puede(user, 'turnos.todos')} conCaja />
}
