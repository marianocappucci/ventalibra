"""Config SMTP por backoffice (libraauth v0.6.0), montada en `/admin/smtp`.

**Que prueba esto que la suite del motor no prueba**: el cableado de ESTE
producto — que el router quedo incluido, que `app.state.smtp_settings` existe y
que la ruta esta gateada por rol admin. La logica (cifrado, centinela de
"no tocar la contrasena", precedencia base/entorno) ya la cubren los 163 tests
de libraauth y no se repite aca.

Se prueba **pidiendo al endpoint** y no mirando `app.routes`: en esta version de
FastAPI los routers incluidos quedan como `_IncludedRouter` sin `.path`, asi que
inspeccionar ahi da un falso "no esta montado" (paso de verdad al adoptar).
"""
from sqlalchemy import text


def test_montado_y_admin_lo_lee(admin_client):
    """404 seria "no esta montado"."""
    r = admin_client.get("/admin/smtp")
    assert r.status_code == 200, r.text
    # Sin nada guardado la config sale del entorno: es lo que hace que adoptar
    # la v0.6.0 no cambie el comportamiento de esta instancia.
    assert r.json()["origen"] == "entorno"
    assert r.json()["password_definida"] is False


def test_staff_no_puede_leerlo(staff_client):
    """Quien pueda escribir aca puede redirigir a donde salen los enlaces de
    recuperacion de contrasena de todos los usuarios."""
    assert staff_client.get("/admin/smtp").status_code == 403
    assert staff_client.put("/admin/smtp", json={"host": "x.test"}).status_code == 403
    assert staff_client.delete("/admin/smtp").status_code == 403


def test_guardar_no_devuelve_la_contrasena_y_en_la_base_esta_cifrada(admin_client):
    r = admin_client.put("/admin/smtp", json={
        "host": "smtp.empresa.test", "port": 2525, "user": "cuenta",
        "password": "hunter2", "from_email": "no-reply@empresa.test",
    })
    assert r.status_code == 200, r.text
    assert "hunter2" not in r.text
    assert r.json()["password_definida"] is True

    lectura = admin_client.get("/admin/smtp")
    assert "hunter2" not in lectura.text
    assert lectura.json()["origen"] == "base"

    # La mitigacion que justifica guardar la credencial en la base del cliente.
    sf = admin_client.app.state.smtp_settings.session_factory
    with sf() as s:
        crudo = s.execute(text("SELECT password_cifrada FROM smtp_settings")).scalar_one()
    assert crudo.startswith("v1:")
    assert "hunter2" not in crudo


def test_editar_sin_mandar_la_contrasena_la_conserva(admin_client):
    admin_client.put("/admin/smtp", json={
        "host": "smtp.empresa.test", "password": "hunter2",
        "from_email": "no-reply@empresa.test"})
    r = admin_client.put("/admin/smtp", json={
        "host": "smtp-nuevo.test", "from_email": "no-reply@empresa.test"})

    assert r.json()["password_definida"] is True
    assert r.json()["host"] == "smtp-nuevo.test"


def test_borrar_vuelve_al_entorno(admin_client):
    admin_client.put("/admin/smtp", json={
        "host": "smtp.empresa.test", "from_email": "no-reply@empresa.test"})
    assert admin_client.delete("/admin/smtp").json()["origen"] == "entorno"


def test_host_vacio_da_422(admin_client):
    assert admin_client.put("/admin/smtp", json={"host": "   "}).status_code == 422
