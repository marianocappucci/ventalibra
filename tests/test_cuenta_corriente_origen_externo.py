"""D3 (ADR-025): el saldo de cuenta corriente cruza por `external_ref`, no
por id. Pedido explícito del orquestador para F3, punto 4 de la
especificación, una vez que existió `libracore` v1.100.0.

El caso real que motiva esto (medido en `ventalibra-dev`, ver el plan): los
`clients.id` de LibraCore NO coinciden con el `party_id` de LibraCommerce
--cada cliente se da de alta como party primero, con autoincremento propio,
y el `clients.id` se enlaza después por `external_ref = party-<id>`--. Cruzar
`sales.customer_party_id` contra `clients.id` directamente (el origen
`VENTAS_LIBRACOMMERCE`, válido para Contalibra/Restolibra) le pondría acá la
deuda de un cliente a otro, en silencio, cada vez que los dos ids
coincidieran por casualidad.

Este test arma esa colisión a propósito: el `clients.id` de Beto es
EXACTAMENTE el `party_id` de Ana. Si el cruce fuera por id directo, la
consulta del saldo de Ana devolvería el de Beto.
"""
from motor_de_test import TEST_DATABASE_URL

from app import db as app_db
from app.services import billing
from app.services.cuenta_corriente import CuentaCorrienteService


def test_el_saldo_de_un_cliente_no_se_confunde_con_el_de_otro_por_id():
    from libracommerce.erp.ventas import repuntar_fk_ventas_pagos

    conn = app_db.connect(TEST_DATABASE_URL)
    billing.configure(TEST_DATABASE_URL)
    # La FK de `ventas_pagos` la repunta la migración `0003` en una instancia
    # real; acá se hace a mano porque este test arranca de una base nueva,
    # sin correr la cadena de Alembic.
    repuntar_fk_ventas_pagos(conn)
    conn.commit()

    def _party(nombre):
        return conn.execute(
            "INSERT INTO parties (party_type, display_name) VALUES ('person', ?)", (nombre,),
        ).lastrowid

    party_ana = _party("Ana")
    party_beto = _party("Beto")
    conn.commit()

    # La colisión adversarial: el `clients.id` de Beto es el `party_id` de
    # Ana. Un cruce por id directo (`VENTAS_LIBRACOMMERCE`) confundiría a los
    # dos -- acá se fuerza el id a mano en vez de dejarlo salir del
    # autoincrement, precisamente para poder afirmarlo con certeza.
    conn.execute(
        "INSERT INTO clients (id, name, external_ref) VALUES (?, 'Ana (LibraCore)', ?)",
        (9001, f"party-{party_ana}"),
    )
    conn.execute(
        "INSERT INTO clients (id, name, external_ref) VALUES (?, 'Beto (LibraCore)', ?)",
        (party_ana, f"party-{party_beto}"),
    )
    conn.commit()
    assert party_ana != 9001  # el id de Ana en LibraCore NO es su party_id

    def _venta_fiada(numero, party_id, total):
        vid = conn.execute(
            "INSERT INTO sales (number, status, customer_party_id, occurred_on, total, source_type) "
            "VALUES (?,'confirmed',?,'2026-09-14',?,'pos')",
            (numero, party_id, total),
        ).lastrowid
        conn.execute(
            "INSERT INTO ventas_pagos (venta_id, medio, monto, estado) "
            "VALUES (?, 'cuenta_corriente', ?, 'aprobado')",
            (vid, total),
        )
        return vid

    _venta_fiada("POS-000001", party_ana, 300)
    _venta_fiada("POS-000002", party_beto, 700)
    conn.commit()

    servicio = CuentaCorrienteService(conn)
    assert servicio.saldo(party_ana) == 300
    assert servicio.saldo(party_beto) == 700
