from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.merchant import Merchant


class MerchantRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, merchant_id: str) -> Optional[Merchant]:
        return self.session.get(Merchant, merchant_id)

    def get_by_slug(self, slug: str) -> Optional[Merchant]:
        stmt = select(Merchant).where(Merchant.slug == slug.strip().lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def create(self, merchant: Merchant) -> Merchant:
        self.session.add(merchant)
        self.session.flush()
        return merchant

    def list_all(self, limit: int = 50) -> Sequence[Merchant]:
        stmt = select(Merchant).order_by(Merchant.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()
