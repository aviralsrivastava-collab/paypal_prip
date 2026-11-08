from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.evidence import EvidenceItem


class EvidenceRepository:
    """
    Repository for immutable structured evidence items.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, item: EvidenceItem) -> EvidenceItem:
        self.session.add(item)
        self.session.flush()
        return item

    def create_many(self, items: Sequence[EvidenceItem]) -> Sequence[EvidenceItem]:
        self.session.add_all(items)
        self.session.flush()
        return items

    def list_by_scan_id(self, scan_id: int, include_quarantined: bool = False) -> Sequence[EvidenceItem]:
        stmt = select(EvidenceItem).where(EvidenceItem.scan_id == scan_id)
        if not include_quarantined:
            stmt = stmt.where(EvidenceItem.merchant_id != "QUARANTINED_ORPHAN")
        stmt = stmt.order_by(EvidenceItem.id.asc())
        return self.session.execute(stmt).scalars().all()
