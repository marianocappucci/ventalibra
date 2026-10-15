// Mermas: la pantalla del kit (`libra-ui/comercio/Mermas`, ADR-063 del kit) sobre el router del motor (`/api/reportes/mermas`, libracommerce
// ADR-059; ADR-086 de este producto): cantidad e importe mermado por producto y período, con export CSV. Es de `costos.ver` (el encargado y
// el admin): el humano decidió que los importes de merma no los vea nadie más. El importe es un piso: las mermas sin costo cargado se cuentan aparte.
import { Mermas as MermasComercio } from 'libra-ui/comercio/Mermas'

export function Mermas() {
  return <MermasComercio />
}
