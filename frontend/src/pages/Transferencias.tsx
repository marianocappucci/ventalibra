// Mover mercadería entre sucursales o depósitos: la pantalla del kit (`libra-ui/comercio/DepositoTransferencia`), la
// misma que monta Contalibra, sobre el router del motor (`/api/depositos/transferir`, ADR-033).
//
// Variante de VentaLibra: `conHistorial`, el historial de transferencias debajo (qué se movió, de dónde a dónde y
// cuándo). ⚠️ No hay estado «en tránsito»: al confirmar, el sistema ya cuenta la mercadería en el destino.
//
// **Un solo local (ADR-048).** Con el plan único (ADR-072) `multisucursal` viene prendido; si un administrador lo apagó, sin el módulo `multisucursal` el backend sólo deja transferir entre
// depósitos de la MISMA sucursal (un local con dos depósitos sigue siendo un local) y rechaza con 403 la que cruza de
// sucursal. La pantalla no se esconde: sirve para lo primero y muestra el historial de lo ya hecho; el aviso dice qué
// no se puede, y el mensaje del backend llega tal cual si alguien lo intenta.
import { DepositoTransferencia } from 'libra-ui/comercio/DepositoTransferencia'
import { AvisoModulo } from '../components/aviso-modulo'
import { MULTISUCURSAL, useTieneModulo } from '../lib/modulos'

export function Transferencias() {
  const multisucursal = useTieneModulo(MULTISUCURSAL)
  return (
    <div className="grid gap-4">
      {!multisucursal && (
        <AvisoModulo titulo="Transferencias entre sucursales">
          Podés mover mercadería entre los depósitos de tu sucursal. Pasarla de una sucursal a otra no está
          habilitado en esta instancia; escribinos para activarlo.
        </AvisoModulo>
      )}
      <DepositoTransferencia conHistorial rutaDeDepositos="/sucursales" />
    </div>
  )
}
