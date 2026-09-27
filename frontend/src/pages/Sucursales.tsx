// Sucursales y depósitos: la pantalla del kit (`libra-ui/comercio/Depositos`), la misma que monta Contalibra, sobre
// el router del motor (`/api/depositos`, ADR-033).
//
// Variantes de VentaLibra, todas props del kit: los dos **tipos** (sucursal / depósito) que se eligen al crear y no
// se cambian, con su filtro; el título propio; y **sólo lectura** para el cajero (el backend igual rechaza sus
// escrituras con 403). Las rutas del detalle y de la transferencia son las de este producto.
import { Depositos as DepositosComercio, type TipoDeDeposito } from 'libra-ui/comercio/Depositos'
import { useAuth } from '../context/AuthContext'

// El código que guarda el backend (`store`/`warehouse`) es el que ya tienen las bases de los clientes; en pantalla
// nunca se ve, sólo la palabra.
export const TIPOS: TipoDeDeposito[] = [
  { valor: 'store', etiqueta: 'Sucursal', plural: 'Sucursales' },
  { valor: 'warehouse', etiqueta: 'Depósito' },
]

export function Sucursales() {
  const { user } = useAuth()
  return (
    <DepositosComercio
      tipos={TIPOS}
      soloLectura={user?.role !== 'admin'}
      titulo="Sucursales / depósitos"
      etiquetaNuevo="Nueva sucursal / depósito"
      rutaDelDetalle={(id) => `/sucursales/${id}`}
      rutaDeTransferencia="/transferencias"
    />
  )
}
