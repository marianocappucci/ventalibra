// Shim sobre libra-ui/Usuarios (extraído 2026-07-26, era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).

import { useAuth } from '../context/AuthContext'
import { Usuarios as Compartida } from 'libra-ui/Usuarios'
import { ROLES_DE_USUARIO } from '../lib/permisos'

/** El icono no se pasa: es el del catálogo de la familia (`ICONOS.usuarios`, libra-ui ADR-035), que es también el que lleva `/usuarios`
 *  en el sidebar (`components/Layout.tsx`). Antes era un `Building2` propio de este producto.
 *
 *  `permitirEliminar` en `true` desde la adopción del router de usuarios de
 *  libraauth (2026-09-13, ADR-018, `libraauth.usuarios.build_users_router`):
 *  el `DELETE {id}` ya trae las guardas del único admin (no se puede borrar
 *  ni al único admin activo ni a uno mismo), así que mostrar el botón deja
 *  de ser "ofrecer algo que el backend no atiende".
 *
 *  `roles` (ADR-049): los cinco roles de la instancia más el `staff` heredado
 *  (`ROLES_DE_USUARIO`, que espeja `app/permisos.py::ROLES`). El kit ya acepta
 *  la lista por prop, así que no hizo falta tocarlo. El primero es el que trae
 *  el alta (el cajero, el de menos privilegio que sirve para trabajar). */
export function Usuarios() {
  const { user } = useAuth()
  return <Compartida roles={ROLES_DE_USUARIO} permitirEliminar usuarioActualId={user?.id} />
}
