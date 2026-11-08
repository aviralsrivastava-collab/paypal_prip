from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.scan import StorefrontScan


class ScanRepository:
    """
    Repository for storefront inspection scans.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, scan: StorefrontScan) -> StorefrontScan:
        self.session.add(scan)
        self.session.flush()
        return scan

    def get_by_id(self, scan_id: int) -> Optional[StorefrontScan]:
        return self.session.get(StorefrontScan, scan_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[StorefrontScan]:
        stmt = select(StorefrontScan).where(StorefrontScan.idempotency_key == idempotency_key)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_sku(self, sku: str, merchant_id: Optional[str] = None) -> Sequence[StorefrontScan]:
        stmt = select(StorefrontScan).where(StorefrontScan.sku == sku)
        if merchant_id is not None:
            stmt = stmt.where(StorefrontScan.merchant_id == merchant_id)
        stmt = stmt.order_by(StorefrontScan.created_at.desc())
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_sku(self, sku: str, merchant_id: Optional[str] = None) -> Optional[StorefrontScan]:
        stmt = select(StorefrontScan).where(StorefrontScan.sku == sku)
        if merchant_id is not None:
            stmt = stmt.where(StorefrontScan.merchant_id == merchant_id)
        stmt = stmt.order_by(StorefrontScan.created_at.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()
