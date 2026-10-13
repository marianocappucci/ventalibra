"""El arranque de VentaLibra con varios procesos (`uvicorn --workers N`; hoy N = 1).

El candado y sus 2 workers de verdad los prueba el motor (`libracore/tests/test_varios_procesos.py`). Lo que se cuida acá
es que **las siembras del arranque estén adentro del candado**: sin `una_vez_al_arrancar`, dos workers que arrancan juntos
contestan los dos «no existe» y crean el admin (o la caja de cada sucursal) dos veces.
"""
import contextlib

from motor_de_test import destino_dominio

from app import main as principal


def test_las_siembras_del_arranque_corren_adentro_de_una_vez_al_arrancar(tmp_path, monkeypatch):
    eventos = []

    @contextlib.contextmanager
    def espia(nombre, **kw):
        eventos.append(("entra", nombre, kw.get("destino")))
        try:
            yield
        finally:
            eventos.append(("sale", nombre))

    def espiar(nombre, original):
        def envuelta(*a, **k):
            eventos.append(nombre)
            return original(*a, **k)
        return envuelta

    monkeypatch.setattr(principal, "una_vez_al_arrancar", espia)
    monkeypatch.setattr(principal.cajas_service, "asegurar_cajas_de_todas",
                        espiar("cajas", principal.cajas_service.asegurar_cajas_de_todas))
    monkeypatch.setattr(principal, "ensure_default_admin", espiar("admin", principal.ensure_default_admin))
    monkeypatch.setattr(principal, "ensure_demo_user", espiar("demo", principal.ensure_demo_user))

    db_path = destino_dominio(tmp_path / "ventalibra.db")
    app = principal.create_app(db_path)
    try:
        assert eventos == [
            ("entra", "ventalibra-sembrar", db_path), "cajas", ("sale", "ventalibra-sembrar"),
            ("entra", "ventalibra-sembrar", db_path), "admin", "demo", ("sale", "ventalibra-sembrar"),
        ]
    finally:
        app.state.auth_engine.dispose()
