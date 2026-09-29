"""Que quien no tiene `costos.ver` no reciba el costo de la mercadería (ADR-049).

La matriz aprobada dice «el vendedor y el cajero no ven costos ni márgenes; el depósito, sin plata». Los márgenes, los
reportes y el dashboard ya están cerrados por su capacidad, pero **el costo unitario viajaba en las respuestas de rutas
que esos roles sí leen**: `precio_costo` en productos, stock y listas de precio, y `unit_cost` (más el `subtotal`, que es
cantidad × costo) en las órdenes y recepciones de compra.

🔑 **El mecanismo es un filtro de RESPUESTA, no una guarda por endpoint**: los routers del motor se montan enteros, y el
costo lo escriben ellos. Un middleware ASGI mira el prefijo de la ruta y, si la respuesta es JSON y quien la pidió no tiene
`costos.ver`, saca del JSON las claves de costo, en cualquier profundidad. Los cuerpos de los pedidos no se tocan: las
escrituras siguen con sus guardas.

- **Por prefijo, no por lista exacta**: `/api/productos` cubre `/api/productos/{id}/variantes`, `/api/productos/escanear`,
  `?incluir_variantes=`, con o sin barra final (la barra final es un 307 sin cuerpo). Se compara contra `scope["path"]`,
  que el servidor ya trae decodificado, así que `%70` no lo saltea.
- **Cierra por defecto**: si no hay sesión, si el usuario está inactivo o si no se puede leer el JSON, el costo no sale. Sólo
  lo ve quien tiene la capacidad.
- **Una ruta nueva fuera de los prefijos NO queda cubierta sola**: por eso `tests/test_roles_costos.py` recorre TODOS los GET
  del `openapi.json` con datos reales y busca el costo (por nombre de clave y por valor) en lo que reciben el vendedor, el
  cajero y el depósito.

Las claves que se sacan (medidas en las respuestas reales, ADR-049): `precio_costo` (productos, detalle de stock, ítems de
una lista de precio), `unit_cost` (líneas de órdenes y de recepciones de compra) y `subtotal` (líneas de las órdenes de
compra, sólo en esos prefijos). El patrón general (`costo`/`cost` como palabra de la clave) cubre además `default_cost`,
`unit_cost_snapshot`, `costo_actual`, `costo_nuevo`, `costo_estimado`, `sin_costo`... que hoy sólo aparecen en rutas de
`costos.ver`, `margen` o `logs`.
"""
import json
import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from .permisos import condicion

#: prefijo de ruta -> claves EXTRA (además del patrón general) que también revelan el costo bajo ese prefijo.
#: Las órdenes de compra traen `subtotal` = cantidad × costo unitario: despejar el costo es una división.
PREFIJOS: dict[str, frozenset[str]] = {
    "/api/productos": frozenset(),
    "/api/stock": frozenset(),
    "/api/depositos": frozenset(),
    "/api/proveedores": frozenset(),
    "/api/listas-precio": frozenset(),
    "/api/actualizacion-masiva": frozenset(),
    "/api/purchase-orders": frozenset({"subtotal"}),
    "/api/purchase-receipts": frozenset({"subtotal"}),
}

#: `costo` o `cost` como palabra de la clave: `precio_costo`, `unit_cost`, `default_cost`, `costo_actual`, `sin_costo`.
_CLAVE_DE_COSTO = re.compile(r"(^|_)(costos?|cost)($|_)")

_puede_ver_costos = condicion("costos.ver")


def extras_de(ruta: str) -> frozenset[str] | None:
    """Las claves extra de la ruta si está bajo un prefijo con costo; `None` si la ruta no se filtra."""
    for prefijo, extras in PREFIJOS.items():
        if ruta == prefijo or ruta.startswith(prefijo + "/"):
            return extras
    return None


def sin_costos(valor, extras: frozenset[str] = frozenset()):
    """El JSON sin las claves de costo, en cualquier profundidad (diccionarios dentro de listas dentro de diccionarios)."""
    if isinstance(valor, dict):
        return {
            clave: sin_costos(v, extras) for clave, v in valor.items()
            if clave not in extras and not _CLAVE_DE_COSTO.search(clave.lower())
        }
    if isinstance(valor, list):
        return [sin_costos(v, extras) for v in valor]
    return valor


async def _ve_costos(scope) -> bool:
    """Si quien hace el pedido tiene `costos.ver`. Lee lo mismo que la guarda (la cookie firmada y el usuario de la base),
    porque el rol vive en la base y no en la cookie. Sin sesión o con el usuario inactivo: no."""
    app = scope["app"]
    username = app.state.session_auth.get_current_user(Request(scope))
    if not username:
        return False
    usuario = await run_in_threadpool(app.state.users.get_by_username, username)
    return bool(usuario and usuario["active"] and _puede_ver_costos(usuario))


class SinCostos:
    """Middleware ASGI puro (no `BaseHTTPMiddleware`): el cuerpo sólo se retiene si hay que reescribirlo."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        extras = extras_de(scope["path"]) if scope["type"] == "http" else None
        if extras is None:
            await self.app(scope, receive, send)
            return

        inicio: dict | None = None  # el `http.response.start` retenido, mientras se junta el cuerpo a reescribir
        trozos: list[bytes] = []

        async def enviar(mensaje):
            nonlocal inicio
            if mensaje["type"] == "http.response.start":
                tipo = dict(mensaje["headers"]).get(b"content-type", b"")
                if tipo.startswith(b"application/json") and not await _ve_costos(scope):
                    inicio = mensaje
                    return
            elif mensaje["type"] == "http.response.body" and inicio is not None:
                trozos.append(mensaje.get("body", b""))
                if mensaje.get("more_body"):
                    return
                await _enviar_sin_costos(send, inicio, b"".join(trozos), extras)
                return
            await send(mensaje)

        await self.app(scope, receive, enviar)


async def _enviar_sin_costos(send, inicio: dict, cuerpo: bytes, extras: frozenset[str]) -> None:
    estado = inicio["status"]
    if cuerpo:
        try:
            cuerpo = json.dumps(
                sin_costos(json.loads(cuerpo), extras), ensure_ascii=False, separators=(",", ":"),
            ).encode()
        except ValueError:
            # Dice ser JSON y no se puede leer: no se sabe qué lleva, así que no sale.
            estado, cuerpo = 500, b'{"detail":"No se pudo ocultar el costo de la respuesta"}'
    cabeceras = [(k, v) for k, v in inicio["headers"] if k.lower() != b"content-length"]
    cabeceras.append((b"content-length", str(len(cuerpo)).encode()))
    await send({**inicio, "status": estado, "headers": cabeceras})
    await send({"type": "http.response.body", "body": cuerpo})
