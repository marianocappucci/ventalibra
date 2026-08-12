#!/usr/bin/env python3
"""
Panel de administración VentaLibra.
Gestiona todos los contenedores de clientes desde un menú interactivo.
Uso: python3 scripts/panel_admin.py [comando] [slug]
     python3 scripts/panel_admin.py           → menú interactivo
     python3 scripts/panel_admin.py listar
     python3 scripts/panel_admin.py backup micliente

Wrapper de configuración sobre libracore.provisioning.panel_admin (lógica
compartida con Contalibra/Restolibra/Gestiolibra/MedLibra — ver
wiki/entities/libracore.md). Solo fija las constantes propias de
VentaLibra; la lógica real vive en LibraCore.
"""
from pathlib import Path

from libracore.provisioning import configure, client_from_config, forward_host_from_config, le_email_from_config, npm_available
from libracore.provisioning.panel_admin import (
    cli, cmd_activar, cmd_backup, cmd_backup_all, cmd_eliminar, cmd_estado_servicio,
    cmd_info, cmd_list_backups, cmd_listar, cmd_logs, cmd_npm_crear, cmd_npm_eliminar,
    cmd_npm_listar, cmd_pausar, cmd_restart, cmd_restore_db, cmd_start, cmd_stop,
    cmd_suspender, cmd_actualizar, compose, container_status, find_client, interactive,
    load_clients, pick_client, _set_servicio_estado,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    # El backup del cron arma el MISMO ZIP que la pantalla de Backups, en
    # `data/backups/`, en vez de un `tar.gz` aparte que la pantalla no lista
    # y el cliente no puede restaurar. Requiere libracore >= v1.29.0.
    #
    # Este producto puede prenderlo porque su pantalla sale de
    # `libracore.respaldo` (`build_backup_router` en app/main.py). Contalibra
    # y Restolibra tienen implementacion propia y todavia no.
    backup_zip=True,
    postgres=True,
    product_name="VENTALIBRA",
    image_name="ventalibra:latest",
    container_prefix="ventalibra",
    db_filename="ventalibra.db",
    repo_root=REPO_ROOT,
    base_port=8082,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"
_NPM_AVAILABLE = npm_available()

if __name__ == "__main__":
    cli()
