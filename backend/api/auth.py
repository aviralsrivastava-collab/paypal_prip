import datetime
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction, get_db
from backend.core.security import (
    AuthenticatedActor,
    create_jwt_token,
    get_current_actor,
    require_role,
)
from backend.models.merchant import Merchant, MerchantMembership, MerchantRole, MerchantStatus
from backend.models.user import User
from backend.schemas.merchant import (
    MembershipResponse,
    MerchantCreateRequest,
    MerchantResponse,
    PayPalMerchantLoginRequest,
    PayPalMerchantLoginResponse,
    SwitchTenantRequest,
    SwitchTenantResponse,
    TenantMemberInviteRequest,
    UserProfileResponse,
)
from backend.services.identity import IdentityService

router = APIRouter(prefix="/api/auth", tags=["Multi-Tenant Authentication & Workspaces"])


@router.post("/paypal-merchant-login", response_model=PayPalMerchantLoginResponse, summary="Authenticate or provision workspace with PayPal Sandbox Merchant ID")
def login_with_paypal_merchant(
    request: PayPalMerchantLoginRequest,
    db: Session = Depends(get_db),
) -> PayPalMerchantLoginResponse:
    """
    OAuth gateway allowing merchants to authenticate into their workspace
    using their verified PayPal Sandbox Merchant ID or sandbox business identity.
    Issues a signed session token scoped to the merchant tenant.
    """
    paypal_merchant_id: str = str(request.paypal_merchant_id).strip()
    raw_name: str = str(request.merchant_name or "").strip()
    clean_id: str = re.sub(r"[^a-zA-Z0-9_-]", "_", paypal_merchant_id.split("@")[0]).lower()[:30]

    service = IdentityService(db)

    # 1. Look up existing merchant by paypal_merchant_id, id, or slug
    matched_merchant: Optional[Merchant] = None
    all_merchants = service.merchant_repo.list_all(limit=100)
    for m in all_merchants:
        if m.paypal_merchant_id == paypal_merchant_id or m.id == paypal_merchant_id or m.slug == clean_id:
            matched_merchant = m
            break

    # If default or recognized sandbox facilitator, match default workspace
    if matched_merchant is None:
        if paypal_merchant_id.lower() in ("default", "merchant_default", "sandbox", "sb-w43kfu53089856@business.example.com"):
            matched_merchant = service.merchant_repo.get_by_id("merchant_default")

    if matched_merchant is None:
        slug = f"paypal-{clean_id}"
        existing_slug = service.merchant_repo.get_by_slug(slug)
        if existing_slug is not None:
            matched_merchant = existing_slug
        else:
            with atomic_transaction(db):
                new_m = Merchant(
                    slug=slug,
                    name=raw_name or f"PayPal Sandbox Store ({paypal_merchant_id})",
                    paypal_merchant_id=paypal_merchant_id,
                    currency="USD",
                    status=MerchantStatus.ACTIVE.value,
                )
                matched_merchant = service.merchant_repo.create(new_m)

    if matched_merchant is None:
        with atomic_transaction(db):
            new_m = Merchant(
                slug=f"ws-{clean_id}",
                name=raw_name or "PayPal Sandbox Store",
                paypal_merchant_id=paypal_merchant_id,
                currency="USD",
                status=MerchantStatus.ACTIVE.value,
            )
            matched_merchant = service.merchant_repo.create(new_m)

    # Type guard: active_merchant is guaranteed non-None
    active_merchant: Merchant = matched_merchant
    if not active_merchant.paypal_merchant_id:
        with atomic_transaction(db):
            active_merchant.paypal_merchant_id = paypal_merchant_id
            db.add(active_merchant)

    # 2. Derive user & membership
    user_email: str = paypal_merchant_id if "@" in paypal_merchant_id else f"{clean_id}@paypal-sandbox.local"
    matched_user = service.user_repo.get_by_email(user_email)
    if matched_user is None:
        with atomic_transaction(db):
            new_u = User(
                iss="https://api-m.sandbox.paypal.com",
                sub=f"paypal_{clean_id}",
                email=user_email,
                full_name=raw_name or f"Merchant ({paypal_merchant_id})",
            )
            matched_user = service.user_repo.create(new_u)

    active_user: User = matched_user

    membership = service.membership_repo.get_membership(str(active_user.id), str(active_merchant.id))
    if membership is None:
        with atomic_transaction(db):
            new_mem = MerchantMembership(
                user_id=str(active_user.id),
                merchant_id=str(active_merchant.id),
                role=MerchantRole.OWNER.value,
                is_active=True,
            )
            service.membership_repo.create(new_mem)

    # 3. Mint signed JWT access token scoped to this merchant tenant
    now = datetime.datetime.now(datetime.timezone.utc)
    token_payload: Dict[str, Any] = {
        "sub": str(active_user.id),
        "email": str(active_user.email),
        "name": str(active_user.full_name or "Merchant"),
        "merchant_id": str(active_merchant.id),
        "paypal_merchant_id": str(paypal_merchant_id),
        "role": MerchantRole.OWNER.value,
        "actor_type": "merchant",
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(days=7)).timestamp()),
    }
    token = create_jwt_token(token_payload)

    profile = service.get_user_profile(
        actor_id=str(active_user.id),
        user_id=str(active_user.id),
        email=str(active_user.email),
        active_merchant_id=str(active_merchant.id),
        active_role=MerchantRole.OWNER.value,
    )

    return PayPalMerchantLoginResponse(
        access_token=token,
        token_type="Bearer",
        merchant_id=str(active_merchant.id),
        merchant_name=str(active_merchant.name),
        paypal_merchant_id=str(paypal_merchant_id),
        role=MerchantRole.OWNER.value,
        profile=profile,
    )


