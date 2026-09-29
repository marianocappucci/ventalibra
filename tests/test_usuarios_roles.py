"""El router de usuarios con los roles de ADR-049: admin, encargado, vendedor, cajero, deposito y el `staff` heredado.

Lo que ya hace `libraauth.usuarios.build_users_router` NO se vuelve a probar ni a implementar acá: el 422 por rol inválido,
el 409 por sacarse el rol de admin a uno mismo y el 422 por dejar la instancia sin admin activo son de la factory (ver su
README y `tests/test_users.py`). Lo que se fija acá es que **este producto le pasa el vocabulario nuevo** (`roles=ROLES`) y
que las protecciones siguen valiendo con él: si alguien monta el router sin `roles=`, los roles nuevos dan 422 y estos tests
se ponen rojos.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from motor_de_test import destino_dominio

from app import permisos
from app.main import create_app


def _alta(client, rol, usuario=None, headers=None):
    cuerpo = {"username": usuario or f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol}
    return client.post("/users", json=cuerpo, headers=headers)


@pytest.mark.parametrize("rol", permisos.ROLES)
def test_el_alta_acepta_cada_rol_del_vocabulario(admin_client, rol):
    creado = _alta(admin_client, rol)
    assert creado.status_code == 201, creado.text
    assert creado.json()["role"] == rol
    # Y ese usuario entra con su rol.
    with https_client(admin_client.app) as cliente:
        entrada = cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"})
        assert entrada.status_code == 200, entrada.text
        assert entrada.json()["role"] == rol


def test_el_repositorio_y_el_router_usan_el_mismo_vocabulario(admin_client):
    assert admin_client.app.state.users.roles == permisos.ROLES


@pytest.mark.parametrize("rol", ["superadmin", "mozo", "operador", "Admin", "", "cajero "])
def test_un_rol_invalido_es_422_en_el_alta_y_en_la_edicion(admin_client, rol):
    alta = _alta(admin_client, rol)
    assert alta.status_code == 422, alta.text
    assert "rol inválido" in alta.text

    creado = _alta(admin_client, "cajero", "victima")
    assert creado.status_code == 201
    edicion = admin_client.put(f"/users/{creado.json()['id']}", json={"name": "V", "role": rol, "active": True})
    assert edicion.status_code == 422, edicion.text
    # Y el usuario no cambió.
    assert admin_client.get(f"/users/{creado.json()['id']}").json()["role"] == "cajero"


def test_un_admin_no_puede_quitarse_el_rol_a_si_mismo_ni_desactivarse(admin_client):
    yo = next(u for u in admin_client.get("/users").json() if u["username"] == "admin")
    bajarse = admin_client.put(f"/users/{yo['id']}", json={"name": yo["name"], "role": "encargado", "active": True})
    assert bajarse.status_code == 409, bajarse.text
    desactivarse = admin_client.put(f"/users/{yo['id']}", json={"name": yo["name"], "role": "admin", "active": False})
    assert desactivarse.status_code == 409, desactivarse.text
    assert admin_client.get(f"/users/{yo['id']}").json()["role"] == "admin"


def test_no_se_puede_dejar_la_instancia_sin_admin(admin_client, monkeypatch):
    """Con el único admin activo, ni degradarlo ni desactivarlo ni borrarlo, viniendo de quien venga: acá, del token de
    servicio del backoffice (que no es 'uno mismo', así que la protección de la propia cuenta no lo cubre)."""
    token = "un-token-de-servicio-de-prueba"
    monkeypatch.setenv(SERVICE_TOKEN_ENV, token)
    servicio = {SERVICE_TOKEN_HEADER: token}
    with https_client(admin_client.app) as backoffice:
        yo = next(u for u in backoffice.get("/users", headers=servicio).json() if u["username"] == "admin")
        cuerpo = {"name": yo["name"], "role": "encargado", "active": True}
        assert backoffice.put(f"/users/{yo['id']}", json=cuerpo, headers=servicio).status_code == 422
        assert backoffice.put(
            f"/users/{yo['id']}", json={**cuerpo, "role": "admin", "active": False}, headers=servicio,
        ).status_code == 422
        assert backoffice.delete(f"/users/{yo['id']}", headers=servicio).status_code == 422
        # Con un segundo admin sí se puede: la regla es «que quede uno», no «nunca».
        otro = _alta(backoffice, "admin", "admin-2", headers=servicio)
        assert otro.status_code == 201, otro.text
        assert backoffice.put(f"/users/{yo['id']}", json=cuerpo, headers=servicio).status_code == 200


@pytest.mark.parametrize("rol", ["encargado", "vendedor", "cajero", "deposito", "staff"])
def test_solo_el_admin_administra_usuarios(admin_client, rol):
    """Ninguno de los otros roles —el encargado incluido— lista, crea, edita, borra ni resetea la contraseña de nadie.
    Y no puede darse a sí mismo el rol admin."""
    assert _alta(admin_client, rol).status_code == 201
    victima = _alta(admin_client, "cajero", "otro").json()
    with https_client(admin_client.app) as cliente:
        assert cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"}).status_code == 200
        assert cliente.get("/users").status_code == 403
        assert cliente.get(f"/users/{victima['id']}").status_code == 403
        assert _alta(cliente, "admin", "usurpador").status_code == 403
        propio = next(u for u in admin_client.get("/users").json() if u["username"] == f"u-{rol}")
        ascenso = cliente.put(f"/users/{propio['id']}", json={"name": "x", "role": "admin", "active": True})
        assert ascenso.status_code == 403
        assert cliente.put(f"/users/{victima['id']}/password", json={"password": "otra-clave-1"}).status_code == 403
        assert cliente.delete(f"/users/{victima['id']}").status_code == 403
    assert admin_client.get(f"/users/{propio['id']}").json()["role"] == rol


def test_cambiar_el_rol_de_alguien_cambia_lo_que_puede_en_el_pedido_siguiente(admin_client):
    """El rol se lee de la base en cada pedido (no se copia a la cookie): el ascenso o la baja rigen de inmediato."""
    creado = _alta(admin_client, "cajero").json()
    with https_client(admin_client.app) as cliente:
        assert cliente.post("/auth/login", json={"username": "u-cajero", "password": "clave-larga-1"}).status_code == 200
        assert cliente.get("/api/reportes").status_code == 403
        subir = admin_client.put(f"/users/{creado['id']}", json={"name": "C", "role": "encargado", "active": True})
        assert subir.status_code == 200, subir.text
        assert cliente.get("/api/reportes").status_code == 200
        assert "reportes" in cliente.get("/auth/me").json()["capacidades"]
        bajar = admin_client.put(f"/users/{creado['id']}", json={"name": "C", "role": "cajero", "active": True})
        assert bajar.status_code == 200
        assert cliente.get("/api/reportes").status_code == 403


def test_un_staff_existente_sigue_entrando_sin_migrar(admin_client, staff_client):
    """Nadie se migra ni se borra: el `staff` de antes sigue siendo un rol válido, con su sesión y sus permisos."""
    assert staff_client.get("/auth/me").json()["role"] == "staff"
    assert staff_client.get("/api/productos").status_code == 200
    assert staff_client.get("/api/reportes").status_code == 403


def test_el_arranque_con_la_demo_sigue_creando_al_visitante_como_staff(monkeypatch, tmp_path):
    """`ensure_demo_user` levanta el arranque si el rol de la demo no está en el vocabulario del producto. `staff` sigue
    estando: si alguien lo sacara de `ROLES`, la demo dejaría de arrancar (se nota acá y no en el deploy)."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")
    from motor_de_test import limpiar_entre_tests

    limpiar_entre_tests()
    app = create_app(destino_dominio(tmp_path / "ventalibra.db"))
    try:
        visitante = app.state.users.get_by_username("visitante")
        assert visitante["role"] == "staff"
    finally:
        app.state.auth_engine.dispose()
