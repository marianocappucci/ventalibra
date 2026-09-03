"""Reportes de ventas, caja y stock -- lectura pura sobre las tablas ya
existentes (sales/sale_items/stock_movements de LibraCommerce en esta
misma conexion, y libracore.db.caja para el resumen de caja, ya
configurado por app/services/billing.py::configure()).

No se agrega ninguna tabla ni estado propio -- son consultas de
agregacion sobre datos que ya se generan al confirmar ventas y
movimientos de stock.
"""
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from libracore.db import caja as db_caja
from libracore.db.core import Conexion

#: Zona del negocio, en un solo lugar. Argentina es UTC-3 fijo, sin horario de
#: verano, así que el desfasaje es una constante y no hace falta una tabla de
#: husos para resolverlo.
_ZONA = timezone(timedelta(hours=-3))


def _ventana_utc(date_from: date, date_to: date) -> tuple[str, str]:
    """El rango de días **locales** traducido a una ventana de instantes UTC.

    🔴 **El defecto que esto arregla.** Acá se comparaba
    `substr(confirmed_at, 1, 10)` —la fecha **UTC**— contra un rango de fechas
    **locales**. Entre las 21:00 y las 24:00 de Argentina esos son dos días
    distintos: una venta confirmada a las 22:00 del 14 se guarda como
    `2026-03-15T01:00:00+00:00` y quedaba contada en el 15. O sea que **en la
    franja de cierre la venta no aparecía en el reporte del día**, que es justo
    cuando alguien lo mira.

    🔑 **Se convierte el rango, no la columna, y eso importa por dos razones.**
    La primera es que conserva la idea que `DECISIONS.md` eligió a propósito:
    `confirmed_at` es TEXT ISO y un ISO bien formado **compara y ordena
    lexicográficamente**, así que no hace falta que el motor parsee nada. Lo que
    había caducado no era esa idea sino el recorte a diez caracteres, que se
    queda con la fecha del meridiano de Greenwich.

    La segunda es que la suite corre contra **los dos motores** —SQLite en el
    primer paso del CI y PostgreSQL en el segundo—, y una conversión del lado
    del motor obligaría a escribirla dos veces. Del lado de Python se escribe
    una sola.

    Devuelve una ventana **semiabierta**: `[desde, hasta)`. El instante
    `03:00:00+00:00` es la medianoche local del día siguiente y pertenece al día
    siguiente, no a éste.
    """
    desde = datetime.combine(date_from, time.min, tzinfo=_ZONA)
    hasta = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=_ZONA)
    return (desde.astimezone(UTC).isoformat(),
            hasta.astimezone(UTC).isoformat())


def _dia_local(confirmado_en: str) -> str:
    """El día comercial de un `confirmed_at` guardado en UTC."""
    return datetime.fromisoformat(confirmado_en).astimezone(_ZONA).date().isoformat()


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))


class ReportsService:
    def __init__(self, conn: Conexion):
        self._conn = conn

    def sales_summary(self, date_from: date, date_to: date) -> dict:
        desde, hasta = _ventana_utc(date_from, date_to)
        # `confirmed_at` es TEXT ISO con offset, y un ISO bien formado compara y
        # ordena lexicograficamente -- por eso alcanza con acotarlo entre dos
        # instantes, sin pedirle al motor que parsee ninguna fecha. La ventana
        # es semiabierta: ver `_ventana_utc`.
        totals = self._conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM sales
            WHERE status = 'confirmed' AND confirmed_at >= ? AND confirmed_at < ?
            """,
            (desde, hasta),
        ).fetchone()

        # El agrupado por dia se arma en Python: el dia es el LOCAL, y pedirselo
        # al motor obligaria a escribir la conversion dos veces, una por motor.
        crudas = self._conn.execute(
            """
            SELECT confirmed_at, total
            FROM sales
            WHERE status = 'confirmed' AND confirmed_at >= ? AND confirmed_at < ?
            """,
            (desde, hasta),
        ).fetchall()
        por_dia: dict[str, list] = {}
        for confirmado_en, total in crudas:
            acumulado = por_dia.setdefault(_dia_local(confirmado_en), [0, Decimal("0")])
            acumulado[0] += 1
            acumulado[1] += _to_decimal(total)
        by_day_rows = [(dia, c, s) for dia, (c, s) in sorted(por_dia.items())]

        top_items_rows = self._conn.execute(
            """
            SELECT si.item_id, MAX(si.description_snapshot),
                   COALESCE(SUM(si.quantity), 0),
                   COALESCE(SUM(si.quantity * si.unit_price - si.discount_amount + si.tax_amount), 0)
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            WHERE s.status = 'confirmed' AND si.kind = 'product'
              AND s.confirmed_at >= ? AND s.confirmed_at < ?
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
