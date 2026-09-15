"""VentaLibra pasa sus ventas a la capa ERP de LibraCommerce (F3 del plan
post-P9, ver DECISIONS.md ADR-025 y wiki/analyses/plan-ventalibra-a-libracommerce.md).

Sólo PostgreSQL: el modo SQLite se retiró para toda la familia el 2026-08-12
(ver `services/billing.py::configure`) y esta revisión no se ejercita contra
otro motor -- a diferencia de la `0002`, que sí necesitaba las dos formas
porque en ese momento SQLite todavía corría en la suite.

`op.get_bind()` da la conexión SQLAlchemy de Alembic, y el DDL de la familia
(`crear_venta_links`, `repuntar_fk_ventas_pagos`) espera una conexión DB-API
con placeholders `?` -- la misma que usa `libracore.db` en todos lados. El
puente es `libracore.db.migraciones.conexion_libracore`, el mismo que usa la
baseline `0001` de Contalibra/Restolibra para llamar a `init_schema_propio()`.

## Qué toca

1. **`venta_links`** (`libracommerce.erp.schema.crear_venta_links`): la tabla
   que ata una venta con su turno de caja y su factura. No existía en este
   producto -- Contalibra/Restolibra la crean desde P9-M5.
2. **La FK de `ventas_pagos`**, repuntada de `ventas(id)` (la tabla legada de
   LibraCore, que este producto nunca usó) a `sales(id)` (LibraCommerce, donde
   viven las ventas de acá) -- `libracommerce.erp.ventas.repuntar_fk_ventas_pagos`.
3. **Copia `sale_payments` → `ventas_pagos`** (`estado='aprobado'`, `recibido`
   = `received_amount`): la capa ERP lee los pagos de ahí, no de
   `sale_payments`.
4. **`venta_links.turno_id`/`factura_id`**, reconstruidos desde
   `caja_movimientos` -- el camino viejo (`app/routers/sales.py`, ya
   retirado) los dejaba ahí con la referencia `sale-<id>` o `sale-<id>-<medio>`
   (`services/billing.py::record_sale_payment`), nunca en una columna de la
   venta.
5. **`sales.occurred_on`**, completado con la fecha LOCAL (Argentina) de
   `confirmed_at` donde está NULL -- las ventas viejas sólo llenaban
   `confirmed_at` (en UTC); sin esto, `erp.reportes` (que agrupa por
   `occurred_on`) las deja afuera de todos los reportes.
6. **Borradores abandonados** (`status='draft'` hace más de un día) pasan a
   `cancelled`/`status_detail='borrador_descartado'` -- decisión del humano
   del 2026-09-14 (ADR-025): no tienen stock descontado ni plata cobrada, y
   con el modelo nuevo aparecerían como ventas pendientes de pago, que no son.
7. **El doble conteo de cuenta corriente**: `cc_debitos` explícito
   (`services/cuenta_corriente.py::registrar_venta_fiada`, ADR-020) y el pago
   `ventas_pagos.medio='cuenta_corriente'` que ahora copia el paso 3 son, para
   la MISMA venta, la MISMA deuda contada dos veces. Se identifica el débito
   por su `referencia` (`sale-<id>` o `sale-<id>-cuenta_corriente`) y, si esa
   venta tiene un `sale_payments` de medio `cuenta_corriente`, se borra el
   débito directo: queda sólo el pago migrado. Una venta fiada SIN ese pago
   (el caso de dev: `medio_pago` como string suelto, sin `pagos[]`) no generó
   nunca una fila en `sale_payments` -- ese débito directo queda como estaba,
   que es lo que `get_cc_saldo` ya suma hoy.

Todo lo anterior se registra en `_migracion_0003` (`datos` como JSON en
TEXT -- no JSONB: así el mismo `?`/`ConnectionWrapper` de siempre alcanza,
sin operadores de Postgres que otro motor no tendría), con lo necesario para
que `downgrade()` lo deshaga exactamente -- no una reconstrucción aproximada.

## Invariantes que tienen que dar igual antes y después

Ventas por estado y suma de totales; pagos por medio (`sale_payments` +
`ventas_pagos`); `SUM(quantity_delta)` de `stock_movements` por ítem y
depósito; `caja_movimientos` (no se toca); y el saldo de cuenta corriente
de cada cliente -- éste último calculado a mano en el test con la MISMA
lógica que va a usar `VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF` (libracore
v1.100.0, todavía no existe): no se inventa el origen acá, sólo se mide el
resultado que va a dar. Ver `tests/test_migracion_0003.py`.

## Idempotencia

Cada paso se guarda contra volver a correrse: `crear_venta_links`/
`repuntar_fk_ventas_pagos` ya son idempotentes por sí mismos; los pasos 3-8
consultan `_migracion_0003` antes de repetir un `INSERT`/`UPDATE`/`DELETE`
que ya hicieron. Hace falta porque, a diferencia de Alembic (que no vuelve a
aplicar una revisión ya registrada en `alembic_version_ventalibra`), un
operador puede invocar `upgrade()` a mano para recuperar un estado a medio
migrar -- ver el incidente real de LibraDesk documentado en el wiki.

🔴 **El paso 4 (`venta_link_turno_factura`) fue el único sin esta guarda hasta
el 2026-09-15** -- se detectó en revisión: sin ella, una segunda corrida
registraba OTRA fila por la misma venta, con el "antes" ya migrado (los
valores que el paso 4 acababa de escribir, no los originales), y
`_migracion_0003` dejaba de ser una bitácora confiable de qué había antes de
`upgrade()`. `downgrade()` daba bien igual, pero por el orden `DESC` --
deshacía primero la fila más nueva (que no cambiaba nada real, porque
"antes" y "después" coincidían) y después la original -- no porque la
bitácora fuera correcta. Se corrigió con `_ya_migrado(conn, "venta_link_
turno_factura", "sale_id", sale_id)`, igual que el resto de los pasos.

## `downgrade()` es un rollback INMEDIATO, no un "volver atrás" general

Sirve para deshacer una corrida de `upgrade()` recién hecha -- el caso real
es un deploy que falla la verificación posterior y se revierte en el acto.
**No sirve para volver a como estaba después de días de uso con el modelo
nuevo.** Desde que `upgrade()` corre, fiar ya no escribe `cc_debitos`: la
deuda vive en el pago `ventas_pagos.medio='cuenta_corriente'` de la venta
(ver ADR-025, D3). Una venta fiada NUEVA -- hecha con la capa ERP después de
migrar, no una de las que esta revisión encontró y reclasificó -- no tiene
ningún `cc_debito` que `downgrade()` pueda restaurar, porque nunca escribió
uno: `_migracion_0003` no tiene nada registrado para ella. Bajar la revisión
con esas ventas encima dejaría al código VIEJO (que sólo sabe leer
`cc_debitos`) sin ver esa deuda -- no es que `downgrade()` la borre, es que
nunca fue suya. El rollback es seguro sólo mientras no haya fiados nuevos
después del `upgrade()` que se quiere deshacer.

## El repunte de la FK (paso 2) puede commitear sin que quede registrado

`repuntar_fk_ventas_pagos` hace su propio `conn.commit()` en la rama de
PostgreSQL (necesario: el `DROP`/`ADD CONSTRAINT` no puede convivir sin
confirmar en el medio contra algunos catálogos) **antes** de devolver si tocó
algo, y `_registrar(conn, "fk_ventas_pagos_repuntada", ...)` corre recién
después, todavía sin confirmar (es parte de la transacción que Alembic cree
que sigue abierta). Si el proceso muere entre esas dos líneas -- o más
adelante, en cualquiera de los pasos 3-8, que hace que la transacción entera
se revierta -- la FK queda repuntada a `sales(id)` DE VERDAD (ya confirmada
por el commit propio de la función) pero sin ninguna fila en
`_migracion_0003` que lo diga: un `downgrade()` posterior no sabría que tiene
que devolverla a `ventas(id)`.

No se resuelve moviendo el `_registrar` antes del llamado: `repuntar_fk_
ventas_pagos` es quien decide si hay algo que tocar (devuelve `False` si la
FK ya apunta a `sales`), y registrar sin esa respuesta duplicaría la fila en
los casos donde la función es un no-op -- el más común en esta suite, donde
`services/billing.py::configure()` ya la repunta en cada arranque **antes**
de que esta revisión corra, así que acá casi siempre no hace nada (ver
`tests/test_migracion_0003.py`, que por eso mismo no ejercita el `downgrade`
de esta acción). Registrar igual rompería esa distinción y el `downgrade`
empezaría a revertir una FK de la que esta migración nunca fue responsable.

Queda documentado, no parcheado: la ventana real es de milisegundos (dos
sentencias seguidas), en una migración que se corre una vez por deploy con
backup previo -- que la sondee y quede sin registrar exige morir en ese
instante exacto. Si algún día hace falta cerrarlo de verdad, la forma
correcta es que `repuntar_fk_ventas_pagos` reciba un callback para registrar
ANTES de su propio commit (cambio en `libracommerce`, no acá).
"""
import json
import re
from datetime import UTC, datetime, timedelta, timezone

