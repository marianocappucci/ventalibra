"""Reportes de ventas, caja y stock -- lectura pura sobre las tablas ya
existentes (sales/sale_items/stock_movements de LibraCommerce en esta
misma conexion, y libracore.db.caja para el resumen de caja, ya
configurado por app/services/billing.py::configure()).

No se agrega ninguna tabla ni estado propio -- son consultas de
agregacion sobre datos que ya se generan al confirmar ventas y
movimientos de stock.

🔴 **`sales_summary` agrupa por `occurred_on`, no por `confirmed_at`, desde
F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025).** Hasta acá
filtraba `confirmed_at` con una ventana convertida a UTC (el arreglo del
2026-08-24 contra el defecto del día-UTC). Pero `libracommerce.erp.ventas.
crear_venta` -- la capa nueva que registra la venta, montada en
`app/main.py` -- nunca escribe `confirmed_at`: sólo `occurred_on`, que ya
llega en la fecha LOCAL (el mismo dato que `fecha` en `VentaPayload`). Con
el filtro viejo, **toda venta nueva quedaba fuera de todos los reportes**,
sin ningún error -- exactamente el riesgo que el ADR-025 dejó anotado
("el reporte tiene que sobrevivir al pasaje"). `occurred_on` ya es la fecha
local sin conversión (y la migración `0003` la completó también para las
ventas viejas), así que el filtro se simplifica: ya no hace falta la ventana
UTC ni la conversión por fila.
"""
from datetime import date
from decimal import Decimal

from libracore.db import caja as db_caja
from libracore.db.core import Conexion


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))


class ReportsService:
    def __init__(self, conn: Conexion):
        self._conn = conn

    def sales_summary(self, date_from: date, date_to: date) -> dict:
        # `occurred_on` ya es la fecha LOCAL (`YYYY-MM-DD`, sin hora): a
        # diferencia de `confirmed_at` (UTC, y que la venta nueva ni
        # siquiera escribe), acá alcanza un `BETWEEN` inclusive, sin
        # ventana ni conversión por fila. Ver el docstring del módulo.
        desde, hasta = date_from.isoformat(), date_to.isoformat()
        totals = self._conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM sales
            WHERE status = 'confirmed' AND occurred_on BETWEEN ? AND ?
            """,
            (desde, hasta),
        ).fetchone()

        by_day_rows = self._conn.execute(
            """
            SELECT occurred_on, COUNT(*), COALESCE(SUM(total), 0)
            FROM sales
            WHERE status = 'confirmed' AND occurred_on BETWEEN ? AND ?
            GROUP BY occurred_on
            ORDER BY occurred_on
            """,
            (desde, hasta),
        ).fetchall()

        top_items_rows = self._conn.execute(
            """
            SELECT si.item_id, MAX(si.description_snapshot),
                   COALESCE(SUM(si.quantity), 0),
                   COALESCE(SUM(si.quantity * si.unit_price - si.discount_amount + si.tax_amount), 0)
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            WHERE s.status = 'confirmed' AND si.kind = 'product'
              AND s.occurred_on BETWEEN ? AND ?
            GROUP BY si.item_id
            ORDER BY 4 DESC
            LIMIT 10
            """,
            (desde, hasta),
        ).fetchall()

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "total_ventas": totals[0],
            "total_facturado": str(_to_decimal(totals[1])),
            "por_dia": [
                {"day": row[0], "cantidad": row[1], "total": str(_to_decimal(row[2]))}
                for row in by_day_rows
            ],
            "top_items": [
                {
                    "item_id": row[0], "descripcion": row[1],
                    "cantidad": str(_to_decimal(row[2])), "total": str(_to_decimal(row[3])),
                }
                for row in top_items_rows
            ],
        }

    def caja_summary(self, date_from: date, date_to: date) -> dict:
        resumen = db_caja.get_caja_resumen(date_from.isoformat(), date_to.isoformat())
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "ingresos": str(_to_decimal(resumen["ingresos"])),
            "egresos": str(_to_decimal(resumen["egresos"])),
            "saldo_periodo": str(_to_decimal(resumen["saldo_periodo"])),
            "saldo_total": str(_to_decimal(resumen["saldo_total"])),
        }

    def stock_summary(self, *, low_stock_threshold: Decimal = Decimal("0")) -> dict:
        rows = self._conn.execute(
            """
            SELECT ci.id, ci.name, ci.unit_code, COALESCE(SUM(sm.quantity_delta), 0) AS stock
            FROM catalog_items ci
            LEFT JOIN stock_movements sm ON sm.item_id = ci.id
            WHERE ci.active = 1 AND ci.item_type = 'product'
            GROUP BY ci.id
            ORDER BY ci.name
            """
        ).fetchall()
        items = [
            {
                "item_id": row[0], "name": row[1], "unit_code": row[2],
                "stock": str(_to_decimal(row[3])),
            }
            for row in rows
        ]
        low_stock = [item for item in items if _to_decimal(item["stock"]) <= low_stock_threshold]
        return {"items": items, "low_stock": low_stock}
