"""LibraEdge de punta a punta en VentaLibra (E6, 2026-10-19, ADR-090): un nodo y su central, **con dos bases**.

El nodo es la app de la suite sobre la base del worker, con la identidad de un nodo en el entorno. El central es una
**copia de esa base** hecha después de cargar la referencia (un producto, `arca_config` ficticia): es lo que deja el
espejo de LibraEdge, el nodo tiene las mismas filas con las mismas claves. En el central se contrata el adicional
`offline`, se publica la referencia y se registra el nodo con el aprovisionamiento del producto (`app.offline`): de ahí
salen el secreto, el prefijo de numeración y las tablas que el nodo espeja. Lo que el nodo hace después (ventas,
facturas) sólo existe en la suya y llega al central por las rutas `/sync/v1/*` reales del producto; lo que el central
cambia en la referencia baja por `/sync/v1/pull`. El transporte HTTP de LibraEdge está cableado al `TestClient` y,
mientras dura cada pedido, la app apunta a la base del central y no es un nodo.

ARCA y el WSAA son dobles (`arca_wsfe` y `arca_wsaa.autenticar`); todo lo demás es el código de verdad: el ticket que
presta el central (libraedge ADR-009), el numerador del nodo (libracore ADR-074), el outbox y los aplicadores
(libracommerce ADR-067 y ADR-068) y la costura del producto (`app/offline.py`). Datos ficticios.
"""
import datetime
import io
import json
import os
import urllib.error

import psycopg
import pytest
from motor_de_test import TEST_DATABASE_URL
from ventas_helpers import abrir_turno, caja_default, crear_item, registrar_venta

NODO = "nodo-e2e-1"
CENTRAL = "https://central.example"
PRECIO = "1500.00"


def _ahora_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _hoy_ar() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).date()


class _EnElCentral:
    """La app apuntada al central y sin identidad de nodo, mientras dura el `with`."""

    def __init__(self, url):
        self.url = url
        self.guardadas = {}
        self.anterior = None

    def __enter__(self):
        from libracore.db import core

        for variable in ("LIBRAEDGE_NODE_ID", "LIBRAEDGE_PREFIJO"):
            self.guardadas[variable] = os.environ.pop(variable, None)
        self.anterior = core._db_path
        core.configure(self.url)
        return self

    def __exit__(self, *exc):
        from libracore.db import core

        core.configure(self.anterior)
        for variable, valor in self.guardadas.items():
            if valor is not None:
                os.environ[variable] = valor
        return False


class _Escenario:
    def __init__(self, client, url_central, node_conn, ruta_estado):
        self.client = client
        self.url_central = url_central
        self.node_conn = node_conn
        self.ruta_estado = ruta_estado
        self.autenticaciones = 0
        self.ultimo_cae = 0
        self.secreto = self.prefijo = self.espejo = None
        self.producto = None

    # ── la conexión del nodo con el central ──
    def en_linea(self, si: bool) -> None:
        with open(self.ruta_estado, "w", encoding="utf-8") as archivo:
            json.dump({"node_id": NODO, "en_linea": si, "ultima_sincronizacion_ok": _ahora_iso()}, archivo)

    def central(self):
        return _EnElCentral(self.url_central)

    def _version(self):
        from libraedge.sync.esquema import version_de_alembic

        version = version_de_alembic(self.node_conn)
        self.node_conn.commit()
        return version

    def subir(self):
        from libraedge.db.repository import NodeRepository
        from libraedge.sync.http import HttpSyncTransport
        from libraedge.sync.worker import OutboxWorker

        worker = OutboxWorker(NodeRepository(self.node_conn),
                              HttpSyncTransport(CENTRAL, self.secreto, version_esquema=self._version()))
        resultado = worker.run_once()
        self.node_conn.commit()
        return resultado

    def bajar(self) -> int:
        from libraedge.db.repository import NodeRepository
        from libraedge.sync.pull import HttpPullTransport, MirrorApplier, PullWorker

        worker = PullWorker(NodeRepository(self.node_conn),
                            HttpPullTransport(CENTRAL, NODO, self.secreto, version_esquema=self._version()),
                            MirrorApplier(self.node_conn, self.espejo))
        aplicados = worker.run_once(NODO)
        self.node_conn.commit()
        return aplicados

    def en_revision_en_el_nodo(self):
        from libraedge.db.repository import NodeRepository

        return NodeRepository(self.node_conn).listar_en_revision()

    def pendientes_en_el_nodo(self):
        from libraedge.db.repository import NodeRepository

        filas = NodeRepository(self.node_conn).list_pending_operations()
        self.node_conn.commit()
        return sorted(op.operation_type for op in filas)

    # ── el nodo vende ──
    def vender(self, *, pagos=None, fecha=None, cliente_id=None, esperar=200):
        return registrar_venta(self.client, self.producto, precio=PRECIO, cantidad="2", pagos=pagos, fecha=fecha,
                               cliente_id=cliente_id, esperar=esperar)


