import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.order import Order
from backend.models.webhook import WebhookEvent
from backend.repositories.audit import AuditRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.demo_state import StateUpdateRequest
from backend.services.audit import AuditService
from backend.services.demo_state import DemoStateService, UnauthorizedError
from backend.services.webhook import WebhookService
from backend.services.webhook_worker import WebhookWorkerService


def test_audit_repository_omitted_merchant_raises_error(db_session: Session):
    """
    Verifies that omitting merchant_id in AuditRepository.append fails closed
    with a ValueError rather than silently defaulting to 'merchant_default'.
    """
    event_no_merchant = AuditEventCreate(
        actor_type="merchant",
        actor_id="actor_1",
        action="TEST_ACTION",
        entity_type="Order",
        entity_id="ord-001",
        correlation_id="corr-audit-001",
    )

    with pytest.raises(ValueError, match="Audit event requires explicit merchant_id or platform scope attribution"):
        AuditRepository.append(session=db_session, event=event_no_merchant)

    # Empty string or blank whitespace must also fail closed
    with pytest.raises(ValueError, match="Audit event requires explicit merchant_id or platform scope attribution"):
        AuditRepository.append(session=db_session, event=event_no_merchant, merchant_id="   ")


def test_audit_repository_conflicting_merchant_rejected(db_session: Session):
    """
    Verifies that supplying conflicting merchant_id in event and method argument is rejected.
    """
    event = AuditEventCreate(
        merchant_id="merchant_alpha",
        actor_type="merchant",
        actor_id="actor_1",
        action="TEST_ACTION",
        entity_type="Order",
        entity_id="ord-001",
        correlation_id="corr-audit-002",
    )

    with pytest.raises(ValueError, match="Conflicting merchant attribution"):
        AuditRepository.append(session=db_session, event=event, merchant_id="merchant_beta")


def test_audit_isolation_cross_tenant_query_blocked(db_session: Session):
    """
    Verifies that AuditRepository isolates events between tenants and that ordinary
    merchants cannot see other tenants', quarantined, or platform-level events.
    """
    # 1. Append events for Merchant Alpha, Merchant Beta, platform_system, and QUARANTINED_ORPHAN
    for m_id, act in [
        ("merchant_alpha", "ALPHA_EVENT"),
        ("merchant_beta", "BETA_EVENT"),
        ("platform_system", "PLATFORM_EVENT"),
        ("QUARANTINED_ORPHAN", "ORPHAN_EVENT"),
    ]:
        AuditRepository.append(
            session=db_session,
            event=AuditEventCreate(
                merchant_id=m_id,
                actor_type="system",
                actor_id="sys_1",
                action=act,
                entity_type="Order",
                entity_id="ord-shared",
                correlation_id=f"corr-{m_id}",
            ),
        )

    # 2. Merchant Alpha querying by entity sees ONLY Merchant Alpha events
    events_alpha = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-shared",
        merchant_id="merchant_alpha",
    )
    assert len(events_alpha) == 1
    assert events_alpha[0].merchant_id == "merchant_alpha"
    assert events_alpha[0].action == "ALPHA_EVENT"

    # 3. Merchant Beta querying by entity sees ONLY Merchant Beta events
    events_beta = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-shared",
        merchant_id="merchant_beta",
    )
    assert len(events_beta) == 1
    assert events_beta[0].merchant_id == "merchant_beta"
    assert events_beta[0].action == "BETA_EVENT"

    # 4. Standard listing without merchant context excludes platform_system and QUARANTINED_ORPHAN
    standard_events = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-shared",
    )
    returned_merchants = {e.merchant_id for e in standard_events}
    assert "platform_system" not in returned_merchants
    assert "QUARANTINED_ORPHAN" not in returned_merchants

    # 5. Querying list_by_merchant for QUARANTINED_ORPHAN returns empty unless explicit allow_quarantined
    orphan_events = AuditRepository.list_by_merchant(
        session=db_session,
        merchant_id="QUARANTINED_ORPHAN",
    )
    assert len(orphan_events) == 0


