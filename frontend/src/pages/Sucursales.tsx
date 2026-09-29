// Las sucursales: la pantalla del kit (`libra-ui/comercio/Sucursales`), sobre el router del motor
// (`/api/sucursales`, modelo jerárquico sucursal → depósitos). Una sucursal agrupa depósitos: el stock vive en
// éstos, y «Ver depósitos» lleva al detalle de la sucursal.
//
// Variantes de VentaLibra, todas props del kit: el título propio, **sólo lectura** para el cajero (el backend igual
// rechaza sus escrituras con 403) y las rutas del detalle y de la transferencia, que son las de este producto.
import { Sucursales as SucursalesComercio } from 'libra-ui/comercio/Sucursales'
import { useAuth } from '../context/AuthContext'

export function Sucursales() {
  const { user } = useAuth()
  return (
    <SucursalesComercio
      soloLectura={user?.role !== 'admin'}
      titulo="Sucursales"
      etiquetaNuevo="Nueva sucursal"
      rutaDelDetalle={(id) => `/sucursales/${id}`}
      rutaDeTransferencia="/transferencias"
    />
  )
}
