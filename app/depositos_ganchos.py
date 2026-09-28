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
- alta, edición, predeterminada y baja son **de admin**; la lectura y **la transferencia son de staff y admin**:
  quien mueve la mercadería entre locales es el encargado del mostrador, no el dueño (2026-09-21).

**Stock:** `OpcionesStock(por_deposito=True)`: el listado trae una columna por depósito y el ajuste va a uno.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException
from libracommerce.web.catalogo_router import (
    DepositoCreatePayload,
    OpcionesDepositos,
    OpcionesStock,
    OpcionesSucursales,
    SucursalUpdatePayload,
)

from .auth import require_admin
from .services import cajas as cajas_service
from .services.sucursales import SucursalService

OPCIONES_DE_STOCK = OpcionesStock(por_deposito=True)

Sucursales = Callable[[], SucursalService]


def opciones_de_depositos() -> OpcionesDepositos:
    def validar_alta(payload: DepositoCreatePayload) -> None:
        if payload.branch_id is None:
            raise HTTPException(422, "Elegí la sucursal a la que pertenece el depósito.")

    return OpcionesDepositos(autorizar_escritura=Depends(require_admin), validar_alta=validar_alta)


def opciones_de_sucursales(sucursales: Sucursales) -> OpcionesSucursales:
    def validar_edicion(payload: SucursalUpdatePayload, actual: dict) -> None:
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
        autorizar_escritura=Depends(require_admin), validar_edicion=validar_edicion, al_guardar=al_guardar
    )


__all__ = ["OPCIONES_DE_STOCK", "opciones_de_depositos", "opciones_de_sucursales"]
