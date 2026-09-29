// El detalle de una sucursal: sus depósitos, con el de venta marcado. Pantalla del kit
// (`libra-ui/comercio/SucursalDetalle`); cada depósito lleva a `/depositos/:id` (`DepositoDetalle`).
import { SucursalDetalle as SucursalDetalleComercio } from 'libra-ui/comercio/SucursalDetalle'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function SucursalDetalle() {
  const { user } = useAuth()
  return (
    <SucursalDetalleComercio
      soloLectura={!puede(user, 'sucursales.admin')}
      rutaDelDeposito={(id) => `/depositos/${id}`}
      rutaDeSucursales="/sucursales"
      rutaDeTransferencia="/transferencias"
    />
  )
}
