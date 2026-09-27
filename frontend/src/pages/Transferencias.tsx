// Mover mercadería entre sucursales o depósitos: la pantalla del kit (`libra-ui/comercio/DepositoTransferencia`), la
// misma que monta Contalibra, sobre el router del motor (`/api/depositos/transferir`, ADR-033).
//
// Variante de VentaLibra: `conHistorial`, el historial de transferencias debajo (qué se movió, de dónde a dónde y
// cuándo). ⚠️ No hay estado «en tránsito»: al confirmar, el sistema ya cuenta la mercadería en el destino.
import { DepositoTransferencia } from 'libra-ui/comercio/DepositoTransferencia'

export function Transferencias() {
  return <DepositoTransferencia conHistorial rutaDeDepositos="/sucursales" />
}
