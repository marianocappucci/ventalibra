"""Movimientos de stock manuales (ajustes y transferencias) sobre
SqliteCommerceRepository.

Los movimientos generados por una venta confirmada viven en
app/services/sales.py::confirm_sale -- este servicio es solo para el ajuste
manual que un admin puede necesitar (rotura, conteo fisico, etc) y para la
transferencia entre sucursales.

## La transferencia delega en el motor, y no se escribe a mano

`libracommerce.usecases.inventory.transfer_stock` hace las DOS escrituras y
la lectura que las autoriza **en la misma transaccion**: o quedan las dos o
no queda ninguna. Escribir dos ajustes sueltos —que es lo unico que se podia
hacer antes de esto— pierde mercaderia si el segundo falla, que es como lo
tenia Contalibra antes de adoptar el caso de uso.

**No hay estado "en transito" ni confirmacion del lado que recibe.** Entre
que la mercaderia sale fisicamente y que llega, el sistema ya la cuenta en
el destino. Si algun dia hace falta que alguien confirme la recepcion, este
no es el mecanismo: hay que agregar el tercer estado.
"""
from datetime import UTC, datetime, timezone
from decimal import Decimal

from libracommerce.domain.inventory import StockMovement, StockMovementType
from libracommerce.usecases.inventory import StockInsuficienteError, transfer_stock
from libracore.db.core import Conexion

from ..commerce import repositorio


class DepositoInexistente(ValueError):
    """El origen o el destino no existen -- el router lo traduce a 404."""


class TransferenciaInvalida(ValueError):
    """Cantidad <= 0, origen == destino, o stock insuficiente (422)."""


