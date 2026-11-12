import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import (
    create_merchant_workspace,
    invite_workspace_member,
    list_workspace_members,
    login_with_paypal_merchant,
    remove_workspace_member,
    switch_active_tenant,
)
from backend.core.security import (
    AuthenticatedActor,
    require_role,
)
from backend.models.merchant import Merchant, MerchantMembership, MerchantRole, MerchantStatus
from backend.models.user import User
from backend.repositories.membership import MembershipRepository
from backend.repositories.merchant import MerchantRepository
from backend.repositories.user import UserRepository
from backend.schemas.merchant import (
    MerchantCreateRequest,
    PayPalMerchantLoginRequest,
    SwitchTenantRequest,
    TenantMemberInviteRequest,
)


def test_user_and_merchant_creation_and_membership(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    merchant_repo = MerchantRepository(db_session)
    membership_repo = MembershipRepository(db_session)

    # 1. Create User
    user = user_repo.create(
        User(
            iss="https://accounts.google.com",
            sub="google-sub-1001",
            email="alice@stridex.com",
            full_name="Alice Stride",
            is_active=True,
        )
    )
    assert user.id is not None
    assert user.email == "alice@stridex.com"
    user_id = str(user.id)

    # 2. Create Merchant
    merchant = merchant_repo.create(
        Merchant(
            slug="stridex-official",
            name="StrideX Official Store",
            status=MerchantStatus.ACTIVE.value,
        )
    )
    assert merchant.id is not None
    assert merchant.slug == "stridex-official"
    merchant_id = str(merchant.id)

    # 3. Create Membership as OWNER
    membership = membership_repo.create(
        MerchantMembership(
            merchant_id=merchant_id,
            user_id=user_id,
            role=MerchantRole.OWNER.value,
            is_active=True,
        )
    )
    assert membership.id is not None
    assert membership.role == "OWNER"

    # 4. Verify lookup
    found_mem = membership_repo.get_membership(user_id, merchant_id)
    assert found_mem is not None
    assert found_mem.role == "OWNER"


def test_rbac_role_hierarchy_enforcement() -> None:
    # OWNER (40) satisfies VIEWER, MANAGER, ADMIN, OWNER
    owner_actor = AuthenticatedActor(actor_id="u1", role="OWNER", merchant_id="m1")
    checker_admin = require_role("ADMIN")
    assert checker_admin(owner_actor).role == "OWNER"

    # VIEWER (10) fails ADMIN (30)
    viewer_actor = AuthenticatedActor(actor_id="u2", role="VIEWER", merchant_id="m1")
    with pytest.raises(HTTPException) as exc:
        checker_admin(viewer_actor)
    assert exc.value.status_code == 403
    assert "requires at least 'ADMIN'" in str(exc.value.detail)

    # MANAGER (20) fails ADMIN (30)
    manager_actor = AuthenticatedActor(actor_id="u3", role="MANAGER", merchant_id="m1")
    with pytest.raises(HTTPException) as exc:
        checker_admin(manager_actor)
    assert exc.value.status_code == 403


def test_auth_api_workspace_creation_and_member_invitation(db_session: Session) -> None:
    actor = AuthenticatedActor(
        actor_id="test-admin-actor",
        role="ADMIN",
        merchant_id="merchant_default",
        email="admin@puma.com",
    )

    # Create workspace
    create_req = MerchantCreateRequest(name="Puma Test Hub", slug="puma-test-hub")
    mch_res = create_merchant_workspace(create_req, actor=actor, db=db_session)
    assert mch_res.slug == "puma-test-hub"
    created_merchant_id = str(mch_res.id)

    # Duplicate slug rejected with 409
    with pytest.raises(HTTPException) as exc:
        create_merchant_workspace(create_req, actor=actor, db=db_session)
    assert exc.value.status_code == 409

    # Invite member to workspace
    admin_actor = AuthenticatedActor(
        actor_id="test-admin-actor",
        role="ADMIN",
        merchant_id=created_merchant_id,
        email="admin@puma.com",
    )
    invite_req = TenantMemberInviteRequest(email="staff.member@puma.com", role="MANAGER")
    inv_res = invite_workspace_member(invite_req, actor=admin_actor, db=db_session)
    assert inv_res.role == "MANAGER"
    assert inv_res.user_email == "staff.member@puma.com"

    # List members
    members = list_workspace_members(actor=admin_actor, db=db_session)
    assert any(m.user_email == "staff.member@puma.com" for m in members)

    # Remove member
    user_repo = UserRepository(db_session)
    staff_user = user_repo.get_by_email("staff.member@puma.com")
    assert staff_user is not None
    assert staff_user.id is not None
    remove_workspace_member(user_id=str(staff_user.id), actor=admin_actor, db=db_session)

    # Confirm removed
    remaining = list_workspace_members(actor=admin_actor, db=db_session)
    assert not any(m.user_email == "staff.member@puma.com" for m in remaining)


def test_switch_tenant_unauthorized_rejected(db_session: Session) -> None:
    user_repo = UserRepository(db_session)
    merchant_repo = MerchantRepository(db_session)
    membership_repo = MembershipRepository(db_session)

    user = user_repo.create(
        User(
            iss="https://accounts.google.com",
            sub="google-sub-2002",
            email="bob@tenant-a.com",
            full_name="Bob A",
        )
    )
    m_a = merchant_repo.create(Merchant(slug="tenant-alpha", name="Tenant Alpha"))
    m_b = merchant_repo.create(Merchant(slug="tenant-beta", name="Tenant Beta"))
    assert user.id is not None
    assert m_a.id is not None
    assert m_b.id is not None
    user_id = str(user.id)
    m_a_id = str(m_a.id)
    m_b_id = str(m_b.id)

    # Bob belongs to Alpha, not Beta
    membership_repo.create(
        MerchantMembership(merchant_id=m_a_id, user_id=user_id, role="OWNER")
    )

    bob_actor = AuthenticatedActor(
        actor_id=str(user.sub),
        user_id=user_id,
        role="OWNER",
        merchant_id=m_a_id,
        email=str(user.email or "bob@tenant-a.com"),
    )

    # Bob tries switching to Tenant Beta (unauthorized -> 403)
    with pytest.raises(HTTPException) as exc:
        switch_active_tenant(SwitchTenantRequest(merchant_id=m_b_id), actor=bob_actor, db=db_session)
    assert exc.value.status_code == 403
    assert "not an authorized member" in str(exc.value.detail)

    # Bob switching to Tenant Alpha succeeds
    ok_res = switch_active_tenant(SwitchTenantRequest(merchant_id=m_a_id), actor=bob_actor, db=db_session)
    assert ok_res.active_merchant_id == m_a_id
    assert ok_res.switched is True


def test_paypal_merchant_login_endpoint(db_session: Session) -> None:
    req = PayPalMerchantLoginRequest(
        paypal_merchant_id="sb-test-merchant-99@business.example.com",
        merchant_name="Test PayPal Store",
    )
    res = login_with_paypal_merchant(req, db=db_session)
    assert res.access_token is not None
    assert res.token_type == "Bearer"
    assert res.paypal_merchant_id == "sb-test-merchant-99@business.example.com"
    assert res.merchant_name == "Test PayPal Store"
    assert res.role == "OWNER"
    assert res.profile.email == "sb-test-merchant-99@business.example.com"

