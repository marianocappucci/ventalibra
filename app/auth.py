"""Session auth para la API JSON de VentaLibra -- shim sobre libraauth.

Extraído 2026-07-26 a libracore.auth (era byte-idéntico en Gestiolibra/
MedLibra/VentaLibra, ver wiki/analyses/auditoria-duplicacion-familia-libra.md)
y **migrado el 2026-07-30 a `libraauth.session_auth`**: el auth salió de
LibraCore y pasó a ser un motor transversal propio, ver
wiki/entities/libraauth.md.

**Los nombres importados no cambiaron**: libraauth re-exporta exactamente la
misma API pública. La diferencia real está en main.py — su UserRepository
trabaja sobre SQLAlchemy, así que VentaLibra (que es sqlite3 crudo) sumó un
engine dedicado **sobre la base de libracore**, donde `usuarios` ya vivía.
"""
from libraauth.session_auth import (
    SessionAuth,
)
from libraauth.session_auth import (
    json_api_get_current_user as get_current_user,
)
from libraauth.session_auth import (
    json_api_get_session_auth as get_session_auth,
)
from libraauth.session_auth import (
    # La base de TODAS las guardas de rol de este producto: `app/permisos.py::requiere` la arma con los roles de
    # cada capacidad. Es la que sabe de la lectura abierta a la demo y del gate de Terminos.
    json_api_require_role as require_role,
)

from .services.users import UserRepository

# Las guardas de cada router ya no viven acá: son las capacidades de `app/permisos.py` (ADR-049). Lo que era
# `require_admin`/`require_staff` y las dos guardas por método (`require_staff_lectura_admin_escritura`,
# `require_staff_precio_admin_resto`) pasó a `requiere(...)`, `requiere_segun_metodo(...)` y
# `requiere_segun_ruta(...)`. El token de servicio del backoffice (`requiere_o_servicio`) sigue siendo sólo del
# router de usuarios.


def build_session_auth(users: UserRepository) -> SessionAuth:
    return SessionAuth(
        dev_secret_fallback="ventalibra-dev-secret-not-for-prod",
        get_user_by_username=users.get_by_username,
        check_credentials=users.check_credentials,
        cookie_name="vl_session",
    )
