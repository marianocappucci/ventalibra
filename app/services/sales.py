"""Lecturas de venta que `app/routers/sales.py` sigue exponiendo.

Desde F3 del plan post-P9 (2026-09-14, ver DECISIONS.md ADR-025) las
escrituras (borrador, confirmar, anular, devolver) viven en
`libracommerce.erp.ventas`, montado en `app/main.py` como `/api/ventas`.
`SaleService` queda reducido a lo que `app/routers/sales.py` mantiene de
sólo lectura: el listado de ventas recientes y el detalle de una, que
`GET /sales/{id}/ticket` también necesita.
"""
import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from libracommerce.domain.sales import Sale, SalePayment
from libracore.db.core import Conexion

from ..commerce import repositorio

#: America/Argentina/Buenos_Aires, UTC-3 fijo, sin horario de verano -- mismo
#: criterio que `libracore.db.core._ar_now()`.
_AR = timezone(timedelta(hours=-3))


class SaleNotFound(Exception):
    pass


class SaleService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def list_recent(self, *, limit: int = 50, search: str = "") -> list[dict]:
        """Las últimas ventas, para encontrar una y poder deshacerla.

        Devuelve el encabezado nada más (sin líneas ni pagos): es una lista
        para buscar, y traer todo de cada venta la haría lenta sin que nadie
        lo mire. El detalle se pide con `get()` al abrir una.
        """
        sql = """
            SELECT id, number, status, status_detail, total, confirmed_at, occurred_on,
                   customer_name_snapshot
            FROM sales
            WHERE status != 'draft'
        """
        params: list = []
        if search:
            sql += " AND (number LIKE ? OR customer_name_snapshot LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [
            {
                "id": row[0], "number": row[1], "status": row[2],
                "status_detail": row[3], "total": Decimal(str(row[4] or 0)),
                "confirmed_at": row[5], "occurred_on": row[6],
                "cliente": row[7] or "",
            }
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def get(self, sale_id: int) -> Sale:
        sale = self._repo.get_sale(sale_id)
        if sale is None:
            raise SaleNotFound(sale_id)
        return self._con_pagos_y_fecha(sale)

    def _con_pagos_y_fecha(self, sale: Sale) -> Sale:
        """Puentea la venta con lo que escribe la capa ERP de LibraCommerce
        (F3, ADR-025), que no vive en el `Sale` que arma el repositorio del
        motor:

        - **Pagos**: desde F3 `POST /api/ventas` los escribe en `ventas_pagos`
          (LibraCore), no en `sale_payments` (de donde los lee el repositorio
          -- por eso `sale.payments` da `()` para una venta nueva). La `0003`
          copió ahí los pagos de las ventas viejas también, así que leer sólo
          de `ventas_pagos` sirve para las dos sin bifurcar.
        - **Fecha**: `libracommerce.erp.ventas.crear_venta_directa` llena
          `occurred_on` (la fecha, sin hora) y nunca `confirmed_at` -- que
          queda en `None` para toda venta nueva. Con `confirmed_at` en `None`
          el ticket (`app/services/tickets.py`) se queda sin fecha, y
          `GET /sales/{id}` la devuelve `null`. Se reconstruye combinando esa
          fecha con la hora de `created_at`, y si `occurred_on` faltara
          también se cae a `created_at` entero. Una venta vieja que sí tiene
          `confirmed_at` no se toca.

          🔴 **Se etiqueta con `-03:00` de verdad (`_AR`), no `UTC`.**
          `created_at` es TEXT naive ya en hora de Argentina (medido en
          PostgreSQL: `datetime('now', '-3 hours')` vía el adaptador de
          `libracore.db._postgres`, que resta 3 horas al UTC del servidor
          ANTES de convertir a texto -- así que sus números son la hora
          local, no UTC), y ésa es la hora real en la que ocurrió la venta.
          Etiquetarla `UTC` (como se hizo primero) hacía que `GET /sales/
          {id}` devolviera un instante corrido 3 horas del real: el
          `confirmed_at` de una venta hecha a las 12:00 AR viajaba como
          `...T12:00:00+00:00`, y todo consumidor que sí convierte por zona
          -- `frontend/src/lib/fechas.ts`, que pasa cualquier valor con
          offset a hora de Argentina -- la mostraba a las 09:00 (o al día
          anterior, antes de las 03:00). Con `-03:00` el offset es el que
          corresponde y esos conversores hacen lo correcto. El ticket
          (`app/services/tickets.py`) hace su propia conversión a hora de
          Argentina antes de imprimir -- no depende de con qué zona venga
          etiquetado esto, siempre que sea un instante real.
        """
        pagos = self._conn.execute(
            "SELECT medio, monto, recibido, referencia FROM ventas_pagos "
            "WHERE venta_id = ? ORDER BY id",
            (sale.id,),
        ).fetchall()
        payments = tuple(
            SalePayment(
                method=medio, amount=Decimal(str(monto)),
                received_amount=Decimal(str(recibido)) if recibido is not None else None,
                reference=referencia or "",
            )
            for medio, monto, recibido, referencia in pagos
        )

        confirmed_at = sale.confirmed_at
        if confirmed_at is None:
            fila = self._conn.execute(
                "SELECT created_at FROM sales WHERE id = ?", (sale.id,),
            ).fetchone()
            creado = str(fila[0]) if fila and fila[0] else None
            if creado:
                if sale.occurred_on:
                    hora = creado[11:19] or "00:00:00"
                    confirmed_at = datetime.fromisoformat(
                        f"{sale.occurred_on} {hora}"
                    ).replace(tzinfo=_AR)
                else:
                    confirmed_at = datetime.fromisoformat(creado[:19]).replace(tzinfo=_AR)

        return dataclasses.replace(sale, payments=payments, confirmed_at=confirmed_at)
