"""Proveedores como Party (rol supplier, ver ROADMAP.md Fase 2).

PartyRole.SUPPLIER no se persiste -- libracommerce.domain.entities.Party no
tiene columna de rol (ver libracommerce/db/schema.py); el rol es contextual,
lo mismo que ya vale para customer_party_id en Sale y supplier_party_id en
PurchaseOrder/PurchaseReceipt. Este servicio es un wrapper fino sobre
save_party/get_party mas un listado propio, igual que CatalogService.
"""

from ..commerce import repositorio
from libracommerce.domain.entities import Party, PartyType
from libracore.db.core import Conexion


class SupplierService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.ORGANIZATION,
        legal_name: str | None = None, tax_id: str | None = None,
        email: str | None = None, phone: str | None = None,
    ) -> Party:
        party = Party(
            id=None, party_type=party_type, display_name=display_name,
            legal_name=legal_name, tax_id=tax_id, email=email, phone=phone,
        )
        saved = self._repo.save_party(party)
        self._conn.execute(
            "INSERT OR IGNORE INTO party_roles (party_id, role) VALUES (?, 'supplier')", (saved.id,)
        )
        self._conn.commit()
        return saved

    def get(self, party_id: int) -> Party | None:
        return self._repo.get_party(party_id)

    def list_all(self) -> list[Party]:
        rows = self._conn.execute(
            """
            SELECT p.id FROM parties p
            JOIN party_roles pr ON pr.party_id = p.id AND pr.role = 'supplier'
            WHERE p.active = 1
            ORDER BY p.display_name
            """
        ).fetchall()
        return [self._repo.get_party(row[0]) for row in rows]
