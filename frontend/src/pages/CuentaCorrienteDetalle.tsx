// La cuenta de un cliente: movimientos, saldo, el pago y la baja.
//
// La pantalla vive en el kit desde P9-M4 (2026-09-07); Contalibra la monta
// igual. Lo que decide este producto: el rol admin borra pagos, y al cobrar
// se emite y se abre el recibo de cobranza (`con_recibos` en el backend, que
// acá está siempre como en Contalibra -- los recibos de cobranza son el
// único origen de este producto).
import { CuentaCorrienteDetalle as CuentaCorrienteDetalleComercio } from 'libra-ui/comercio/CuentaCorrienteDetalle'
import { useAuth } from '../context/AuthContext'

export function CuentaCorrienteDetalle() {
  const { user } = useAuth()
  return <CuentaCorrienteDetalleComercio esAdmin={user?.role === 'admin'} conRecibos />
}