"""Roles y capacidades de VentaLibra: la matriz de permisos, en UN solo lugar (ADR-049).

Hasta el 2026-09-29 el producto sólo tenía dos roles (`admin` y `staff`) y cada router se montaba con
`admin_only` o `staff_or_admin`. El humano pidió cinco roles con permisos distintos, así que ese binario
ya no alcanza: lo que un rol puede hacer se dice acá, con **capacidades nombradas** (`reportes`,
`stock.ajustar`, ...), y cada router de `app/main.py` se monta con la capacidad que le corresponde.

**Una sola fuente.** `_ROLES_DE` es la única tabla que decide quién puede qué. De ella salen:

- las guardas del backend (`requiere(...)`, más abajo);
- la lista de capacidades que `/auth/me` le manda a la SPA (`capacidades_de`, ver `app/routers/auth.py`),
  que es lo que decide el menú y las rutas del frontend;
- el vocabulario de roles de `UserRepository` y del router de usuarios (`ROLES`).

**Sólo se listan los roles que NO son admin.** `admin` tiene todas las capacidades por construcción
(«admin: todo»): una capacidad nueva la trae puesta sin tocar nada, y la fila dice a quién más se le abre.
Es una asimetría deliberada: para un permiso nuevo el error seguro es que lo tenga el admin y nadie más.

Los roles:

- `admin`: todo.
- `encargado`: todo menos usuarios, configuración, logs, estructura (sucursales, depósitos y cajas) y
  reabrir un día cerrado.
- `vendedor`: mostrador con clientes; no ve costos ni márgenes ni reportes.
- `cajero`: POS, su turno y su caja; no ve cierre diario, cuentas corrientes ni reportes.
- `deposito` (sin tilde, es un valor de base y de URL; en pantalla se lee «Depósito»): stock, ajustes y transferencias, y
  lectura de órdenes y recepciones de compra sin importes; no recibe compras, sin POS y sin plata.
- `staff`: **heredado; migrar a un rol concreto.** Los usuarios que ya existían. Tiene exactamente lo que
  tenía antes de los roles (la unión de lo que hacía un cajero y un mozo de mostrador): ni una capacidad más,
  ni una menos. No se migra ni se borra a nadie.

🔴 **El visitante de la demo** entra como `staff`, y `json_api_require_role` de libraauth le abre la
LECTURA de todo lo que pida cualquier rol. Las guardas de acá se construyen SOBRE esa función y no la
duplican, así que la demo, el gate de Términos y demás excepciones del motor siguen funcionando igual
(`requiere` no las reimplementa: las hereda).

Cambiar la matriz: editar `_ROLES_DE`, y el ADR-049 de `DECISIONS.md` (la tabla de allá es la misma). La suite
tiene una tabla propia, escrita a mano y independiente de este archivo (`tests/test_roles_matriz.py`): si se
afloja una capacidad acá, esa tabla se pone roja a propósito.
"""
import re
from collections.abc import Callable, Iterable

from fastapi import Depends, Request, Response
from libraauth.session_auth import SERVICE_USER, token_de_servicio_valido

from .auth import get_current_user, get_session_auth, require_role

# ── Roles ────────────────────────────────────────────────────────────────────

ADMIN = "admin"
ENCARGADO = "encargado"
VENDEDOR = "vendedor"
CAJERO = "cajero"
DEPOSITO = "deposito"
#: Heredado: los usuarios de antes de los roles. Sigue siendo válido, con los permisos de siempre.
STAFF = "staff"

#: El vocabulario de roles de la instancia: lo usan `UserRepository` y `build_users_router`. Un rol que no
#: esté acá es 422 en el alta y en la edición de usuarios.
ROLES: tuple[str, ...] = (ADMIN, ENCARGADO, VENDEDOR, CAJERO, DEPOSITO, STAFF)

# ── Capacidades y quién las tiene ────────────────────────────────────────────

