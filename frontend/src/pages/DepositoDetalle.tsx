// El detalle de un depósito: el stock que tiene. Pantalla del kit (`libra-ui/comercio/DepositoDetalle`); «Volver»
// lleva a la lista de sucursales, desde donde se llegó.
import { DepositoDetalle as DepositoDetalleComercio } from 'libra-ui/comercio/DepositoDetalle'
import { useAuth } from '../context/AuthContext'

export function DepositoDetalle() {
  const { user } = useAuth()
  return (
    <DepositoDetalleComercio
      soloLectura={user?.role !== 'admin'} rutaDeDepositos="/sucursales" rutaDeTransferencia="/transferencias"
    />
  )
}
