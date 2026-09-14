// Shim sobre libra-ui/Usuarios (extraído 2026-07-26, era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).

import { Building2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Usuarios as Compartida } from 'libra-ui/Usuarios'

/** El icono se pasa acá y no en el router: es un dato de ESTE producto —el que
 *  su propio sidebar le da a `/usuarios`— y el paquete no puede saberlo.
 *
 *  `permitirEliminar` en `true` desde la adopción del router de usuarios de
 *  libraauth (2026-09-13, ADR-018, `libraauth.usuarios.build_users_router`):
 *  el `DELETE {id}` ya trae las guardas del único admin (no se puede borrar
 *  ni al único admin activo ni a uno mismo), así que mostrar el botón deja
 *  de ser "ofrecer algo que el backend no atiende". `roles` sin pasar: el
 *  default de `Usuarios` (`admin`/`staff`) es el vocabulario de VentaLibra,
 *  igual que el default de `UserRepository` en `app/main.py`. */
export function Usuarios() {
  const { user } = useAuth()
  return <Compartida icono={Building2} permitirEliminar usuarioActualId={user?.id} />
}