_E, _V, _C, _D, _S = ENCARGADO, VENDEDOR, CAJERO, DEPOSITO, STAFF

#: capacidad -> los roles que NO son admin y la tienen (admin las tiene todas). Un frozenset vacío es
#: «sólo admin». Cada línea dice qué abre.
_ROLES_DE: dict[str, frozenset[str]] = {
    # ── Sólo admin ──
    # Alta, edición y baja de usuarios, y su contraseña. Además, el token de servicio del backoffice.
    "usuarios.admin": frozenset(),
    # Configuración: datos de empresa, logo, correo (SMTP), ARCA, MercadoPago, backup y resguardo, balanza y
    # ticket.
    "config": frozenset(),
    # El log de auditoría: quién vendió qué y desde qué IP.
    "logs": frozenset(),
    # Alta, edición y baja de sucursales y depósitos: cambia la estructura del local.
    "sucursales.admin": frozenset(),
    # ABM de cajas (dar de alta un mostrador es configurar el local).
    "caja.admin": frozenset(),
    # Reabrir un día ya cerrado: más sensible que cerrarlo (LibraCore v1.107.0).
    "cierre_diario.reabrir": frozenset(),
    # ── Catálogo y stock ──
    # Leer productos (con códigos y variantes), sucursales, depósitos, categorías y unidades.
    "catalogo.ver": frozenset({_E, _V, _C, _D, _S}),
    # Crear y editar las unidades y las categorías del catálogo (`/catalog/*`). Es configuración (decisión de
    # criterio de ADR-049: viven en esa pantalla y cambian el vocabulario de todo el local), así que el rol nuevo
    # que la tiene es sólo el admin. La tiene también `staff` **por herencia**: hasta los roles el router entero
    # era de staff y nadie lo acotó; es un permiso que sólo existe en la API (ninguna pantalla lo ofrecía a un
    # staff) y que se va cuando ese rol se migre.
    "catalogo.configurar": frozenset({_S}),
    # Alta, edición y baja de productos, códigos y variantes.
    "productos.escribir": frozenset({_E, _S}),
    # Consultar cuánto hay (stock, stock por depósito, historial de movimientos).
    "stock.ver": frozenset({_E, _V, _C, _D, _S}),
    # Ajustar el stock de un producto (merma, conteo).
    "stock.ajustar": frozenset({_E, _D, _S}),
    # Mover mercadería entre depósitos.
    "stock.transferir": frozenset({_E, _D, _S}),
    # Las pantallas de gestión de Productos, Stock y Proveedores (ADR-054). Son SOLO de la SPA: el cajero necesita LEER el catálogo
    # y el stock (el POS busca productos), pero su menú es el mostrador y nada más, así que la pantalla no se le ofrece ni se le
    # abre por URL. Lo que corta de verdad sigue siendo `catalogo.ver` / `stock.ver` / `compras.ver` en cada endpoint.
    "catalogo.pantalla": frozenset({_E, _V, _D, _S}),
    "stock.pantalla": frozenset({_E, _V, _D, _S}),
    # La pantalla de Proveedores: gestión de compras. El depósito lee las órdenes (`compras.ver`) pero no administra proveedores.
    "proveedores.pantalla": frozenset({_E, _S}),
    # ── Precios ──
    # Leer las listas de precio y el precio de una línea (el POS se lo pide a la lista predeterminada).
    "precios.consultar": frozenset({_E, _V, _C, _S}),
    # Escribir listas, quiebres, vigencias, promociones y la actualización masiva.
    "precios.escribir": frozenset({_E}),
    # La pantalla de etiquetas de góndola. Es SOLO de la SPA: no hay endpoint propio (lee productos y
    # listas, que ya gatean las capacidades de arriba). Existe aparte para poder separarla algún día.
    "etiquetas": frozenset({_E}),
    # ── Mostrador ──
    # POS: registrar y cobrar ventas, facturar, cobro por QR, tickets, ver el detalle de una venta y anular o
    # devolver (decisión del humano, 2026-09-15: el cajero también anula y devuelve).
    "ventas.pos": frozenset({_E, _V, _C, _S}),
    # El turno propio (abrir, ver, cerrar), elegir la caja, y el ticket del cierre del propio turno. El POS
    # exige turno abierto para vender: cualquiera que venda necesita esta capacidad.
    "caja.propia": frozenset({_E, _V, _C, _S}),
    # Ver y cerrar los turnos de OTROS usuarios.
    "turnos.todos": frozenset({_E}),
    # Cierre diario: vista previa, cierre, historial y tickets. NO incluye el ticket del propio turno.
    "cierre_diario": frozenset({_E, _S}),
    # ── Clientes y cuenta corriente ──
    "clientes.ver": frozenset({_E, _V, _C, _S}),
    # La pantalla de Clientes (SOLO de la SPA, ADR-054): el cajero lee y da de alta clientes desde el POS, no entra a la ficha.
    "clientes.pantalla": frozenset({_E, _V, _S}),
    # Alta de un cliente (y la consulta de CUIT en ARCA que la acompaña): el cajero da de alta en el mostrador.
    "clientes.alta": frozenset({_E, _V, _C, _S}),
    # Editar, activar/desactivar, alias de facturación y facturar solo (todo lo que no es el alta).
    "clientes.escribir": frozenset({_E, _V, _S}),
    # Asignarle a un cliente su lista de precio (`PUT /api/clientes/{id}/lista-precio`): es una decisión de
    # precio, así que no la tiene el vendedor; el staff heredado sí, como hasta ahora.
    "clientes.lista_precio": frozenset({_E, _S}),
    # Cuenta corriente y recibos: ver, cobrar y emitir.
    "cuenta_corriente": frozenset({_E, _V, _S}),
    # Dar de baja un pago de cuenta corriente y anular un recibo (plata que ya entró).
    "cobranzas.anular": frozenset({_E}),
    # ── Compras y proveedores ──
    "compras.ver": frozenset({_E, _D, _S}),
    # Órdenes de compra, y alta, edición y baja de proveedores.
    "compras.escribir": frozenset({_E, _S}),
    # Recepción de mercadería contra una compra (crear, cargar líneas, confirmar). NO la tiene el depósito (decisión del
    # humano, 2026-09-29): confirmar una recepción deja su `unit_cost` como nuevo costo del producto (`default_cost`), o sea
    # que quien recibe fija costos, y el depósito no ve ni maneja plata. Recibe el encargado; el depósito lee las órdenes y
    # recepciones (`compras.ver`) sin importes y maneja el stock.
    "compras.recibir": frozenset({_E, _S}),
    # ── Costos ──
    # Ver lo que cuesta la mercadería: el `precio_costo` de un producto (productos, stock, listas de precio) y el costo
    # y el subtotal de cada línea de las órdenes y recepciones de compra. Sin ella la API no manda esos campos
    # (`app/costos.py`, un filtro de RESPUESTA por prefijo de ruta). No abre ninguna ruta: sólo decide qué campos viajan.
    # El vendedor y el cajero no ven costos y el depósito no ve plata; el staff heredado los sigue viendo.
    "costos.ver": frozenset({_E, _S}),
    # ── Plata y reportes ──
    "egresos": frozenset({_E, _S}),
    "tesoreria": frozenset({_E}),
    "libros_iva": frozenset({_E}),
    "dashboard": frozenset({_E}),
    "reportes": frozenset({_E}),
    # Margen y rotación: costo y margen son de quien maneja el negocio, no del mostrador.
    "margen": frozenset({_E}),
    # Reposición sugerida: qué pedir y cuánto (ADR-051). Sólo lectura y sin costos. Admin, encargado y depósito (decisión del
    # humano, 2026-10-01, ADR-054: reponer es trabajo del depósito y la pantalla no muestra plata); NO el staff heredado (es una
    # pantalla nueva, no algo que ya tuviera).
    "reposicion.ver": frozenset({_E, _D}),
    # ── Vencimientos y lotes (ADR-052) ──
    # Ver qué lotes vencen, qué stock no tiene lote y los lotes de un producto (`/api/vencimientos`, sólo lectura, sin costos). Es de
    # quien maneja la mercadería: el encargado y el depósito. NO el staff heredado (pantalla nueva: una capacidad nueva no se abre por
    # herencia) ni el mostrador.
    "vencimientos.ver": frozenset({_E, _D}),
    # Marcar qué productos vencen (`PUT /api/vencimientos/productos/{id}` y la marca `vence` del alta y la edición de un producto,
    # `OpcionesCatalogo.autorizar_marcar_vence`): decide qué productos entran al control. Sólo el encargado.
    "vencimientos.marcar": frozenset({_E}),
    # Mover el ledger por lote: ponerle lote y vencimiento a stock que no lo tiene (`POST /asignar`), cargar stock nuevo con lote
    # (`POST /entrada`) y dar de baja un lote por merma (`POST /merma`, habilitada desde A-4: ADR-053). Como `stock.ajustar`, es de quien
    # maneja la mercadería: el encargado y el depósito; no lleva plata.
    "vencimientos.mover": frozenset({_E, _D}),
}

