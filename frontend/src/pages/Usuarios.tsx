// Shim sobre libra-ui/Usuarios (extraído 2026-07-26, era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).

import { Building2 } from 'lucide-react'
import { Usuarios as Compartida } from 'libra-ui/Usuarios'

/** El icono se pasa acá y no en el router: es un dato de ESTE producto —el que
 *  su propio sidebar le da a `/usuarios`— y el paquete no puede saberlo. */
export function Usuarios() {
  return <Compartida icono={Building2} />
}
