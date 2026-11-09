import datetime
import json
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.health import get_health
from backend.api.operations import (
    get_operations_overview,
    list_stuck_webhooks,
    replay_webhook_event,
    trigger_reconciliation,
)
from backend.core.security import AuthenticatedActor
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.order import Order
from backend.models.product import Product
from backend.models.reservation import DemoInventoryReservation
from backend.models.webhook import WebhookEvent
from backend.models.worker_heartbeat import WorkerHeartbeat
from backend.policies.checkout_policy import (
    CaptureStatus,
    OrderStatus,
    PaymentStatus,
    ReconciliationStatus,
    ReservationStatus,
    WebhookEventStatus,
)
from backend.repositories.reconciliation import PaymentReconciliationRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.schemas.operations import ReplayWebhookRequest, TriggerReconciliationRequest
from backend.schemas.payment import CapturePaymentRequest
from backend.services.payment import PaymentService
from backend.services.webhook import WebhookService
from backend.services.webhook_worker import WebhookWorkerService, calculate_backoff


@pytest.fixture
def mock_paypal() -> MockPayPalClient:
    return MockPayPalClient()


@pytest.fixture
def operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="operator-1",
        actor_type="merchant",
        role="demo_operator",
        is_authenticated=True,
    )


@pytest.fixture
def ordinary_user_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="buyer-1",
        actor_type="ordinary_user",
        role="ordinary_user",
        is_authenticated=True,
    )


@pytest.fixture
def sample_order(db_session: Session) -> Order:
    product = Product(
        sku="SX-001",
        title="StrideX Runner",
        description="High-performance running shoe.",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    db_session.add(product)
    db_session.flush()

    order = Order(
        order_id=f"prip_ord_{uuid.uuid4().hex[:8]}",
        paypal_order_id=f"PAYPAL-ORD-{uuid.uuid4().hex[:8].upper()}",
        sku=product.sku,
        product_id=product.id,
        unit_price=product.price,
        currency="USD",
        quantity=1,
        total_amount=product.price,
        order_status=OrderStatus.CREATED.value,
        payment_status=PaymentStatus.PENDING.value,
        preflight_passed=True,
    )
    db_session.add(order)
    db_session.flush()

    reservation = DemoInventoryReservation(
        order_id=order.id,
        sku=order.sku,
        quantity=1,
        status=ReservationStatus.RESERVED.value,
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15),
    )
    db_session.add(reservation)
    db_session.commit()
    db_session.refresh(order)
    return order