#: Capacidades que sólo mira la SPA: ningún endpoint las exige. `requiere()` no las usa y el test que revisa
#: que toda capacidad tenga una guarda las exceptúa por acá.
SOLO_SPA: frozenset[str] = frozenset({"etiquetas", "catalogo.pantalla", "clientes.pantalla", "stock.pantalla", "proveedores.pantalla"})

CAPACIDADES: tuple[str, ...] = tuple(_ROLES_DE)


def _validar_matriz() -> None:
    for capacidad, roles in _ROLES_DE.items():
        sobran = roles - set(ROLES)
        if sobran or ADMIN in roles:
            raise ValueError(
                f"la capacidad {capacidad!r} lista roles que no van: {sorted(sobran | (roles & {ADMIN}))}"
                " (admin es implícito; el resto tiene que estar en ROLES)"
            )


_validar_matriz()


def roles_con(capacidad: str) -> tuple[str, ...]:
    """Los roles que tienen la capacidad, `admin` incluido, en el orden de `ROLES`. `KeyError` si no existe."""
    extra = _ROLES_DE[capacidad]
    return tuple(r for r in ROLES if r == ADMIN or r in extra)


def capacidades_de(rol: str | None) -> list[str]:
    """Las capacidades de un rol, ordenadas. Un rol desconocido no tiene ninguna."""
    if rol == ADMIN:
        return sorted(CAPACIDADES)
    return sorted(c for c, roles in _ROLES_DE.items() if rol in roles)


