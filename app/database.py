"""Modulos y add-ons: el contrato que espera el backoffice.

🔴 El backoffice prende/apaga add-ons y lee su estado corriendo un snippet
DENTRO de este contenedor (`libracore.admin.services.set_addon` /
`addons_de_instancia`, por `docker exec`), y ese snippet importa
`app.database.get_modulos` / `app.database.set_addon`. Es el contrato que
VentaLibra tiene que cumplir desde que declaro `ADDONS = {"resguardo_externo"}`
en `plans.py`.

Este producto no tenia `app/database.py` -- el dominio es sqlite3 crudo sobre
la conexion de `app/db.py` --, asi que el `docker exec` habria muerto con
`ModuleNotFoundError` y el backoffice habria mostrado el add-on como "no se
pudo leer". Es lo mismo que le paso a LibraDesk el 2026-09-09 con
`modo_simple` (ver su `app/database.py`).

Delegan en `libracore.db.modulos`, que es donde vive la implementacion unica
de la familia. Aca no se copia logica: se cumple el contrato.

⚠️ **Escriben por `libracore.db.core`, no por la conexion del dominio.** Dentro
de la app el core apunta a la base de LibraCore (`billing.configure`) y
`ModuleRepository` lee `modulos` por la conexion del dominio; en VentaLibra las
dos son **la misma base** (`VENTALIBRA_DB_PATH` y `VENTALIBRA_LIBRACORE_DB_PATH`
apuntan al mismo PostgreSQL, medido en `ventalibra-demo` el 2026-09-10). Lo
sostiene `tests/test_resguardo_externo_addon.py`: si un dia se separaran, el
backoffice prenderia el add-on en una base y el gate lo leeria en la otra.
"""


def _asegurar_core_configurado() -> None:
    """Apunta `libracore.db.core` a la base de ESTA instancia si nadie lo hizo.

    Estas dos funciones tienen dos vidas muy distintas:

    - Dentro de la app, `create_app()` ya configuro el core (via
      `services.billing.configure`) y aca no hay nada que hacer.
    - Bajo `docker exec python3 -c "from app.database import get_modulos"` no
      corrio ningun arranque, asi que el core esta sin configurar y
      `get_connection()` levanta `RuntimeError`. Ese es el caso que necesita
      resolverse solo, sin pedirle al backoffice que bootee la app entera.

    Se pregunta antes de configurar (`esta_configurado()`) para no pisarle la
    configuracion a una app viva. Y se resuelve con la base del DOMINIO
    (`url_de_instancia("ventalibra")`), que es la que lee `ModuleRepository`.
    """
    from libracore.db import core as libracore_core
    from libracore.db.url_de_instancia import url_de_instancia

    if not libracore_core.esta_configurado():
        libracore_core.configure(url_de_instancia("ventalibra", requerida=True))


def get_modulos() -> dict[str, bool]:
    """`{modulo: habilitado}` de esta instancia. Ver `_asegurar_core_configurado`."""
    _asegurar_core_configurado()
    from libracore.db.modulos import get_modulos as _get_modulos

    return _get_modulos()


def set_addon(nombre: str, habilitado: bool) -> None:
    """Prende/apaga un add-on suelto en esta instancia. Efecto inmediato:
    `ModuleRepository.is_enabled` relee la fila en cada request.

    No valida que `nombre` sea un add-on: eso lo hace quien llama, contra
    `plans.ADDONS` (ver `libracore.db.modulos.set_addon`)."""
    _asegurar_core_configurado()
    from libracore.db.modulos import set_addon as _set_addon

    _set_addon(nombre, habilitado)