class _Respuesta:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _cable(escenario):
    """`urlopen` de LibraEdge apuntado a la app real, que mientras contesta es el central."""

    def urlopen(pedido, timeout=None):
        ruta = pedido.full_url.replace(CENTRAL, "")
        cabeceras = dict(pedido.header_items())
        with escenario.central():
            if pedido.get_method() == "POST":
                r = escenario.client.post(ruta, content=pedido.data, headers=cabeceras)
            else:
                r = escenario.client.get(ruta, headers=cabeceras)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pedido.full_url, r.status_code, "error", {}, io.BytesIO(r.content))
        return _Respuesta(r.content)

    return urlopen


@pytest.fixture()
def escenario(admin_client, monkeypatch, tmp_path):
    from libracore import adicionales, arca_credenciales, arca_wsaa, arca_wsfe
    from libracore.db import arca_config as db_arca
    from libracore.db import core
    from libracore.db.modulos import set_addon
    from libracore.respaldo_postgres import con_base
    from libraedge import aprovisionamiento as aprov
    from libraedge.sync import http as http_module
    from libraedge.sync import pull as pull_module
    from libraedge.sync import ticket as ticket_module

    from app import offline

    # La referencia que el central publica y el nodo espeja: un producto y ARCA (datos ficticios).
    producto = crear_item(admin_client, name="Yerba ficticia 1kg", price=PRECIO)
    db_arca.crear_arca_config("Comercio Ficticio", "20000000001", 3, "", "", ambiente="homologacion")
    caja = caja_default(admin_client)

    # El central: una copia de la base en este momento. `CREATE DATABASE ... TEMPLATE` exige que nadie esté conectado
    # a la del worker: se sueltan el pool de auth y las conexiones vivas (la de arranque de la app se renueva sola).
    worker = TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0]
    nombre_central = f"{worker}_central"
    original = os.environ["_LIBRACORE_PG_VENTALIBRA_ORIGINAL"].replace("postgresql+psycopg://", "postgresql://")
    admin_client.app.state.auth_engine.dispose()
    with psycopg.connect(original, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre_central}" WITH (FORCE)')
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s"
                      " AND pid <> pg_backend_pid() AND usename = current_user", (worker,))
        admin.execute(f'CREATE DATABASE "{nombre_central}" TEMPLATE "{worker}"')
    url_central = con_base(os.environ["_LIBRACORE_PG_VENTALIBRA_ORIGINAL"], nombre_central)

    ruta_estado = str(tmp_path / "estado.json")
    node_conn = core.get_connection()
    esc = _Escenario(admin_client, url_central, node_conn, ruta_estado)
    esc.producto = producto

    # En el central, como lo haría el backoffice y `libraedge-central nodo`: el adicional contratado, la referencia
    # publicada y el nodo registrado en la sucursal principal.
    with esc.central(), core.get_connection() as conn:
        set_addon("offline", True)
        adicionales.fijar_cantidad("offline", 1)
        sucursal = str(conn.execute("SELECT id FROM branches WHERE is_default = 1").fetchone()[0])
        salida = []
        assert aprov.publicar(conn, offline.aprovisionamiento, salida=salida.append) == 0, salida
        assert not [linea for linea in salida if "no estan" in linea], salida
        alta = aprov.registrar(conn, offline.aprovisionamiento, NODO, sucursal, salida=salida.append)
    esc.secreto, esc.prefijo, esc.espejo = alta.secreto, alta.prefijo, alta.espejo

    for variable, valor in {"LIBRAEDGE_NODE_ID": NODO, "LIBRAEDGE_PREFIJO": esc.prefijo,
                            "LIBRAEDGE_ESTADO": ruta_estado, "LIBRAEDGE_CENTRAL_URL": CENTRAL,
                            "LIBRAEDGE_NODE_SECRET": esc.secreto}.items():
        monkeypatch.setenv(variable, valor)
    monkeypatch.setattr(offline, "_cliente_de_ticket", None)
    esc.en_linea(True)

    cable = _cable(esc)
    for modulo in (http_module, pull_module, ticket_module):
        monkeypatch.setattr(modulo, "urlopen", cable)

    # ARCA, de mentira: el WSAA del central (con el certificado «en disco») y el WSFE del nodo.
    async def autenticar(cert, clave, ambiente, servicio):
        esc.autenticaciones += 1
        vence = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=12)
        return {"token": "TOKEN-FICTICIO", "sign": "SIGN-FICTICIO", "expiracion": vence.isoformat()}

    async def ultimo_numero_autorizado(pv, tipo, cuit, token, sign, ambiente):
        assert token == "TOKEN-FICTICIO", "el nodo tiene que firmar con el ticket que prestó el central"
        return esc.ultimo_cae

    async def solicitar_cae(factura, cuit, token, sign, ambiente):
        esc.ultimo_cae += 1
        return {"cae": f"7000000000{esc.ultimo_cae:04d}", "cae_vto": "20261231"}

    monkeypatch.setattr(arca_credenciales, "paths_en_disco", lambda arca: ("cert-ficticio", "clave-ficticia"))
    monkeypatch.setattr(arca_wsaa, "autenticar", autenticar)
    monkeypatch.setattr(arca_wsfe, "ultimo_numero_autorizado", ultimo_numero_autorizado)
    monkeypatch.setattr(arca_wsfe, "solicitar_cae", solicitar_cae)

    # El turno es del nodo: sin turno abierto no se vende (`exigir_turno=True`).
    abrir_turno(admin_client, caja_id=caja)

    yield esc

    node_conn.close()
    with psycopg.connect(original, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{nombre_central}" WITH (FORCE)')


def _en_el_central(esc, sql, params=()):
    from libracore.db.core import get_connection

    with esc.central(), get_connection() as conn:
        return [tuple(f) for f in conn.execute(sql, params).fetchall()]


def _venta_del_central(esc, venta_id_nodo):
    filas = _en_el_central(
        esc, "SELECT id, number, status_detail, customer_party_id FROM sales WHERE source_type = ? AND source_id = ?",
        (f"libraedge:{NODO}", venta_id_nodo))
    assert len(filas) == 1, f"la venta {venta_id_nodo} del nodo está {len(filas)} veces en el central"
    return filas[0]


def test_el_aprovisionamiento_publica_toda_la_referencia_con_su_clave(escenario):
    """Las tablas de referencia de `app.offline` existen en la instancia y se publican con la clave de la base:
    `party_roles` con la compuesta, `units` con `code`. El prefijo lo asigna el central por sucursal."""
    esc = escenario
    from app.offline import TABLAS_DE_REFERENCIA

    assert set(esc.espejo) == set(TABLAS_DE_REFERENCIA)
    assert set(esc.espejo["party_roles"]) == {"party_id", "role"}
    assert esc.espejo["units"] == ("code",) and esc.espejo["commerce_settings"] == ("key",)
    assert esc.prefijo.startswith("S")


def test_las_ventas_suben_con_el_prefijo_del_nodo_y_el_qr_posterior_cierra_la_parcial(escenario):
    esc = escenario
    total = 2 * float(PRECIO)
    cobrada = esc.vender()
    parcial = esc.vender(pagos=[
        {"medio": "efectivo", "monto": 1000.0},
        {"medio": "mercadopago", "monto": total - 1000.0, "cobrar_con_qr": True},
    ])
    assert cobrada["numero"].startswith(f"{esc.prefijo}-POS-"), cobrada["numero"]
    assert parcial["estado"] == "parcial"

    resultado = esc.subir()
    assert resultado.confirmadas == 2 and esc.en_revision_en_el_nodo() == ()

    vid, numero, estado, _ = _venta_del_central(esc, cobrada["id"])
    assert numero == cobrada["numero"] and estado == "cobrada"
    # La parcial también sube (decisión 5), esperando el QR.
    vid_parcial, _, estado, _ = _venta_del_central(esc, parcial["id"])
    assert estado == "parcial"
    # La caja del central: lo acreditado, sin el QR pendiente.
    caja = _en_el_central(esc, "SELECT COALESCE(SUM(monto), 0) FROM caja_movimientos WHERE tipo = 'ingreso'")
    assert float(caja[0][0]) == total + 1000.0
    # El stock que descontó el nodo, repetido en el central.
    stock = _en_el_central(esc, "SELECT COALESCE(SUM(quantity_delta), 0) FROM stock_movements WHERE item_id = ?",
                           (esc.producto,))
    assert float(stock[0][0]) == -4.0

    # Entra el QR en el nodo (lo que haría el webhook): sube el pago y el central cierra la venta.
    from app import db_ventas

    assert db_ventas.acreditar_pago_qr(parcial["id"], "pago-ficticio-1") is True
    esc.subir()
    assert _venta_del_central(esc, parcial["id"])[2] == "cobrada"

    # Un segundo ciclo no repite nada.
    esc.subir()
    assert len(_en_el_central(esc, "SELECT id FROM sales")) == 2
    assert esc.pendientes_en_el_nodo() == []


def test_un_cliente_nuevo_del_central_baja_al_nodo_con_su_rol_y_se_le_vende(escenario):
    """La bajada: el central da de alta un cliente (y su fila de `party_roles`, clave compuesta) y el nodo lo espeja;
    la venta del nodo a ese cliente sube con el mismo id."""
    esc = escenario
    from libracore.db.core import get_connection

    with esc.central():
        r = esc.client.post("/api/clientes", json={"name": "Cliente Ficticio SA"})
        assert r.status_code in (200, 201), r.text
        cliente_id = r.json()["id"]
        with get_connection() as conn:
            conn.execute("INSERT INTO party_roles (party_id, role) VALUES (?, ?)", (cliente_id, "customer"))
            conn.commit()

    assert esc.bajar() > 0
    en_el_nodo = esc.node_conn.execute("SELECT name FROM clients WHERE id = ?", (cliente_id,)).fetchone()
    assert en_el_nodo is not None and en_el_nodo[0] == "Cliente Ficticio SA"
    roles = esc.node_conn.execute("SELECT party_id, role FROM party_roles WHERE party_id = ?", (cliente_id,)).fetchall()
    esc.node_conn.commit()
    assert [tuple(f) for f in roles] == [(cliente_id, "customer")]

    # Una segunda bajada reaplica sin chocar (upsert por la clave compuesta).
    esc.bajar()

    venta = esc.vender(cliente_id=cliente_id)
    esc.subir()
    assert _venta_del_central(esc, venta["id"])[3] == cliente_id


def test_con_internet_el_nodo_factura_con_el_ticket_prestado_y_la_factura_sube(escenario):
    esc = escenario
    venta = esc.vender()

    r = esc.client.post(f"/api/ventas/{venta['id']}/facturar")
    assert r.status_code == 200, r.text
    factura = r.json()["factura"]
    assert factura["cae"] and factura["numero"] == 1 and factura["punto_venta"] == 3
    # Facturar dos veces no emite otra: devuelve la misma.
    r = esc.client.post(f"/api/ventas/{venta['id']}/facturar")
    assert r.status_code == 200 and r.json()["factura"]["id"] == factura["id"]
    assert esc.autenticaciones == 1, "el central autentica una vez y el nodo guarda el ticket hasta que vence"
    assert esc.client.get(f"/api/ventas/{venta['id']}").json()["factura_pendiente"] is None

    esc.subir()
    assert esc.en_revision_en_el_nodo() == ()
    vid, _, _, _ = _venta_del_central(esc, venta["id"])
    en_el_central = _en_el_central(
        esc, "SELECT f.numero, f.cae, f.punto_venta FROM venta_links vl JOIN facturas f ON f.id = vl.factura_id"
             " WHERE vl.venta_id = ?", (vid,))
    assert en_el_central == [(1, factura["cae"], 3)], "la factura del nodo sube con su número y su CAE"


def test_sin_conexion_va_a_la_bandeja_el_ticket_lo_dice_y_al_volver_sale_con_la_fecha_de_la_venta(escenario):
    esc = escenario
    hace_dos = (_hoy_ar() - datetime.timedelta(days=2)).isoformat()
    venta = esc.vender(fecha=hace_dos)

    esc.en_linea(False)
    r = esc.client.post(f"/api/ventas/{venta['id']}/facturar")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "factura_pendiente", r.text
    detalle = esc.client.get(f"/api/ventas/{venta['id']}").json()
    assert detalle["factura_pendiente"] is not None, "la pantalla tiene que poder decir «se factura al volver»"
    assert esc.client.get("/api/nodo/conexion").json() == {
        "es_nodo": True, "en_linea": False, "node_id": NODO, "a_facturar": 1}
    assert esc.autenticaciones == 0, "sin conexión no se sale a pedir el ticket"

    from pypdf import PdfReader

    ticket = esc.client.get(f"/ventas/{venta['id']}/ticket")
    assert ticket.status_code == 200, ticket.text
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(ticket.content)).pages)
    assert "NO VÁLIDO COMO FACTURA" in texto

    # Sin conexión el QR no se ofrece ni se pide.
    assert esc.client.get("/pos/mp-estado").json()["disponible"] is False
    r = esc.client.post(f"/api/ventas/{venta['id']}/mp-qr")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_conexion", r.text

    # Vuelve la conexión: la bandeja se factura (lo mismo que hace sola la tanda de cada minuto).
    esc.en_linea(True)
    r = esc.client.post("/api/nodo/facturar-pendientes")
    assert r.status_code == 200, r.text
    detalle = esc.client.get(f"/api/ventas/{venta['id']}").json()
    assert detalle["factura_pendiente"] is None and detalle["factura_id"]
    from libracore.db import facturas as db_facturas

    assert db_facturas.get_factura(r.json()["facturadas"][0]["factura_id"])["fecha"] == hace_dos, (
        "la factura al volver lleva la fecha de la venta (dentro de los 5 días de ARCA)")

    esc.subir()
    vid, _, _, _ = _venta_del_central(esc, venta["id"])
    assert _en_el_central(esc, "SELECT f.fecha FROM venta_links vl JOIN facturas f ON f.id = vl.factura_id"
                               " WHERE vl.venta_id = ?", (vid,)) == [(hace_dos,)]


