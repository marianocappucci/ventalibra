// El detalle de una sucursal: sus depósitos, con el de venta marcado. Pantalla del kit
// (`libra-ui/comercio/SucursalDetalle`); cada depósito lleva a `/depositos/:id` (`DepositoDetalle`).
import { SucursalDetalle as SucursalDetalleComercio } from 'libra-ui/comercio/SucursalDetalle'
import { useAuth } from '../context/AuthContext'

export function SucursalDetalle() {
  const { user } = useAuth()
  return (
    <SucursalDetalleComercio
      soloLectura={user?.role !== 'admin'}
      rutaDelDeposito={(id) => `/depositos/${id}`}
      rutaDeSucursales="/sucursales"
      rutaDeTransferencia="/transferencias"
    />
  )
}
