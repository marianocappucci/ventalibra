"""Las reglas de sucursales y depósitos de VentaLibra sobre los routers del motor.

Desde la fase 6 (2026-09-26, ADR-033) VentaLibra monta `build_depositos_router` y `build_stock_router` de
`libracommerce`, y desde la fase 1 de la jerarquía (2026-09-28) también `build_sucursales_router`: una sucursal
es una entidad propia (`branches`) y **el stock vive sólo en sus depósitos** (`locations.branch_id`). El motor
impone la mayor parte (ADR-012/013): toda sucursal tiene al menos un depósito y uno es el de venta, no se
desactiva ni se elimina el último depósito activo de una sucursal, y la baja de una sucursal exige que no queden
existencias en sus depósitos. Acá quedan las reglas de este producto:

- **todo depósito pertenece a una sucursal** (se elige al crearlo): un depósito suelto no tiene dónde venderse;
- **la última sucursal activa no se desactiva** (409): la instancia necesita al menos una;
- **una sucursal con un turno de caja abierto no se desactiva** (409);
- una sucursal que se da de alta **recibe su primera caja** (sin ella nadie puede abrir turno ahí y el alta de
  cajas es de admin);
- alta, edición, predeterminada y baja son **de admin** (capacidad `sucursales.admin`); la lectura es de todos los
  roles (`catalogo.ver`/`stock.ver`) y **la transferencia** de quien mueve mercadería (`stock.transferir`: encargado,
  depósito y el staff heredado): quien mueve la mercadería entre locales no es el dueño (2026-09-21, ADR-049);
- **un solo local sin el módulo `multisucursal`** (plan Básico, ADR-048): no se da de alta ni se reactiva una segunda
  sucursal activa, y no se transfiere mercadería entre depósitos de sucursales distintas (403, con el mismo texto
  que `require_module`). La unidad es la **sucursal** y no el depósito: un local con dos depósitos sigue siendo un
  local, así que transferir entre ellos es libre. El gate mira el módulo en cada request (`app.state.modules`, como
  `require_module`) y no toca lo que ya existe: una instalación con varias sucursales creadas antes sigue leyéndose,
  editándose y vendiendo igual; sólo se le impide crear más y cruzar mercadería.

**Stock:** `OpcionesStock(por_deposito=True)`: el listado trae una columna por depósito y el ajuste va a uno.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request
from libracommerce.erp import catalogo
from libracommerce.web.catalogo_router import (
    DepositoCreatePayload,
    OpcionesDepositos,
    OpcionesStock,
    OpcionesSucursales,
    SucursalCreatePayload,
    SucursalUpdatePayload,
)
from pydantic import TypeAdapter, ValidationError

from .permisos import requiere
from .services import cajas as cajas_service
from .services.sucursales import SucursalService

_ENTERO = TypeAdapter(int)  # mismo modo laxo que los campos `int` del cuerpo de la transferencia

#: `con_lotes` (ADR-053, libracommerce v0.30.0): el ajuste de stock acepta `lot_code` y `expires_at` para un producto marcado «vence»
#: («Cargar stock con lote», el conteo de un lote). Un producto sin marcar no cambia: sin lote es el ajuste de siempre.
OPCIONES_DE_STOCK = OpcionesStock(por_deposito=True, con_lotes=True)

Sucursales = Callable[[], SucursalService]
#: Quien dice qué módulos tiene la instancia (`ModuleRepository`): se pide en cada request, no al armar el router.
Modulos = Callable[[], Any]

MULTISUCURSAL = "multisucursal"

_MENSAJE_SUCURSAL = (
    "El plan Básico es de un solo local: para {accion} hace falta el plan Premium "
    "(modulo '" + MULTISUCURSAL + "' no incluido en el plan actual)."
)


def _exigir_multisucursal(modulos: Modulos, accion: str) -> None:
    if not modulos().is_enabled(MULTISUCURSAL):
        raise HTTPException(403, _MENSAJE_SUCURSAL.format(accion=accion))


def opciones_de_depositos() -> OpcionesDepositos:
    def validar_alta(payload: DepositoCreatePayload) -> None:
        if payload.branch_id is None:
            raise HTTPException(422, "Elegí la sucursal a la que pertenece el depósito.")

    return OpcionesDepositos(autorizar_escritura=Depends(requiere("sucursales.admin")), validar_alta=validar_alta)


def opciones_de_sucursales(sucursales: Sucursales, modulos: Modulos) -> OpcionesSucursales:
    def validar_alta(payload: SucursalCreatePayload) -> None:
        # Sin `multisucursal` la única sucursal activa que puede haber es la que ya existe (`list()` trae sólo las
        # activas, y el motor no deja quedarse sin ninguna). Las dadas de baja no cuentan como un local más.
        if sucursales().list():
            _exigir_multisucursal(modulos, "dar de alta otra sucursal")

    def validar_edicion(payload: SucursalUpdatePayload, actual: dict) -> None:
        if payload.activa and not actual["activa"]:
            # Reactivar una dada de baja es abrir otra sucursal: mismo tope que el alta.
            if [s for s in sucursales().list() if s.id != actual["id"]]:
                _exigir_multisucursal(modulos, "reactivar una sucursal mientras hay otra activa")
            return
        if payload.activa or not actual["activa"]:
            return  # sólo la baja tiene guardas
        if not [s for s in sucursales().list() if s.id != actual["id"]]:
            raise HTTPException(
                409, "La instancia necesita como mínimo una sucursal activa: no se puede desactivar la última."
            )
        if cajas_service.tiene_turno_abierto_en(actual["id"]):
            raise HTTPException(
                409,
                f"No se puede desactivar la sucursal {actual['nombre']!r}: tiene un turno de caja abierto.",
            )

    def al_guardar(sucursal: dict) -> None:
        # Una sucursal nueva (o reactivada) necesita su caja.
        if sucursal["activa"]:
            cajas_service.asegurar_caja_de(sucursal["id"])

    return OpcionesSucursales(
        autorizar_escritura=Depends(requiere("sucursales.admin")), validar_alta=validar_alta, validar_edicion=validar_edicion,
        al_guardar=al_guardar,
    )


def gate_de_transferencias(conexion: Callable[[], Any], modulos: Modulos):
    """La dependencia que cierra `POST /api/depositos/transferir` entre sucursales sin el módulo `multisucursal`.

    🔴 **Es una dependencia del router y no un gancho porque el motor no tiene ninguno para la transferencia**
    (`OpcionesDepositos` sólo cubre alta, edición, baja y guardado; ver `libracommerce/web/catalogo_router.py`).
    Se monta sobre TODO el router de depósitos y actúa sólo sobre esa ruta: cualquier otra pasa sin tocar nada, ni el
    cuerpo. Si el motor un día suma un gancho propio, esto se muda a él y este test (`test_planes_y_sucursales.py`)
    dice si la ruta se movió: reconoce la ruta por su forma (`POST …/transferir`), y si dejara de reconocerla el
    caso «Básico rechaza la transferencia entre sucursales» se pone en rojo.

    Sin el módulo, deja pasar la transferencia entre depósitos de la MISMA sucursal y rechaza (403) la que cruza de
    sucursal. Lo que no puede resolver (cuerpo ilegible, un id que no existe, campos que faltan) lo deja pasar: lo
    contesta el propio endpoint con su 422 de siempre.
    """

    async def _cuerpo(request: Request) -> dict | None:
        ruta = request.scope.get("route")
        if request.method != "POST" or not str(getattr(ruta, "path", "")).endswith("/transferir"):
            return None
        try:
            cuerpo = await request.json()  # la lectura queda cacheada en `request`: el endpoint la vuelve a leer
        except ValueError:
            return None
        return cuerpo if isinstance(cuerpo, dict) else None

    def _sucursal_de(conn, deposito_id: Any) -> tuple[bool, int | None]:
        """`(existe, sucursal_id)` del depósito, o `(False, None)` si el id no es un entero utilizable."""
        # 🔴 Se coacciona con el MISMO criterio que `TransferenciaPayload.origen_id: int` (pydantic, modo laxo): el
        # endpoint acepta `"3"`, `3.0` o `true` como ids; si acá sólo valiera el `int` estricto, mandar el id como
        # texto salteaba el gate y cruzaba de sucursal sin el módulo (hallazgo de Codex, 2026-09-29).
        try:
            deposito_id = _ENTERO.validate_python(deposito_id)
        except ValidationError:
            return False, None
        deposito = catalogo.get_deposito(conn, deposito_id)
        return (deposito is not None), (deposito or {}).get("branch_id")

    def dependencia(cuerpo: dict | None = Depends(_cuerpo)) -> None:
        if cuerpo is None or modulos().is_enabled(MULTISUCURSAL):
            return
        with conexion() as conn:
            existe_origen, sucursal_origen = _sucursal_de(conn, cuerpo.get("origen_id"))
            existe_destino, sucursal_destino = _sucursal_de(conn, cuerpo.get("destino_id"))
        if existe_origen and existe_destino and sucursal_origen != sucursal_destino:
            raise HTTPException(403, _MENSAJE_SUCURSAL.format(accion="transferir mercadería entre sucursales"))

    return dependencia


__all__ = ["OPCIONES_DE_STOCK", "gate_de_transferencias", "opciones_de_depositos", "opciones_de_sucursales"]
