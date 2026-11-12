import datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.models.merchant import Merchant, MerchantMembership, MerchantRole, MerchantStatus
from backend.models.user import User
from backend.repositories.membership import MembershipRepository
from backend.repositories.merchant import MerchantRepository
from backend.repositories.user import UserRepository
from backend.schemas.merchant import (
    MerchantResponse,
    MembershipResponse,
    SwitchTenantResponse,
    UserProfileResponse,
)


class IdentityService:
    """
    Business service coordinating user identity, tenant workspaces, and membership authorization.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.merchant_repo = MerchantRepository(session)

    def get_or_create_user(
        self,
        iss: str,
        sub: str,
        email: str,
        full_name: Optional[str] = None,
    ) -> User:
        return self.user_repo.get_or_create_from_claims(
            iss=iss,
            sub=sub,
            email=email,
            full_name=full_name,
        )

    def get_user_profile(
        self,
        actor_id: str,
        user_id: Optional[str],
        email: Optional[str],
        active_merchant_id: str,
        active_role: str,
    ) -> UserProfileResponse:
        user = None
        if user_id:
            user = self.user_repo.get_by_id(user_id)
        if not user and email:
            user = self.user_repo.get_by_email(email)

        if not user:
            # Construct profile from actor context for demo/test actors
            return UserProfileResponse(
                id=actor_id,
                email=email or f"{actor_id}@prip.local",
                full_name=actor_id,
                active_merchant_id=active_merchant_id,
                active_role=active_role,
                memberships=[
                    MembershipResponse(
                        id=f"mem_{actor_id}_{active_merchant_id}",
                        merchant_id=active_merchant_id,
                        merchant_name="Demo Merchant Workspace",
                        merchant_slug=active_merchant_id,
                        user_id=actor_id,
                        user_email=email or f"{actor_id}@prip.local",
                        role=active_role,
                        is_active=True,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    )
                ],
            )

        db_memberships = self.membership_repo.list_user_memberships(user.id)
        membership_items: List[MembershipResponse] = []
        for m in db_memberships:
            mch = self.merchant_repo.get_by_id(m.merchant_id)
            membership_items.append(
                MembershipResponse(
                    id=m.id,
                    merchant_id=m.merchant_id,
                    merchant_name=mch.name if mch else m.merchant_id,
                    merchant_slug=mch.slug if mch else m.merchant_id,
                    user_id=user.id,
                    user_email=user.email,
                    role=m.role,
                    is_active=m.is_active,
                    created_at=m.created_at,
                )
            )

        return UserProfileResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            active_merchant_id=active_merchant_id,
            active_role=active_role,
            memberships=membership_items,
        )

    def create_merchant_workspace(
        self,
        actor_id: str,
        user_id: Optional[str],
        email: Optional[str],
        name: str,
        slug: str,
    ) -> Merchant:
        clean_slug = slug.strip().lower()
        if self.merchant_repo.get_by_slug(clean_slug):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Merchant workspace with slug '{clean_slug}' already exists.",
            )

        user = None
        if user_id:
            user = self.user_repo.get_by_id(user_id)
        if not user and email:
            user = self.user_repo.get_by_email(email)
        if not user:
            user = self.user_repo.create(
                User(
                    iss="https://accounts.google.com",
                    sub=actor_id,
                    email=email or f"{actor_id}@prip.local",
                    full_name=actor_id,
                    is_active=True,
                )
            )

        with atomic_transaction(self.session):
            merchant = Merchant(
                slug=clean_slug,
                name=name.strip(),
                status=MerchantStatus.ACTIVE.value,
            )
            self.merchant_repo.create(merchant)

            membership = MerchantMembership(
                merchant_id=merchant.id,
                user_id=user.id,
                role=MerchantRole.OWNER.value,
                is_active=True,
            )
            self.membership_repo.create(membership)

        return merchant

    def switch_tenant(
        self,
        actor_id: str,
        user_id: Optional[str],
        email: Optional[str],
        target_merchant_id: str,
        default_role: str,
    ) -> SwitchTenantResponse:
        user = None
        if user_id:
            user = self.user_repo.get_by_id(user_id)
        if not user and email:
            user = self.user_repo.get_by_email(email)

        target_merchant = self.merchant_repo.get_by_id(target_merchant_id) or self.merchant_repo.get_by_slug(target_merchant_id)
        if not target_merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Merchant workspace '{target_merchant_id}' not found.",
            )

        if user:
            membership = self.membership_repo.get_membership(user.id, target_merchant.id)
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: You are not an authorized member of workspace '{target_merchant.name}'.",
                )
            active_role = membership.role
        else:
            if target_merchant.id in ("QUARANTINED_ORPHAN", "platform_system"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot switch to reserved system tenant.")
            active_role = default_role

        return SwitchTenantResponse(
            active_merchant_id=target_merchant.id,
            active_merchant_name=target_merchant.name,
            active_role=active_role,
            switched=True,
        )

    def list_workspace_members(self, merchant_id_or_slug: str) -> List[MembershipResponse]:
        target_merchant = self.merchant_repo.get_by_id(merchant_id_or_slug) or self.merchant_repo.get_by_slug(merchant_id_or_slug)
        merchant_id = target_merchant.id if target_merchant else merchant_id_or_slug
        merchant_name = target_merchant.name if target_merchant else merchant_id_or_slug
        merchant_slug = target_merchant.slug if target_merchant else merchant_id_or_slug

        db_members = self.membership_repo.list_merchant_memberships(merchant_id)
        results: List[MembershipResponse] = []
        for m in db_members:
            u = self.user_repo.get_by_id(m.user_id)
            results.append(
                MembershipResponse(
                    id=m.id,
                    merchant_id=m.merchant_id,
                    merchant_name=merchant_name,
                    merchant_slug=merchant_slug,
                    user_id=m.user_id,
                    user_email=u.email if u else None,
                    role=m.role,
                    is_active=m.is_active,
                    created_at=m.created_at,
                )
            )
        return results

    def invite_workspace_member(
        self,
        merchant_id_or_slug: str,
        email: str,
        role: str,
    ) -> MembershipResponse:
        target_merchant = self.merchant_repo.get_by_id(merchant_id_or_slug) or self.merchant_repo.get_by_slug(merchant_id_or_slug)
        if not target_merchant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active merchant workspace not found.")

        clean_email = email.strip().lower()
        user = self.user_repo.get_by_email(clean_email)
        if not user:
            user = self.user_repo.create(
                User(
                    iss="https://accounts.google.com",
                    sub=f"invited_{clean_email}",
                    email=clean_email,
                    full_name=clean_email.split("@")[0],
                    is_active=True,
                )
            )

        existing = self.membership_repo.get_membership(user.id, target_merchant.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User '{clean_email}' is already a member of this workspace (role: {existing.role}).",
            )

        with atomic_transaction(self.session):
            membership = MerchantMembership(
                merchant_id=target_merchant.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
            self.membership_repo.create(membership)

        return MembershipResponse(
            id=membership.id,
            merchant_id=target_merchant.id,
            merchant_name=target_merchant.name,
            merchant_slug=target_merchant.slug,
            user_id=user.id,
            user_email=user.email,
            role=membership.role,
            is_active=membership.is_active,
            created_at=membership.created_at,
        )

    def remove_workspace_member(
        self,
        merchant_id_or_slug: str,
        user_id: str,
        actor_role: str,
    ) -> None:
        target_merchant = self.merchant_repo.get_by_id(merchant_id_or_slug) or self.merchant_repo.get_by_slug(merchant_id_or_slug)
        merchant_id = target_merchant.id if target_merchant else merchant_id_or_slug

        membership = self.membership_repo.get_membership(user_id, merchant_id)
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this workspace.")

        if membership.role == MerchantRole.OWNER.value and actor_role != MerchantRole.OWNER.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only workspace Owners can remove other Owners.")

        with atomic_transaction(self.session):
            self.membership_repo.delete(membership)
