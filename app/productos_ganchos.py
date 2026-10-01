"""Las reglas de catálogo de VentaLibra sobre el router de productos del motor.

Desde la fase 7 de la adopción de los motores (2026-09-27, ADR-034) VentaLibra monta
`libracommerce.web.catalogo_router.build_productos_router`, el mismo de Contalibra y Restolibra, y declara acá lo que
lo hace distinto (`libracommerce` v0.19.0). Son las reglas del catálogo que vivían en `app/routers/catalog.py` y
`app/services/catalog.py`:

- las **unidades** las administra la instalación (`/catalog/units`: código, nombre, si admite fracciones, escala
  decimal): un producto con una unidad que no existe es 422, no la crea al pasar;
- la **categoría** tiene que existir y estar activa (422); las categorías —jerárquicas, con baja— se administran en
  Configuración (`/catalog/categories`), no por el alta y la baja del motor;
- precio y costo **no negativos** (422);
- **producto o servicio se elige al crear** y no se cambia (409);
- la **unidad se bloquea** cuando el producto ya tiene movimientos —stock, ventas o compras— (409): cambiarla
  cambiaría el significado de todo lo ya registrado;
- un producto **no se elimina**, se desactiva (409): tiene o puede tener historial;
- la marca **«vence»** (vencimientos y lotes, ADR-052 y ADR-053): el listado y la ficha devuelven `vence` y el alta y la edición
  la aceptan (`libracommerce` v0.30.0). Marcarla o desmarcarla es de quien tiene `vencimientos.marcar` (el encargado y el admin:
  `autorizar_marcar_vence`), aunque la edición del producto sea de más gente (`productos.escribir`).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from libracommerce.web.catalogo_router import OpcionesCatalogo, ProductoPayload
from libracore.db.core import get_connection

from .permisos import condicion


def categorias_se_administran_en_configuracion() -> None:
    """Dependencia de `POST`/`DELETE /api/productos/categorias`: cierra esa vía. Las categorías tienen jerarquía y baja
    lógica y se administran por `/catalog/categories` (Configuración)."""
    raise HTTPException(405, "Las categorías se administran en Configuración.")


def tiene_movimientos(conn, producto_id: int) -> bool:
    """True si el producto ya aparece en stock, una venta o una compra. Las cuatro tablas graban `item_id` con la
    unidad puesta en el momento del movimiento; una orden de compra sin recepción también registró una cantidad en la
    unidad vieja."""
    fila = conn.execute(
        """
        SELECT
            EXISTS(SELECT 1 FROM stock_movements WHERE item_id = ?)
            OR EXISTS(SELECT 1 FROM sale_items WHERE item_id = ?)
            OR EXISTS(SELECT 1 FROM purchase_order_items WHERE item_id = ?)
            OR EXISTS(SELECT 1 FROM purchase_receipt_items WHERE item_id = ?)
        """,
        (producto_id, producto_id, producto_id, producto_id),
    ).fetchone()
    return bool(fila[0])


def validar_producto(payload: ProductoPayload, actual: dict | None) -> None:
    if payload.precio_venta < 0:
        raise HTTPException(422, "el precio de venta no puede ser negativo")
    if payload.precio_costo < 0:
        raise HTTPException(422, "el costo no puede ser negativo")
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM units WHERE code = ?", (payload.unidad,)).fetchone() is None:
            raise HTTPException(422, f"unidad desconocida: {payload.unidad!r}")
        categoria = payload.categoria.strip()
        if categoria and conn.execute(
            "SELECT 1 FROM categories WHERE name = ? AND active = 1", (categoria,)
        ).fetchone() is None:
            raise HTTPException(422, f"categoria desconocida: {categoria!r}")
        if actual is None:
            return
        if payload.tipo != actual["tipo"]:
            raise HTTPException(409, "El tipo (producto o servicio) se elige al crear y no se cambia.")
        if payload.unidad != actual["unidad"] and tiene_movimientos(conn, actual["id"]):
            raise HTTPException(409, "No se puede cambiar la unidad de un producto que ya tiene movimientos.")


def validar_eliminacion(actual: dict) -> None:
    raise HTTPException(409, f"Un producto no se elimina ({actual['nombre']!r} puede tener historial): desactivalo.")


OPCIONES_DE_CATALOGO = OpcionesCatalogo(
    unidades_de_la_base=True,
    autorizar_categorias=Depends(categorias_se_administran_en_configuracion),
    validar_producto=validar_producto,
    validar_eliminacion=validar_eliminacion,
    # Vencimientos y lotes (ADR-053): el producto trae y acepta `vence`. El gancho recibe el dict de la sesión (con `role`) y
    # decide SÓLO si la marca cambia: `condicion` mira la capacidad `vencimientos.marcar`, la misma del `PUT /api/vencimientos/
    # productos/{id}`, así que las dos vías de marcar (ésta y aquélla) no pueden discrepar.
    con_vencimientos=True,
    autorizar_marcar_vence=condicion("vencimientos.marcar"),
)