def test_la_anulacion_sube_y_lo_facturado_no_se_anula_sin_conexion(escenario):
    esc = escenario
    sin_factura = esc.vender()
    facturada = esc.vender()
    assert esc.client.post(f"/api/ventas/{facturada['id']}/facturar").status_code == 200

    assert esc.client.post(f"/api/ventas/{sin_factura['id']}/anular").status_code == 200
    esc.en_linea(False)
    r = esc.client.post(f"/api/ventas/{facturada['id']}/anular")
    assert r.status_code == 409, "anular lo facturado sin conexión está prohibido (libracommerce ADR-067)"

    esc.subir()
    assert _venta_del_central(esc, sin_factura["id"])[2] == "anulada"
    assert _venta_del_central(esc, facturada["id"])[2] == "cobrada"
    assert esc.pendientes_en_el_nodo() == [], "quedó algo sin subir"


def test_un_nodo_dado_de_baja_no_recibe_el_ticket_y_no_va_a_la_bandeja(escenario):
    """El rechazo del central (`TicketRechazado`) es 422 `nodo_sin_arca`: no se arregla solo al volver la conexión,
    así que no se deja en la bandeja para reintentar."""
    from libracore.db.core import get_connection
    from libraedge.db.repository import NodeRepository

    esc = escenario
    with esc.central(), get_connection() as conn:
        NodeRepository(conn).deactivate_node(NODO)
        conn.commit()
    venta = esc.vender()
    r = esc.client.post(f"/api/ventas/{venta['id']}/facturar")
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "nodo_sin_arca", r.text
    assert esc.client.get(f"/api/ventas/{venta['id']}").json()["factura_pendiente"] is None


