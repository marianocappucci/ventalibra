"""De donde sale el repositorio de LibraCommerce en VentaLibra.

Existe por una sola razon: que **ningun servicio construya el repositorio
desnudo**. Envuelto, cada escritura queda en `actividad_log`; desnudo, no —y no
se nota, porque el log sigue mostrando las filas de los otros servicios y
parece sano.

Los diez servicios de `app/services/` construyen el suyo (`_repo =
repositorio(conn)`), asi que no hay una instancia unica que envolver en
`create_app()`. La fabrica es el punto unico que faltaba.

`test_ningun_servicio_usa_el_repositorio_desnudo` es lo que lo sostiene: falla
si alguien vuelve a importar `SqliteCommerceRepository` fuera de este archivo.

El usuario sale del `ContextVar` de `libraauth`, que llena
`agregar_middleware_de_usuario` en cada request. Se pasa como callable y no
como valor porque cambia por request; y va de este lado, no adentro de
LibraCommerce, para que el motor comercial no dependa del de auth.
"""

from libraauth.auditoria import usuario_actual
from libracommerce.db.auditoria import RepositorioAuditado
from libracommerce.db.repository import SqliteCommerceRepository
from libracore.db.core import Conexion


def repositorio(conn: Conexion) -> RepositorioAuditado:
    return RepositorioAuditado(
        SqliteCommerceRepository(conn), conn, usuario=usuario_actual.get,
    )
