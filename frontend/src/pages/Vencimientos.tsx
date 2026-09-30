// Vencimientos y lotes: la pantalla del kit (`libra-ui/comercio/Vencimientos`) sobre los routers del motor (`/api/vencimientos`, ADR-052):
// qué lotes vencen pronto o ya vencieron, qué stock no tiene lote ni fecha, y las tres cosas que se pueden hacer con eso: ponerle lote y
// vencimiento a stock que no lo tiene y dar de baja un lote (`vencimientos.mover`: el encargado y el depósito) y marcar qué productos
// vencen (`vencimientos.marcar`: sólo el encargado). El kit oculta los botones según estas dos props; el que corta de verdad es el backend
// (403 a quien no tiene la capacidad).
//
// Hasta que las ventas descuenten por lote (A-4) el saldo por lote puede ser MAYOR al real: la pantalla del kit lo avisa, sin botón para
// cerrarlo.
import { Vencimientos as VencimientosComercio } from 'libra-ui/comercio/Vencimientos'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Vencimientos() {
  const { user } = useAuth()
  return <VencimientosComercio puedeMover={puede(user, 'vencimientos.mover')} puedeMarcar={puede(user, 'vencimientos.marcar')} />
}
