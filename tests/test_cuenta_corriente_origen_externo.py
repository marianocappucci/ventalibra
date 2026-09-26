"""El saldo de cuenta corriente cruza por ID, como en Contalibra y Restolibra (migración `0004`,
2026-09-26): `clients.id == parties.id`.

Historia: hasta el 2026-09-25 este archivo probaba lo contrario (D3, ADR-025): los ids NO
coincidían y el cruce era por `external_ref`, con una colisión armada a propósito (el `clients.id`
de Beto era el `party_id` de Ana). Con la paridad esa colisión no puede existir: el cliente se da de
alta en `clients` y su party espejo nace con el mismo id (`libracore.db.clients.create_client`).
Lo que se prueba ahora es que **dos clientes con deudas distintas no se confunden**.
"""
from libracore.db import clients as db_clients
from motor_de_test import TEST_DATABASE_URL

from app import db as app_db
from app.services import billing
from app.services.cuenta_corriente import CuentaCorrienteService


def test_el_saldo_de_un_cliente_no_se_confunde_con_el_de_otro():
    from libracommerce.erp.ventas import repuntar_fk_ventas_pagos

    conn = app_db.connect(TEST_DATABASE_URL)
    billing.configure(TEST_DATABASE_URL)
    # La FK de `ventas_pagos` la repunta la migración `0003` en una instancia real; acá se hace a
    # mano porque este test arranca de una base nueva, sin correr la cadena de Alembic.
    repuntar_fk_ventas_pagos(conn)
    conn.commit()

    ana = db_clients.create_client("Ana")
    beto = db_clients.create_client("Beto")
    # Paridad: el id del cliente ES el id de su party espejo.
    assert conn.execute("SELECT display_name FROM parties WHERE id = ?", (ana,)).fetchone()[0] == "Ana"
    assert conn.execute("SELECT display_name FROM parties WHERE id = ?", (beto,)).fetchone()[0] == "Beto"

    def _venta_fiada(numero, cliente_id, total):
        vid = conn.execute(
            "INSERT INTO sales (number, status, customer_party_id, occurred_on, total, source_type) "
            "VALUES (?,'confirmed',?,'2026-09-14',?,'pos')",
            (numero, cliente_id, total),
        ).lastrowid
        conn.execute(
            "INSERT INTO ventas_pagos (venta_id, medio, monto, estado) "
            "VALUES (?, 'cuenta_corriente', ?, 'aprobado')",
            (vid, total),
        )
        return vid

    _venta_fiada("POS-000001", ana, 300)
    _venta_fiada("POS-000002", beto, 700)
    conn.commit()

    servicio = CuentaCorrienteService(conn)
    assert servicio.saldo(ana) == 300
    assert servicio.saldo(beto) == 700