def test_webhook_audit_uses_platform_scope_or_order_merchant(db_session: Session):
    """
    Verifies that webhook ingestion and worker processing stamp 'platform_system'
    for unassociated webhooks, but correctly attribute to the order's merchant when matched.
    """
    mock_paypal = MockPayPalClient()
    wh_service = WebhookService(db_session, paypal_client=mock_paypal)
    worker = WebhookWorkerService(session=db_session, worker_id="test_worker_1")

    headers = {
        "paypal-transmission-id": "trans-unassoc-01",
        "paypal-transmission-time": "2026-11-07T12:00:00Z",
        "paypal-transmission-sig": "VALID_SIG",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
        "paypal-auth-algo": "SHA256withRSA",
    }

    # 1. Ingest a webhook with no existing order -> audit must be 'platform_system'
    raw_payload_unassociated = '{"id": "WH-UNASSOC-1", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "NON-EXISTENT-ORDER"}}'
    wh_service.process_webhook(
        headers=headers,
        raw_body=raw_payload_unassociated,
    )

    admin_actor = AuthenticatedActor(
        actor_id="sysadmin_1",
        actor_type="system",
        role="superadmin",
        merchant_id="platform_system",
    )

    wh_events = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="WebhookEvent",
        entity_id="WH-UNASSOC-1",
        merchant_id="platform_system",
        authorized_actor=admin_actor,
    )
    assert len(wh_events) >= 1
    assert all(e.merchant_id == "platform_system" for e in wh_events)

    # 2. Ingest a webhook corresponding to an order belonging to 'merchant_gamma'
    order = Order(
        order_id="ord-gamma-001",
        merchant_id="merchant_gamma",
        paypal_order_id="PAYPAL-ORDER-GAMMA",
        sku="SX-001",
        product_id=1,
        unit_price=100.00,
        currency="USD",
        quantity=1,
        total_amount=100.00,
        order_status="CREATED",
        payment_status="PENDING",
        preflight_passed=True,
        correlation_id="corr-gamma",
    )
    db_session.add(order)
    db_session.flush()

    headers_gamma = {
        "paypal-transmission-id": "trans-gamma-01",
        "paypal-transmission-time": "2026-11-07T12:00:00Z",
        "paypal-transmission-sig": "VALID_SIG",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
        "paypal-auth-algo": "SHA256withRSA",
    }
    raw_payload_gamma = '{"id": "WH-GAMMA-1", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "PAYPAL-ORDER-GAMMA"}}'
    wh_service.process_webhook(
        headers=headers_gamma,
        raw_body=raw_payload_gamma,
    )

    # Inbound receipt is initially platform_system before processing
    received_event = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="WebhookEvent",
        entity_id="WH-GAMMA-1",
        merchant_id="platform_system",
        authorized_actor=admin_actor,
    )
    assert len(received_event) == 1
    assert received_event[0].action == "WEBHOOK_RECEIVED"

    # Worker claims and processes the gamma event
    wh_record = db_session.query(WebhookEvent).filter_by(paypal_event_id="WH-GAMMA-1").one()
    worker.process_event(wh_record)

    # The resulting business event must be attributed to 'merchant_gamma'
    order_audits = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="Order",
        entity_id="ord-gamma-001",
        merchant_id="merchant_gamma",
    )
    assert len(order_audits) == 1
    assert order_audits[0].action == "ORDER_APPROVED_BY_WEBHOOK"
    assert order_audits[0].merchant_id == "merchant_gamma"
    assert order_audits[0].merchant_id == "merchant_gamma"


def test_demo_state_trusted_actor_attribution(db_session: Session):
    """
    Verifies that DemoStateService.update_state_with_audit requires trusted
    actor context, attributes identity from the trusted actor, and fails closed
    if trusted context is omitted or unauthenticated.
    """
    DemoStateService.initialize_state(db_session, "config_param", "1.0")

    request = StateUpdateRequest(
        value="2.0",
        expected_version=1,
        correlation_id="corr-state-001",
    )

    # 1. Missing trusted_actor fails closed
    with pytest.raises(UnauthorizedError, match="missing trusted actor context"):
        DemoStateService.update_state_with_audit(
            session=db_session,
            key="config_param",
            request=request,
            trusted_actor=None,
        )

    # 2. Unauthenticated actor fails closed
    unauth_actor = AuthenticatedActor(
        actor_id="anonymous",
        merchant_id="merchant_alpha",
        is_authenticated=False,
    )
    with pytest.raises(UnauthorizedError, match="actor identity required"):
        DemoStateService.update_state_with_audit(
            session=db_session,
            key="config_param",
            request=request,
            trusted_actor=unauth_actor,
        )

    # 3. Reserved tenant actor cannot mutate state
    reserved_actor = AuthenticatedActor(
        actor_id="orphan_actor",
        merchant_id="QUARANTINED_ORPHAN",
        role="merchant_operator",
    )
    with pytest.raises(UnauthorizedError, match="Reserved tenant"):
        DemoStateService.update_state_with_audit(
            session=db_session,
            key="config_param",
            request=request,
            trusted_actor=reserved_actor,
        )

    # 4. Valid trusted actor succeeds and correctly attributes actor_id and merchant_id
    valid_actor = AuthenticatedActor(
        actor_id="admin_1",
        merchant_id="merchant_alpha",
        role="merchant_admin",
    )
    updated_state, audit_resp = DemoStateService.update_state_with_audit(
        session=db_session,
        key="config_param",
        request=request,
        trusted_actor=valid_actor,
    )

    assert updated_state.value == "2.0"
    assert audit_resp.actor_id == "admin_1"
    assert audit_resp.merchant_id == "merchant_alpha"

    persisted = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="DEMO_STATE",
        entity_id="config_param",
        merchant_id="merchant_alpha",
    )
    assert len(persisted) == 1
    assert persisted[0].merchant_id == "merchant_alpha"
    assert persisted[0].actor_id == "admin_1"