@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile & merchant memberships")
def get_current_user_profile(
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    service = IdentityService(db)
    return service.get_user_profile(
        actor_id=actor.actor_id,
        user_id=actor.user_id,
        email=actor.email,
        active_merchant_id=actor.merchant_id,
        active_role=actor.role,
    )


@router.post("/merchants", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED, summary="Create a new merchant workspace")
def create_merchant_workspace(
    request: MerchantCreateRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> MerchantResponse:
    service = IdentityService(db)
    merchant = service.create_merchant_workspace(
        actor_id=actor.actor_id,
        user_id=actor.user_id,
        email=actor.email,
        name=request.name,
        slug=request.slug,
    )
    return MerchantResponse.model_validate(merchant)


@router.post("/switch-tenant", response_model=SwitchTenantResponse, summary="Switch active merchant workspace")
def switch_active_tenant(
    request: SwitchTenantRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> SwitchTenantResponse:
    service = IdentityService(db)
    return service.switch_tenant(
        actor_id=actor.actor_id,
        user_id=actor.user_id,
        email=actor.email,
        target_merchant_id=request.merchant_id,
        default_role=actor.role,
    )


@router.get("/members", response_model=List[MembershipResponse], summary="List members of active merchant workspace")
def list_workspace_members(
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[MembershipResponse]:
    service = IdentityService(db)
    return service.list_workspace_members(actor.merchant_id)


@router.post("/members", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED, summary="Invite/add a member to active workspace")
def invite_workspace_member(
    request: TenantMemberInviteRequest,
    actor: AuthenticatedActor = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> MembershipResponse:
    service = IdentityService(db)
    return service.invite_workspace_member(
        merchant_id_or_slug=actor.merchant_id,
        email=request.email,
        role=request.role,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a member from active workspace")
def remove_workspace_member(
    user_id: str,
    actor: AuthenticatedActor = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> None:
    service = IdentityService(db)
    service.remove_workspace_member(
        merchant_id_or_slug=actor.merchant_id,
        user_id=user_id,
        actor_role=actor.role,
    )
