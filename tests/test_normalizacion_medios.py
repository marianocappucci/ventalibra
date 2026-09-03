"""La grafia vieja de MercadoPago se normaliza sola al arrancar.

Este POS escribio `mercado_pago`, con guion bajo, desde que existe; el resto de
la familia usa `mercadopago`. El plan era **primero los datos y despues la
grafia**, y estos tests cubren la primera mitad.

## Como se siembra: usando el producto, no un INSERT

Las filas con la grafia vieja no se insertan a mano. Se genera una venta cobrada
por MercadoPago y una cobranza de cuenta corriente **por los endpoints reales**
—que es lo que crea `sale_payments`, `caja_movimientos`, `cc_pagos` y el
`recibos` con su snapshot, con todas sus FK satisfechas— y recien despues se les
reescribe la grafia a la vieja. Asi la base de partida es la que tendria una
instancia de verdad, no una que yo arme para que el test pase.

## El barrido es un instrumento aparte, a proposito

`_columnas_con_la_grafia_vieja()` no consulta las listas de
`app.normalizacion_medios`: recorre **todas** las columnas de las dos bases y
casteia a texto. Es deliberado. La lista de columnas del modulo se armo mirando
la base real, y el primer barrido —el que uno escribe por reflejo, filtrando
`column_name LIKE '%medio%'`— **se perdio `recibos.pagos`**, que guarda el medio
adentro de un JSON en una columna que no se llama nada parecido. Un guard que
comparta el criterio con lo que verifica hereda ese punto ciego.

Por eso el degradado sigue siendo explicito y por tabla: si el barrido estuviera
mal, sembrar CON el barrido y verificar CON el barrido daria verde igual.
"""
import io
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from motor_de_test import destino_dominio
from pypdf import PdfReader

from app import normalizacion_medios as norm
from app.main import create_app

VIEJA = "mercado_pago"
CANONICA = "mercadopago"


# ── Arnes ────────────────────────────────────────────────────────────────────

def _client(app) -> TestClient:
    """Mismo `base_url` que `conftest.https_client`: la cookie de sesion es
    Secure y httpx no la reenvia sobre http plano."""
    return TestClient(app, base_url="https://ventalibra.test")


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text


def _texto_del_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(contenido)).pages)


def _es_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _todas_las_columnas(conn) -> list[tuple[str, str]]:
    """Todas las columnas de la base, sin filtrar por nombre ni por tipo."""
    if _es_sqlite(conn):
        tablas = [
            fila[0] for fila in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        return [
            (tabla, fila[1])
            for tabla in tablas
            for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        ]
    return [
        (fila[0], fila[1])
        for fila in conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        ).fetchall()
    ]


def _columnas_con_la_grafia_vieja(conn) -> dict[str, int]:
    """`{tabla.columna: filas}` para todo lugar donde aparezca `mercado_pago`.

    El `ESCAPE` no es adorno: sin el, el `_` del patron es un comodin y
    `mercadoXpago` contaria como coincidencia. Los dos motores aceptan la misma
    forma.
    """
    patron = "%" + VIEJA.replace("_", "\\_") + "%"
    encontrado: dict[str, int] = {}
    for tabla, columna in _todas_las_columnas(conn):
        sql = (
            f"SELECT COUNT(*) FROM {tabla} "
            f"WHERE CAST({columna} AS TEXT) LIKE ? ESCAPE '\\'"
        )
        try:
            n = conn.execute(sql, (patron,)).fetchone()[0]
        except Exception:
            # Una columna que no se puede castear a texto no puede contener la
            # grafia. Se saltea; no se tapa el resto del barrido.
            conn.rollback()
            continue
        if n:
            encontrado[f"{tabla}.{columna}"] = n
    return encontrado


def _libracore():
    from libracore.db.core import get_connection

    return get_connection()


# ── Siembra por el camino real ───────────────────────────────────────────────