def test_demo_state_rejects_tenant_and_actor_mismatch(db_session: Session):
    """
    Verifies that client-supplied actor_id or merchant_id in StateUpdateRequest
    that conflicts with trusted actor context is strictly rejected.
    """
    DemoStateService.initialize_state(db_session, "mismatch_key", "initial")

    trusted_actor = AuthenticatedActor(
        actor_id="legit_admin",
        merchant_id="merchant_alpha",
        role="merchant_admin",
    )

    # 1. Tenant mismatch between request and trusted actor
    request_bad_tenant = StateUpdateRequest(
        value="new_val",
        expected_version=1,
        correlation_id="corr-mismatch-1",
        merchant_id="merchant_beta",
    )
    with pytest.raises(ValueError, match="Tenant mismatch"):
        DemoStateService.update_state_with_audit(
            session=db_session,
            key="mismatch_key",
            request=request_bad_tenant,
            trusted_actor=trusted_actor,
        )

    # 2. Actor mismatch between request and trusted actor
    request_bad_actor = StateUpdateRequest(
        value="new_val",
        expected_version=1,
        correlation_id="corr-mismatch-2",
        actor_id="attacker_actor",
    )
    with pytest.raises(UnauthorizedError, match="Actor mismatch"):
        DemoStateService.update_state_with_audit(
            session=db_session,
            key="mismatch_key",
            request=request_bad_actor,
            trusted_actor=trusted_actor,
        )


def test_reserved_system_tenants_cannot_be_accessed_by_ordinary_merchants():
    """
    Verifies that reserved system tenants (QUARANTINED_ORPHAN, platform_system, platform)
    cannot be accessed or claimed by ordinary merchant actors.
    """
    ordinary_actor = AuthenticatedActor(
        actor_id="merchant_user_1",
        actor_type="merchant",
        role="merchant_operator",
        merchant_id="merchant_alpha",
    )

    for reserved in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        with pytest.raises(HTTPException) as exc_info:
            require_merchant_access(ordinary_actor, reserved)
        assert exc_info.value.status_code == 403

    # Superadmin / system role is permitted for platform operations
    superadmin_actor = AuthenticatedActor(
        actor_id="admin_1",
        actor_type="system",
        role="superadmin",
        merchant_id="platform_system",
    )
    for reserved in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        require_merchant_access(superadmin_actor, reserved)


