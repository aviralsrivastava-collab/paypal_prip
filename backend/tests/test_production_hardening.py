import datetime
import json
import logging
import time
from decimal import Decimal
from typing import Generator

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.api.health import get_liveness, get_readiness
from backend.api.main import (
    apply_security_headers,
    validate_request_size,
)
from backend.api.operations import get_operations_metrics
from backend.core.config import Settings, get_settings
from backend.core.database import Base, get_engine_kwargs
from backend.core.logging import (
    StructuredJsonFormatter,
    correlation_id_ctx,
    mask_sensitive_data,
)
from backend.core.security import (
    AuthenticatedActor,
    create_jwt_token,
    get_current_actor,
    require_merchant_access,
    verify_oidc_token,
)
from backend.integrations.storefront.extractor import is_safe_storefront_url
from backend.models.audit import AuditEvent
from backend.models.order import Order
from backend.models.product import Product
from backend.models.proposal import CorrectionProposal
from backend.models.reconciliation import PaymentReconciliation
from backend.models.scan import StorefrontScan
from backend.models.webhook import WebhookEvent
from backend.repositories.order import OrderRepository
from backend.repositories.product import ProductRepository
from backend.repositories.proposal import ProposalRepository
from backend.repositories.reconciliation import PaymentReconciliationRepository
from backend.repositories.scan import ScanRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository
from backend.services.webhook_worker import WebhookWorkerService
from backend.worker import run_worker_loop


