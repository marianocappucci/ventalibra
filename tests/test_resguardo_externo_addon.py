"""El add-on `resguardo_externo` y el router del enlace con la nube.

🔴 **El riesgo que custodian estos tests no es el router: es el gate.**
`ModuleRepository.is_enabled` devolvia `True` para cualquier modulo fuera de
`plans.TODOS_LOS_MODULOS` y tambien cuando faltaba la fila. Un add-on queda
afuera de ese set a proposito, asi que con esa regla
`require_module("resguardo_externo")` no cortaba nunca: el enlace con la nube
del cliente quedaba abierto en todas las instancias, sin que el backoffice lo
hubiera prendido en ninguna.

Por eso el caso que importa es el primero (sin fila -> 403), y es el que se
verifico poniendolo en rojo con la rama de add-ons de `is_enabled` revertida.
"""
import pytest

import plans

URL = "/api/config/resguardo-externo/enlace"
ADDON = "resguardo_externo"


@pytest.fixture(autouse=True)
def _data_dir_temporal(monkeypatch, tmp_path):
    # Con la base en PostgreSQL, la carpeta de backups sale de `DATA_DIR`
    # (`app.main._carpeta_de_backups`). Sin esto caeria en `./data/backups`,
    # dentro del checkout. Autouse: corre antes de que `admin_client` arme la app.
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


def test_sin_fila_el_addon_esta_apagado_y_da_403(admin_client):
    from app.database import get_modulos

    assert ADDON not in get_modulos(), "el add-on no tiene que sembrarse"
    # El 403 primero: es lo que ve el cliente, y lo que se puso en rojo con la
    # rama de add-ons de `is_enabled` revertida.
    assert admin_client.get(URL).status_code == 403
    assert admin_client.app.state.modules.is_enabled(ADDON) is False


def test_con_la_fila_apagada_da_403(admin_client):
    from app.database import get_modulos, set_addon

    set_addon(ADDON, False)
    assert get_modulos()[ADDON] is False
    assert admin_client.get(URL).status_code == 403


def test_prendido_el_admin_ve_el_enlace(admin_client):
    from app.database import set_addon

    set_addon(ADDON, True)
    r = admin_client.get(URL)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert "proveedores" in cuerpo
    assert "enlace" in cuerpo


def test_prender_y_apagar_tiene_efecto_inmediato(admin_client):
    """`require_module` relee la fila en cada request: el backoffice no tiene
    que reiniciar el contenedor para que el toggle se note."""
    from app.database import set_addon

    set_addon(ADDON, True)
    assert admin_client.get(URL).status_code == 200
    set_addon(ADDON, False)
    assert admin_client.get(URL).status_code == 403


def test_el_cajero_no_entra_aunque_el_addon_este_prendido(staff_client):
    from app.database import set_addon

    set_addon(ADDON, True)
    assert staff_client.get(URL).status_code == 403
    assert staff_client.delete(URL).status_code == 403
    assert staff_client.post(f"{URL}/drive").status_code == 403


def test_un_modulo_de_plan_sin_fila_sigue_habilitado(admin_client):
    """Regresion: la regla nueva es SOLO para add-ons. Un modulo de plan sin fila
    se sigue tratando como habilitado, igual que antes."""
    conn = admin_client.app.state.conn
    conn.execute("DELETE FROM modulos WHERE modulo = ?", ("facturacion",))
    conn.commit()
    assert admin_client.app.state.modules.is_enabled("facturacion") is True
    # Y un modulo que no es de plan ni add-on, tampoco se gatea.
    assert admin_client.app.state.modules.is_enabled("cualquier_otro") is True
    assert admin_client.get("/config/arca").status_code != 403


def test_el_addon_esta_afuera_de_los_planes():
    assert ADDON in plans.ADDONS
    assert ADDON not in plans.TODOS_LOS_MODULOS
    for plan in plans.PLANES:
        assert ADDON not in plans.modulos_de_plan(plan), plan


def test_contrato_del_backoffice_importa():
    """El snippet que corre el backoffice por `docker exec` es exactamente
    `from app.database import get_modulos` / `set_addon`
    (`libracore.admin.services`)."""
    from app.database import get_modulos, set_addon

    assert callable(get_modulos)
    assert callable(set_addon)


def test_backoffice_y_gate_leen_la_misma_base(admin_client):
    """🔴 `set_addon` escribe por el core de LibraCore y el gate lee por la
    conexion del dominio. Si apuntaran a bases distintas, el backoffice
    prenderia el add-on en una y la app lo seguiria viendo apagado en la otra."""
    from app.database import get_modulos, set_addon

    set_addon(ADDON, True)
    assert admin_client.app.state.modules.get_all() == get_modulos()
    assert admin_client.app.state.modules.is_enabled(ADDON) is True


def test_sin_arranque_se_configura_sola_contra_la_base_del_dominio(admin_client, monkeypatch):
    """El caso del `docker exec`: nadie llamo a `create_app()`, asi que el core
    esta sin configurar. Se resuelve con la URL del dominio de la instancia."""
    from libracore.db import core
    from motor_de_test import TEST_DATABASE_URL

    from app.database import get_modulos

    monkeypatch.setattr(core, "_db_path", None)
    monkeypatch.setattr(core, "_database_url", None)
    monkeypatch.delenv("VENTALIBRA_DATABASE_URL", raising=False)
    monkeypatch.setenv("VENTALIBRA_DB_PATH", TEST_DATABASE_URL)
    assert not core.esta_configurado()

    assert get_modulos() == admin_client.app.state.modules.get_all()
    assert core.esta_configurado()
