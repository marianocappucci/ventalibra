// La caja por medio de cobro y por mostrador: el pivot del kit (`libra-ui/comercio/CajaMedios`) sobre
// `/api/reportes/caja-medios` (ADR-035). Con varias cajas por sucursal es lo que dice cuánto entró por cada caja y cada medio; la
// cuenta corriente no aparece (fiar no es cobrar).
import { CajaMedios } from 'libra-ui/comercio/CajaMedios'

export function CajaPorMedio() {
  return <CajaMedios />
}
