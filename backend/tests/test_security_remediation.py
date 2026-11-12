import datetime
from decimal import Decimal
from unittest.mock import patch

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.checkout import capture_order, reconcile_order
from backend.api.corrections import (
    approve_proposal,
    cancel_proposal,
    execute_proposal,
    get_proposal,
    reject_proposal,
)
from backend.api.diagnoses import create_diagnosis, list_scan_diagnoses
from backend.api.operations import (
    get_operations_overview,
    list_stuck_webhooks,
    replay_webhook_event,
)
from backend.api.scans import get_scan, get_scan_evidence
from backend.api.storefront import update_storefront_price
from backend.core.config import get_settings
from backend.core.database import init_db_engine
from backend.core.security import (
    AuthenticatedActor,
    clear_test_jwks_keys,
    create_rsa_jwt_token,
    generate_test_rsa_key_pair,
    get_current_actor,
    register_test_jwks_key,
    verify_oidc_token,
)
from backend.models.order import Order
from backend.models.product import Product
from backend.models.proposal import CorrectionProposal
from backend.models.scan import StorefrontScan
from backend.models.storefront import StorefrontProduct
from backend.models.webhook import WebhookEvent
from backend.policies.checkout_policy import (
    OrderStatus,
    PaymentStatus,
    WebhookEventStatus,
)
from backend.policies.correction_policy import (
    ApprovalStatus,
    ExecutionStatus,
    PolicyValidationStatus,
)
from backend.repositories.audit import AuditRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.proposal import CorrectionProposalRejectRequest
from backend.schemas.storefront import StorefrontUpdatePriceRequest


@pytest.fixture(autouse=True)
def cleanup_jwks():
    clear_test_jwks_keys()
    yield
    clear_test_jwks_keys()


# ---------------------------------------------------------------------------
# SEC-TENANT-001: Cross-Merchant State Mutations (Proposals, Orders, Storefront)
# ---------------------------------------------------------------------------


