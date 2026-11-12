from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_role,
)
from backend.schemas.merchant import (
    MerchantCreateRequest,
    MerchantResponse,
    MembershipResponse,
    SwitchTenantRequest,
    SwitchTenantResponse,
    TenantMemberInviteRequest,
    UserProfileResponse,
)
from backend.services.identity import IdentityService

router = APIRouter(prefix="/api/auth", tags=["Multi-Tenant Authentication & Workspaces"])


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