def _sembrar_cobros_con_mercadopago(client) -> int:
    """Una venta cobrada por MercadoPago y una cobranza de cuenta corriente.

    Entre las dos tocan las cuatro tablas que este producto llena con un medio
    de pago: `sale_payments`, `caja_movimientos`, `cc_pagos` y el snapshot de
    `recibos.pagos`. Devuelve el id del recibo emitido.
    """
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    item = client.post("/catalog/items", json={
        "name": "Yerba 1kg", "unit_code": "u", "default_sale_price": "2000.00",
    })
    assert item.status_code == 200, item.text
    item_id = item.json()["id"]

    location = client.post("/locations", json={"name": "Sucursal 1"})
    assert location.status_code == 200, location.text
    location_id = location.json()["id"]

    cliente = client.post("/customers", json={"display_name": "Panaderia Sol"})
    assert cliente.status_code == 200, cliente.text
    cliente_id = cliente.json()["id"]

    turno = client.post("/shifts/open", json={"monto_inicial": 0})
    assert turno.status_code == 200, turno.text

    # 1) Venta cobrada por MercadoPago -> sale_payments + caja_movimientos.
    borrador = client.post("/sales", json={})
    sale_id = borrador.json()["id"]
    client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": "1"})
    # Con `pagos` y no con `medio_pago`: el camino de un solo medio NO crea
    # linea en `sale_payments` —registra el movimiento de caja y nada mas—, asi
    # que sembrar por ahi dejaria esa tabla vacia y el test pasaria sin haberla
    # ejercitado nunca.
    cobrada = client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": [{"medio": CANONICA, "monto": "2000.00"}],
    })
    assert cobrada.status_code == 200, cobrada.text

    # 2) Una venta fiada, para que el cliente tenga deuda que saldar.
    fiada = client.post("/sales", json={"customer_party_id": cliente_id})
    fiada_id = fiada.json()["id"]
    client.post(f"/sales/{fiada_id}/items", json={"item_id": item_id, "quantity": "1"})
    confirmada = client.post(f"/sales/{fiada_id}/confirm", json={
        "location_id": location_id, "medio_pago": "cuenta_corriente",
    })
    assert confirmada.status_code == 200, confirmada.text

    # 3) La cobranza por MercadoPago -> cc_pagos + caja_movimientos + recibos.
    cobranza = client.post(f"/accounts/{cliente_id}/payments", json={
        "monto": "2000.00", "medio_pago": CANONICA, "referencia": "mp 7781",
    })
    assert cobranza.status_code == 200, cobranza.text
    recibo_id = cobranza.json()["recibo_id"]
    assert recibo_id is not None, "no se emitio el recibo"
    return recibo_id


def _degradar_a_la_grafia_vieja(conn_dominio, conn_core) -> int:
    """Deja la base como la de una instancia anterior a la normalizacion.

    Las sentencias van escritas a mano y por tabla: sembrar con el mismo
    recorrido que despues verifica seria un control que comparte el
    instrumento. Devuelve cuantas filas degrado — el test lo exige distinto de
    cero, porque una siembra vacia haria pasar cualquier normalizacion, incluso
    una que no haga nada.
    """
    tocadas = 0
    tocadas += conn_dominio.execute(
        "UPDATE sale_payments SET method = ? WHERE method = ?", (VIEJA, CANONICA)
    ).rowcount
    for tabla in ("caja_movimientos", "cc_pagos"):
        tocadas += conn_core.execute(
            f"UPDATE {tabla} SET medio_pago = ? WHERE medio_pago = ?", (VIEJA, CANONICA)
        ).rowcount
    for tabla, columna in (("recibos", "pagos"), ("cajas", "medios_pago")):
        tocadas += conn_core.execute(
            f"UPDATE {tabla} SET {columna} = REPLACE({columna}, ?, ?) "
            f"WHERE {columna} LIKE ?",
            (json.dumps(CANONICA), json.dumps(VIEJA), f"%{json.dumps(CANONICA)}%"),
        ).rowcount
    conn_dominio.commit()
    conn_core.commit()
    return tocadas


