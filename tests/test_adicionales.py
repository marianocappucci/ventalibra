"""Los adicionales fuera de la escalera (ADR-082; ADR-048 del motor): el catálogo de VentaLibra, el abono por líneas y el router de la instancia.

El abono de las sucursales NO cambia (ADR-073): el camino nuevo (`resolver` + `calcular_abono_total`) da lo mismo que `calcular_abono`. El router nuevo
convive con `/api/limites/sucursales` y los dos escriben la misma clave del `config.json`.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from libracore import adicionales as ad
from libracore.abono import calcular_abono
from libracore.admin import services
from motor_de_test import destino_dominio

import plans
from app.main import create_app

TOKEN = "un-token-de-servicio-de-prueba"
SERVICIO = {SERVICE_TOKEN_HEADER: TOKEN}
RUTA = "/api/adicionales"
BASE = plans.PLAN_PRECIOS["unico"]
ADICIONAL = plans.PLAN_UNIDADES_ADICIONALES["unico"]["precio"]


@pytest.fixture
def sin_sesion(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        yield client


# ── el catálogo ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_catalogo_declarado_es_el_mismo_que_se_sintetizaba():
    """`ADICIONALES` no inventa nada: dice lo que ya decían `ADDONS` y `PLAN_UNIDADES_ADICIONALES` (precio y sucursal incluida)."""
    cat = ad.catalogo(plans)
    assert sorted(cat) == ["resguardo_externo", "sucursal"]
    sucursal = cat["sucursal"]
    assert (sucursal.precio, sucursal.unidad, sucursal.incluidas, sucursal.limite, sucursal.modulos) == (
        ADICIONAL, "sucursal", {"unico": plans.PLAN_UNIDADES_ADICIONALES["unico"]["incluidas"]}, "sucursales", frozenset())
    assert (cat["resguardo_externo"].precio, cat["resguardo_externo"].modulos) == (None, frozenset({"resguardo_externo"}))
    assert ad.modulos_de_adicionales(plans) == plans.ADDONS == {"resguardo_externo"}


def test_los_adicionales_no_estan_en_la_escalera():
    for plan in plans.PLANES:
        assert not ad.modulos_de_adicionales(plans) & plans.modulos_de_plan(plan)


@pytest.mark.parametrize("contratadas, total", [(1, BASE), (2, BASE + ADICIONAL), (3, BASE + 2 * ADICIONAL), (10, BASE + 9 * ADICIONAL)])
def test_el_abono_de_n_sucursales_es_la_base_mas_las_adicionales(contratadas, total):
    """Regresión del ADR-048: 3 sucursales = 39.900 + 2 × 19.950, por el camino nuevo y por `calcular_abono`."""
    lineas = ad.resolver(plans, "unico", {"sucursal": contratadas})["lineas_abono"]
    assert ad.calcular_abono_total(BASE, lineas)["total"] == total == calcular_abono(BASE, 1, ADICIONAL, contratadas)["total"]
    assert total == 39900 + (contratadas - 1) * 19950


def test_el_resguardo_externo_sale_a_cotizar_y_no_suma():
    abono = ad.calcular_abono_total(BASE, ad.resolver(plans, "unico", {"sucursal": 3, "resguardo_externo": True})["lineas_abono"])
    assert abono["total"] == 79800 and abono["a_cotizar"] == ["resguardo_externo"]


def test_planes_info_trae_los_adicionales_del_plan_unico(monkeypatch, tmp_path):
    """Lo que el backoffice lista: la sucursal con su precio y su incluida, y el resguardo a cotizar."""
    monkeypatch.setattr(services, "_plans", lambda: plans)
    (unico,) = services.planes_info()
    por_clave = {a["clave"]: a for a in unico["adicionales"]}
    assert (por_clave["sucursal"]["precio"], por_clave["sucursal"]["incluidas"]) == (19950, 1)
    assert por_clave["resguardo_externo"]["precio"] is None
    assert unico["adicional"] == plans.PLAN_UNIDADES_ADICIONALES["unico"]  # el campo viejo sigue, para un backoffice anterior


# ── el router de la instancia ────────────────────────────────────────────────────────────────────────────────────────


def _item(client, clave, **kw):
    return next(i for i in client.get(RUTA, **kw).json()["adicionales"] if i["clave"] == clave)


def test_get_dice_lo_contratado_y_lo_usado(admin_client):
    sucursal = _item(admin_client, "sucursal")
    assert (sucursal["cantidad"], sucursal["usadas"], sucursal["precio"], sucursal["incluidas"]) == (None, 1, 19950, {"unico": 1})
    assert _item(admin_client, "resguardo_externo")["habilitado"] is False
    assert admin_client.get(RUTA).json()["limites"] == {}


def test_el_backoffice_carga_las_sucursales_por_el_router_nuevo_y_la_instancia_las_hace_cumplir(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.put(f"{RUTA}/sucursal", json={"cantidad": 1}, headers=SERVICIO)
    assert r.status_code == 200, r.text
    assert (r.json()["cantidad"], r.json()["usadas"]) == (1, 1)
    from libracore import limites

    assert limites.sucursales_contratadas() == 1  # el mismo dato que lee el gancho de alta
    assert sin_sesion.get("/api/limites/sucursales", headers=SERVICIO).json() == {"contratadas": 1, "activas": 1, "mensaje_de_limite": limites.mensaje_de_limite(1)}  # el alias ve lo mismo
    with pytest.raises(limites.LimiteExcedido):
        limites.verificar_alta_de_sucursal(1)


def test_el_alias_y_el_router_nuevo_escriben_la_misma_clave(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    sin_sesion.put("/api/limites/sucursales", json={"contratadas": 4}, headers=SERVICIO)
    assert _item(sin_sesion, "sucursal", headers=SERVICIO)["cantidad"] == 4
    sin_sesion.put(f"{RUTA}/sucursal", json={"cantidad": None}, headers=SERVICIO)
    assert sin_sesion.get("/api/limites/sucursales", headers=SERVICIO).json()["contratadas"] is None


def test_el_resguardo_externo_se_prende_y_apaga_por_el_router(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.put(f"{RUTA}/resguardo_externo", json={"habilitado": True}, headers=SERVICIO).json()["habilitado"] is True
    assert sin_sesion.app.state.modules.is_enabled("resguardo_externo") is True  # lo que lee `require_module`
    assert sin_sesion.put(f"{RUTA}/resguardo_externo", json={"habilitado": False}, headers=SERVICIO).json()["habilitado"] is False
    assert sin_sesion.app.state.modules.is_enabled("resguardo_externo") is False


def test_el_admin_de_la_instancia_lee_pero_no_puede_contratar(admin_client):
    """🔴 Un adicional es un límite comercial: el admin del cliente no se lo da."""
    assert admin_client.get(RUTA).status_code == 200
    assert admin_client.put(f"{RUTA}/sucursal", json={"cantidad": 50}).status_code == 403
    assert admin_client.put(f"{RUTA}/resguardo_externo", json={"habilitado": True}).status_code == 403
    assert _item(admin_client, "sucursal")["cantidad"] is None and _item(admin_client, "resguardo_externo")["habilitado"] is False


def test_sin_sesion_ni_token_ni_lee_ni_escribe(sin_sesion):
    assert sin_sesion.get(RUTA).status_code == 401
    assert sin_sesion.put(f"{RUTA}/sucursal", json={"cantidad": 5}).status_code == 401
