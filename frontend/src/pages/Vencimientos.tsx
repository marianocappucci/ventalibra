// Vencimientos y lotes: la pantalla del kit (`libra-ui/comercio/Vencimientos`) sobre los routers del motor (`/api/vencimientos`, ADR-052):
// qué lotes vencen pronto o ya vencieron, qué stock no tiene lote ni fecha, y las tres cosas que se pueden hacer con eso: ponerle lote y
// vencimiento a stock que no lo tiene y dar de baja un lote (`vencimientos.mover`: el encargado y el depósito) y marcar qué productos
// vencen (`vencimientos.marcar`: sólo el encargado). El kit oculta los botones según estas dos props; el que corta de verdad es el backend
// (403 a quien no tiene la capacidad).
//
// Desde libracommerce v0.30.0 (A-4, ADR-053) las ventas y el resto de las salidas descuentan por lote y la baja de un lote está habilitada
// (`puedeMover` abre asignar, cargar stock con lote y dar de baja). 🔴 El kit v0.92.0 TODAVÍA muestra un aviso ámbar fijo («Hasta que las
// ventas descuenten por lote, el saldo de cada lote puede ser MAYOR al real…») que ya no es cierto para lo vendido después de A-4 (sólo lo
// anterior, y un saldo «sin lote» negativo, pueden sobreestimar): no tiene prop para apagarlo; está pedido al kit en `TASKS.md`.
import { Vencimientos as VencimientosComercio } from 'libra-ui/comercio/Vencimientos'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function Vencimientos() {
  const { user } = useAuth()
  return <VencimientosComercio puedeMover={puede(user, 'vencimientos.mover')} puedeMarcar={puede(user, 'vencimientos.marcar')} />
}
