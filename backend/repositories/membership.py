from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.merchant import MerchantMembership, MerchantRole


class MembershipRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, membership_id: str) -> Optional[MerchantMembership]:
        return self.session.get(MerchantMembership, membership_id)

    def get_membership(self, user_id: str, merchant_id: str) -> Optional[MerchantMembership]:
        stmt = select(MerchantMembership).where(
            MerchantMembership.user_id == user_id,
            MerchantMembership.merchant_id == merchant_id,
            MerchantMembership.is_active == True,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_user_memberships(self, user_id: str) -> Sequence[MerchantMembership]:
        stmt = (
            select(MerchantMembership)
            .where(MerchantMembership.user_id == user_id, MerchantMembership.is_active == True)
            .order_by(MerchantMembership.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_merchant_memberships(self, merchant_id: str) -> Sequence[MerchantMembership]:
        stmt = (
            select(MerchantMembership)
            .where(MerchantMembership.merchant_id == merchant_id, MerchantMembership.is_active == True)
            .order_by(MerchantMembership.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def create(self, membership: MerchantMembership) -> MerchantMembership:
        self.session.add(membership)
        self.session.flush()
        return membership

    def delete(self, membership: MerchantMembership) -> None:
        self.session.delete(membership)
        self.session.flush()
