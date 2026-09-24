// Quién debe, cuánto, y la cuenta de cada uno.
//
// Es la pantalla del kit (`libra-ui/comercio/CuentaCorriente`, la misma que
// montan Contalibra y Restolibra desde P9-M4, 2026-09-07): listado con el
// cartel de deuda total y, al abrir un cliente, se navega a
// `/cuenta-corriente/:id` con los movimientos, el pago y la baja de pago
// (ver `CuentaCorrienteDetalle`). Acá sólo se monta: el contrato lo sirve
// `app/routers/cuenta_corriente_api.py` y las reglas de VentaLibra (turno
// obligatorio, caja del turno) las aplica el backend, no esta pantalla.
import { CuentaCorriente as CuentaCorrienteComercio } from 'libra-ui/comercio/CuentaCorriente'

export function CuentasCorrientes() {
  return <CuentaCorrienteComercio />
}