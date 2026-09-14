"""Contrato de usuarios: `libraauth.usuarios.build_users_router` (ADR-018).

VentaLibra adoptó la factory el 2026-09-13 (ver `app/main.py`), reemplazando
su `app/routers/users.py` propio -- que este archivo probaba a mano hasta
esa fecha. El ciclo completo de ABM (listar → alta → editar → releer por
`GET /{id}` → borrar) ahora lo prueba `libraauth.testing
.verificar_contrato_de_usuarios`, el mismo helper que corren los otros siete
productos de la familia contra su propia instancia del router -- así el
contrato no puede volver a divergir producto por producto.

Lo que queda ACÁ es lo que ese helper no cubre:

- El cambio de contraseña ajena verificado con un LOGIN real (el contrato
  sólo verifica el `204`, no que la clave nueva sirva y la vieja no).
- Que el guard de VentaLibra (`require_admin_o_servicio`) deja pasar el
  contrato entero también por el token de servicio del backoffice, no sólo
  por sesión de admin -- `test_token_de_servicio.py` prueba el borde del
  guard (qué entra y qué no); esto prueba que, una vez adentro, el ABM
  funciona igual.
- Los casos de borde de email y contraseña que son específicos de esta
  instancia (nada de esto es "regla de negocio de la factory": ahí las
  prueba `libraauth` mismo, una sola vez, contra su propio router).

── Comportamiento que CAMBIÓ al adoptar la factory (ver el README de
libraauth, sección "Router de usuarios unificado", y el ADR-018) ──────────

- `POST /users` responde `201` (antes `200`, sin `status_code` declarado).
  Afecta a `conftest.py::staff_client` y a
  `test_token_de_servicio.py::test_el_token_puede_dar_de_alta_un_usuario`,
  actualizados en el mismo commit que este archivo.
- `PUT /{id}/password` exige ahora el mismo mínimo de 6 caracteres que el
  alta (antes sólo rechazaba la cadena vacía) -- reemplaza a
  `test_no_hay_minimo_de_longitud`, que hasta hoy probaba justo lo
  contrario: que una contraseña de un solo caracter SÍ se aceptaba. No es
  una regresión sin avisar: es la fila "Contraseña < 6, reset ajeno" de la
  tabla de protecciones de la factory, marcada ahí como "nuevo -- ninguno
  lo exigía".
- El 404 de un id inexistente cambia el cuerpo del mensaje: era
  `{"detail": "user not found"}`, ahora
  `{"detail": "no existe el usuario <id>"}`.
- `DELETE /{id}` responde `204` sin cuerpo (antes `200` con `{"ok": true}`).
  No había test en este archivo que mirara ese cuerpo, así que no hay nada
  que reemplazar acá -- el frontend (`Usuarios` de `libra-ui`) tampoco lo
  mira, ver el comentario en `app/main.py` sobre el `include_router`.

── Mutación verificada a mano (no queda como test permanente) ─────────────

Se montó una vez `build_users_router(prefix="/users",
admin_guard=lambda: {"id": None, "role": "staff"})` -- un guard que NO exige
admin -- en lugar de `require_admin_o_servicio`, y se corrió
`test_staff_no_puede_cambiarle_la_contrasena_a_nadie` (de este archivo) y
`test_staff_cannot_manage_users` (`test_auth.py`): las dos dieron rojo,
confirmando que sin el guard correcto la suite lo nota. Se revirtió antes de
correr el resto de la suite -- ver el reporte de la sesión que agregó esta
adopción.
"""
import pytest
from conftest import https_client
from fastapi.testclient import TestClient
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from libraauth.testing import verificar_contrato_de_usuarios
from motor_de_test import destino_dominio

from app.main import create_app


def test_contrato_de_usuarios(admin_client: TestClient):
    """El mismo ciclo que ejerce el backoffice -- ver `libraauth.testing`."""
    verificar_contrato_de_usuarios(admin_client, "/users", role="staff")