def test_audit_repository_blocks_explicit_reserved_tenant_queries(db_session: Session):
    """
    Verifies that list_by_entity, list_by_correlation_id, and list_by_merchant
    cannot expose reserved tenants (QUARANTINED_ORPHAN, platform_system, platform)
    through an ordinary merchant query, even when explicitly supplied.
    """
    # Seed events for reserved tenants and an ordinary tenant
    for res_tenant in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        AuditRepository.append(
            session=db_session,
            event=AuditEventCreate(
                merchant_id=res_tenant,
                actor_type="SYSTEM",
                actor_id=f"sys_{res_tenant}",
                action="SYSTEM_ACTION",
                entity_type="SYSTEM_ENTITY",
                entity_id="sys_100",
                correlation_id=f"corr_{res_tenant}",
                before_state=None,
                after_state=None,
                details=None,
            ),
        )

    # 1. list_by_entity with explicit reserved tenant IDs without privileged actor -> returns empty list
    for res_tenant in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        res_events = AuditRepository.list_by_entity(
            session=db_session,
            entity_type="SYSTEM_ENTITY",
            entity_id="sys_100",
            merchant_id=res_tenant,
        )
        assert res_events == [], f"Expected empty list for reserved tenant {res_tenant}"

    # 2. list_by_correlation_id with explicit reserved tenant IDs without privileged actor -> returns empty list
    for res_tenant in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        corr_events = AuditRepository.list_by_correlation_id(
            session=db_session,
            correlation_id=f"corr_{res_tenant}",
            merchant_id=res_tenant,
        )
        assert corr_events == [], f"Expected empty list for correlation {res_tenant}"

    # 3. list_by_merchant for reserved tenant IDs without privileged actor -> returns empty list
    for res_tenant in ["QUARANTINED_ORPHAN", "platform_system", "platform"]:
        merch_events = AuditRepository.list_by_merchant(
            session=db_session,
            merchant_id=res_tenant,
        )
        assert merch_events == [], f"Expected empty list for merchant {res_tenant}"


def test_audit_repository_unauthorized_privileged_flags_raise_error(db_session: Session):
    """
    Verifies that include_system=True and allow_quarantined=True are not treated
    as authorization and raise PermissionError when invoked by unauthorized callers.
    """
    AuditRepository.append(
        session=db_session,
        event=AuditEventCreate(
            merchant_id="platform_system",
            actor_type="SYSTEM",
            actor_id="sys_admin",
            action="SYSTEM_INIT",
            entity_type="SYSTEM_ENTITY",
            entity_id="sys_100",
            correlation_id="corr_platform_system",
            before_state=None,
            after_state=None,
            details=None,
        ),
    )

    ordinary_actor = AuthenticatedActor(
        actor_id="merchant_user_1",
        actor_type="merchant",
        role="merchant_operator",
        merchant_id="merchant_alpha",
    )

    # 1. list_by_entity with include_system=True without authorized actor
    with pytest.raises(PermissionError, match="include_system flag requires platform administrative authorization"):
        AuditRepository.list_by_entity(
            session=db_session,
            entity_type="SYSTEM_ENTITY",
            entity_id="sys_100",
            include_system=True,
        )

    # 2. list_by_entity with include_system=True with ordinary merchant actor
    with pytest.raises(PermissionError, match="include_system flag requires platform administrative authorization"):
        AuditRepository.list_by_entity(
            session=db_session,
            entity_type="SYSTEM_ENTITY",
            entity_id="sys_100",
            include_system=True,
            authorized_actor=ordinary_actor,
        )

    # 3. list_by_correlation_id with include_system=True without authorized actor
    with pytest.raises(PermissionError, match="include_system flag requires platform administrative authorization"):
        AuditRepository.list_by_correlation_id(
            session=db_session,
            correlation_id="corr_platform_system",
            include_system=True,
        )

    # 4. list_by_merchant with allow_quarantined=True without authorized actor
    with pytest.raises(PermissionError, match="allow_quarantined flag requires platform administrative authorization"):
        AuditRepository.list_by_merchant(
            session=db_session,
            merchant_id="QUARANTINED_ORPHAN",
            allow_quarantined=True,
        )

    # 5. Privileged actor (superadmin) succeeds with include_system=True
    superadmin_actor = AuthenticatedActor(
        actor_id="admin_1",
        actor_type="system",
        role="superadmin",
        merchant_id="platform_system",
    )
    events = AuditRepository.list_by_entity(
        session=db_session,
        entity_type="SYSTEM_ENTITY",
        entity_id="sys_100",
        include_system=True,
        authorized_actor=superadmin_actor,
    )
    assert len(events) >= 1

    # 6. AuditService boundary enforces authorization
    with pytest.raises(PermissionError, match="actor lacks platform administrative privileges"):
        AuditService.list_events_by_entity(
            session=db_session,
            entity_type="SYSTEM_ENTITY",
            entity_id="sys_100",
            actor=ordinary_actor,
            include_system=True,
        )

    svc_events = AuditService.list_events_by_entity(
        session=db_session,
        entity_type="SYSTEM_ENTITY",
        entity_id="sys_100",
        actor=superadmin_actor,
        include_system=True,
    )
    assert len(svc_events) >= 1