def matriz_por_rol() -> dict[str, list[str]]:
    """`{rol: [capacidades]}` para todos los roles: la matriz tal como la ve la SPA (`/auth/me`).

    De acá sale `frontend/src/test/capacidades-por-rol.json`, que usan los tests del frontend para armar un
    usuario de cada rol sin repetir la matriz a mano (una tercera copia). Un test del backend
    (`tests/test_roles_matriz.py`) falla si ese archivo no coincide; se regenera con
    `python -m app.permisos > frontend/src/test/capacidades-por-rol.json`.
    """
    return {rol: capacidades_de(rol) for rol in ROLES}


# ── Guardas ──────────────────────────────────────────────────────────────────
#
# 🔴 Todas se construyen sobre `json_api_require_role` (libraauth), que es quien sabe de la excepción de lectura
# de la demo y del gate de Términos. Acá sólo se decide QUÉ roles pasan; cómo se rechaza no se reescribe.

Guarda = Callable[..., dict]

_LECTURA = frozenset({"GET", "HEAD"})

_usadas: set[str] = set()


def _guarda(capacidad: str) -> Guarda:
    _usadas.add(capacidad)
    return require_role(*roles_con(capacidad))


def capacidades_usadas() -> frozenset[str]:
    """Las capacidades con las que se armó alguna guarda (para el test de cobertura)."""
    return frozenset(_usadas)


