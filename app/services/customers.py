"""Clientes como Party (rol customer, contextual -- ver app/services/suppliers.py)
con extension opcional de facturacion (party_billing: cuit/condicion_iva),
mismo patron que `client_billing` de Gestiolibra. La extension es opcional
porque en retail la mayoria de las ventas son a "Consumidor Final" sin
cliente registrado -- solo hace falta un Customer si se va a facturar A/B
con CUIT real.
"""

from libracommerce.domain.entities import Party, PartyType
from libracore.db import clients as db_clients
from libracore.db.core import Conexion

from ..commerce import repositorio


class CustomerService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.PERSON,
        email: str | None = None, phone: str | None = None,
        cuit: str | None = None, condicion_iva: str | None = None,
    ) -> dict:
        party = self._repo.save_party(
            Party(id=None, party_type=party_type, display_name=display_name, email=email, phone=phone)
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO party_roles (party_id, role) VALUES (?, 'customer')", (party.id,)
        )
        if cuit or condicion_iva:
            self._conn.execute(
                "INSERT INTO party_billing (party_id, cuit, condicion_iva) VALUES (?, ?, ?)",
                (party.id, cuit, condicion_iva),
            )
        self._conn.commit()
        # 🔴 Crea de una el `clients.id` enlazado por `external_ref = party-<id>`
        # (misma función que usa `CuentaCorrienteService._cliente_cc`/
        # `app/ganchos.py::cliente_cc_de`, no se duplica la lógica). Sin esto la
        # fila nacía recién cuando alguien pedía LA CUENTA de este cliente
        # puntual (`GET /accounts/{party_id}`): un cliente que fía por primera
        # vez no aparecía en `GET /accounts` (`get_clientes_con_saldo_cc`), que
        # sólo enumera `clients` ya existentes -- ver F3, ADR-025.
        db_clients.resolver_cliente_externo(
            f"party-{party.id}", display_name, cuit_dni=cuit or "", email=email or "", phone=phone or "",
        )
        return self._to_out(party)

    def get(self, party_id: int) -> dict | None:
        party = self._repo.get_party(party_id)
        return self._to_out(party) if party is not None else None

    def list_all(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT p.id FROM parties p
            JOIN party_roles pr ON pr.party_id = p.id AND pr.role = 'customer'
            WHERE p.active = 1
            ORDER BY p.display_name
            """
        ).fetchall()
        return [self._to_out(self._repo.get_party(row[0])) for row in rows]

    def _to_out(self, party: Party) -> dict:
        billing = self._conn.execute(
            "SELECT cuit, condicion_iva FROM party_billing WHERE party_id = ?", (party.id,)
        ).fetchone()
        return {
            "id": party.id, "party_type": party.party_type, "display_name": party.display_name,
            "email": party.email, "phone": party.phone, "active": party.active,
            "cuit": billing[0] if billing else None,
            "condicion_iva": billing[1] if billing else None,
        }