def test_sin_el_secreto_de_un_nodo_la_sincronizacion_no_atiende(admin_client):
    """`/sync/v1/*` está montado siempre y no lo decide el rol (`test_roles_matriz.py` lo lista como público): lo
    autentica el secreto del nodo. Sin un nodo registrado no hay secreto válido, ni con la sesión del admin."""
    operacion = {"operation_id": "x:1", "node_id": "x", "sequence": 1, "operation_type": "venta.registrada",
                 "aggregate_type": "venta", "aggregate_id": "x:venta:1", "occurred_at": _ahora_iso(),
                 "schema_version": 1, "payload": {}}
    assert admin_client.post("/sync/v1/push", json=operacion).status_code == 401
    r = admin_client.post("/sync/v1/push", json=operacion, headers={"Authorization": "Bearer inventado"})
    assert r.status_code == 401
    assert admin_client.get("/sync/v1/pull", params={"node_id": "x"}).status_code == 401
    assert admin_client.post("/sync/v1/ticket-arca", json={"node_id": "x", "emisor_id": None}).status_code == 401
    assert admin_client.get("/api/nodo/conexion").json() == {
        "es_nodo": False, "en_linea": True, "node_id": None, "a_facturar": 0}


def test_en_un_nodo_la_app_arranca_la_facturacion_al_volver_y_la_para_al_cerrar(monkeypatch, tmp_path):
    """El arranque de la app arranca la tanda que factura la bandeja sola (libracore ADR-074) sólo en un nodo, y el
    cierre la para. Fuera de un nodo no arranca nada (lo cubre el resto de la suite: ningún test tiene la identidad)."""
    from conftest import https_client
    from motor_de_test import destino_dominio

    from app.main import create_app

    monkeypatch.setenv("LIBRAEDGE_NODE_ID", NODO)
    monkeypatch.setenv("LIBRAEDGE_PREFIJO", "S01")
    monkeypatch.setenv("LIBRAEDGE_ESTADO", str(tmp_path / "estado.json"))
    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    try:
        with https_client(app):
            parar = app.state.parar_facturacion_al_volver
            assert parar is not None and not parar.is_set()
        assert parar.is_set()
    finally:
        app.state.auth_engine.dispose()
