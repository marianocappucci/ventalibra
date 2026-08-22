// La pantalla vive en libra-ui (v0.12.0), igual que `Usuarios`.
//
// La actividad que muestra sale del motor comercial (libracommerce v0.5.0) y
// los accesos del de auth (libraauth v0.8.0), pero eso lo resuelve el backend:
// las dos mitades llegan por el mismo endpoint y con la misma forma.

import { ScrollText } from 'lucide-react'
import { Logs as Compartida } from 'libra-ui/Logs'

/** Ver el comentario de `Usuarios`: el icono es de este producto. */
export function Logs() {
  return <Compartida icono={ScrollText} />
}