@pytest.fixture
def instancia_degradada(tmp_path):
    """Una instancia con datos reales y la grafia vieja, lista para arrancar.

    Cede un dict con el destino, cuantas filas quedaron degradadas, el id del
    recibo y el TEXTO del PDF de ese recibo tal como sale con la grafia vieja
    —capturado con la app todavia abierta, porque volver a arrancarla es
    justamente lo que normaliza—.
    """
    destino = destino_dominio(tmp_path / "ventalibra.db")
    with _client(create_app(destino)) as client:
        _login(client)
        recibo_id = _sembrar_cobros_con_mercadopago(client)
        conn_core = _libracore()
        try:
            degradadas = _degradar_a_la_grafia_vieja(client.app.state.conn, conn_core)
        finally:
            conn_core.close()
        pdf = client.get(f"/accounts/receipts/{recibo_id}/pdf")
        assert pdf.status_code == 200, pdf.text
        texto_antes = _texto_del_pdf(pdf.content)

    assert degradadas > 0, "la siembra no dejo ninguna fila con la grafia vieja"
    return {
        "destino": destino,
        "degradadas": degradadas,
        "recibo_id": recibo_id,
        "texto_antes": texto_antes,
    }


# ── Los tests ────────────────────────────────────────────────────────────────

def test_el_arranque_normaliza_la_grafia_vieja(instancia_degradada):
    """🔴 El test principal, y no llama a `normalizar_*()` a proposito.

    Tener el mecanismo no es tenerlo invocado. Lo que se afirma es que **abrir
    la app** deja la base normalizada: si alguien saca la llamada de
    `db.connect()` o de `billing.configure()`, este test se pone rojo y el que
    ejercita las funciones sueltas seguiria verde.
    """
    with _client(create_app(instancia_degradada["destino"])) as client:
        conn_dominio = client.app.state.conn
        conn_core = _libracore()
        try:
            assert _columnas_con_la_grafia_vieja(conn_dominio) == {}
            assert _columnas_con_la_grafia_vieja(conn_core) == {}

            # Y los valores concretos, no solo la ausencia: una normalizacion
            # que hubiera vaciado las columnas tambien pasaria el barrido.
            medios_de_venta = [
                fila[0] for fila in conn_dominio.execute(
                    "SELECT method FROM sale_payments"
                ).fetchall()
            ]
            assert CANONICA in medios_de_venta, medios_de_venta

            medios_de_caja = [
                fila[0] for fila in conn_core.execute(
                    "SELECT medio_pago FROM caja_movimientos"
                ).fetchall()
            ]
            assert CANONICA in medios_de_caja, medios_de_caja

            medios_de_cc = [
                fila[0] for fila in conn_core.execute(
                    "SELECT medio_pago FROM cc_pagos"
                ).fetchall()
            ]
            assert medios_de_cc == [CANONICA], medios_de_cc
        finally:
            conn_core.close()