def test_contrato_de_usuarios_con_token_de_servicio(monkeypatch, tmp_path):
    """El guard de VentaLibra acepta ADEMÁS el token de servicio del
    backoffice (2026-08-02, ver `test_token_de_servicio.py`) -- el contrato
    entero tiene que servir igual entrando por ahí, no sólo con sesión de
    admin."""
    token = "un-token-de-servicio-de-prueba"
    monkeypatch.setenv(SERVICE_TOKEN_ENV, token)
    db_path = destino_dominio(tmp_path / "ventalibra.db")
    with https_client(create_app(db_path)) as client:
        verificar_contrato_de_usuarios(
            client, "/users", role="staff",
            username="contrato-servicio",
            headers={SERVICE_TOKEN_HEADER: token},
        )


def _alta_de_staff(client: TestClient, **extra) -> dict:
    body = {"username": "cristina", "name": "Cristina", "password": "vieja123",
            "role": "staff"}
    body.update(extra)
    r = client.post("/users", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_el_admin_le_cambia_la_contrasena_a_otro_usuario(admin_client: TestClient):
    """Se asiertan las DOS puntas: que la vieja deja de entrar y que la nueva
    entra. Con sólo la segunda, un endpoint que no hiciera nada y un login que
    aceptara cualquier cosa darían el mismo verde."""
    creado = _alta_de_staff(admin_client)

    r = admin_client.put(f"/users/{creado['id']}/password", json={"password": "nueva456"})
    assert r.status_code == 204

    otro = https_client(admin_client.app)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 401
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "nueva456"}).status_code == 200


def test_la_contrasena_vacia_se_rechaza_y_no_cambia_nada(admin_client: TestClient):
    """No alcanza con asertar el 422: un endpoint que devolviera 422 *después*
    de haber hasheado el vacío daría el mismo código y la cuenta quedaría
    abierta. Lo que prueba la guarda es que la anterior sigue entrando."""
    creado = _alta_de_staff(admin_client)

    for vacia in ("", "   "):
        r = admin_client.put(f"/users/{creado['id']}/password", json={"password": vacia})
        assert r.status_code == 422, f"{vacia!r} tendría que rechazarse"

    otro = https_client(admin_client.app)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 200


def test_la_contrasena_corta_se_rechaza_en_el_reset_ajeno(admin_client: TestClient):
    """Reemplaza a `test_no_hay_minimo_de_longitud`, que hasta el 2026-09-13
    probaba lo contrario de esto: que una contraseña de un solo caracter
    ("x") se aceptaba sin mínimo. Con la factory de libraauth (ADR-018) el
    reset de la contraseña de OTRO usuario exige el mismo mínimo que el
    alta -- fila "Contraseña < 6, reset ajeno" del README de libraauth,
    marcada ahí como "nuevo -- ninguno lo exigía". No se pierde cobertura:
    lo que probaba el test viejo (que "x" entraba) es exactamente lo que
    ahora se rechaza, a propósito."""
    creado = _alta_de_staff(admin_client)

    r = admin_client.put(f"/users/{creado['id']}/password", json={"password": "corta"})
    assert r.status_code == 422

    assert https_client(admin_client.app).post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 200


def test_contrasena_de_usuario_inexistente_devuelve_404(admin_client: TestClient):
    """Se asierta el cuerpo y no sólo el código: este producto sirve la SPA con
    un catch-all, así que una ruta que no existe también puede contestar 404 —
    un assert sobre el status daría verde con el endpoint sin escribir."""
    r = admin_client.put("/users/9999/password", json={"password": "loquesea"})
    assert r.status_code == 404
    assert r.json() == {"detail": "no existe el usuario 9999"}


