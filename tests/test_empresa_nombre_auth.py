"""El nombre del negocio del sidebar sale del JSON de la config, sin tocar el almacén de secretos."""
import json

from libracore import config_manager

from app.routers import auth


def test_empresa_nombre_lee_el_json_sin_resolver_secretos(tmp_path, monkeypatch):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"empresa_nombre": "  Kiosco Ana "}), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(ruta))
    monkeypatch.setattr(config_manager, "load", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe usar load()")))
    assert auth._extras(None, {"role": "admin"})["empresa_nombre"] == "  Kiosco Ana ".strip()


def test_empresa_nombre_vacio_o_sin_archivo_es_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "no-existe.json"))
    assert "empresa_nombre" not in auth._extras(None, {"role": "admin"})
    (tmp_path / "c.json").write_text(json.dumps({"empresa_nombre": ""}), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "c.json"))
    assert "empresa_nombre" not in auth._extras(None, {"role": "admin"})