def test_el_recibo_ya_emitido_deja_de_imprimir_el_slug_crudo(instancia_degradada):
    """🔴 `recibos.pagos` es un snapshot de un comprobante YA EMITIDO.

    Reescribirlo hay que justificarlo sobre el papel, no sobre la fila. Y el
    papel **mejora**: LibraCore no sabe nombrar `mercado_pago`, asi que el
    recibo de una cobranza por MercadoPago venia imprimiendo el slug crudo, con
    guion bajo, en la columna "Medio" de un comprobante que se le entrega al
    cliente. Con la grafia normalizada imprime la etiqueta.

    Lo demas del comprobante —importe, referencia, cliente, numero— queda
    igual: se compara el texto completo del PDF, no solo la linea del medio.

    🔴 **La etiqueta esperada sale del motor, no de este archivo.** Estuvo
    hardcodeada como `"MercadoPago"` —lo que imprimia `pdf_generator` con su
    mapa propio— y el bump del pin la cambio a `"Mercado Pago"`, porque el
    generador pasa a usar `medios_pago.label()`. Un literal aca ata el test a
    una version del motor y se rompe en el proximo bump por una razon que no
    tiene nada que ver con lo que mide.
    """
    from libracore import medios_pago

    etiqueta = medios_pago.label(CANONICA)
    # El control de que la derivacion sirve: si el motor devolviera el slug tal
    # cual —porque no conoce la clave—, los asserts de abajo pasarian sin que el
    # papel diga nada legible.
    assert etiqueta != CANONICA, f"el motor no sabe nombrar «{CANONICA}»"

    antes = instancia_degradada["texto_antes"]
    assert VIEJA in antes, (
        "el PDF con la grafia vieja no imprime el slug: cambio el generador y "
        "este test ya no mide lo que dice"
    )

    with _client(create_app(instancia_degradada["destino"])) as client:
        _login(client)
        pdf = client.get(f"/accounts/receipts/{instancia_degradada['recibo_id']}/pdf")
        assert pdf.status_code == 200, pdf.text
        despues = _texto_del_pdf(pdf.content)

    assert VIEJA not in despues
    assert etiqueta in despues
    # El resto del comprobante, intacto: lo unico que cambia entre los dos
    # textos es como se nombra el medio.
    assert antes.replace(VIEJA, etiqueta) == despues


def test_es_idempotente(instancia_degradada):
    """Corre en cada arranque, asi que la segunda vez no puede mover nada."""
    with _client(create_app(instancia_degradada["destino"])) as primera:
        # Ya normalizada por este arranque. Volver a pedirla no cambia nada.
        assert norm.normalizar_dominio(primera.app.state.conn) == {}
        conn_core = _libracore()
        try:
            assert norm.normalizar_libracore(conn_core) == {}
        finally:
            conn_core.close()


def test_sobre_una_base_sin_la_grafia_vieja_no_toca_nada(tmp_path):
    """El caso de toda instancia nueva: la normalizacion no puede tener efecto.

    Es el control del test de arriba. Sin el, un `normalizar_*()` que devolviera
    siempre `{}` —porque no encuentra las tablas, por ejemplo— pasaria por
    idempotente.
    """
    destino = destino_dominio(tmp_path / "ventalibra.db")
    with _client(create_app(destino)) as client:
        _login(client)
        _sembrar_cobros_con_mercadopago(client)
        assert norm.normalizar_dominio(client.app.state.conn) == {}
        conn_core = _libracore()
        try:
            assert norm.normalizar_libracore(conn_core) == {}
            assert _columnas_con_la_grafia_vieja(conn_core) == {}
        finally:
            conn_core.close()


def test_las_funciones_dicen_cuantas_filas_movieron(instancia_degradada):
    """El conteo antes/despues que pide el estandar de migraciones.

    No es cosmetico: es lo unico que permite verificar en una instancia real
    que la migracion movio lo que la medicion decia que habia, en vez de
    confiar en que no fallo.
    """
    from libracore.db import core as libracore_core

    destino = instancia_degradada["destino"]

    # Se llama a mano, y para eso hay que abrir la conexion del dominio SIN
    # `create_app`: arrancar la app ya normalizaria y no quedaria nada que
    # contar.
    if libracore_core.es_url_postgres(destino):
        conn_dominio = libracore_core.conectar(destino)
    else:
        conn_dominio = sqlite3.connect(destino)
    try:
        movidas_dominio = norm.normalizar_dominio(conn_dominio)
    finally:
        conn_dominio.close()

    conn_core = _libracore()
    try:
        movidas_core = norm.normalizar_libracore(conn_core)
    finally:
        conn_core.close()

    total = sum(movidas_dominio.values()) + sum(movidas_core.values())
    assert total == instancia_degradada["degradadas"], (movidas_dominio, movidas_core)
    assert "sale_payments.method" in movidas_dominio
    assert "caja_movimientos.medio_pago" in movidas_core
    assert "cc_pagos.medio_pago" in movidas_core
    assert "recibos.pagos" in movidas_core
    assert "cajas.medios_pago" in movidas_core
