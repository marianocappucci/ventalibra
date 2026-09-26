// El detalle de una sucursal o depósito: el stock que tiene. Pantalla del kit (`libra-ui/comercio/DepositoDetalle`).
import { DepositoDetalle } from 'libra-ui/comercio/DepositoDetalle'
import { useAuth } from '../context/AuthContext'

export function SucursalDetalle() {
  const { user } = useAuth()
  return (
    <DepositoDetalle
      soloLectura={user?.role !== 'admin'} rutaDeDepositos="/sucursales" rutaDeTransferencia="/transferencias"
    />
  )
}