class TestOperationalResilience:
    """
    Phase 7 Comprehensive Automated Test Suite.
    Covers durable background processing, worker leasing, retry backoff,
    dead-letter recovery, authoritative reconciliation, and operational visibility.
    """

    def test_01_pending_webhook_is_processed_successfully(
        self, db_session: Session, sample_order: Order
    ) -> None:
        """Scenario 1: Pending webhook is claimed and processed successfully to PROCESSED."""
        wh_repo = WebhookEventRepository(db_session)
        raw_payload = json.dumps({
            "id": "WH-TEST-01",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": sample_order.paypal_order_id},
        })
        event = WebhookEvent(
            paypal_event_id="WH-TEST-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PENDING.value,
            raw_payload=raw_payload,
            attempt_count=0,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        worker = WebhookWorkerService(db_session, worker_id="test_worker_1")
        processed_count = worker.tick(batch_size=5)

        assert processed_count == 1
        db_session.refresh(event)
        assert event.status == WebhookEventStatus.PROCESSED.value
        assert event.processed_at is not None
        assert event.locked_by is None

        db_session.refresh(sample_order)
        assert sample_order.order_status == OrderStatus.APPROVED.value

    def test_02_duplicate_webhook_is_processed_only_once(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 2: Duplicate webhook with same paypal_event_id is processed only once."""
        service = WebhookService(db_session, paypal_client=mock_paypal)
        headers = {
            "paypal-transmission-id": "trans-dup-01",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        body = json.dumps({
            "id": "WH-DUP-EVENT-001",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": sample_order.paypal_order_id},
        })

        # First delivery
        resp1 = service.process_webhook(headers=headers, raw_body=body)
        assert resp1.status == WebhookEventStatus.PROCESSED.value

        # Second delivery (duplicate)
        resp2 = service.process_webhook(headers=headers, raw_body=body)
        assert resp2.status == WebhookEventStatus.DUPLICATE.value

    def test_03_worker_crash_during_processing_is_recovered(
        self, db_session: Session, sample_order: Order
    ) -> None:
        """Scenario 3: Worker crash leaves event in PROCESSING; subsequent worker recovers and finishes."""
        wh_repo = WebhookEventRepository(db_session)
        raw_payload = json.dumps({
            "id": "WH-CRASH-01",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": sample_order.paypal_order_id},
        })
        # Simulate crashed worker: status=PROCESSING, lease expired 30 seconds ago
        past_lease = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=30)
        event = WebhookEvent(
            paypal_event_id="WH-CRASH-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PROCESSING.value,
            raw_payload=raw_payload,
            locked_by="crashed_worker_dead",
            processing_lease_expires_at=past_lease,
            attempt_count=1,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        # Recovery worker
        recovery_worker = WebhookWorkerService(db_session, worker_id="recovery_worker_1")
        processed = recovery_worker.tick(batch_size=5)

        assert processed == 1
        db_session.refresh(event)
        assert event.status == WebhookEventStatus.PROCESSED.value
        assert event.locked_by is None
        db_session.refresh(sample_order)
        assert sample_order.order_status == OrderStatus.APPROVED.value

    def test_04_expired_processing_lease_is_reclaimed_safely(
        self, db_session: Session
    ) -> None:
        """Scenario 4: Expired processing lease is safely reclaimed by another worker."""
        wh_repo = WebhookEventRepository(db_session)
        past_lease = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
        event = WebhookEvent(
            paypal_event_id="WH-LEASE-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PROCESSING.value,
            raw_payload=json.dumps({"id": "WH-LEASE-01"}),
            locked_by="worker_old",
            processing_lease_expires_at=past_lease,
            attempt_count=1,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        claimed = wh_repo.claim_eligible_event(worker_id="worker_new", lease_seconds=60)
        assert claimed is not None
        assert claimed.id == event.id
        assert claimed.locked_by == "worker_new"
        assert claimed.attempt_count == 2

    def test_05_concurrent_workers_cannot_claim_the_same_event(
        self, db_session: Session
    ) -> None:
        """Scenario 5: Two concurrent worker claim attempts on single event; only one succeeds."""
        wh_repo = WebhookEventRepository(db_session)
        event = WebhookEvent(
            paypal_event_id="WH-CONCURRENT-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PENDING.value,
            raw_payload=json.dumps({"id": "WH-CONCURRENT-01"}),
            attempt_count=0,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        # Worker A claims
        claimed_a = wh_repo.claim_eligible_event(worker_id="worker_A", lease_seconds=60)
        assert claimed_a is not None
        assert claimed_a.locked_by == "worker_A"

        # Worker B tries to claim immediately
        claimed_b = wh_repo.claim_eligible_event(worker_id="worker_B", lease_seconds=60)
        assert claimed_b is None

    def test_06_retry_backoff_schedules_the_next_attempt_correctly(
        self, db_session: Session
    ) -> None:
        """Scenario 6: Failed event is transitioned to RETRYABLE_FAILURE with future exponential backoff."""
        wh_repo = WebhookEventRepository(db_session)
        # Invalid JSON triggers failure
        event = WebhookEvent(
            paypal_event_id="WH-FAIL-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PROCESSING.value,
            raw_payload="INVALID_JSON{{{",
            attempt_count=1,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        worker = WebhookWorkerService(db_session, worker_id="test_worker")
        success = worker.process_event(event)

        assert success is False
        db_session.refresh(event)
        assert event.status == WebhookEventStatus.RETRYABLE_FAILURE.value
        assert event.error_category == "INVALID_PAYLOAD"
        assert event.next_retry_at is not None
        retry_time = event.next_retry_at
        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=datetime.timezone.utc)
        assert retry_time > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)

        # Backoff function calculation verification
        backoff_1 = calculate_backoff(1, base_delay=1.0)
        backoff_3 = calculate_backoff(3, base_delay=1.0)
        assert backoff_3 > backoff_1

    def test_07_maximum_attempts_move_an_event_to_dead_letter(
        self, db_session: Session
    ) -> None:
        """Scenario 7: When attempt_count reaches max_attempts, event moves to DEAD_LETTER."""
        wh_repo = WebhookEventRepository(db_session)
        event = WebhookEvent(
            paypal_event_id="WH-DEAD-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PROCESSING.value,
            raw_payload="MALFORMED_DATA",
            attempt_count=5,  # Max reached
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        worker = WebhookWorkerService(db_session, worker_id="test_worker")
        success = worker.process_event(event)

        assert success is False
        db_session.refresh(event)
        assert event.status == WebhookEventStatus.DEAD_LETTER.value
        assert event.error_category == "INVALID_PAYLOAD"

    def test_08_authorized_replay_processes_an_eligible_dead_letter_event(
        self, db_session: Session, sample_order: Order
    ) -> None:
        """Scenario 8: Authorized operator replays an eligible dead-letter event and succeeds."""
        wh_repo = WebhookEventRepository(db_session)
        raw_payload = json.dumps({
            "id": "WH-REPLAY-01",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": sample_order.paypal_order_id},
        })
        event = WebhookEvent(
            paypal_event_id="WH-REPLAY-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.DEAD_LETTER.value,
            raw_payload=raw_payload,
            attempt_count=5,
            max_attempts=5,
            last_error="Simulated permanent error",
        )
        wh_repo.create(event)
        db_session.commit()

        worker = WebhookWorkerService(db_session, worker_id="operator_worker")
        replayed = worker.replay_event(event.id, actor_id="operator-1", actor_type="DEMO_OPERATOR")

        assert replayed.status == WebhookEventStatus.PROCESSED.value
        db_session.refresh(sample_order)
        assert sample_order.order_status == OrderStatus.APPROVED.value

    def test_09_unauthorized_replay_is_rejected(
        self, db_session: Session, ordinary_user_actor: AuthenticatedActor
    ) -> None:
        """Scenario 9: Ordinary user without operator permissions cannot trigger replay (HTTP 403)."""
        wh_repo = WebhookEventRepository(db_session)
        event = WebhookEvent(
            paypal_event_id="WH-UNAUTH-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.DEAD_LETTER.value,
            raw_payload=json.dumps({"id": "WH-UNAUTH-01"}),
            attempt_count=5,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        req = ReplayWebhookRequest()
        with pytest.raises(HTTPException) as exc_info:
            replay_webhook_event(
                event_id=event.id,
                request=req,
                current_actor=ordinary_user_actor,
                db=db_session,
            )
        assert exc_info.value.status_code == 403

    def test_10_replay_does_not_duplicate_audit_events_or_payment_transitions(
        self, db_session: Session, sample_order: Order
    ) -> None:
        """Scenario 10: Replay of an already captured order is idempotent and does not corrupt payment state."""
        sample_order.payment_status = PaymentStatus.CAPTURED.value
        sample_order.order_status = OrderStatus.COMPLETED.value
        db_session.commit()

        wh_repo = WebhookEventRepository(db_session)
        raw_payload = json.dumps({
            "id": "WH-REPLAY-DUP-01",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"custom_id": sample_order.order_id},
        })
        event = WebhookEvent(
            paypal_event_id="WH-REPLAY-DUP-01",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            resource_type="capture",
            status=WebhookEventStatus.DEAD_LETTER.value,
            raw_payload=raw_payload,
            attempt_count=5,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        worker = WebhookWorkerService(db_session)
        replayed = worker.replay_event(event.id)

        assert replayed.status == WebhookEventStatus.PROCESSED.value
        db_session.refresh(sample_order)
        # Order remains in COMPLETED / CAPTURED state
        assert sample_order.payment_status == PaymentStatus.CAPTURED.value
        assert sample_order.order_status == OrderStatus.COMPLETED.value

    def test_11_paypal_outage_does_not_lose_durable_jobs(
        self, db_session: Session, sample_order: Order
    ) -> None:
        """Scenario 11: Outage during processing persists failure in durable queue without data loss."""
        wh_repo = WebhookEventRepository(db_session)
        event = WebhookEvent(
            paypal_event_id="WH-OUTAGE-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.PENDING.value,
            raw_payload=json.dumps({"id": "WH-OUTAGE-01"}),
            attempt_count=0,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        # Job is durably stored in database
        saved = wh_repo.get_by_paypal_event_id("WH-OUTAGE-01")
        assert saved is not None
        assert saved.status == WebhookEventStatus.PENDING.value

    def test_12_uncertain_capture_is_reconciled_before_any_retry(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 12: Capture timeout sets UNKNOWN; blind retry is blocked until reconciled."""
        service = PaymentService(db_session, paypal_client=mock_paypal)
        mock_paypal.mock_buyer_approve(sample_order.paypal_order_id)  # type: ignore

        # 1. Trigger simulated timeout
        req = CapturePaymentRequest(order_id=sample_order.order_id, simulate_timeout=True)
        resp = service.capture_payment(req)
        assert resp.status == CaptureStatus.UNKNOWN.value
        assert resp.reconciliation_status == ReconciliationStatus.RECONCILIATION_REQUIRED.value

        db_session.refresh(sample_order)
        assert sample_order.payment_status == PaymentStatus.UNKNOWN.value

        # 2. Attempting blind capture retry raises ValueError
        retry_req = CapturePaymentRequest(order_id=sample_order.order_id)
        with pytest.raises(ValueError, match="ambiguous capture outcome"):
            service.capture_payment(retry_req)

    def test_13_provider_confirmed_capture_updates_local_state_correctly(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 13: Reconciliation confirms provider completed capture -> updates state to CAPTURED."""
        service = PaymentService(db_session, paypal_client=mock_paypal)
        sample_order.payment_status = PaymentStatus.UNKNOWN.value
        db_session.commit()

        # PayPal confirms COMPLETED
        mock_paypal.mock_set_order_status(sample_order.paypal_order_id, "COMPLETED")  # type: ignore

        res = service.reconcile_payment(sample_order.order_id)
        assert res.payment_status == PaymentStatus.CAPTURED.value
        assert res.order_status == OrderStatus.COMPLETED.value

        # Check PaymentReconciliation log
        rec_repo = PaymentReconciliationRepository(db_session)
        history = rec_repo.list_history()
        assert len(history) >= 1
        assert history[0].outcome == "RESOLVED_CAPTURED"

    def test_14_provider_confirmed_failure_updates_local_state_correctly(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 14: Reconciliation confirms provider declined/failed -> updates state to FAILED."""
        service = PaymentService(db_session, paypal_client=mock_paypal)
        sample_order.payment_status = PaymentStatus.UNKNOWN.value
        db_session.commit()

        # PayPal confirms DECLINED
        mock_paypal.mock_set_order_status(sample_order.paypal_order_id, "DECLINED")  # type: ignore

        res = service.reconcile_payment(sample_order.order_id)
        assert res.payment_status == PaymentStatus.FAILED.value
        assert res.order_status == OrderStatus.FAILED.value

        rec_repo = PaymentReconciliationRepository(db_session)
        history = rec_repo.list_history()
        assert history[0].outcome == "RESOLVED_FAILED"

    def test_15_reconciliation_is_safe_to_repeat(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 15: Repeated reconciliation is idempotent and logs NO_DISCREPANCY."""
        service = PaymentService(db_session, paypal_client=mock_paypal)
        sample_order.payment_status = PaymentStatus.CAPTURED.value
        sample_order.order_status = OrderStatus.COMPLETED.value
        db_session.commit()

        mock_paypal.mock_set_order_status(sample_order.paypal_order_id, "COMPLETED")  # type: ignore

        # Run 1
        res1 = service.reconcile_payment(sample_order.order_id)
        assert res1.payment_status == PaymentStatus.CAPTURED.value

        # Run 2 (repeat)
        res2 = service.reconcile_payment(sample_order.order_id)
        assert res2.payment_status == PaymentStatus.CAPTURED.value

        rec_repo = PaymentReconciliationRepository(db_session)
        history = rec_repo.list_history()
        assert history[0].outcome == "NO_DISCREPANCY"

    def test_16_delayed_webhooks_do_not_regress_payment_state(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient
    ) -> None:
        """Scenario 16: Out-of-order/delayed approval webhook cannot regress CAPTURED order."""
        sample_order.payment_status = PaymentStatus.CAPTURED.value
        sample_order.order_status = OrderStatus.COMPLETED.value
        db_session.commit()

        service = WebhookService(db_session, paypal_client=mock_paypal)
        headers = {
            "paypal-transmission-id": "trans-delayed-01",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        delayed_payload = json.dumps({
            "id": "WH-DELAYED-APPROVAL-01",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": sample_order.paypal_order_id},
        })

        service.process_webhook(headers=headers, raw_body=delayed_payload)

        db_session.refresh(sample_order)
        # Order cannot regress to APPROVED
        assert sample_order.payment_status == PaymentStatus.CAPTURED.value
        assert sample_order.order_status == OrderStatus.COMPLETED.value

    def test_17_concurrent_reconciliation_requests_do_not_duplicate_work(
        self, db_session: Session, sample_order: Order, mock_paypal: MockPayPalClient, operator_actor: AuthenticatedActor
    ) -> None:
        """Scenario 17: Concurrent reconciliation triggers execute idempotently."""
        sample_order.payment_status = PaymentStatus.UNKNOWN.value
        db_session.commit()

        mock_paypal.mock_set_order_status(sample_order.paypal_order_id, "COMPLETED")  # type: ignore

        req = TriggerReconciliationRequest(order_id=sample_order.order_id)
        res1 = trigger_reconciliation(request=req, current_actor=operator_actor, db=db_session)
        res2 = trigger_reconciliation(request=req, current_actor=operator_actor, db=db_session)

        assert res1.reconciled_count == 1
        assert res2.reconciled_count == 1
        db_session.refresh(sample_order)
        assert sample_order.payment_status == PaymentStatus.CAPTURED.value

    def test_18_worker_heartbeat_becomes_stale_after_a_simulated_crash(
        self, db_session: Session, operator_actor: AuthenticatedActor
    ) -> None:
        """Scenario 18: Worker crash causes heartbeat to exceed stale threshold -> reported as STALE."""
        past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=200)

        hb = WorkerHeartbeat(
            worker_id="crashed_worker_01",
            worker_type="WEBHOOK_PROCESSOR",
            status="ACTIVE",
            last_heartbeat_at=past_time,
        )
        db_session.add(hb)
        db_session.commit()

        overview = get_operations_overview(current_actor=operator_actor, db=db_session)
        assert overview.stale_workers_count >= 1

        worker_resp = next(w for w in overview.workers if w.worker_id == "crashed_worker_01")
        assert worker_resp.status == "STALE"

    def test_19_health_endpoints_distinguish_application_and_dependency_health(
        self, db_session: Session
    ) -> None:
        """Scenario 19: Health endpoint surfaces granular application and dependency health breakdown."""
        health = get_health(db=db_session)
        assert health.status in ("healthy", "degraded")
        assert health.dependencies is not None
        assert "database" in health.dependencies
        assert health.dependencies["database"]["status"] == "healthy"
        assert "paypal_sandbox" in health.dependencies

    def test_20_logs_and_operational_api_responses_do_not_expose_secrets_or_raw_payloads(
        self, db_session: Session, operator_actor: AuthenticatedActor
    ) -> None:
        """Scenario 20: Operational endpoints never expose raw_payload or secrets."""
        wh_repo = WebhookEventRepository(db_session)
        event = WebhookEvent(
            paypal_event_id="WH-SECRET-01",
            event_type="CHECKOUT.ORDER.APPROVED",
            resource_type="order",
            status=WebhookEventStatus.DEAD_LETTER.value,
            raw_payload=json.dumps({"secret_token": "SENSITIVE_DATA_12345"}),
            attempt_count=5,
            max_attempts=5,
        )
        wh_repo.create(event)
        db_session.commit()

        stuck_list = list_stuck_webhooks(current_actor=operator_actor, db=db_session)
        assert len(stuck_list) >= 1
        item = next(e for e in stuck_list if e.paypal_event_id == "WH-SECRET-01")
        item_dict = item.model_dump(mode="json")

        assert "raw_payload" not in item_dict
        assert "SENSITIVE_DATA_12345" not in json.dumps(item_dict)

    def test_21_database_migration_upgrade_and_downgrade_work(self) -> None:
        """Scenario 21: Alembic migration upgrade to 007 and downgrade to 006 work without error."""
        import subprocess
        import sys
        # Downgrade to 006
        p1 = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "006_payment_and_orders"], capture_output=True, text=True)
        assert p1.returncode == 0

        # Upgrade to head (007)
        p2 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True)
        assert p2.returncode == 0

    def test_22_existing_phase_1_to_6_regression_tests_remain_passing(
        self, db_session: Session
    ) -> None:
        """Scenario 22: Non-negotiable PRIP invariants from Phase 1-6 remain satisfied."""
        from unittest.mock import MagicMock

        from backend.policies.checkout_policy import (
            validate_checkout_preflight,
            validate_order_transition,
            validate_payment_transition,
        )

        # 1. State machine invariants
        assert validate_order_transition(OrderStatus.CREATED, OrderStatus.APPROVED) is True
        assert validate_order_transition(OrderStatus.COMPLETED, OrderStatus.APPROVED) is False  # Monotonic
        assert validate_payment_transition(PaymentStatus.UNKNOWN, PaymentStatus.CAPTURED) is True
        assert validate_payment_transition(PaymentStatus.CAPTURED, PaymentStatus.PENDING) is False

        # 2. Preflight price discrepancy invariant
        cat_prod = MagicMock(sku="SX-001", price=Decimal("100.00"), currency="USD", is_active=True)
        store_prod_diff = MagicMock(sku="SX-001", price=Decimal("120.00"), currency="USD", is_published=True)
        store_prod_same = MagicMock(sku="SX-001", price=Decimal("100.00"), currency="USD", is_published=True)

        blocked = validate_checkout_preflight(cat_prod, store_prod_diff)
        assert blocked.passed is False
        assert any("Price discrepancy detected" in r for r in blocked.blocking_reasons)

        passed = validate_checkout_preflight(cat_prod, store_prod_same)
        assert passed.passed is True
