"""Del modelo plano de ubicaciones al jerárquico: `app/sucursales_migracion.py`.

La migración conserva los ids (cada `store` S es la sucursal con `id = S.id` y su propia fila queda como su
depósito), así que lo que apuntaba a S —cajas, turnos, precios, stock— sigue apuntando a lo mismo.

El estado «viejo» se fabrica a mano sobre la base de una app ya arrancada: una base que nació con el modelo plano
ya no se puede crear con el código de hoy.
"""
import pytest

from app.sucursales_migracion import migrar, parsear_mapa


def _ubicacion(conn, nombre, tipo, *, activa=1, default=0) -> int:
    conn.execute(
        "INSERT INTO locations (name, location_type, active, is_default) VALUES (?, ?, ?, ?)",
        (nombre, tipo, activa, default),
    )
    return conn.execute("SELECT id FROM locations WHERE name = ? ORDER BY id DESC", (nombre,)).fetchone()[0]


def _caja(conn, nombre, sucursal_id) -> int:
    conn.execute("INSERT INTO cajas (nombre, sucursal_id) VALUES (?, ?)", (nombre, sucursal_id))
    return conn.execute("SELECT id FROM cajas WHERE nombre = ?", (nombre,)).fetchone()[0]


@pytest.fixture
def conn(admin_client):
    """Una base con el modelo VIEJO: sin sucursales, sólo `locations` con `store`/`warehouse`."""
    c = admin_client.app.state.conn
    c.execute("DELETE FROM cajas")
    c.execute("DELETE FROM stock_movements")
    c.execute("UPDATE locations SET branch_id = NULL")
    c.execute("DELETE FROM branches")
    c.execute("DELETE FROM locations")
    return c


def test_cada_store_pasa_a_ser_una_sucursal_con_su_mismo_id(conn):
    centro = _ubicacion(conn, "Centro", "store", default=1)
    norte = _ubicacion(conn, "Norte", "store")

    informe = migrar(conn)

    assert informe["sucursales_creadas"] == 2
    ramas = conn.execute("SELECT id, name, is_default, default_location_id FROM branches ORDER BY id").fetchall()
    assert [(r[0], r[1]) for r in ramas] == [(centro, "Centro"), (norte, "Norte")]
    # La fila de la sucursal es su propio depósito predeterminado: el stock no se mueve.
    assert [r[3] for r in ramas] == [centro, norte]
    tipos = conn.execute("SELECT id, branch_id, location_type FROM locations ORDER BY id").fetchall()
    assert [(t[0], t[1], t[2]) for t in tipos] == [(centro, centro, "warehouse"), (norte, norte, "warehouse")]


def test_la_sucursal_predeterminada_es_la_store_que_ya_lo_era(conn):
    _ubicacion(conn, "Centro", "store")
    norte = _ubicacion(conn, "Norte", "store", default=1)

    migrar(conn)

    assert conn.execute("SELECT id FROM branches WHERE is_default = 1").fetchone()[0] == norte


def test_sin_store_predeterminada_elige_la_activa_de_menor_id(conn):
    _ubicacion(conn, "Inactiva", "store", activa=0)
    activa = _ubicacion(conn, "Activa", "store")

    migrar(conn)

    assert conn.execute("SELECT id FROM branches WHERE is_default = 1").fetchone()[0] == activa


def test_una_sucursal_inactiva_migra_inactiva(conn):
    vieja = _ubicacion(conn, "Cerrada", "store", activa=0)
    _ubicacion(conn, "Abierta", "store", default=1)

    migrar(conn)

    assert conn.execute("SELECT active FROM branches WHERE id = ?", (vieja,)).fetchone()[0] == 0


def test_un_deposito_sin_dueno_va_a_la_sucursal_predeterminada(conn):
    centro = _ubicacion(conn, "Centro", "store", default=1)
    salon = _ubicacion(conn, "Salón", "warehouse")

    informe = migrar(conn)

    assert informe["depositos_asignados"] == 1
    assert conn.execute("SELECT branch_id FROM locations WHERE id = ?", (salon,)).fetchone()[0] == centro


def test_el_mapa_manda_sobre_la_predeterminada(conn):
    _ubicacion(conn, "Centro", "store", default=1)
    norte = _ubicacion(conn, "Norte", "store")
    salon = _ubicacion(conn, "Salón", "warehouse")

    migrar(conn, depositos_a_sucursal={salon: norte})

    assert conn.execute("SELECT branch_id FROM locations WHERE id = ?", (salon,)).fetchone()[0] == norte


def test_un_mapa_a_una_sucursal_inexistente_falla_sin_asignar(conn):
    _ubicacion(conn, "Centro", "store", default=1)
    salon = _ubicacion(conn, "Salón", "warehouse")

    with pytest.raises(RuntimeError, match="no existe"):
        migrar(conn, depositos_a_sucursal={salon: 9999})


