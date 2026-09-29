"""Compras (órdenes y recepciones) de VentaLibra sobre el router del motor.

Desde la fase 9 de la adopción de los motores (2026-09-27, ADR-036) VentaLibra monta
`libracommerce.web.compras_router.build_compras_router`, extraído del propio
`app/routers/purchasing.py` y `app/services/purchasing.py` de este producto (era el único que lo tenía
montado: `libracommerce` v0.21.0). Lo que hace distinto a VentaLibra son dos ganchos, no reglas de negocio:

- **la numeración**: `next_sequence(conn, "ventalibra_purchase_order")`, atómica dentro de la misma
  transacción (a diferencia del `MAX(id)+1` sin lock del motor, pensado para baja concurrencia);
- **el `proveedor_id`**: VentaLibra guarda los proveedores en su propia tabla (`libracore.db.egresos`,
  ADR-030) con un id que NO es el `party_id` que exige la FK de compras — la traducción, en los dos
  sentidos, ya vivía en `app/services/proveedores.py` (`party_de_proveedor`/`proveedor_de_party`,
  offset `+100.000`) y se reusa acá tal cual.

`autorizar_escritura` no se pasa: como en depósitos y productos, el `requiere_segun_ruta(...)` con el
que este producto monta el router entero ya cubre lectura y escritura por capacidad (`compras.ver`,
`compras.escribir` y `compras.recibir`, ADR-049).
"""
from __future__ import annotations

from fastapi import HTTPException
from libracommerce.web.compras_router import OpcionesCompras

from .db import next_sequence
from .services.proveedores import ProveedorNoExiste, party_de_proveedor, proveedor_de_party


def _numerador(conn) -> str:
    return f"OC-{next_sequence(conn, 'ventalibra_purchase_order'):06d}"


def _resolver_proveedor(conn, proveedor_id: int) -> int:
    try:
        return party_de_proveedor(conn, proveedor_id)
    except ProveedorNoExiste as exc:
        raise HTTPException(404, str(exc)) from exc


def _proveedor_de(_conn, party_id: int) -> int:
    return proveedor_de_party(party_id)


OPCIONES_DE_COMPRAS = OpcionesCompras(
    numerador=_numerador, resolver_proveedor=_resolver_proveedor, proveedor_de=_proveedor_de,
)

__all__ = ["OPCIONES_DE_COMPRAS"]