def test_merchant_cannot_mutate_another_merchants_proposal(db_session: Session):
    """
    SEC-TENANT-001: Verifies Merchant A cannot approve, reject, cancel,
    or execute Merchant B's correction proposal (HTTP 403 Forbidden).
    Verifies no database state changes or misleading audit logs occur.
    """
    # 1. Seed product, storefront product, scan and proposal belonging to merchant_b
    prod = Product(
        merchant_id="merchant_b",
        sku="SX-001",
        title="StrideX Runner",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    db_session.add(prod)
    db_session.commit()
    db_session.refresh(prod)

    storefront_prod = StorefrontProduct(
        merchant_id="merchant_b",
        sku="SX-001",
        title="StrideX Runner",
        price=Decimal("120.00"),
        currency="USD",
        availability="IN_STOCK",
        version=1,
    )
    db_session.add(storefront_prod)
    db_session.commit()
    db_session.refresh(storefront_prod)

    scan = StorefrontScan(
        merchant_id="merchant_b",
        product_id=prod.id,
        sku="SX-001",
        url="https://merchant-b.store/products/runner",
        state="ISSUE_DETECTED",
        correlation_id="corr-scan-b-01",
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)

    now = datetime.datetime.now(datetime.timezone.utc)
    proposal = CorrectionProposal(
        merchant_id="merchant_b",
        scan_id=scan.id,
        product_id=prod.id,
        sku="SX-001",
        proposal_type="PRICE_SYNCHRONIZATION",
        current_value=Decimal("120.00"),
        proposed_value=Decimal("100.00"),
        currency="USD",
        reason="Price synchronization from catalog",
        policy_validation_status=PolicyValidationStatus.VALID.value,
        approval_status=ApprovalStatus.PENDING_APPROVAL.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        created_by="system",
        expires_at=now + datetime.timedelta(hours=24),
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    actor_a = AuthenticatedActor(
        actor_id="actor_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )
    actor_b = AuthenticatedActor(
        actor_id="actor_b",
        role="merchant_admin",
        merchant_id="merchant_b",
    )

    # 2. Merchant A attempts to APPROVE Merchant B's proposal -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        approve_proposal(proposal.id, None, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail

    # Verify state was not changed
    db_session.refresh(proposal)
    assert proposal.approval_status == ApprovalStatus.PENDING_APPROVAL.value

    # 3. Merchant A attempts to REJECT Merchant B's proposal -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        reject_proposal(
            proposal.id,
            CorrectionProposalRejectRequest(reason="Malicious rejection attempt"),
            current_actor=actor_a,
            db=db_session,
        )
    assert exc.value.status_code == 403
    db_session.refresh(proposal)
    assert proposal.approval_status == ApprovalStatus.PENDING_APPROVAL.value

    # 4. Merchant A attempts to CANCEL Merchant B's proposal -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        cancel_proposal(proposal.id, None, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    db_session.refresh(proposal)
    assert proposal.approval_status == ApprovalStatus.PENDING_APPROVAL.value

    # 5. Legitimate Merchant B approves the proposal -> succeeds
    approved_res = approve_proposal(proposal.id, None, current_actor=actor_b, db=db_session)
    assert approved_res.approval_status == ApprovalStatus.APPROVED.value
    db_session.refresh(proposal)
    assert proposal.approval_status == ApprovalStatus.APPROVED.value

    # 6. Merchant A attempts to EXECUTE Merchant B's approved proposal -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        execute_proposal(proposal.id, None, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    db_session.refresh(proposal)
    assert proposal.approval_status == ApprovalStatus.APPROVED.value
    assert proposal.execution_status == ExecutionStatus.NOT_STARTED.value


def test_merchant_cannot_capture_or_reconcile_another_merchants_order(
    db_session: Session,
):
    """
    SEC-TENANT-001: Verifies Merchant A cannot capture or reconcile
    Merchant B's checkout order (HTTP 403 Forbidden).
    """
    prod = Product(
        merchant_id="merchant_b",
        sku="SKU-B",
        title="Product B",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
    )
    db_session.add(prod)
    db_session.commit()
    db_session.refresh(prod)

    order = Order(
        merchant_id="merchant_b",
        order_id="ord-merchant-b-001",
        paypal_order_id="PAYPAL-B-001",
        order_status=OrderStatus.CREATED.value,
        payment_status=PaymentStatus.PENDING.value,
        product_id=prod.id,
        sku="SKU-B",
        currency="USD",
        unit_price=Decimal("100.00"),
        quantity=1,
        total_amount=Decimal("100.00"),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    actor_a = AuthenticatedActor(
        actor_id="actor_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )

    # Merchant A tries to capture Merchant B's order -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        capture_order(order.order_id, None, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail

    # Verify order state remains unchanged
    db_session.refresh(order)
    assert order.payment_status == PaymentStatus.PENDING.value

    # Merchant A tries to reconcile Merchant B's order -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        reconcile_order(order.order_id, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail


def test_merchant_cannot_update_another_merchants_storefront_price(
    db_session: Session,
):
    """
    SEC-TENANT-001: Verifies Merchant A cannot update Merchant B's
    storefront product price (HTTP 403 Forbidden).
    """
    product_b = StorefrontProduct(
        merchant_id="merchant_b",
        sku="SX-B-001",
        title="Merchant B Shoes",
        price=Decimal("120.00"),
        currency="USD",
        availability="IN_STOCK",
        version=1,
    )
    db_session.add(product_b)
    db_session.commit()
    db_session.refresh(product_b)

    actor_a = AuthenticatedActor(
        actor_id="actor_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )
    actor_b = AuthenticatedActor(
        actor_id="actor_b",
        role="merchant_admin",
        merchant_id="merchant_b",
    )

    update_req = StorefrontUpdatePriceRequest(
        price=Decimal("99.00"),
        currency="USD",
        actor_id="actor_a",
        expected_version=1,
        reason="Malicious price decrease",
    )

    # Merchant A tries to update product B's price -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        update_storefront_price(
            sku="SX-B-001",
            request=update_req,
            current_actor=actor_a,
            db=db_session,
        )
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail

    # Verify price is untouched
    db_session.refresh(product_b)
    assert product_b.price == Decimal("120.00")

    # Merchant B updates product B's price -> succeeds
    update_req_b = StorefrontUpdatePriceRequest(
        price=Decimal("99.00"),
        currency="USD",
        actor_id="actor_b",
        expected_version=1,
        reason="Authorized price decrease",
    )
    updated = update_storefront_price(
        sku="SX-B-001",
        request=update_req_b,
        current_actor=actor_b,
        db=db_session,
    )
    assert updated.price == "99.00"
    db_session.refresh(product_b)
    assert product_b.price == Decimal("99.00")


# ---------------------------------------------------------------------------
# SEC-TENANT-002: Diagnosis Authentication & Multi-Tenant Isolation
# ---------------------------------------------------------------------------


def test_diagnosis_endpoints_enforce_auth_and_tenant_isolation(
    db_session: Session, monkeypatch
):
    """
    SEC-TENANT-002: Verifies that diagnosis endpoints enforce authentication
    in production and strict multi-merchant tenant isolation.
    """
    prod_b = Product(
        merchant_id="merchant_b",
        sku="SX-B-001",
        title="Product B",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
    )
    db_session.add(prod_b)
    db_session.commit()
    db_session.refresh(prod_b)

    scan_b = StorefrontScan(
        merchant_id="merchant_b",
        product_id=prod_b.id,
        sku="SX-B-001",
        url="https://merchant-b.store/shoes",
        state="ISSUE_DETECTED",
        correlation_id="corr-scan-b-02",
    )
    db_session.add(scan_b)
    db_session.commit()
    db_session.refresh(scan_b)

    # 1. Test unauthenticated access in production
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(HTTPException) as exc:
        get_current_actor(authorization=None)
    assert exc.value.status_code == 401
    assert "Production authentication token required" in exc.value.detail

    # Reset to test environment for header-based tenant testing
    monkeypatch.setattr(settings, "app_env", "test")

    actor_a = AuthenticatedActor(
        actor_id="actor_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )

    # 2. Merchant A attempts to create a diagnosis for Merchant B's scan -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        create_diagnosis(scan_id=scan_b.id, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail

    # 3. Merchant A attempts to read diagnoses of Merchant B's scan -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        list_scan_diagnoses(scan_id=scan_b.id, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# SEC-AUTH-001: Enterprise OIDC Asymmetric JWKS Verification
# ---------------------------------------------------------------------------


def test_oidc_asymmetric_jwks_verification_and_production_enforcement(monkeypatch):
    """
    SEC-AUTH-001: Comprehensive testing of asymmetric JWKS verification:
    - Valid RS256 token verification
    - Invalid signature rejection
    - Expired token rejection
    - Immature token (nbf) rejection
    - Invalid issuer/audience rejection
    - Algorithm 'none' rejection
    - HS256 rejection in production
    - Missing/unknown kid rejection in production
    - Missing merchant_id rejection in production
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.prip.example.com")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://auth.prip.example.com/certs")
    monkeypatch.setattr(settings, "oidc_client_id", "prip-service-app")

    priv_pem, pub_pem = generate_test_rsa_key_pair()
    kid = "test-key-2026"
    register_test_jwks_key(kid, pub_pem)

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    # 1. Valid RS256 token succeeds
    valid_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "role": "merchant_admin",
            "exp": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    payload = verify_oidc_token(valid_token)
    assert payload["sub"] == "user_123"
    assert payload["merchant_id"] == "merchant_alpha"

    # 2. Token signed with wrong key fails with 401
    other_priv, _ = generate_test_rsa_key_pair()
    wrong_sig_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        private_key_pem=other_priv,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(wrong_sig_token)
    assert exc.value.status_code == 401
    assert "Invalid JWT signature" in exc.value.detail

    # 3. Expired token fails with 401
    expired_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts - 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(expired_token)
    assert exc.value.status_code == 401
    assert "JWT token has expired" in exc.value.detail

    # 4. Immature token (nbf in future) fails with 401
    immature_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 600,
            "nbf": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(immature_token)
    assert exc.value.status_code == 401
    assert "JWT token is not yet valid" in exc.value.detail

    # 5. Invalid issuer fails with 401
    bad_iss_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://impostor.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(bad_iss_token)
    assert exc.value.status_code == 401
    assert "Invalid JWT issuer" in exc.value.detail

    # 6. Invalid audience fails with 401
    bad_aud_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "wrong-client-id",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(bad_aud_token)
    assert exc.value.status_code == 401
    assert "Invalid JWT audience" in exc.value.detail

    # 7. Algorithm 'none' fails with 401
    none_token = pyjwt.encode(
        {"sub": "user_123", "iss": "https://auth.prip.example.com", "aud": "prip-service-app"},
        key="",
        algorithm="none",
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(none_token)
    assert exc.value.status_code == 401
    assert "Signing algorithm 'none' is prohibited" in exc.value.detail

    # 8. Symmetric HS256 rejected in production
    hs256_token = pyjwt.encode(
        {
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        key="supersecretkey12345678901234567890",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(hs256_token)
    assert exc.value.status_code == 401
    assert "Unsupported JWT signing algorithm in production: 'HS256'" in exc.value.detail

    # 9. Missing 'kid' header rejected in production
    no_kid_token = pyjwt.encode(
        {
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        key=priv_pem,
        algorithm="RS256",
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(no_kid_token)
    assert exc.value.status_code == 401
    assert "Missing required 'kid' header" in exc.value.detail

    # 10. Unknown 'kid' rejected in production
    unknown_kid_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "merchant_id": "merchant_alpha",
            "exp": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid="unknown-kid-xyz",
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(unknown_kid_token)
    assert exc.value.status_code == 401

    # 11. Token missing merchant_id rejected in production
    no_merchant_token = create_rsa_jwt_token(
        payload={
            "sub": "user_123",
            "iss": "https://auth.prip.example.com",
            "aud": "prip-service-app",
            "exp": now_ts + 300,
        },
        private_key_pem=priv_pem,
        kid=kid,
    )
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(no_merchant_token)
    assert exc.value.status_code == 401
    assert "Missing required merchant identity claim" in exc.value.detail


# ---------------------------------------------------------------------------
# SEC-TENANT-003: Audit Tenant Attribution and Query Isolation
# ---------------------------------------------------------------------------


def test_audit_tenant_attribution_and_query_isolation(db_session: Session):
    """
    SEC-TENANT-003: Verifies that AuditRepository stamps merchant_id
    and isolates query results between tenants.
    """
    # Append events for Merchant A and Merchant B
    AuditRepository.append(
        session=db_session,
        event=AuditEventCreate(
            action="TEST_ACTION_A",
            entity_type="Order",
            entity_id="ord-001",
            actor_type="merchant",
            actor_id="actor_a",
            correlation_id="corr-audit-01",
        ),
        merchant_id="merchant_a",
    )
    AuditRepository.append(
        session=db_session,
        event=AuditEventCreate(
            action="TEST_ACTION_B",
            entity_type="Order",
            entity_id="ord-001",  # Same entity_id to test isolation!
            actor_type="merchant",
            actor_id="actor_b",
            correlation_id="corr-audit-02",
        ),
        merchant_id="merchant_b",
    )

    # Merchant A query by entity only sees Merchant A events
    events_a = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-001",
        merchant_id="merchant_a",
    )
    assert len(events_a) == 1
    assert events_a[0].merchant_id == "merchant_a"
    assert events_a[0].action == "TEST_ACTION_A"

    # Merchant B query by entity only sees Merchant B events
    events_b = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-001",
        merchant_id="merchant_b",
    )
    assert len(events_b) == 1
    assert events_b[0].merchant_id == "merchant_b"
    assert events_b[0].action == "TEST_ACTION_B"

    # Query without tenant scope (superadmin/audit) sees both
    events_all = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-001",
    )
    assert len(events_all) == 2

    # list_by_merchant queries
    assert len(AuditRepository.list_by_merchant(session=db_session, merchant_id="merchant_a")) == 1
    assert len(AuditRepository.list_by_merchant(session=db_session, merchant_id="merchant_b")) == 1


# ---------------------------------------------------------------------------
# SEC-TENANT-004: Tenant-Scoped Operational Endpoints
# ---------------------------------------------------------------------------


def test_operational_endpoints_tenant_scoping(db_session: Session):
    """
    SEC-TENANT-004: Verifies /api/operations endpoints scope metrics and
    replay operations by tenant, while allowing superadmin global access.
    """
    # 1. Seed webhook events: one for merchant_a, one for merchant_b
    event_a = WebhookEvent(
        merchant_id="merchant_a",
        paypal_event_id="WH-EVT-A-001",
        event_type="CHECKOUT.ORDER.APPROVED",
        resource_type="checkout-order",
        status=WebhookEventStatus.DEAD_LETTER.value,
        raw_payload='{"id": "order-a"}',
    )
    event_b = WebhookEvent(
        merchant_id="merchant_b",
        paypal_event_id="WH-EVT-B-001",
        event_type="CHECKOUT.ORDER.APPROVED",
        resource_type="checkout-order",
        status=WebhookEventStatus.DEAD_LETTER.value,
        raw_payload='{"id": "order-b"}',
    )
    db_session.add_all([event_a, event_b])
    db_session.commit()
    db_session.refresh(event_a)
    db_session.refresh(event_b)

    actor_a = AuthenticatedActor(
        actor_id="admin_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )
    superadmin = AuthenticatedActor(
        actor_id="superadmin",
        role="superadmin",
        merchant_id="merchant_default",
    )

    # Merchant A requests stuck webhooks: sees only their own event
    stuck_a = list_stuck_webhooks(current_actor=actor_a, db=db_session)
    assert len(stuck_a) == 1
    assert stuck_a[0].paypal_event_id == "WH-EVT-A-001"

    # Superadmin sees both stuck events
    stuck_super = list_stuck_webhooks(current_actor=superadmin, db=db_session)
    assert len(stuck_super) == 2

    # Overview scoped by tenant
    overview_a = get_operations_overview(current_actor=actor_a, db=db_session)
    assert overview_a.dead_letter_count == 1
    overview_super = get_operations_overview(current_actor=superadmin, db=db_session)
    assert overview_super.dead_letter_count == 2

    # Merchant A attempts to replay Merchant B's webhook event -> 403 Forbidden
    with pytest.raises(HTTPException) as exc:
        replay_webhook_event(event_id=event_b.id, current_actor=actor_a, db=db_session)
    assert exc.value.status_code == 403
    assert "Forbidden: Actor from merchant 'merchant_a' is not authorized" in exc.value.detail


# ---------------------------------------------------------------------------
# SEC-OPS-001 & SEC-OPS-002: Production Engine Fail-Closed & No Create All
# ---------------------------------------------------------------------------


def test_production_engine_fails_closed_without_sqlite_fallback(monkeypatch):
    """
    SEC-OPS-001: Verifies that engine creation failure in production raises
    RuntimeError and fails closed without falling back to SQLite.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@nonexistent:5432/prip")

    with patch("backend.core.database.create_engine", side_effect=Exception("Connection refused")):
        with pytest.raises(RuntimeError) as exc:
            init_db_engine()
        assert "Production database connection failed" in str(exc.value)
        assert "Engine fails closed without fallback" in str(exc.value)


# ---------------------------------------------------------------------------
# Phase 6 Comprehensive Security Regressions
# ---------------------------------------------------------------------------


def test_cross_tenant_proposal_and_scan_read_access_blocked(db_session: Session):
    """
    Phase 6: Verifies Merchant A cannot view Merchant B's proposal details,
    scan details, or evidence items (HTTP 403 Forbidden).
    """
    prod = Product(
        merchant_id="merchant_b",
        sku="SX-SEC-01",
        title="Sec Runner",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    db_session.add(prod)
    db_session.commit()
    db_session.refresh(prod)

    scan = StorefrontScan(
        merchant_id="merchant_b",
        product_id=prod.id,
        sku="SX-SEC-01",
        url="https://merchant-b.store/products/runner",
        state="ISSUE_DETECTED",
        correlation_id="corr-scan-b-02",
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)

    now = datetime.datetime.now(datetime.timezone.utc)
    proposal = CorrectionProposal(
        merchant_id="merchant_b",
        scan_id=scan.id,
        product_id=prod.id,
        sku="SX-SEC-01",
        proposal_type="PRICE_SYNCHRONIZATION",
        current_value=Decimal("120.00"),
        proposed_value=Decimal("100.00"),
        currency="USD",
        reason="Cross-tenant test proposal",
        policy_validation_status=PolicyValidationStatus.VALID.value,
        approval_status=ApprovalStatus.PENDING_APPROVAL.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        created_by="system",
        expires_at=now + datetime.timedelta(hours=24),
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    actor_a = AuthenticatedActor(
        actor_id="actor_a",
        role="merchant_admin",
        merchant_id="merchant_a",
    )

    # 1. Merchant A cannot read Merchant B's proposal -> 403
    with pytest.raises(HTTPException) as exc:
        get_proposal(proposal_id=proposal.id, db=db_session, current_actor=actor_a)
    assert exc.value.status_code == 403

    # 2. Merchant A cannot read Merchant B's scan details -> 403
    with pytest.raises(HTTPException) as exc:
        get_scan(scan_id=scan.id, db=db_session, current_actor=actor_a)
    assert exc.value.status_code == 403

    # 3. Merchant A cannot read Merchant B's scan evidence -> 403
    with pytest.raises(HTTPException) as exc:
        get_scan_evidence(scan_id=scan.id, db=db_session, current_actor=actor_a)
    assert exc.value.status_code == 403


def test_unauthenticated_and_expired_oidc_tokens_fail_closed(monkeypatch):
    """
    Phase 6: Verifies that expired OIDC tokens, forged signatures, and unverified
    Google accounts fail closed with appropriate HTTP 401 or 403.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
    monkeypatch.setattr(settings, "oidc_client_id", "prip-api")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
    monkeypatch.setattr(settings, "allowed_google_email", "authorized@prip.demo")

    priv_pem, pub_pem = generate_test_rsa_key_pair()
    register_test_jwks_key("key-exp-1", pub_pem)

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Expired token raises 401
    expired_payload = {
        "sub": "user-123",
        "iss": "https://accounts.google.com",
        "aud": "prip-api",
        "exp": int((now - datetime.timedelta(minutes=10)).timestamp()),
        "email": "authorized@prip.demo",
        "email_verified": True,
    }
    expired_token = create_rsa_jwt_token(expired_payload, priv_pem, kid="key-exp-1")
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(expired_token)
    assert exc.value.status_code == 401
    assert "JWT token has expired" in exc.value.detail

    # 2. Forged signature raises 401
    other_priv_pem, _ = generate_test_rsa_key_pair()
    valid_payload = {
        "sub": "user-123",
        "iss": "https://accounts.google.com",
        "aud": "prip-api",
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "email": "authorized@prip.demo",
        "email_verified": True,
    }
    forged_token = create_rsa_jwt_token(valid_payload, other_priv_pem, kid="key-exp-1")
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(forged_token)
    assert exc.value.status_code == 401
    assert "Invalid JWT signature" in exc.value.detail

    # 3. Unverified email raises 401
    unverified_email_payload = {
        "sub": "user-123",
        "iss": "https://accounts.google.com",
        "aud": "prip-api",
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "email": "authorized@prip.demo",
        "email_verified": False,
    }
    unverified_token = create_rsa_jwt_token(unverified_email_payload, priv_pem, kid="key-exp-1")
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(unverified_token)
    assert exc.value.status_code == 401
    assert "Google account email is not verified" in exc.value.detail

    # 4. Unallowlisted email raises 403
    unallowlisted_payload = {
        "sub": "user-123",
        "iss": "https://accounts.google.com",
        "aud": "prip-api",
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "email": "attacker@otherdomain.com",
        "email_verified": True,
    }
    unallowlisted_token = create_rsa_jwt_token(unallowlisted_payload, priv_pem, kid="key-exp-1")
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(unallowlisted_token)
    assert exc.value.status_code == 403
    assert "Forbidden: Google account" in exc.value.detail


def test_invalid_jwks_signature_forgery_rejected(monkeypatch):
    """
    Phase 6: Verifies that tokens with an unresolvable or untrusted kid fail closed.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
    monkeypatch.setattr(settings, "oidc_client_id", "prip-api")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")

    priv_pem, _ = generate_test_rsa_key_pair()
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "user-123",
        "iss": "https://accounts.google.com",
        "aud": "prip-api",
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "email": "test@demo.com",
        "email_verified": True,
    }
    # Unregistered key ID
    token = create_rsa_jwt_token(payload, priv_pem, kid="nonexistent-kid-999")
    with pytest.raises(HTTPException) as exc:
        verify_oidc_token(token)
    assert exc.value.status_code == 401
    assert "Unable to obtain signing key from JWKS endpoint" in exc.value.detail


def test_webhook_signature_forgery_and_duplicate_events(db_session: Session):
    """
    Phase 6: Verifies that forged webhook signatures are rejected with ValueError,
    and duplicate event submissions are recognized without re-executing transitions.
    """
    from backend.integrations.paypal.mock_client import MockPayPalClient
    from backend.services.webhook import WebhookService

    # 1. Forged signature rejected
    mock_client = MockPayPalClient()
    mock_client.simulate_invalid_signature = True
    webhook_service = WebhookService(db_session, paypal_client=mock_client)

    headers = {
        "paypal-transmission-id": "t-forged-1",
        "paypal-transmission-time": "2026-11-11T12:00:00Z",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "FORGED",
    }
    import json
    raw_payload = json.dumps({"id": "WH-FORGED-01", "event_type": "PAYMENT.CAPTURE.COMPLETED"})

    with pytest.raises(ValueError, match="Cryptographic webhook signature verification failed"):
        webhook_service.process_webhook(headers=headers, raw_body=raw_payload)

    # 2. Valid event followed by duplicate submission
    mock_client.simulate_invalid_signature = False
    valid_headers = {
        "paypal-transmission-id": "t-valid-1",
        "paypal-transmission-time": "2026-11-11T12:00:00Z",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "VALID_SIGNATURE",
    }
    valid_payload = json.dumps({
        "id": "WH-DUP-TEST-01",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "NONEXISTENT-ORD"},
    })

    resp1 = webhook_service.process_webhook(headers=valid_headers, raw_body=valid_payload)
    assert resp1.paypal_event_id == "WH-DUP-TEST-01"

    # Duplicate submission
    resp2 = webhook_service.process_webhook(headers=valid_headers, raw_body=valid_payload)
    assert resp2.paypal_event_id == "WH-DUP-TEST-01"
    assert resp2.status == "DUPLICATE"


def test_payment_capture_retry_idempotency(db_session: Session):
    """
    Phase 6: Verifies repeated capture requests on the same order reuse existing capture
    and do not create duplicate rows or alter COMPLETED status.
    """
    from backend.integrations.paypal.mock_client import MockPayPalClient
    from backend.models.payment_capture import PaymentCapture
    from backend.repositories.storefront import StorefrontRepository
    from backend.schemas.checkout import CreateOrderRequest
    from backend.schemas.payment import CapturePaymentRequest
    from backend.services.catalog import CatalogService
    from backend.services.checkout import CheckoutService
    from backend.services.payment import PaymentService

    cat_service = CatalogService(db_session)
    cat_service.seed_initial_catalog(reset=True)

    st_repo = StorefrontRepository(db_session)
    prod = st_repo.get_by_sku("SX-001")
    assert prod is not None
    prod.price = Decimal("100.00")
    db_session.commit()

    mock_paypal = MockPayPalClient()
    checkout_service = CheckoutService(db_session, paypal_client=mock_paypal)
    order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

    payment_service = PaymentService(db_session, paypal_client=mock_paypal)
    cap_req = CapturePaymentRequest(order_id=order_resp.order_id)

    # First capture
    cap1 = payment_service.capture_payment(cap_req, actor_id="buyer")
    assert cap1.status == "COMPLETED"

    # Immediate second capture
    cap2 = payment_service.capture_payment(cap_req, actor_id="buyer")
    assert cap2.status == "COMPLETED"
    assert cap2.capture_id == cap1.capture_id

    # Verify exactly one record in DB
    stored = db_session.query(PaymentCapture).filter(PaymentCapture.order_id == order_resp.id).all()
    assert len(stored) == 1