def test_las_cajas_de_un_deposito_pasan_a_su_sucursal(conn):
    centro = _ubicacion(conn, "Centro", "store", default=1)
    salon = _ubicacion(conn, "Salón", "warehouse")
    de_sucursal = _caja(conn, "Caja del centro", centro)
    de_deposito = _caja(conn, "Caja vieja del salón", salon)

    informe = migrar(conn)

    assert informe["cajas_reasignadas"] == 1
    assert conn.execute("SELECT sucursal_id FROM cajas WHERE id = ?", (de_sucursal,)).fetchone()[0] == centro
    assert conn.execute("SELECT sucursal_id FROM cajas WHERE id = ?", (de_deposito,)).fetchone()[0] == centro


def test_migrar_dos_veces_no_hace_nada_la_segunda(conn):
    _ubicacion(conn, "Centro", "store", default=1)
    _ubicacion(conn, "Salón", "warehouse")
    migrar(conn)

    segunda = migrar(conn)

    assert segunda == {"sucursales_creadas": 0, "depositos_asignados": 0, "cajas_reasignadas": 0}


def test_la_secuencia_de_sucursales_sigue_a_los_ids_conservados(conn):
    """Los ids entran explícitos: sin `setval`, la próxima sucursal choca con una migrada."""
    for i in range(3):
        _ubicacion(conn, f"Sucursal {i}", "store", default=1 if i == 0 else 0)
    migrar(conn)
    maximo = conn.execute("SELECT MAX(id) FROM branches").fetchone()[0]

    conn.execute("INSERT INTO branches (name) VALUES ('Nueva')")

    assert conn.execute("SELECT id FROM branches WHERE name = 'Nueva'").fetchone()[0] > maximo


def test_una_base_sin_ubicaciones_no_hace_nada(conn):
    assert migrar(conn) == {"sucursales_creadas": 0, "depositos_asignados": 0, "cajas_reasignadas": 0}


def test_parsear_mapa():
    assert parsear_mapa("2:1, 5:3") == {2: 1, 5: 3}
    assert parsear_mapa("") == {}


# ── El preflight (`scripts/preflight_jerarquia.py`): sólo lectura, y coincide con lo que hace `migrar` ──


def _preflight():
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parent.parent / "scripts" / "preflight_jerarquia.py"
    spec = importlib.util.spec_from_file_location("preflight_jerarquia", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_preflight_no_escribe_y_predice_lo_que_hace_migrar(conn):
    centro = _ubicacion(conn, "Centro", "store", default=1)
    salon = _ubicacion(conn, "Salón", "warehouse")
    caja = _caja(conn, "Caja vieja del salón", salon)

    informe = _preflight().auditar(conn)

    assert informe["apto_para_migrar"] and informe["bloqueos"] == []
    assert [s["id"] for s in informe["sucursales_a_crear"]] == [centro]
    assert informe["sucursal_predeterminada"]["id"] == centro
    assert informe["depositos_sin_dueno"] == [
        {"id": salon, "nombre": "Salón", "activo": True, "sucursal_destino": centro, "por_mapa": False}
    ]
    assert informe["cajas_que_cambian_de_sucursal"] == [
        {"caja": caja, "nombre": "Caja vieja del salón", "de": salon, "a": centro}
    ]
    assert any("sin dueño" in a for a in informe["avisos"])
    # Sólo lectura: nada cambió.
    assert conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0] == 0
    assert conn.execute("SELECT branch_id FROM locations WHERE id = ?", (salon,)).fetchone()[0] is None
    # Y lo que predijo es lo que después hace la migración.
    real = migrar(conn)
    assert real["sucursales_creadas"] == len(informe["sucursales_a_crear"])
    assert real["depositos_asignados"] == len(informe["depositos_sin_dueno"])
    assert real["cajas_reasignadas"] == len(informe["cajas_que_cambian_de_sucursal"])


def test_el_preflight_respeta_el_mapa(conn):
    _ubicacion(conn, "Centro", "store", default=1)
    norte = _ubicacion(conn, "Norte", "store")
    salon = _ubicacion(conn, "Salón", "warehouse")

    informe = _preflight().auditar(conn, {salon: norte})

    assert informe["depositos_sin_dueno"][0]["sucursal_destino"] == norte
    assert informe["depositos_sin_dueno"][0]["por_mapa"] is True
    assert not any("sin dueño" in a for a in informe["avisos"])


def test_el_preflight_bloquea_un_mapa_a_una_sucursal_que_no_existe(conn):
    _ubicacion(conn, "Centro", "store", default=1)
    salon = _ubicacion(conn, "Salón", "warehouse")

    informe = _preflight().auditar(conn, {salon: 9999})

    assert not informe["apto_para_migrar"]
    assert any("9999" in b for b in informe["bloqueos"])


def test_el_preflight_bloquea_si_ninguna_sucursal_esta_activa(conn):
    _ubicacion(conn, "Cerrada", "store", activa=0)

    informe = _preflight().auditar(conn)

    assert not informe["apto_para_migrar"]
    assert any("Ninguna sucursal" in b for b in informe["bloqueos"])
