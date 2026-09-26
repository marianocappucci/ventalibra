"""Clientes, sobre el modelo del motor: `libracore.db.clients` (tabla `clients`).

Desde la migración `0004` (2026-09-26) VentaLibra sigue la misma convención que Contalibra y
Restolibra: **el cliente vive en `clients` y su `parties` espejo tiene el MISMO id**
(`libracore.db.clients.create_client` lo crea en la misma transacción). El id que devuelve este
servicio es, por lo tanto, a la vez el `clients.id` (cuenta corriente, facturas, remitos) y el
`parties.id` (`sales.customer_party_id`): ya no hay nada que traducir.

Antes el origen era `parties` + `party_billing` y `clients` era un espejo con otro id
(`external_ref = party-<id>`). `parties`, `party_roles` y `party_billing` quedan como datos
históricos y espejo; este servicio ya no los lee.

Es una capa fina que conserva el contrato de `GET/POST /customers` que usan hoy el POS y la
pantalla de Clientes; la fase 2 de la adopción de los motores la reemplaza por el router del motor
(`/api/clientes`).
"""

from libracommerce.domain.entities import PartyType
from libracore.db import clients as db_clients
from libracore.db.core import Conexion


class CustomerService:
    def __init__(self, conn: Conexion):
        self._conn = conn

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.PERSON,  # noqa: ARG002
        email: str | None = None, phone: str | None = None,
        cuit: str | None = None, condicion_iva: str | None = None,
    ) -> dict:
        """Levanta `ValueError` si el CUIT/DNI ya lo tiene otro cliente (regla del motor).

        `party_type` se acepta por compatibilidad del contrato y se ignora: `clients` no lo guarda.
        """
        client_id = db_clients.create_client(
            display_name, cuit_dni=cuit or "", email=email or "", phone=phone or "",
            iva_condition=condicion_iva or "",
        )
        return self._to_out(db_clients.get_client(client_id))

    def get(self, client_id: int) -> dict | None:
        client = db_clients.get_client(client_id)
        return self._to_out(client) if client is not None else None

    def list_all(self) -> list[dict]:
        return [self._to_out(c) for c in db_clients.get_all_clients()]

    @staticmethod
    def _to_out(client: dict) -> dict:
        return {
            "id": client["id"], "party_type": PartyType.PERSON.value,
            "display_name": client["name"],
            "email": client.get("email") or None, "phone": client.get("phone") or None,
            "active": bool(client.get("activo", 1)),
            "cuit": client.get("cuit_dni") or None,
            "condicion_iva": client.get("iva_condition") or None,
        }
