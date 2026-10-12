"""Los clientes (`/api/clientes`, tabla `clients` del motor de core) quedan en el log de actividad (ADR-080).

Hasta el 2026-10-12 no: `libracore.clientes_router` escribe por `libracore.db.clients` y no por el repositorio de
LibraCommerce, que es lo unico que este producto auditaba (ver el docstring de `test_los_tres_servicios_pasan_por_la_fabrica`
en `test_logs.py`). Con libracore v1.157.0 el motor le avisa cada escritura a un registrador y `app/commerce.py` le
enchufa el de libraauth, el mismo que usa el repositorio.

Lo que fija:
1. alta y edicion por la API quedan en `/api/logs`, a nombre de quien las hizo, con el diff en vocabulario de la base;
2. `actividad_log` esta en la MISMA base que escribe el motor de core (si no, la escritura fallaria: el log es
   transaccional);
3. `cliente` (la tabla `clients`) no se confunde con `cliente/proveedor` (la tabla `parties`);
4. el filtro de la pantalla ofrece `cliente`.
"""


def _logs(client, **params) -> dict:
    r = client.get("/api/logs", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _clientes(client, **params) -> list[dict]:
    return _logs(client, entidad="cliente", **params)["actividad"]


def test_el_alta_y_la_edicion_de_un_cliente_quedan_en_el_log_con_el_usuario(admin_client):
    r = admin_client.post("/api/clientes", json={"name": "Ana Pérez", "email": "ana@t.com"})
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    r = admin_client.put(f"/api/clientes/{cid}", json={"name": "Ana Pérez SA", "email": "ana@t.com"})
    assert r.status_code == 200, r.text

    filas = _clientes(admin_client)
    assert [f["accion"] for f in filas] == ["editar", "crear"]
    crear, editar = filas[1], filas[0]
    assert crear["usuario"] == editar["usuario"] == "admin"
    # La tabla de LibraCommerce declara `entidad_id INTEGER`: el registrador manda texto y la base lo asigna al entero.
    assert crear["entidad_id"] == editar["entidad_id"] == cid
    assert "Ana Pérez" in crear["descripcion"] and crear["cambios"] is None
    assert editar["cambios"] == {"name": ["Ana Pérez", "Ana Pérez SA"]}


def test_guardar_un_cliente_sin_cambios_no_deja_fila(admin_client):
    cid = admin_client.post("/api/clientes", json={"name": "Igual", "email": "i@t.com"}).json()["id"]
    admin_client.put(f"/api/clientes/{cid}", json={"name": "Igual", "email": "i@t.com"})
    assert [f["accion"] for f in _clientes(admin_client)] == ["crear"]


def test_desactivar_y_activar_quedan_en_el_log(admin_client):
    cid = admin_client.post("/api/clientes", json={"name": "Baja"}).json()["id"]
    assert admin_client.post(f"/api/clientes/{cid}/desactivar").status_code == 200
    assert admin_client.post(f"/api/clientes/{cid}/activar").status_code == 200
    cambios = [f["cambios"] for f in _clientes(admin_client) if f["accion"] == "editar"]
    assert cambios == [{"activo": [0, 1]}, {"activo": [1, 0]}]


def test_el_usuario_es_el_de_la_request(admin_client, encargado_client):
    """El middleware de libraauth sella el usuario de la cookie: si quedara en `Sistema`, el log no diria quien fue."""
    encargado_client.post("/api/clientes", json={"name": "Del encargado"})
    # Los logs son de admin: se leen con su cliente (la misma app).
    usuarios = {f["usuario"] for f in _clientes(admin_client)}
    assert usuarios and "Sistema" not in usuarios and "admin" not in usuarios


def test_el_log_esta_en_la_base_del_motor_de_core(admin_client):
    """La fila la escribe el motor de core (su conexion) y la lee el `ActividadRepository` del dominio: si fueran dos
    bases, el alta fallaria (el log es transaccional) o la pantalla no la veria."""
    from libracore.db.core import get_connection

    admin_client.post("/api/clientes", json={"name": "En la misma base"})
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM actividad_log WHERE entidad = 'cliente'").fetchone()[0]
    assert n == len(_clientes(admin_client)) == 1


def test_cliente_no_se_confunde_con_cliente_proveedor(admin_client):
    """`clients` es `cliente`; `parties` (lo que escribe `save_party`) es `cliente/proveedor`. El filtro compara el
    texto entero, y el espejo en `parties` que el motor crea en el alta no deja una segunda fila."""
    admin_client.post("/api/clientes", json={"name": "Solo uno"})
    datos = _logs(admin_client)
    assert {f["entidad"] for f in datos["actividad"] if "Solo uno" in f["descripcion"]} == {"cliente"}
    assert "cliente" in datos["entidades"] and "cliente/proveedor" in datos["entidades"]
    assert _logs(admin_client, entidad="cliente/proveedor")["actividad"] == []