def condicion(capacidad: str) -> Callable[[dict], bool]:
    """`usuario -> bool`: si el usuario tiene la capacidad. Para lo que no es un 403 sino una DECISIÓN dentro de un
    endpoint (por ejemplo, ver los turnos ajenos). Se arma al montar, como `requiere`: un typo es un `KeyError` al
    arrancar, y la capacidad queda contada como usada (`capacidades_usadas`)."""
    _usadas.add(capacidad)
    roles = roles_con(capacidad)
    return lambda usuario: (usuario or {}).get("role") in roles


def requiere(capacidad: str) -> Guarda:
    """La dependencia de FastAPI que deja pasar sólo a los roles con esa capacidad (403 al resto).

    Las capacidades se resuelven AL ARMAR la guarda, o sea al montar el router: un typo es un `KeyError` al
    arrancar y no un endpoint abierto. Para `Depends(requiere("reportes"))`.
    """
    return _guarda(capacidad)


def requiere_segun_metodo(*, lectura: str, escritura: str) -> Guarda:
    """`lectura` para GET/HEAD y `escritura` para cualquier otro método. Para los routers del motor que se
    montan enteros pero donde leer es de más gente que escribir (listas de precio, stock, productos...)."""
    return requiere_segun(lambda r: lectura if r.method in _LECTURA else escritura, (lectura, escritura))


def requiere_segun_ruta(*reglas: tuple[str, str, str], por_defecto: str) -> Guarda:
    """Elige la capacidad por método y ruta. Cada regla es `(método, patrón, capacidad)`: `método` es `GET`,
    `POST`... o `*`; `patrón` es una expresión regular que tiene que coincidir con TODO el path
    (`re.fullmatch`). Gana la primera que coincide; si ninguna, `por_defecto`.

    Es lo que hace falta cuando un router del motor mezcla rutas de gente distinta: el motor no deja poner una
    guarda por endpoint, sólo una por router (o los ganchos que él mismo ofrece).
    """
    compiladas = [(m, re.compile(p), c) for m, p, c in reglas]

    def elegir(request: Request) -> str:
        for metodo, patron, capacidad in compiladas:
            if metodo in ("*", request.method) and patron.fullmatch(request.url.path):
                return capacidad
        return por_defecto

    return requiere_segun(elegir, [c for _, _, c in compiladas] + [por_defecto])


def requiere_segun(elegir: Callable[[Request], str], posibles: Iterable[str]) -> Guarda:
    """Como `requiere`, con la capacidad decidida por pedido. `posibles` son todas las que `elegir` puede
    devolver: se arman de antemano, así una capacidad mal escrita falla al arrancar y no en el primer pedido."""
    guardas = {c: _guarda(c) for c in dict.fromkeys(posibles)}

    def _dependency(request: Request, user: dict = Depends(get_current_user)) -> dict:
        return guardas[elegir(request)](request, user)

    return _dependency


def requiere_o_servicio(capacidad: str) -> Guarda:
    """`requiere` o el token de servicio del backoffice de la suite (libraauth v0.7.0).

    Es lo que monta el router de usuarios y NADA más: el backoffice no tiene por qué tocar el resto del
    dominio. El token se chequea primero y a propósito, como en `json_api_require_admin_o_servicio`: una
    request del backoffice no trae cookie de sesión. Sin `LIBRA_SERVICE_TOKEN` en el entorno se comporta
    igual que `requiere`.
    """
    guardia = _guarda(capacidad)

    def _dependency(request: Request, response: Response = None) -> dict:
        if token_de_servicio_valido(request):
            return dict(SERVICE_USER)
        usuario = get_current_user(request, get_session_auth(request), response)
        return guardia(request, usuario)

    return _dependency



if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(matriz_por_rol(), indent=2, ensure_ascii=False))
