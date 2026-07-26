"""Clientes como Party (rol customer, contextual -- ver app/services/suppliers.py)
con extension opcional de facturacion (party_billing: cuit/condicion_iva),
mismo patron que `client_billing` de Gestiolibra. La extension es opcional
porque en retail la mayoria de las ventas son a "Consumidor Final" sin
cliente registrado -- solo hace falta un Customer si se va a facturar A/B
con CUIT real.
"""
import sqlite3

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.entities import Party, PartyType


class CustomerService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = SqliteCommerceRepository(conn)

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.PERSON,
        email: str | None = None, phone: str | None = None,
        cuit: str | None = None, condicion_iva: str | None = None,
    ) -> dict:
        party = self._repo.save_party(
            Party(id=None, party_type=party_type, display_name=display_name, email=email, phone=phone)
        )
        if cuit or condicion_iva:
            self._conn.execute(
                "INSERT INTO party_billing (party_id, cuit, condicion_iva) VALUES (?, ?, ?)",
                (party.id, cuit, condicion_iva),
            )
            self._conn.commit()
        return self._to_out(party)

    def get(self, party_id: int) -> dict | None:
        party = self._repo.get_party(party_id)
        return self._to_out(party) if party is not None else None

    def list_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id FROM parties WHERE active = 1 ORDER BY display_name"
        ).fetchall()
        return [self._to_out(self._repo.get_party(row[0])) for row in rows]

    def get_billing(self, party_id: int) -> dict | None:
        """cuit/condicion_iva de un cliente, para facturar -- None si nunca
        se le cargo esa extension (venta ad-hoc sin datos fiscales)."""
        row = self._conn.execute(
            "SELECT cuit, condicion_iva FROM party_billing WHERE party_id = ?", (party_id,)
        ).fetchone()
        if row is None:
            return None
        party = self._repo.get_party(party_id)
        return {"cuit": row[0], "condicion_iva": row[1], "display_name": party.display_name if party else ""}

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
