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

**El formato de la fila no se define aca ni en LibraCommerce** (ADR-080, libracommerce v0.57.0 / libracore
v1.157.0 / libraauth v0.49.0): lo define `libraauth.auditoria.registrador_dbapi`, y este modulo arma UN registrador
que usan los dos motores. El usuario lo resuelve el registrador, del `ContextVar` de `libraauth` que llena
`agregar_middleware_de_usuario` en cada request.

El mismo `REGISTRADOR` se le enchufa a `libracore.auditoria` en `create_app()` (`app/main.py`): las escrituras de
`clients` (`/api/clientes`, el fiado) son del motor de core, no del repositorio de LibraCommerce, y asi quedan en el
mismo log con el mismo formato.
"""

from libraauth.auditoria import registrador_dbapi
from libracommerce.db import auditoria as auditoria_comercial
from libracommerce.db.auditoria import RepositorioAuditado
from libracommerce.db.repository import SqliteCommerceRepository, usar_fabrica_de_repositorio
from libracore.db.core import Conexion

#: `{tabla: nombre logico}` de todo lo que este producto audita: lo de LibraCommerce y los clientes del motor de core.
#:
#: 🔴 `cliente` (la tabla `clients`, la de `/api/clientes` y la cuenta corriente) **no es** `cliente/proveedor` (la
#: tabla `parties` de LibraCommerce, que escribe `save_party`): son dos entidades distintas con dos nombres, y el filtro
#: de la pantalla de Logs compara el texto entero, asi que no se mezclan. `cliente` es el mismo nombre que le da la
#: familia a `clients` (LibraDesk, Contalibra, Restolibra).
ENTIDADES = {**auditoria_comercial.entidades_por_tabla(), "clients": "cliente"}

REGISTRADOR = registrador_dbapi(ENTIDADES, **auditoria_comercial.opciones_del_registrador())


def entidades_del_log() -> dict[str, str]:
    """Lo que ofrece el filtro de la pantalla de Logs: las entidades de LibraCommerce y `cliente`."""
    return {**auditoria_comercial.entidades(), "clients": "cliente"}


def repositorio(conn: Conexion) -> RepositorioAuditado:
    return RepositorioAuditado(SqliteCommerceRepository(conn), conn, REGISTRADOR)


# Las funciones del ERP del motor (`libracommerce.erp.catalogo`, listas de precio: las que usan los routers de
# productos y depósitos) arman su repositorio adentro. Se les declara ACÁ, una vez, cómo se arma el de este producto,
# así lo que entra por el motor también queda en `actividad_log` (libracommerce v0.19.0).
usar_fabrica_de_repositorio(repositorio)
