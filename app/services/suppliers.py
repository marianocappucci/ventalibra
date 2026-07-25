"""Proveedores como Party (rol supplier, ver ROADMAP.md Fase 2).

PartyRole.SUPPLIER no se persiste -- libracommerce.domain.entities.Party no
tiene columna de rol (ver libracommerce/db/schema.py); el rol es contextual,
lo mismo que ya vale para customer_party_id en Sale y supplier_party_id en
PurchaseOrder/PurchaseReceipt. Este servicio es un wrapper fino sobre
save_party/get_party mas un listado propio, igual que CatalogService.
"""
import sqlite3

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.entities import Party, PartyType


class SupplierService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = SqliteCommerceRepository(conn)

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.ORGANIZATION,
        legal_name: str | None = None, tax_id: str | None = None,
        email: str | None = None, phone: str | None = None,
    ) -> Party:
        party = Party(
            id=None, party_type=party_type, display_name=display_name,
            legal_name=legal_name, tax_id=tax_id, email=email, phone=phone,
        )
        return self._repo.save_party(party)

    def get(self, party_id: int) -> Party | None:
        return self._repo.get_party(party_id)

    def list_all(self) -> list[Party]:
        rows = self._conn.execute(
            "SELECT id FROM parties WHERE active = 1 ORDER BY display_name"
        ).fetchall()
        return [self._repo.get_party(row[0]) for row in rows]