from alembic import op
from libracore.db.migraciones import conexion_libracore

revision = "0003_capa_erp"
down_revision = "0002_created_at_hora_ar"
branch_labels = None
depends_on = None

#: America/Argentina/Buenos_Aires, UTC-3 fijo, sin horario de verano -- mismo
#: criterio que `libracore.db.core._ar_now()`.
_AR = timezone(timedelta(hours=-3))

#: `services/cuenta_corriente.py::registrar_venta_fiada` arma la referencia
#: con el id de la venta, con o sin el sufijo del medio según el camino de
#: confirmación (`pagos[]` vs. `medio_pago` suelto -- ver `app/routers/sales.py`
#: histórico, git blame de esta revisión). Las dos formas empiezan igual.
_REF_VENTA = re.compile(r"^sale-(\d+)(?:-.+)?$")


def _sale_id_de_referencia(referencia: str | None) -> int | None:
    if not referencia:
        return None
    m = _REF_VENTA.match(referencia)
    return int(m.group(1)) if m else None


def _fecha_local(confirmed_at: str) -> str:
    """La fecha (sin hora) en horario de Argentina de un `confirmed_at` en
    UTC (`datetime.now(UTC).isoformat()`, ver `libracommerce.db.repository`)."""
    dt = datetime.fromisoformat(confirmed_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_AR).strftime("%Y-%m-%d")


