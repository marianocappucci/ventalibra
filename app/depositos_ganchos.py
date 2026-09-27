"""Las reglas de sucursales y depósitos de VentaLibra sobre los routers del motor.

Desde la fase 6 de la adopción de los motores (2026-09-26, ADR-033) VentaLibra monta
`libracommerce.web.catalogo_router.build_depositos_router` y `build_stock_router`, los mismos de Contalibra y
Restolibra, y declara acá lo que lo hace distinto (`libracommerce` v0.18.0). Son las reglas de «sólo `store` vende»
(2026-09-25) y del modelo de ubicaciones (2026-09-25/26), que ya no viven en routers propios (`/locations`, `/stock`):

- dos tipos, **`store` (sucursal) y `warehouse` (depósito)**, que se eligen al crear y **no se cambian**;
- toda instancia tiene **como mínimo una sucursal y un depósito activos**: no se desactiva ni se elimina el último
  de su tipo (409);
- **una sucursal con un turno de caja abierto no se desactiva** (409);
- **una sucursal no se elimina** (tiene cajas y ventas): se desactiva; un depósito se elimina si no tiene
  movimientos (guarda del motor);
- una sucursal que se da de alta **recibe su primera caja** (sin ella nadie puede abrir turno ahí y el alta de cajas
  es de admin);
- alta, edición, predeterminada y baja son **de admin**; la lectura y **la transferencia son de staff y admin**:
  quien mueve la mercadería entre locales es el encargado del mostrador, no el dueño (2026-09-21).

**Stock:** `OpcionesStock(por_deposito=True)`: el listado trae una columna por sucursal/depósito y el ajuste va a
uno de ellos.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from libracommerce.web.catalogo_router import (
    DepositoCreatePayload,
    DepositoUpdatePayload,
    OpcionesDepositos,
    OpcionesStock,
)

from .auth import require_admin
from .cajas_ganchos import Sucursales
from .services import cajas as cajas_service
from .services.locations import TIPO_QUE_VENDE, TIPOS_VALIDOS

OPCIONES_DE_STOCK = OpcionesStock(por_deposito=True)


def solo_lectura(request: Request) -> None:
    """Los productos del motor (`/api/productos`) se montan sólo para leer: se editan por `/catalog` hasta que la
    fase 7 adopte la pantalla del kit y retire esa API. Escribir por los dos caminos saltaría las reglas de este
    producto (unidades, variantes, códigos)."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        raise HTTPException(405, "Los productos se editan desde el catálogo (/catalog) hasta la fase 7.")


def opciones_de_depositos(sucursales: Sucursales) -> OpcionesDepositos:
    def _activos_de_tipo(tipo: str, sin: int) -> int:
        return sum(1 for loc in sucursales().list() if loc.location_type == tipo and loc.id != sin)

    def validar_alta(payload: DepositoCreatePayload) -> None:
        if payload.tipo is not None and payload.tipo not in TIPOS_VALIDOS:
            raise HTTPException(422, "El tipo tiene que ser «store» (sucursal) o «warehouse» (depósito).")

    def _sin_el_ultimo(actual: dict, accion: str) -> None:
        """Toda instancia declara como mínimo una sucursal y un depósito activos."""
        tipo = actual["tipo"]
        if tipo in TIPOS_VALIDOS and actual["activo"] and _activos_de_tipo(tipo, actual["id"]) == 0:
            ultimo = "la última sucursal" if tipo == TIPO_QUE_VENDE else "el último depósito"
            raise HTTPException(
                409,
                "La instancia necesita como mínimo una sucursal y un depósito activos: "
                f"no se puede {accion} {ultimo}.",
            )

    def validar_edicion(payload: DepositoUpdatePayload, actual: dict) -> None:
        if payload.activo or not actual["activo"]:
            return  # sólo la baja tiene guardas
        _sin_el_ultimo(actual, "desactivar")
        if actual["tipo"] == TIPO_QUE_VENDE and cajas_service.tiene_turno_abierto_en(actual["id"]):
            raise HTTPException(
                409,
                f"No se puede desactivar la sucursal {actual['nombre']!r}: tiene un turno de caja abierto.",
            )

    def validar_eliminacion(actual: dict) -> None:
        if actual["tipo"] == TIPO_QUE_VENDE:
            raise HTTPException(
                409, f"Una sucursal no se elimina ({actual['nombre']!r} tiene cajas y ventas): desactivala."
            )
        _sin_el_ultimo(actual, "eliminar")

    def al_guardar(deposito: dict) -> None:
        # Un depósito que pasa a vender (o una sucursal nueva) necesita su caja.
        if deposito["tipo"] == TIPO_QUE_VENDE and deposito["activo"]:
            cajas_service.asegurar_caja_de(deposito["id"])

    return OpcionesDepositos(
        autorizar_escritura=Depends(require_admin),
        validar_alta=validar_alta,
        validar_edicion=validar_edicion,
        validar_eliminacion=validar_eliminacion,
        al_guardar=al_guardar,
    )


__all__ = ["OPCIONES_DE_STOCK", "opciones_de_depositos", "solo_lectura"]