def test_staff_no_puede_cambiarle_la_contrasena_a_nadie(
    admin_client: TestClient, staff_client: TestClient,
):
    """El router entero cuelga de `require_admin_o_servicio` (pasado ahora
    como `admin_guard=` de la factory, no en `dependencies=` del
    `include_router` -- ver `app/main.py`), así que la ruta hereda el gate.
    Se cubre igual: el día que alguien lo desmonte, el gate se pierde sin
    que nada avise. Mutación verificada a mano -- ver el docstring del
    módulo."""
    victima = _alta_de_staff(admin_client, username="victima")
    r = staff_client.put(f"/users/{victima['id']}/password", json={"password": "tomada"})
    assert r.status_code == 403


def test_el_email_del_alta_se_guarda_y_se_devuelve(admin_client: TestClient):
    creado = _alta_de_staff(admin_client, email="cristina@empresa.com")
    assert creado["email"] == "cristina@empresa.com"

    listado = admin_client.get("/users").json()
    guardado = next(u for u in listado if u["username"] == "cristina")
    assert guardado["email"] == "cristina@empresa.com"


def test_editar_nombre_o_rol_no_borra_el_email(admin_client: TestClient):
    """La razón por la que `UsuarioEdicion.email` es `None` y no `""`.

    El toggle de activo/inactivo de la grilla manda el cuerpo entero sin tocar
    el correo. Con un default vacío, desactivar a alguien le borraba el mail en
    silencio — y el mail es lo único que permite recuperar la contraseña.
    """
    creado = _alta_de_staff(admin_client, email="cristina@empresa.com")

    r = admin_client.put(f"/users/{creado['id']}", json={
        "name": "Cristina G.", "role": "staff", "active": False})
    assert r.status_code == 200
    assert r.json()["email"] == "cristina@empresa.com"
    assert r.json()["name"] == "Cristina G."


def test_el_email_se_puede_vaciar_pidiendolo(admin_client: TestClient):
    """La contracara: `""` explícito sí lo borra. Sin esto, un correo cargado
    mal no se podría sacar nunca."""
    creado = _alta_de_staff(admin_client, email="mal@escrito.com")

    r = admin_client.put(f"/users/{creado['id']}", json={
        "name": "Cristina", "role": "staff", "active": True, "email": ""})
    assert r.status_code == 200
    assert r.json()["email"] == ""


def test_borrar_a_un_usuario_con_turno_da_409(
    admin_client: TestClient, staff_client: TestClient,
):
    """Bug conocido de libraauth v0.43.0 (`build_users_router` /
    `UserRepository.delete`), NO de VentaLibra -- reportado por el humano el
    2026-09-14. `turnos_caja.usuario_id` es `NOT NULL REFERENCES usuarios(id)`
    SIN `ON DELETE` (a diferencia del resto de las FK de usuario en
    libracore.db.schema, casi todas `ON DELETE SET NULL`) -- ver ese archivo.
    `UserRepository.delete` no atrapaba el `IntegrityError` del
    `session.commit()`, así que borrar a un usuario que alguna vez abrió un
    turno de caja no daba el 409 esperable: directamente PROPAGABA la
    excepción (con `raise_server_exceptions` en default, como el resto de
    esta suite; en producción, uvicorn la convertía en un 500 sin cuerpo
    útil). libraauth v0.43.1 agregó un `except IntegrityError` en
    `UserRepository.delete` que lo traduce a un 409 con rollback de la
    sesión -- este test confirma ese comportamiento.

    `staff_client` ya viene logueado (ver conftest.py) -- abre un turno con
    esa sesión y después el admin intenta borrar a ESE usuario."""
    victima_id = staff_client.get("/auth/me").json()["id"]

    abierto = staff_client.post("/shifts/open", json={"monto_inicial": 100})
    assert abierto.status_code == 200, abierto.text

    r = admin_client.delete(f"/users/{victima_id}")
    assert r.status_code == 409, r.text
    assert "el usuario tiene historial" in r.json()["detail"]

    # El rollback dejó a la sesión sana: el usuario sigue existiendo.
    sigue = admin_client.get(f"/users/{victima_id}")
    assert sigue.status_code == 200, sigue.text