def _crear_bookkeeping(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migracion_0003 (
            id SERIAL PRIMARY KEY,
            accion TEXT NOT NULL,
            referencia_id INTEGER NOT NULL,
            datos TEXT NOT NULL DEFAULT '{}',
            creado_en TIMESTAMP NOT NULL DEFAULT now()
        )
    """)


def _registrar(conn, accion: str, referencia_id: int, datos: dict) -> None:
    conn.execute(
        "INSERT INTO _migracion_0003 (accion, referencia_id, datos) VALUES (?, ?, ?)",
        (accion, referencia_id, json.dumps(datos)),
    )


def _ya_migrado(conn, accion: str, clave: str, valor) -> bool:
    """Guarda de idempotencia: si ya existe un registro de esta acción con
    este dato, no se repite el trabajo. Compara en Python (no con un operador
    JSON de Postgres) para no depender de un motor puntual -- son pocas filas
    por instancia real."""
    valor = str(valor)
    filas = conn.execute(
        "SELECT datos FROM _migracion_0003 WHERE accion = ?", (accion,),
    ).fetchall()
    for fila in filas:
        datos = json.loads(fila[0])
        if str(datos.get(clave)) == valor:
            return True
    return False


def upgrade() -> None:
    conn = conexion_libracore(op.get_bind())
    _crear_bookkeeping(conn)

    # 1-2. venta_links + la FK de ventas_pagos, del motor (P9-M5). Las dos
    # funciones son idempotentes por sí mismas; acá sólo se registra si ESTA
    # corrida fue la que hizo algo, para que el downgrade sepa si revertir.
    from libracommerce.erp.schema import crear_venta_links
    from libracommerce.erp.ventas import repuntar_fk_ventas_pagos

    tabla_existia = conn.execute(
        "SELECT to_regclass('venta_links') IS NOT NULL"
    ).fetchone()[0]
    crear_venta_links(conn)
    if not tabla_existia and not _ya_migrado(conn, "venta_links_tabla_creada", "listo", "si"):
        _registrar(conn, "venta_links_tabla_creada", 0, {"listo": "si"})

    fk_repuntada = repuntar_fk_ventas_pagos(conn)
    if fk_repuntada and not _ya_migrado(conn, "fk_ventas_pagos_repuntada", "listo", "si"):
        _registrar(conn, "fk_ventas_pagos_repuntada", 0, {"listo": "si"})

    # 3. sale_payments -> ventas_pagos.
    pagos = conn.execute(
        "SELECT id, sale_id, method, amount, reference, received_amount "
        "FROM sale_payments ORDER BY id"
    ).fetchall()
    for p in pagos:
        pago_id, venta_id, medio, monto, referencia, recibido = p
        if _ya_migrado(conn, "ventas_pago_creado", "sale_payment_id", pago_id):
            continue
        cur = conn.execute(
            "INSERT INTO ventas_pagos (venta_id, medio, monto, referencia, estado, recibido) "
            "VALUES (?, ?, ?, ?, 'aprobado', ?)",
            (venta_id, medio, float(monto), referencia or "",
             float(recibido) if recibido is not None else None),
        )
        _registrar(conn, "ventas_pago_creado", cur.lastrowid, {"sale_payment_id": pago_id})

    # 4. venta_links.turno_id / factura_id, desde caja_movimientos.
    ventas = conn.execute("SELECT id FROM sales WHERE status != 'draft'").fetchall()
    for (sale_id,) in ventas:
        # 🔴 Único paso de los 3-7 que le faltaba la guarda: sin esto, una
        # segunda corrida de `upgrade()` (recuperando un estado a medio
        # migrar, ver "Idempotencia" arriba) volvía a escribir el mismo
        # `venta_link_turno_factura` con el "antes" ya migrado -- la
        # bitácora quedaba con dos filas por venta y `downgrade()` sólo daba
        # bien por el orden `DESC` (deshace la segunda, que no cambió nada
        # real, antes que la primera), de casualidad y no por diseño.
        if _ya_migrado(conn, "venta_link_turno_factura", "sale_id", sale_id):
            continue
        fila = conn.execute(
            "SELECT turno_id, factura_id FROM caja_movimientos "
            "WHERE (referencia = ? OR referencia LIKE ?) AND tipo = 'ingreso' "
            "ORDER BY id LIMIT 1",
            (f"sale-{sale_id}", f"sale-{sale_id}-%"),
        ).fetchone()
        if fila is None:
            continue
        turno_id, factura_id = fila
        if turno_id is None and factura_id is None:
            continue
        antes = conn.execute(
            "SELECT turno_id, factura_id FROM venta_links WHERE venta_id = ?", (sale_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO venta_links (venta_id, turno_id, factura_id) VALUES (?, ?, ?) "
            "ON CONFLICT (venta_id) DO UPDATE "
            "SET turno_id = EXCLUDED.turno_id, factura_id = EXCLUDED.factura_id",
            (sale_id, turno_id, factura_id),
        )
        _registrar(conn, "venta_link_turno_factura", sale_id, {
            "sale_id": sale_id,
            "turno_id_antes": antes[0] if antes else None,
            "factura_id_antes": antes[1] if antes else None,
            "existia_antes": antes is not None,
        })

    # 5. occurred_on = fecha local de confirmed_at, donde falta.
    sin_fecha = conn.execute(
        "SELECT id, confirmed_at FROM sales WHERE occurred_on IS NULL AND confirmed_at IS NOT NULL"
    ).fetchall()
    for sale_id, confirmed_at in sin_fecha:
        conn.execute(
            "UPDATE sales SET occurred_on = ? WHERE id = ?",
            (_fecha_local(confirmed_at), sale_id),
        )
        _registrar(conn, "occurred_on_completado", sale_id, {})

    # 6. Borradores abandonados (más de un día) -> cancelados.
    limite = (datetime.now(_AR) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    borradores = conn.execute(
        "SELECT id, status, status_detail FROM sales WHERE status = 'draft' AND created_at < ?",
        (limite,),
    ).fetchall()
    for sale_id, status, status_detail in borradores:
        conn.execute(
            "UPDATE sales SET status = 'cancelled', status_detail = 'borrador_descartado' WHERE id = ?",
            (sale_id,),
        )
        _registrar(conn, "borrador_cancelado", sale_id, {
            "status_antes": status, "status_detail_antes": status_detail,
        })

    # 7. Doble conteo de cuenta corriente.
    debitos = conn.execute(
        "SELECT id, cliente_id, monto, fecha, concepto, referencia, usuario_id FROM cc_debitos"
    ).fetchall()
    for debito_id, cliente_id, monto, fecha, concepto, referencia, usuario_id in debitos:
        sale_id = _sale_id_de_referencia(referencia)
        if sale_id is None:
            continue
        tiene_pago_cc = conn.execute(
            "SELECT 1 FROM sale_payments WHERE sale_id = ? AND method = 'cuenta_corriente' LIMIT 1",
            (sale_id,),
        ).fetchone()
        if tiene_pago_cc is None:
            continue
        conn.execute("DELETE FROM cc_debitos WHERE id = ?", (debito_id,))
        _registrar(conn, "cc_debito_eliminado_por_duplicado", debito_id, {
            "cliente_id": cliente_id, "monto": float(monto), "fecha": fecha,
            "concepto": concepto, "referencia": referencia, "usuario_id": usuario_id,
        })

    # 8. Backfill: cada party con rol "customer" que todavía no tiene su fila
    #    `clients` enlazada por `external_ref = 'party-<id>'`. Desde esta misma
    #    fase, `app/services/customers.py::CustomerService.create` la crea al
    #    dar de alta -- este paso es sólo para los que se dieron de alta ANTES
    #    de ese cambio (el caso real de `ventalibra-dev`/`demo`, con clientes ya
    #    cargados). Mismo criterio de traducción que `resolver_cliente_externo`/
    #    `app/ganchos.py::cliente_cc_de`, no se duplica la lógica de negocio,
    #    sólo el `INSERT` -- llamar a esa función abriría una conexión aparte
    #    (ver su docstring) fuera de la transacción de esta migración.
    #
    #    Sin esto, un cliente que ya fiaba antes de F3 (con su deuda migrada en
    #    el paso 3, arriba) seguiría sin aparecer en `GET /accounts` hasta que
    #    alguien pidiera SU cuenta puntual -- el mismo agujero que el paso (a)
    #    del arreglo tapa para clientes nuevos.
    parties_clientes = conn.execute(
        "SELECT p.id, p.display_name, p.tax_id, p.email, p.phone "
        "FROM parties p JOIN party_roles pr ON pr.party_id = p.id AND pr.role = 'customer'"
    ).fetchall()
    for party_id, display_name, tax_id, email, phone in parties_clientes:
        external_ref = f"party-{party_id}"
        if conn.execute(
            "SELECT 1 FROM clients WHERE external_ref = ?", (external_ref,)
        ).fetchone() is not None:
            continue
        if _ya_migrado(conn, "cliente_backfill_creado", "party_id", party_id):
            continue
        cur = conn.execute(
            "INSERT INTO clients (name, cuit_dni, email, phone, external_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            (display_name, tax_id or "", email or "", phone or "", external_ref),
        )
        _registrar(conn, "cliente_backfill_creado", cur.lastrowid, {"party_id": party_id})

    # 🔴 `repuntar_fk_ventas_pagos` (pasos 1-2) hace su PROPIO `conn.commit()`
    # en la rama de PostgreSQL -- necesario ahí porque el `ALTER TABLE` que
    # saca la constraint vieja y el que pone la nueva no pueden convivir sin
    # confirmar en el medio contra algunos catálogos. Eso pasa por el DBAPI
    # crudo, por debajo de la transacción que Alembic cree que sigue
    # abierta: sin este `commit()` explícito acá, los pasos 3-7 quedan en una
    # transacción que la conexión de SQLAlchemy nunca ve confirmada de
    # verdad. Medido con el escenario de `tests/test_migracion_0003.py`.
    conn.commit()


def downgrade() -> None:
    conn = conexion_libracore(op.get_bind())
    existe = conn.execute("SELECT to_regclass('_migracion_0003') IS NOT NULL").fetchone()[0]
    if not existe:
        return  # upgrade() nunca corrió sobre esta base: nada que deshacer.

    registros = conn.execute(
        "SELECT id, accion, referencia_id, datos FROM _migracion_0003 ORDER BY id DESC"
    ).fetchall()

    for _id, accion, referencia_id, datos_raw in registros:
        datos = json.loads(datos_raw)
        if accion == "cliente_backfill_creado":
            # Sólo si nadie le cargó movimientos DESPUÉS del upgrade -- un
            # cobro real contra este cliente no se descarta porque la fila que
            # lo hace posible haya nacido de un backfill. `cliente_id` acá es
            # `referencia_id`: lo que se guardó fue el id de la fila creada.
            tiene_movimientos = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM cc_debitos WHERE cliente_id = ?) "
                "OR EXISTS(SELECT 1 FROM cc_pagos WHERE cliente_id = ?)",
                (referencia_id, referencia_id),
            ).fetchone()[0]
            if tiene_movimientos:
                print(
                    f"[0003 downgrade] cliente {referencia_id} (backfill de "
                    f"party-{datos['party_id']}) tiene movimientos de cuenta "
                    "corriente propios -- no se borra."
                )
            else:
                conn.execute("DELETE FROM clients WHERE id = ?", (referencia_id,))
        elif accion == "cc_debito_eliminado_por_duplicado":
            conn.execute(
                "INSERT INTO cc_debitos (id, cliente_id, monto, fecha, concepto, referencia, usuario_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
                (referencia_id, datos["cliente_id"], datos["monto"], datos["fecha"],
                 datos["concepto"], datos["referencia"], datos["usuario_id"]),
            )
        elif accion == "borrador_cancelado":
            conn.execute(
                "UPDATE sales SET status = ?, status_detail = ? WHERE id = ?",
                (datos["status_antes"], datos["status_detail_antes"], referencia_id),
            )
        elif accion == "occurred_on_completado":
            conn.execute("UPDATE sales SET occurred_on = NULL WHERE id = ?", (referencia_id,))
        elif accion == "venta_link_turno_factura":
            if datos["existia_antes"]:
                conn.execute(
                    "UPDATE venta_links SET turno_id = ?, factura_id = ? WHERE venta_id = ?",
                    (datos["turno_id_antes"], datos["factura_id_antes"], referencia_id),
                )
            else:
                conn.execute("DELETE FROM venta_links WHERE venta_id = ?", (referencia_id,))
        elif accion == "ventas_pago_creado":
            conn.execute("DELETE FROM ventas_pagos WHERE id = ?", (referencia_id,))
        elif accion == "fk_ventas_pagos_repuntada":
            conn.execute("ALTER TABLE ventas_pagos DROP CONSTRAINT IF EXISTS ventas_pagos_venta_id_fkey")
            conn.execute(
                "ALTER TABLE ventas_pagos ADD CONSTRAINT ventas_pagos_venta_id_fkey "
                "FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE"
            )
        elif accion == "venta_links_tabla_creada":
            conn.execute("DROP TABLE IF EXISTS venta_links")

    conn.execute("DROP TABLE IF EXISTS _migracion_0003")
    conn.commit()