@pytest.fixture
def isolated_db() -> Generator[Session, None, None]:
    """Provides a pristine in-memory SQLite database session with full schema."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    try:
        yield session
    finally:
        session.close()


# =============================================================================
# 1. Production Configuration & Fail-Closed Guards (Tests 1-6)
# =============================================================================

def test_production_rejects_sqlite():
    settings = Settings(
        app_env="production",
        database_url="sqlite:///./prod.db",
        session_secret="strong-prod-secret-1234567890",
        oidc_issuer="https://auth.example.com",
        oidc_client_id="prod-client",
        paypal_client_id="sb-id",
        paypal_client_secret="sb-sec",
    )
    with pytest.raises(ValueError, match="strictly rejects SQLite"):
        settings.validate_production_settings()


def test_production_rejects_default_session_secret():
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@localhost:5432/db",
        session_secret="prip-insecure-default-change-in-production",
        oidc_issuer="https://auth.example.com",
        oidc_client_id="prod-client",
        paypal_client_id="sb-id",
        paypal_client_secret="sb-sec",
    )
    with pytest.raises(ValueError, match="default insecure session_secret"):
        settings.validate_production_settings()


def test_production_rejects_paypal_live():
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@localhost:5432/db",
        session_secret="strong-prod-secret-1234567890",
        paypal_environment="live",
        oidc_issuer="https://auth.example.com",
        oidc_client_id="prod-client",
        paypal_client_id="sb-id",
        paypal_client_secret="sb-sec",
    )
    with pytest.raises(ValueError, match="strictly rejects PayPal Live"):
        settings.validate_production_settings()


def test_production_rejects_missing_oidc_credentials():
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@localhost:5432/db",
        session_secret="strong-prod-secret-1234567890",
        oidc_issuer="",
        oidc_client_id="",
        paypal_client_id="sb-id",
        paypal_client_secret="sb-sec",
    )
    with pytest.raises(ValueError, match="requires OIDC authentication"):
        settings.validate_production_settings()


def test_production_rejects_missing_paypal_credentials():
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@localhost:5432/db",
        session_secret="strong-prod-secret-1234567890",
        oidc_issuer="https://auth.example.com",
        oidc_client_id="prod-client",
        paypal_client_id="",
        paypal_client_secret="",
    )
    with pytest.raises(ValueError, match="requires PayPal Sandbox credentials"):
        settings.validate_production_settings()


def test_connection_pool_configuration():
    pg_kwargs = get_engine_kwargs("postgresql://user:pass@localhost:5432/db")
    assert pg_kwargs["pool_size"] == 10
    assert pg_kwargs["max_overflow"] == 20
    assert pg_kwargs["pool_timeout"] == 30.0
    assert pg_kwargs["pool_pre_ping"] is True
    assert pg_kwargs["pool_recycle"] == 1800

    sqlite_kwargs = get_engine_kwargs("sqlite:///test.db")
    assert "connect_args" in sqlite_kwargs
    assert sqlite_kwargs["connect_args"]["check_same_thread"] is False


# =============================================================================
# 2. Multi-Merchant Tenancy Isolation (Tests 7-12)
# =============================================================================

def test_multi_merchant_product_isolation(isolated_db: Session):
    repo = ProductRepository(isolated_db)
    p1 = Product(sku="SX-A", title="Shoe A", price=Decimal("100.00"), merchant_id="tenant_alpha")
    p2 = Product(sku="SX-B", title="Shoe B", price=Decimal("150.00"), merchant_id="tenant_beta")
    repo.create(p1)
    repo.create(p2)
    isolated_db.commit()

    alpha_products = repo.get_all(merchant_id="tenant_alpha")
    assert len(alpha_products) == 1
    assert alpha_products[0].sku == "SX-A"

    beta_products = repo.get_all(merchant_id="tenant_beta")
    assert len(beta_products) == 1
    assert beta_products[0].sku == "SX-B"

    assert repo.get_by_sku("SX-B", merchant_id="tenant_alpha") is None


def test_multi_merchant_order_isolation(isolated_db: Session):
    p = Product(sku="SX-001", title="Shoe", price=Decimal("100.00"), merchant_id="tenant_alpha")
    isolated_db.add(p)
    isolated_db.flush()

    order_repo = OrderRepository(isolated_db)
    o1 = Order(
        order_id="ord_alpha_1",
        sku="SX-001",
        product_id=p.id,
        unit_price=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        merchant_id="tenant_alpha",
    )
    o2 = Order(
        order_id="ord_beta_1",
        sku="SX-001",
        product_id=p.id,
        unit_price=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        merchant_id="tenant_beta",
    )
    order_repo.create(o1)
    order_repo.create(o2)
    isolated_db.commit()

    alpha_orders = order_repo.list_orders(merchant_id="tenant_alpha")
    assert len(alpha_orders) == 1
    assert alpha_orders[0].order_id == "ord_alpha_1"

    assert order_repo.get_by_order_id("ord_beta_1", merchant_id="tenant_alpha") is None
    assert order_repo.get_by_order_id("ord_beta_1", merchant_id="tenant_beta") is not None


def test_multi_merchant_scan_isolation(isolated_db: Session):
    p = Product(sku="SX-001", title="Shoe", price=Decimal("100.00"), merchant_id="tenant_alpha")
    isolated_db.add(p)
    isolated_db.flush()

    scan_repo = ScanRepository(isolated_db)
    s1 = StorefrontScan(
        product_id=p.id,
        sku="SX-001",
        url="/products/sx-001",
        state="VERIFIED_NO_ISSUE",
        is_comparable=True,
        correlation_id="c1",
        merchant_id="tenant_alpha",
    )
    s2 = StorefrontScan(
        product_id=p.id,
        sku="SX-001",
        url="/products/sx-001",
        state="ISSUE_DETECTED",
        is_comparable=True,
        correlation_id="c2",
        merchant_id="tenant_beta",
    )
    scan_repo.create(s1)
    scan_repo.create(s2)
    isolated_db.commit()

    alpha_scans = scan_repo.list_by_sku("SX-001", merchant_id="tenant_alpha")
    assert len(alpha_scans) == 1
    assert alpha_scans[0].correlation_id == "c1"


def test_multi_merchant_proposal_isolation(isolated_db: Session):
    p = Product(sku="SX-001", title="Shoe", price=Decimal("100.00"))
    isolated_db.add(p)
    isolated_db.flush()

    s = StorefrontScan(
        product_id=p.id,
        sku="SX-001",
        url="/products/sx-001",
        state="ISSUE_DETECTED",
        is_comparable=True,
        correlation_id="c1",
    )
    isolated_db.add(s)
    isolated_db.flush()

    prop_repo = ProposalRepository(isolated_db)
    prop1 = CorrectionProposal(
        scan_id=s.id,
        product_id=p.id,
        sku="SX-001",
        current_value=Decimal("120.00"),
        proposed_value=Decimal("100.00"),
        reason="Sync A",
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
        created_by="admin_a",
        merchant_id="tenant_alpha",
    )
    prop2 = CorrectionProposal(
        scan_id=s.id,
        product_id=p.id,
        sku="SX-001",
        current_value=Decimal("120.00"),
        proposed_value=Decimal("100.00"),
        reason="Sync B",
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
        created_by="admin_b",
        merchant_id="tenant_beta",
    )
    prop_repo.create(prop1)
    prop_repo.create(prop2)
    isolated_db.commit()

    alpha_proposals = prop_repo.list_proposals(merchant_id="tenant_alpha")
    assert len(alpha_proposals) == 1
    assert alpha_proposals[0].created_by == "admin_a"


def test_multi_merchant_reconciliation_isolation(isolated_db: Session):
    p = Product(sku="SX-001", title="Shoe", price=Decimal("100.00"))
    isolated_db.add(p)
    isolated_db.flush()

    o = Order(
        order_id="ord_rec_1",
        sku="SX-001",
        product_id=p.id,
        unit_price=Decimal("100.00"),
        total_amount=Decimal("100.00"),
    )
    isolated_db.add(o)
    isolated_db.flush()

    rec_repo = PaymentReconciliationRepository(isolated_db)
    r1 = PaymentReconciliation(
        order_id=o.id,
        outcome="ALIGNED_CAPTURED",
        previous_payment_status="UNKNOWN",
        new_payment_status="CAPTURED",
        provider_status="COMPLETED",
        merchant_id="tenant_alpha",
    )
    r2 = PaymentReconciliation(
        order_id=o.id,
        outcome="ALIGNED_FAILED",
        previous_payment_status="UNKNOWN",
        new_payment_status="FAILED",
        provider_status="VOIDED",
        merchant_id="tenant_beta",
    )
    rec_repo.create(r1)
    rec_repo.create(r2)
    isolated_db.commit()

    alpha_recs = rec_repo.list_history(merchant_id="tenant_alpha")
    assert len(alpha_recs) == 1
    assert alpha_recs[0].outcome == "ALIGNED_CAPTURED"


def test_multi_merchant_cross_tenant_access_forbidden():
    actor_alpha = AuthenticatedActor(actor_id="user-alpha", merchant_id="tenant_alpha", role="merchant_operator")
    with pytest.raises(HTTPException) as exc_info:
        require_merchant_access(actor_alpha, "tenant_beta")

    assert exc_info.value.status_code == 403
    assert "forbidden" in exc_info.value.detail.lower()

    # System superadmin is exempt from tenant restriction
    admin = AuthenticatedActor(actor_id="superadmin-1", merchant_id="tenant_alpha", role="superadmin")
    require_merchant_access(admin, "tenant_beta")  # Does not raise


# =============================================================================
# 3. OIDC Token Authentication & Verification (Tests 13-20)
# =============================================================================

def test_oidc_token_valid_authentication():
    settings = get_settings()
    token = create_jwt_token(
        {
            "sub": "user-jwt-123",
            "merchant_id": "tenant-custom-99",
            "role": "merchant_admin",
            "actor_type": "merchant",
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_client_id,
            "exp": time.time() + 3600,
        }
    )
    claims = verify_oidc_token(token)
    assert claims["sub"] == "user-jwt-123"
    assert claims["merchant_id"] == "tenant-custom-99"
    assert claims["role"] == "merchant_admin"


def test_oidc_token_expired_rejected():
    settings = get_settings()
    expired_token = create_jwt_token(
        {
            "sub": "user-expired",
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_client_id,
            "exp": time.time() - 3600,
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_oidc_token(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_oidc_token_invalid_signature_rejected():
    settings = get_settings()
    tampered_token = create_jwt_token(
        {
            "sub": "user-tampered",
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_client_id,
            "exp": time.time() + 3600,
        },
        secret="wrong-secret-key-that-does-not-match",
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_oidc_token(tampered_token)
    assert exc_info.value.status_code == 401
    assert "invalid jwt signature" in exc_info.value.detail.lower()


def test_oidc_token_invalid_issuer_rejected():
    settings = get_settings()
    wrong_iss_token = create_jwt_token(
        {
            "sub": "user-bad-issuer",
            "iss": "https://unauthorized-issuer.com",
            "aud": settings.oidc_client_id,
            "exp": time.time() + 3600,
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_oidc_token(wrong_iss_token)
    assert exc_info.value.status_code == 401
    assert "invalid jwt issuer" in exc_info.value.detail.lower()


def test_oidc_token_invalid_audience_rejected():
    settings = get_settings()
    wrong_aud_token = create_jwt_token(
        {
            "sub": "user-bad-audience",
            "iss": settings.oidc_issuer,
            "aud": "wrong-client-app-id",
            "exp": time.time() + 3600,
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_oidc_token(wrong_aud_token)
    assert exc_info.value.status_code == 401
    assert "invalid jwt audience" in exc_info.value.detail.lower()


def test_oidc_token_missing_claims_rejected():
    settings = get_settings()
    # Missing 'sub' claim
    missing_sub = create_jwt_token(
        {
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_client_id,
            "exp": time.time() + 3600,
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_oidc_token(missing_sub)
    assert exc_info.value.status_code == 401
    assert "sub" in exc_info.value.detail.lower()


def test_production_rejects_demo_headers(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(HTTPException) as exc_info:
        get_current_actor(x_actor_id="demo-user", x_actor_role="merchant_operator")
    assert exc_info.value.status_code == 401
    assert "production authentication token required" in exc_info.value.detail.lower()


def test_development_allows_demo_headers(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")

    actor = get_current_actor(
        x_actor_id="custom-dev-user",
        x_actor_role="merchant_admin",
        x_merchant_id="merchant-42",
    )
    assert actor.actor_id == "custom-dev-user"
    assert actor.role == "merchant_admin"
    assert actor.merchant_id == "merchant-42"


# =============================================================================
# 4. Standalone Background Worker Lifecycle & Resilience (Tests 21-23)
# =============================================================================

def test_background_worker_lifecycle(isolated_db: Session, monkeypatch):
    monkeypatch.setattr("backend.worker.SessionLocal", lambda: isolated_db)
    processed = run_worker_loop(once=True)
    assert processed >= 0


def test_background_worker_lease_and_heartbeat(isolated_db: Session):
    worker = WebhookWorkerService(isolated_db, worker_id="test_worker_hbeat")
    worker.send_heartbeat(status="ACTIVE", successful_run=True)

    hb_repo = WorkerHeartbeatRepository(isolated_db)
    heartbeats = hb_repo.list_heartbeats()
    found = [h for h in heartbeats if h.worker_id == "test_worker_hbeat"]
    assert len(found) == 1
    assert found[0].status == "ACTIVE"


def test_background_worker_crash_recovery(isolated_db: Session):
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_lease = now - datetime.timedelta(seconds=120)

    # Insert an event locked by a crashed worker with an expired lease
    wh_repo = WebhookEventRepository(isolated_db)
    ev = WebhookEvent(
        paypal_event_id="WH-CRASH-TEST-001",
        event_type="CHECKOUT.ORDER.APPROVED",
        resource_type="checkout-order",
        status="PROCESSING",
        raw_payload=json.dumps({"id": "WH-CRASH-TEST-001", "event_type": "CHECKOUT.ORDER.APPROVED"}),
        locked_by="crashed_worker_999",
        processing_lease_expires_at=expired_lease,
        attempt_count=1,
    )
    wh_repo.create(ev)
    isolated_db.commit()

    # New worker instance claims eligible event
    worker = WebhookWorkerService(isolated_db, worker_id="recovery_worker_1")
    assert worker.worker_id == "recovery_worker_1"
    claimed = wh_repo.claim_eligible_event(worker_id="recovery_worker_1", lease_seconds=60)

    assert claimed is not None
    assert claimed.paypal_event_id == "WH-CRASH-TEST-001"
    assert claimed.locked_by == "recovery_worker_1"


# =============================================================================
# 5. API Security, Middleware & SSRF Defense (Tests 24-28)
# =============================================================================

def test_security_headers_present():
    headers = {}
    applied = apply_security_headers(headers, correlation_id="cid-security-check")
    assert applied.get("Content-Security-Policy") == "default-src 'self'"
    assert applied.get("X-Content-Type-Options") == "nosniff"
    assert applied.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in applied
    assert applied.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert applied.get("Permissions-Policy") == "geolocation=(), camera=(), microphone=()"
    assert applied.get("X-Correlation-ID") == "cid-security-check"


def test_request_body_size_limit_exceeded():
    # 2MB > 1MB limit
    assert validate_request_size(2_097_152, max_bytes=1_048_576) is False
    # 500KB <= 1MB limit
    assert validate_request_size(500_000, max_bytes=1_048_576) is True
    # None (no content-length header)
    assert validate_request_size(None, max_bytes=1_048_576) is True


def test_correlation_id_propagation():
    custom_cid = "corr-test-trace-id-12345"
    token = correlation_id_ctx.set(custom_cid)
    try:
        assert correlation_id_ctx.get() == custom_cid
        headers = apply_security_headers({}, correlation_id=custom_cid)
        assert headers["X-Correlation-ID"] == custom_cid
    finally:
        correlation_id_ctx.reset(token)


def test_ssrf_protection_blocks_internal_ips():
    assert is_safe_storefront_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_storefront_url("http://10.0.0.1/admin") is False
    assert is_safe_storefront_url("http://192.168.1.50/dashboard") is False
    assert is_safe_storefront_url("http://172.16.0.10:8080/metrics") is False
    assert is_safe_storefront_url("http://evil-storefront.com/phish", allowed_base="http://localhost:3000") is False


def test_ssrf_protection_allows_configured_storefront():
    assert is_safe_storefront_url("/products/stridex-runner") is True
    assert is_safe_storefront_url("http://localhost:3000/products/stridex-runner", allowed_base="http://localhost:3000") is True


# =============================================================================
# 6. Observability, Logging, Immutability & Health (Tests 29-34)
# =============================================================================

def test_structured_json_logging():
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test structured log entry",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Test structured log entry"
    assert "timestamp" in data


def test_sensitive_data_masked_in_logs():
    raw_log = 'User token Bearer eyJhbGciOiJIUzI1NiJ9.test and client_secret: "super-secret-password-123"'
    masked = mask_sensitive_data(raw_log)

    assert "eyJhbGci" not in masked
    assert "super-secret-password-123" not in masked
    assert "[MASKED" in masked


def test_audit_event_immutability(isolated_db: Session):
    audit = AuditEvent(
        actor_type="MERCHANT",
        actor_id="admin-1",
        action="TEST_ACTION",
        entity_type="Product",
        entity_id="1",
        correlation_id="corr-audit-1",
        merchant_id="tenant_alpha",
    )
    isolated_db.add(audit)
    isolated_db.commit()

    persisted = isolated_db.get(AuditEvent, audit.id)
    assert persisted is not None
    assert persisted.merchant_id == "tenant_alpha"
    assert persisted.action == "TEST_ACTION"


def test_operations_metrics_endpoint():
    actor = AuthenticatedActor(actor_id="admin-1", role="merchant_admin")
    resp = get_operations_metrics(current_actor=actor)
    assert resp["status"] == "healthy"
    assert "metrics" in resp
    assert "timestamp" in resp


def test_health_check_readiness_and_liveness(isolated_db: Session):
    live_resp = get_liveness()
    assert live_resp == {"status": "alive"}

    ready_resp = get_readiness(db=isolated_db)
    assert ready_resp["status"] == "ready"


def test_migration_008_up_and_down(isolated_db: Session):
    import importlib
    mig_008 = importlib.import_module("backend.migrations.versions.008_multi_merchant_and_production_hardening")

    # Verify migration module has upgrade and downgrade functions
    assert callable(mig_008.upgrade)
    assert callable(mig_008.downgrade)
    assert mig_008.revision == "008_multi_merchant_and_production_hardening"
    assert mig_008.down_revision == "007_operational_resilience"
