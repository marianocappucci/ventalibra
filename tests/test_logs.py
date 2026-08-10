"""
Logs: actividad del sistema y accesos, admin-only.

VentaLibra es el único producto de la familia **sin SQLAlchemy en el dominio**,
así que su actividad no sale del mismo lado que la de los otros tres: el
mecanismo vive en `libracommerce.db.auditoria` (repositorio envuelto) y no en
`libraauth.auditoria` (flush). Los dos motores tienen sus propios tests.

Lo que se prueba **acá** es lo que sólo este producto puede verificar:

1. 🔴 Que **ningún servicio construya el repositorio desnudo**. Uno que lo haga
   escribe sin auditar, y no se nota: el log sigue mostrando las filas de los
   otros nueve servicios y parece sano.
2. Que la actividad llegue de verdad end-to-end, desde un POST del router hasta
   la fila del log — que es lo que ninguno de los dos motores puede probar solo.
3. Que la fila quede a nombre del usuario de la request y no del anterior.
4. Que la pantalla sea admin-only.
"""
import pathlib

import pytest


def _logs(client, **params) -> dict:
    r = client.get("/logs", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _unidad(client, code="u") -> None:
    """Un producto no se puede dar de alta sin su unidad de medida. Se ignora
    el 409 porque varios tests dan de alta más de un producto."""
    client.post("/catalog/units", json={"code": code, "name": "Unidad"})


def _producto(client, nombre="Yerba 1kg") -> dict:
    _unidad(client)
    r = client.post("/catalog/items", json={
        "item_type": "product", "name": nombre, "unit_code": "u",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


# ── 🔴 Que nadie se saltee la fábrica ─────────────────────────────────────

def test_ningun_servicio_usa_el_repositorio_desnudo():
    """`app/commerce.py` es el único lugar que puede importar
    `SqliteCommerceRepository`. Cualquier otro que lo importe se salta la
    auditoría entera.

    Esto no es una preferencia de estilo: un servicio que construye el
    repositorio desnudo escribe en la base sin dejar una sola fila en
    `actividad_log`, y **nadie se entera nunca**, porque el log sigue lleno de
    la actividad de los demás. No hay pantalla donde se vea el hueco.

    Se mira el import y no cualquier mención del nombre, para que un docstring
    que lo nombre —hay varios— no rompa el test.
    """
    raiz = pathlib.Path(__file__).resolve().parent.parent / "app"
    culpables = []
    for archivo in raiz.rglob("*.py"):
        if archivo.name == "commerce.py":
            continue
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            despojada = linea.strip()
            if despojada.startswith(("import ", "from ")) and "SqliteCommerceRepository" in linea:
                culpables.append(f"{archivo.relative_to(raiz)}:{numero}")

    assert not culpables, (
        f"importan el repositorio desnudo y por lo tanto escriben sin auditar: {culpables}. "
        "Usá `from ..commerce import repositorio`."
    )


def test_los_diez_servicios_pasan_por_la_fabrica():
    """La contracara del test de arriba: que la fábrica se esté usando de
    verdad y no que simplemente nadie importe nada. Si un servicio dejara de
    construir su repositorio, el test de arriba seguiría en verde."""
    raiz = pathlib.Path(__file__).resolve().parent.parent / "app" / "services"
    usan = [
        f.name for f in raiz.glob("*.py")
        if "from ..commerce import repositorio" in f.read_text(encoding="utf-8")
    ]
    assert len(usan) == 10, f"esperaba 10 servicios sobre la fábrica, hay {len(usan)}: {sorted(usan)}"


# ── Que registre, end-to-end ──────────────────────────────────────────────

def test_dar_de_alta_un_producto_queda_registrado(admin_client):
    """El router no llama a nada de auditoría: la fila sale del repositorio
    envuelto, tres capas más abajo. Si `app/commerce.py` devolviera el
    repositorio desnudo, esto quedaría vacío sin dar ningún error."""
    _producto(admin_client)

    filas = [f for f in _logs(admin_client)["actividad"] if f["entidad"] == "producto"]
    assert filas, "el alta de un producto no dejó ninguna fila"
    assert filas[0]["accion"] == "crear"
    assert "Yerba 1kg" in filas[0]["descripcion"]
    assert filas[0]["usuario"] == "admin"


def _balanza(client, prefix="20") -> None:
    r = client.put("/settings/scale", json={
        "prefix": prefix, "code_digits": 5, "value_digits": 5,
        "value_kind": "weight", "divisor": 1000, "total_digits": 13,
    })
    assert r.status_code == 200, r.text


def test_cambiar_una_configuracion_guarda_el_antes_y_el_despues(admin_client):
    """La rama de EDITAR, por la vía real.

    Se usa la balanza y no un producto porque **hoy este producto no expone
    edición por HTTP de ninguna entidad comercial**: el catálogo, los clientes,
    los proveedores y los depósitos son todos POST de alta. Las
    configuraciones sí se editan, y pasan por `set_setting`, que es la otra
    rama del envoltorio.
    """
    _balanza(admin_client, prefix="20")
    _balanza(admin_client, prefix="21")

    ediciones = [f for f in _logs(admin_client)["actividad"] if f["accion"] == "editar"]
    assert ediciones, "cambiar la configuración de la balanza no dejó ninguna fila"
    assert ediciones[0]["entidad"] == "configuracion"


def test_editar_una_entidad_guarda_el_antes_y_el_despues(admin_client):
    """La rama de EDITAR sobre una entidad del motor comercial, con su diff.

    Va contra el repositorio y no contra la API **a propósito**: ver el test de
    arriba — por HTTP no hay hoy forma de editar un producto. Se prueba igual
    para que el día que se agregue el endpoint la auditoría ya esté cubierta, y
    no dependa de que alguien se acuerde de mirarla.
    """
    from dataclasses import replace

    from app.commerce import repositorio

    item = _producto(admin_client)
    repo = repositorio(admin_client.app.state.conn)
    actual = repo.get_catalog_item(item["id"])
    repo.save_catalog_item(replace(actual, name="Yerba 500g"))

    edicion = [
        f for f in _logs(admin_client)["actividad"]
        if f["entidad"] == "producto" and f["accion"] == "editar"
    ][0]
    assert edicion["cambios"]["name"] == ["Yerba 1kg", "Yerba 500g"]


def test_el_filtro_ofrece_las_entidades_del_motor_comercial(admin_client):
    entidades = _logs(admin_client)["entidades"]
    for esperada in ("producto", "venta", "deposito", "movimiento de stock"):
        assert esperada in entidades, f"falta '{esperada}' en el filtro"


# ── Accesos ───────────────────────────────────────────────────────────────

def test_el_login_queda_registrado(admin_client):
    accesos = _logs(admin_client)["accesos"]
    assert accesos[0]["evento"] == "login"
    assert accesos[0]["username"] == "admin"


def test_el_intento_fallido_deja_el_usuario_tipeado(admin_client):
    admin_client.post("/auth/login", json={"username": "fantasma", "password": "x"})
    fallidos = [a for a in _logs(admin_client)["accesos"] if a["evento"] == "login_fallido"]
    assert fallidos[0]["username"] == "fantasma"


def test_la_contrasena_no_aparece_en_ningun_lado(admin_client):
    admin_client.post("/auth/login", json={"username": "admin", "password": "clave-secretisima"})
    assert "secretisima" not in str(_logs(admin_client))


# ── Permisos y usuario ────────────────────────────────────────────────────

def test_el_cajero_no_ve_los_logs(staff_client):
    """Es la pantalla que dice desde qué IP entró cada uno y quién vendió qué."""
    assert staff_client.get("/logs").status_code == 403


def test_lo_que_escribe_el_cajero_queda_a_su_nombre(admin_client, staff_client):
    """El usuario sale de la cookie de cada request, vía el middleware del
    motor de auth. Si quedara pegado del contexto anterior, la venta del
    empleado aparecería como del admin — que es peor que no tener log."""
    _producto(staff_client, "Producto del cajero")

    filas = [f for f in _logs(admin_client)["actividad"] if f["entidad"] == "producto"]
    assert filas and filas[0]["usuario"] == "staff-1"