class StockService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def adjust(
        self, item_id: int, location_id: int, quantity_delta: Decimal, reason: str = "",
        *, variant_id: int | None = None,
    ) -> StockMovement:
        movement = StockMovement(
            id=None,
            item_id=item_id,
            variant_id=variant_id,
            location_id=location_id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity_delta=quantity_delta,
            occurred_at=datetime.now(UTC),
            source_type="manual_adjustment",
        )
        return self._repo.append_stock_movement(movement)

    def current_stock(self, item_id: int, location_id: int, *, variant_id: int | None = None) -> Decimal:
        return self._repo.current_stock(item_id, location_id, variant_id=variant_id)

    def movements(self, item_id: int, location_id: int, *, variant_id: int | None = None) -> list[StockMovement]:
        return list(self._repo.list_stock_movements(item_id, location_id, variant_id=variant_id))

    # ── Transferencia entre sucursales ───────────────────────────────────
    #
    # Un solo camino para "mover stock de A a B", sean dos sucursales o una
    # sucursal y un deposito. **No hay un endpoint aparte por tipo de
    # location** y es a proposito: el movimiento es el mismo y el destino ya
    # dice a donde va. Dos caminos obligarian a la pantalla a elegir cual
    # llamar mirando el `location_type`, que es exactamente lo que el servicio
    # hace mejor.

    def transferir(
        self, item_id: int, origen_id: int, destino_id: int, cantidad: Decimal,
        *, nota: str = "", usuario_id: int | None = None, variant_id: int | None = None,
    ) -> dict:
        """Mueve `cantidad` de `origen_id` a `destino_id`, en una transaccion.

        Levanta `DepositoInexistente` (404) si alguna punta no existe, y
        `TransferenciaInvalida` (422) si la cantidad no es positiva, si origen
        y destino son el mismo, o si no hay stock suficiente en el origen.

        Devuelve el par de movimientos ya escritos mas el stock que quedo de
        los dos lados —no un `{"ok": true}`—, para que la pantalla pueda
        pintar el resultado sin volver a preguntar y para que un test pueda
        afirmar donde quedo cada cosa.
        """
        origen = self._repo.get_location(origen_id)
        destino = self._repo.get_location(destino_id)
        if origen is None or destino is None:
            faltante = origen_id if origen is None else destino_id
            raise DepositoInexistente(f"No existe la sucursal o el depósito {faltante}.")
        if origen_id == destino_id:
            raise TransferenciaInvalida(
                "El origen y el destino son el mismo: la transferencia no movería nada."
            )
        if cantidad <= 0:
            raise TransferenciaInvalida(
                f"La cantidad a transferir tiene que ser positiva (recibido: {cantidad})."
            )
        try:
            salida, entrada = transfer_stock(
                self._repo,
                item_id=item_id,
                from_location_id=origen_id,
                to_location_id=destino_id,
                quantity=Decimal(cantidad),
                occurred_at=datetime.now(UTC),
                variant_id=variant_id,
                note=nota,
                created_by=usuario_id,
                # El vocabulario propio: la pantalla de actividad muestra el
                # `reason_code` tal cual, y sin esto los dos movimientos
                # aparecerian como `transfer_out`/`transfer_in` en ingles.
                reason_code_salida="transferencia_salida",
                reason_code_entrada="transferencia_entrada",
            )
        except StockInsuficienteError as e:
            raise TransferenciaInvalida(str(e)) from e
        return {
            "salida_id": salida.id,
            "entrada_id": entrada.id,
            "item_id": item_id,
            "variant_id": variant_id,
            "origen": {
                "id": origen_id,
                "nombre": origen.name,
                "stock": self._repo.current_stock(item_id, origen_id, variant_id=variant_id),
            },
            "destino": {
                "id": destino_id,
                "nombre": destino.name,
                "stock": self._repo.current_stock(item_id, destino_id, variant_id=variant_id),
            },
            "cantidad": Decimal(cantidad),
            "nota": nota,
        }

    def transferencias(self, *, location_id: int | None = None, limit: int = 200) -> list[dict]:
        """El historial, reconstruido desde el ledger: no hay tabla propia.

        Cada transferencia son DOS filas de `stock_movements` que el motor
        aparea: la entrada lleva `source_type="transfer"` y `source_id` = id de
        la salida. La salida no puede apuntar a la entrada porque se escribe
        primero y los movimientos son inmutables —que es justamente la
        propiedad que hace confiable a `current_stock`—, asi que el ancla es la
        salida y la entrada se busca por ahi.

        **Por que SQL crudo y no el repositorio.** El motor no tiene un listado
        por tipo de movimiento: `list_stock_movements` pide item Y location, y
        `list_stock_movements_by_source` pide el id de la salida, que es
        justamente lo que se esta buscando. Agregarselo al motor tocaria a sus
        seis consumidores para servir una pantalla de este producto. Se hace
        aca, como ya lo hace `LocationService.list()`.

        `location_id` trae las que tocan esa sucursal **de los dos lados** —lo
        que salio y lo que entro—, que es la pregunta que se le hace a esta
        pantalla: "¿que se movio de aca?" incluye lo que llego.

        > 📌 **Que un ajuste manual no aparezca aca lo garantizan DOS guardas
        > independientes**, y conviene saberlo antes de sacar una por
        > "redundante": el `movement_type = transfer_out` y el `JOIN` estricto
        > con la contraparte. Medido por mutacion el 2026-09-21: aflojando
        > **una sola** de las dos, `test_el_ajuste_manual_NO_aparece_como_
        > transferencia` sigue en VERDE —la otra lo tapa—; hay que voltear las
        > dos para que se ponga rojo. O sea que el test es real, pero no
        > custodia ninguna de las dos por separado.
        """
        where = ""
        params: list = [StockMovementType.TRANSFER_OUT.value]
        if location_id is not None:
            where = "AND (salida.location_id = ? OR entrada.location_id = ?)"
            params += [location_id, location_id]
        params.append(limit)
        filas = self._conn.execute(
            f"""
            SELECT salida.id, salida.item_id, salida.variant_id,
                   -salida.quantity_delta,
                   salida.location_id, entrada.location_id,
                   salida.occurred_at, salida.note, salida.created_by,
                   item.name
            FROM stock_movements AS salida
            JOIN stock_movements AS entrada
              ON entrada.source_type = 'transfer' AND entrada.source_id = salida.id
            LEFT JOIN catalog_items AS item ON item.id = salida.item_id
            WHERE salida.movement_type = ? {where}
            ORDER BY salida.occurred_at DESC, salida.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        nombres = {loc.id: loc.name for loc in self._repo.list_locations()}
        return [
            {
                "id": f[0],
                "item_id": f[1],
                "item": f[9] or f"#{f[1]}",
                "variant_id": f[2],
                "cantidad": Decimal(str(f[3])),
                "origen_id": f[4],
                "origen": nombres.get(f[4], f"#{f[4]}"),
                "destino_id": f[5],
                "destino": nombres.get(f[5], f"#{f[5]}"),
                "fecha": f[6],
                "nota": f[7] or "",
                "usuario_id": f[8],
            }
            for f in filas
        ]
