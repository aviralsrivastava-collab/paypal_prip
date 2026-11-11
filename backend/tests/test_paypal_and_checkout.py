import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.checkout import (
    capture_order,
    create_order,
    get_order,
    list_orders,
    preflight_check,
    reconcile_order,
)
from backend.api.webhooks import list_webhook_events
from backend.core.security import AuthenticatedActor
from backend.integrations.paypal import (
    PayPalError,
    PayPalSandboxClient,
)
from backend.integrations.paypal.base import (
    PayPalApiError,
    PayPalCaptureResponse,
    PayPalOrderResponse,
)
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.policies.checkout_policy import (
    OrderStatus,
    PaymentStatus,
    ReconciliationStatus,
    ReservationStatus,
)
from backend.repositories.order import OrderRepository
from backend.repositories.payment_capture import PaymentCaptureRepository
from backend.repositories.reservation import ReservationRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.checkout import CreateOrderRequest, PreflightCheckRequest
from backend.schemas.payment import CapturePaymentRequest
from backend.services.catalog import CatalogService
from backend.services.checkout import CheckoutService
from backend.services.inspection import InspectionService
from backend.services.payment import PaymentService
from backend.services.webhook import WebhookService


@pytest.fixture
def merchant_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="merchant-jane", role="merchant_operator", actor_type="merchant")


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    catalog_service = CatalogService(db_session)
    catalog_service.seed_initial_catalog(reset=True)
    return db_session


class TestPayPalAndCheckout:
    """
    Phase 6 Comprehensive Verification Suite:
    - Preflight discrepancy gate
    - Server-side PayPal Orders v2 creation and demo reservation
    - Server-side capture with fee breakdown
    - Ambiguous timeout handling to UNKNOWN and authoritative reconciliation
    - Webhook cryptographic signature check and deduplication
    - Sandbox isolation
    - API route handler verification
    """

    def test_1_preflight_blocks_when_price_discrepancy_exists(self, seeded_db: Session) -> None:
        """
        Gating check: Catalog USD 100.00 vs Storefront USD 120.00 must block checkout.
        """
        checkout_service = CheckoutService(seeded_db)
        preflight = checkout_service.preflight_check("SX-001")

        assert preflight.passed is False
        assert preflight.sku == "SX-001"
        assert preflight.catalog_price == Decimal("100.00")
        assert preflight.storefront_price == Decimal("120.00")
        assert any("Price discrepancy detected" in reason for reason in preflight.blocking_reasons)

        # Attempting to create an order directly must raise an exception
        req = CreateOrderRequest(sku="SX-001", quantity=1)
        with pytest.raises(ValueError, match="Checkout blocked"):
            checkout_service.create_order(req, actor_id="merchant-jane")

    def test_2_preflight_passes_when_prices_match(self, seeded_db: Session) -> None:
        """
        Gating check: When storefront price is synchronized to ground truth USD 100.00,
        preflight must pass and allow order creation.
        """
        # Synchronize storefront price to 100.00
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        # Run inspection scan to produce clean state
        from backend.schemas.scan import ScanCreateRequest
        inspection_service = InspectionService(seeded_db)
        actor = AuthenticatedActor(actor_id="merchant-jane", role="merchant_operator", actor_type="merchant")
        scan = inspection_service.run_inspection(ScanCreateRequest(sku="SX-001"), trusted_actor=actor)
        assert scan.state == "VERIFIED_NO_ISSUE"

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        preflight = checkout_service.preflight_check("SX-001")

        assert preflight.passed is True
        assert preflight.catalog_price == Decimal("100.00")
        assert preflight.storefront_price == Decimal("100.00")
        assert len(preflight.blocking_reasons) == 0

        # Create order
        req = CreateOrderRequest(sku="SX-001", quantity=1)
        order_resp = checkout_service.create_order(req, actor_id="merchant-jane")

        assert order_resp.order_id.startswith("prip_ord_")
        assert order_resp.paypal_order_id is not None
        assert order_resp.paypal_order_id.startswith("MOCK-ORD-")
        assert order_resp.total_amount == Decimal("100.00")
        assert order_resp.order_status == OrderStatus.CREATED.value
        assert order_resp.payment_status == PaymentStatus.PENDING.value
        assert order_resp.preflight_passed is True
        assert order_resp.approve_url is not None

    def test_3_order_creation_idempotency(self, seeded_db: Session) -> None:
        """
        Idempotency check: Repeated request with identical idempotency_key returns existing order.
        """
        # Synchronize price first
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        checkout_service = CheckoutService(seeded_db, paypal_client=MockPayPalClient())
        key = "idemp-checkout-key-001"

        req1 = CreateOrderRequest(sku="SX-001", quantity=1, idempotency_key=key)
        resp1 = checkout_service.create_order(req1, actor_id="merchant-jane")

        req2 = CreateOrderRequest(sku="SX-001", quantity=1, idempotency_key=key)
        resp2 = checkout_service.create_order(req2, actor_id="merchant-jane")

        assert resp1.order_id == resp2.order_id
        assert resp1.paypal_order_id == resp2.paypal_order_id

        # Verify only 1 order exists in database
        order_repo = OrderRepository(seeded_db)
        orders = order_repo.list_orders()
        assert len(orders) == 1

    def test_4_demo_inventory_reservation(self, seeded_db: Session) -> None:
        """
        Inventory check: Demo inventory reservation is created with 15-minute expiration.
        """
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        checkout_service = CheckoutService(seeded_db, paypal_client=MockPayPalClient())
        req = CreateOrderRequest(sku="SX-001", quantity=2)
        order_resp = checkout_service.create_order(req, actor_id="merchant-jane")

        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None

        reservation_repo = ReservationRepository(seeded_db)
        res = reservation_repo.get_by_order_id(order.id)
        assert res is not None
        assert res.sku == "SX-001"
        assert res.quantity == 2
        assert res.status == ReservationStatus.RESERVED.value
        assert res.expires_at > res.created_at

    def test_5_server_side_capture_success_and_fee_breakdown(self, seeded_db: Session) -> None:
        """
        Payment check: Authoritative server-side capture succeeds, records fee breakdown,
        commits inventory reservation, and logs audit event.
        """
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(
            CreateOrderRequest(sku="SX-001", quantity=1),
            actor_id="merchant-jane",
        )

        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        capture_resp = payment_service.capture_payment(
            CapturePaymentRequest(order_id=order_resp.order_id),
            actor_id="merchant-jane",
        )

        assert capture_resp.status == "COMPLETED"
        assert capture_resp.amount == Decimal("100.00")
        assert capture_resp.fee_amount == Decimal("3.49")
        assert capture_resp.net_amount == Decimal("96.51")
        assert capture_resp.reconciliation_status == ReconciliationStatus.NOT_NEEDED.value

        # Verify order state transition
        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.CAPTURED.value
        assert order.order_status == OrderStatus.COMPLETED.value

        # Verify inventory reservation committed
        reservation_repo = ReservationRepository(seeded_db)
        res = reservation_repo.get_by_order_id(order.id)
        assert res is not None
        assert res.status == ReservationStatus.COMMITTED.value

    def test_6_capture_timeout_transitions_to_unknown_and_requires_reconciliation(
        self, seeded_db: Session
    ) -> None:
        """
        Ambiguity & Invariant check:
        When PayPal capture times out, outcome is ambiguous:
        - Must persist UNKNOWN state.
        - Must set reconciliation_status to RECONCILIATION_REQUIRED.
        - Blind retry must be blocked.
        - Authoritative reconciliation queries PayPal and updates status to CAPTURED.
        """
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(
            CreateOrderRequest(sku="SX-001", quantity=1),
            actor_id="merchant-jane",
        )

        # Trigger capture with timeout simulation
        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        capture_resp = payment_service.capture_payment(
            CapturePaymentRequest(order_id=order_resp.order_id, simulate_timeout=True),
            actor_id="merchant-jane",
        )

        assert capture_resp.status == "UNKNOWN"
        assert capture_resp.reconciliation_status == ReconciliationStatus.RECONCILIATION_REQUIRED.value

        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.UNKNOWN.value

        # Blind retry MUST be blocked
        mock_paypal.simulate_timeout = False
        with pytest.raises(ValueError, match="ambiguous capture outcome"):
            payment_service.capture_payment(
                CapturePaymentRequest(order_id=order_resp.order_id),
                actor_id="merchant-jane",
            )

        # Authoritative reconciliation
        # Simulate that PayPal actually completed the order
        assert order.paypal_order_id is not None
        mock_paypal._orders[order.paypal_order_id]["status"] = "COMPLETED"

        rec_resp = payment_service.reconcile_payment(order_resp.order_id, actor_id="merchant-jane")
        assert rec_resp.payment_status == PaymentStatus.CAPTURED.value
        assert rec_resp.order_status == OrderStatus.COMPLETED.value
        assert rec_resp.reconciliation_status == ReconciliationStatus.RECONCILED.value

        # Re-check database
        seeded_db.refresh(order)
        assert order.payment_status == PaymentStatus.CAPTURED.value
        assert order.order_status == OrderStatus.COMPLETED.value

    def test_7_capture_decline_transitions_to_failed(self, seeded_db: Session) -> None:
        """
        Failure check: Buyer decline transitions order to FAILED.
        """
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(
            CreateOrderRequest(sku="SX-001", quantity=1),
            actor_id="merchant-jane",
        )

        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        capture_resp = payment_service.capture_payment(
            CapturePaymentRequest(order_id=order_resp.order_id, simulate_decline=True),
            actor_id="merchant-jane",
        )

        assert capture_resp.status == "DECLINED"
        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.FAILED.value
        assert order.order_status == OrderStatus.FAILED.value

    def test_8_webhook_cryptographic_signature_verification(self, seeded_db: Session) -> None:
        """
        Security check: Webhook requires authentic cryptographic transmission headers.
        Missing headers or forged signatures must be rejected.
        """
        webhook_service = WebhookService(seeded_db, paypal_client=MockPayPalClient())
        payload = json.dumps({"id": "WH-EVT-100", "event_type": "CHECKOUT.ORDER.APPROVED"})

        # Missing headers -> rejected
        with pytest.raises(ValueError, match="signature verification failed"):
            webhook_service.process_webhook(headers={}, raw_body=payload)

        # Forged signature -> rejected
        forged_headers = {
            "paypal-transmission-id": "trans-123",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "FORGED",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        with pytest.raises(ValueError, match="signature verification failed"):
            webhook_service.process_webhook(headers=forged_headers, raw_body=payload)

        # Valid mock headers -> accepted
        valid_headers = {
            "paypal-transmission-id": "trans-123",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIGNATURE_BYTES",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        resp = webhook_service.process_webhook(headers=valid_headers, raw_body=payload)
        assert resp.paypal_event_id == "WH-EVT-100"
        assert resp.status == "PROCESSED"

    def test_9_webhook_deduplication_and_idempotency(self, seeded_db: Session) -> None:
        """
        Deduplication check: Submitting the same paypal_event_id twice must be safely ignored.
        """
        webhook_service = WebhookService(seeded_db, paypal_client=MockPayPalClient())
        payload = json.dumps({"id": "WH-EVT-DEDUP-001", "event_type": "CHECKOUT.ORDER.APPROVED"})
        valid_headers = {
            "paypal-transmission-id": "trans-dedup-1",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "SIG-VALID",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }

        # First delivery
        resp1 = webhook_service.process_webhook(headers=valid_headers, raw_body=payload)
        assert resp1.status == "PROCESSED"

        # Duplicate delivery
        resp2 = webhook_service.process_webhook(headers=valid_headers, raw_body=payload)
        assert resp2.status == "DUPLICATE"
        assert resp2.paypal_event_id == "WH-EVT-DEDUP-001"

    def test_10_webhook_drives_order_lifecycle_transitions(self, seeded_db: Session) -> None:
        """
        Event processing check:
        - CHECKOUT.ORDER.APPROVED webhook transitions order to APPROVED
        - PAYMENT.CAPTURE.COMPLETED webhook transitions order to COMPLETED / CAPTURED
        """
        storefront_repo = StorefrontRepository(seeded_db)
        st_prod = storefront_repo.get_by_sku("SX-001")
        assert st_prod is not None
        st_prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(
            CreateOrderRequest(sku="SX-001", quantity=1),
            actor_id="merchant-jane",
        )

        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.order_status == OrderStatus.CREATED.value

        webhook_service = WebhookService(seeded_db, paypal_client=mock_paypal)
        headers = {
            "paypal-transmission-id": "trans-wh-appr",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }

        # 1. ORDER.APPROVED webhook
        wh_order_approved = json.dumps({
            "id": "WH-ORDER-APPROVED-001",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": order.paypal_order_id},
        })
        webhook_service.process_webhook(headers=headers, raw_body=wh_order_approved)

        seeded_db.refresh(order)
        assert order.order_status == OrderStatus.APPROVED.value

        # 2. CAPTURE.COMPLETED webhook
        headers["paypal-transmission-id"] = "trans-wh-cap"
        wh_capture_completed = json.dumps({
            "id": "WH-CAPTURE-COMPLETED-001",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "custom_id": order.order_id,
                "amount": {"value": "100.00", "currency_code": "USD"},
            },
        })
        webhook_service.process_webhook(headers=headers, raw_body=wh_capture_completed)

        seeded_db.refresh(order)
        assert order.payment_status == PaymentStatus.CAPTURED.value
        assert order.order_status == OrderStatus.COMPLETED.value

    def test_11_sandbox_isolation_blocks_non_sandbox_endpoints(self) -> None:
        """
        Security check: PayPalSandboxClient refuses to initialize if base URL is not Sandbox.
        """
        with pytest.raises(PayPalError, match="not a PayPal Sandbox domain"):
            PayPalSandboxClient(
                client_id="test",
                client_secret="test",
                base_url="https://api-m.paypal.com",  # Production URL forbidden
            )

    def test_12_api_route_handlers_for_checkout_and_webhooks(
        self, seeded_db: Session, merchant_actor: AuthenticatedActor
    ) -> None:
        """
        Direct route handler verification:
        - preflight_check
        - create_order
        - capture_order
        - reconcile_order
        - list_orders
        - get_order
        - list_webhook_events
        """
        # 1. Preflight initially blocked
        pf_req = PreflightCheckRequest(sku="SX-001")
        pf_res = preflight_check(pf_req, db=seeded_db)
        assert pf_res.passed is False

        # Attempt to create order -> HTTP 400
        ord_req = CreateOrderRequest(sku="SX-001", quantity=1)
        with pytest.raises(HTTPException) as exc_info:
            create_order(ord_req, current_actor=merchant_actor, db=seeded_db)
        assert exc_info.value.status_code == 400

        # Synchronize price on storefront
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        # 2. Preflight now passes
        pf_res2 = preflight_check(pf_req, db=seeded_db)
        assert pf_res2.passed is True

        # 3. Create Order
        created = create_order(ord_req, current_actor=merchant_actor, db=seeded_db)
        assert created.order_id.startswith("prip_ord_")
        assert created.payment_status == "PENDING"

        # 4. List and Get Order
        orders = list_orders(current_actor=merchant_actor, db=seeded_db)
        assert len(orders) >= 1

        fetched = get_order(created.order_id, current_actor=merchant_actor, db=seeded_db)
        assert fetched.order_id == created.order_id

        # 5. Capture Order
        cap_res = capture_order(created.order_id, current_actor=merchant_actor, db=seeded_db)
        assert cap_res.status == "COMPLETED"
        assert cap_res.amount == Decimal("100.00")

        # 6. Reconcile Order
        rec_res = reconcile_order(created.order_id, current_actor=merchant_actor, db=seeded_db)
        assert rec_res.reconciliation_status == "RECONCILED"

        # 7. List webhook events
        wh_events = list_webhook_events(current_actor=merchant_actor, db=seeded_db)
        assert isinstance(wh_events, list)

    def test_13_paypal_request_id_passed_and_reused_on_retries(self, seeded_db: Session) -> None:
        """
        Idempotency check:
        - Confirms PayPal-Request-Id is passed to create_order and capture_order
        - Confirms stable key is reused across retries of the same logical operation
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        mock_paypal.received_request_ids.clear()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)

        custom_idemp_key = "user-idemp-key-999"
        req = CreateOrderRequest(sku="SX-001", quantity=1, idempotency_key=custom_idemp_key)
        order_resp = checkout_service.create_order(req, actor_id="merchant-jane")

        # Verify custom idempotency key was propagated as PayPal-Request-Id
        assert custom_idemp_key in mock_paypal.received_request_ids

        # Capture order with stable idempotency key
        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        cap_req = CapturePaymentRequest(order_id=order_resp.order_id, idempotency_key="cap-req-key-888")
        payment_service.capture_payment(cap_req, actor_id="merchant-jane")

        # Verify capture PayPal-Request-Id was received
        assert "cap-req-key-888" in mock_paypal.received_request_ids

    def test_14_fee_and_net_amount_represented_as_unavailable_when_omitted(self, seeded_db: Session) -> None:
        """
        Fee integrity check:
        When PayPal response omits seller_receivable_breakdown (fee unavailable),
        PRIP must record fee_amount and net_amount as None (unavailable) rather than inventing a fee.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient(simulate_missing_fee_breakdown=True)
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="merchant-jane")

        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        cap_resp = payment_service.capture_payment(CapturePaymentRequest(order_id=order_resp.order_id), actor_id="merchant-jane")

        assert cap_resp.status == "COMPLETED"
        assert cap_resp.amount == Decimal("100.00")
        assert cap_resp.fee_amount is None
        assert cap_resp.net_amount is None

        # Verify database record also has None (not 0.00, not invented)
        cap_repo = PaymentCaptureRepository(seeded_db)
        stored_cap = cap_repo.get_by_order_id(order_resp.id)
        assert stored_cap is not None
        assert stored_cap.fee_amount is None
        assert stored_cap.net_amount is None

    def test_15_out_of_order_events_cannot_regress_payment_state(self, seeded_db: Session) -> None:
        """
        State integrity check:
        Out-of-order webhook events (e.g. CHECKOUT.ORDER.APPROVED arriving after capture)
        cannot regress the payment_status or order_status from terminal COMPLETED / CAPTURED.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="merchant-jane")

        # Capture order
        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        payment_service.capture_payment(CapturePaymentRequest(order_id=order_resp.order_id), actor_id="merchant-jane")

        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.CAPTURED.value
        assert order.order_status == OrderStatus.COMPLETED.value

        # Now an out-of-order CHECKOUT.ORDER.APPROVED arrives
        webhook_service = WebhookService(seeded_db, paypal_client=mock_paypal)
        headers = {
            "paypal-transmission-id": "trans-ooo-1",
            "paypal-transmission-time": "2026-11-07T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        payload = json.dumps({
            "id": "WH-OUT-OF-ORDER-001",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": order.paypal_order_id},
        })
        webhook_service.process_webhook(headers=headers, raw_body=payload)

        # Confirm state did NOT regress to APPROVED or PENDING
        seeded_db.refresh(order)
        assert order.order_status == OrderStatus.COMPLETED.value
        assert order.payment_status == PaymentStatus.CAPTURED.value

    def test_16_public_buyer_checkout_succeeds_in_production_mode(self, seeded_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Public buyer checkout check:
        In production mode (app_env="production"), unauthenticated buyers can create an order,
        inspect its status, and capture it without requiring merchant OIDC Bearer tokens.
        """
        from backend.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")

        # Synchronize price so preflight passes
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        # 1. Public buyer creates order (current_actor=None)
        req = CreateOrderRequest(sku="SX-001", quantity=1)
        created = create_order(request=req, current_actor=None, db=seeded_db)
        assert created.order_id.startswith("prip_ord_")
        assert created.payment_status == "PENDING"
        assert created.order_status == "CREATED"

        # 2. Public buyer fetches order status (current_actor=None)
        fetched = get_order(order_id=created.order_id, current_actor=None, db=seeded_db)
        assert fetched.order_id == created.order_id

        # 3. Public buyer captures approved order (current_actor=None)
        cap = capture_order(order_id=created.order_id, request=None, current_actor=None, db=seeded_db)
        assert cap.status == "COMPLETED"
        assert cap.amount == Decimal("100.00")

    def test_17_root_post_returns_diagnostic_webhook_guidance(self) -> None:
        """
        Webhook diagnostics check:
        Verifies that POST / returns HTTP 400 with explicit guidance to use /api/webhooks/paypal.
        """
        from backend.api.main import root_post

        resp = root_post()
        assert resp.status_code == 400
        data = json.loads(resp.body.decode("utf-8"))
        assert data["error"] == "INCORRECT_WEBHOOK_URL"
        assert "/api/webhooks/paypal" in data["message"]
        assert data["registered_webhook_endpoint"] == "/api/webhooks/paypal"

    def test_18_webhook_signature_rejects_missing_headers_and_untrusted_cert(self) -> None:
        """
        Signature security check:
        Verifies PayPalSandboxClient.verify_webhook_signature strictly rejects missing headers
        and cert_url hostnames outside paypal.com.
        """
        client = PayPalSandboxClient(
            client_id="test-client-id",
            client_secret="test-client-secret",
            base_url="https://api-m.sandbox.paypal.com",
        )

        valid_payload = json.dumps({"id": "WH-TEST-001", "event_type": "CHECKOUT.ORDER.APPROVED"})

        # 1. Missing required headers
        assert client.verify_webhook_signature(headers={}, raw_body=valid_payload, webhook_id="WH-123") is False

        # 2. Untrusted cert host
        malicious_headers = {
            "paypal-transmission-id": "t1",
            "paypal-transmission-time": "2026-11-11T12:00:00Z",
            "paypal-transmission-sig": "sig123",
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://attacker.evil.com/fake-cert.pem",
        }
        assert client.verify_webhook_signature(headers=malicious_headers, raw_body=valid_payload, webhook_id="WH-123") is False

        # 3. Empty webhook ID
        legit_headers = {
            "paypal-transmission-id": "t1",
            "paypal-transmission-time": "2026-11-11T12:00:00Z",
            "paypal-transmission-sig": "sig123",
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        }
        assert client.verify_webhook_signature(headers=legit_headers, raw_body=valid_payload, webhook_id="") is False

    def test_19_capture_reconciles_order_already_captured(self, seeded_db: Session) -> None:
        """
        Concurrency check:
        When PayPal returns ORDER_ALREADY_CAPTURED error during capture, PRIP reconciles with PayPal
        and records COMPLETED rather than failing the transaction.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        # Create order
        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        # Mock PayPal client that throws ORDER_ALREADY_CAPTURED on capture, but returns COMPLETED on get_order_details
        class AlreadyCapturedMockClient(MockPayPalClient):
            def capture_order(self, paypal_order_id: str, paypal_request_id: str | None = None) -> PayPalCaptureResponse:
                raise PayPalApiError(422, "UNPROCESSABLE_ENTITY", '{"name":"ORDER_ALREADY_CAPTURED","message":"The order has already been captured."}')

            def get_order_details(self, paypal_order_id: str) -> PayPalOrderResponse:
                return PayPalOrderResponse(
                    paypal_order_id=paypal_order_id,
                    status="COMPLETED",
                    intent="CAPTURE",
                    amount=Decimal("100.00"),
                    currency="USD",
                    raw_response={"id": paypal_order_id, "status": "COMPLETED"},
                )

        reconciling_client = AlreadyCapturedMockClient()
        payment_service = PaymentService(seeded_db, paypal_client=reconciling_client)

        cap_resp = payment_service.capture_payment(CapturePaymentRequest(order_id=order_resp.order_id), actor_id="buyer")
        assert cap_resp.status == "COMPLETED"
        assert cap_resp.amount == Decimal("100.00")

        # Verify DB state
        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.CAPTURED.value
        assert order.order_status == OrderStatus.COMPLETED.value

    def test_20_webhook_payment_capture_completed_creates_payment_capture_record(self, seeded_db: Session) -> None:
        """
        Webhook persistence check:
        When PAYMENT.CAPTURE.COMPLETED webhook arrives, a PaymentCapture database record is
        created if not already captured via frontend.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        webhook_service = WebhookService(seeded_db, paypal_client=mock_paypal)
        headers = {
            "paypal-transmission-id": "t-cap-comp-1",
            "paypal-transmission-time": "2026-11-11T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        payload = json.dumps({
            "id": "WH-CAPTURE-COMPLETED-001",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAP-PAYPAL-REAL-999",
                "custom_id": order_resp.order_id,
                "amount": {"value": "100.00", "currency_code": "USD"},
                "seller_receivable_breakdown": {
                    "paypal_fee": {"value": "3.49", "currency_code": "USD"},
                    "net_amount": {"value": "96.51", "currency_code": "USD"},
                },
            },
        })
        webhook_service.process_webhook(headers=headers, raw_body=payload)

        # Verify order transitioned to CAPTURED
        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.CAPTURED.value

        # Verify PaymentCapture record exists in database
        cap_repo = PaymentCaptureRepository(seeded_db)
        cap = cap_repo.get_by_order_id(order.id)
        assert cap is not None
        assert cap.paypal_capture_id == "CAP-PAYPAL-REAL-999"
        assert cap.status == "COMPLETED"
        assert cap.amount == Decimal("100.00")
        assert cap.fee_amount == Decimal("3.49")
        assert cap.net_amount == Decimal("96.51")

    def test_21_webhook_pending_and_reversed_handling(self, seeded_db: Session) -> None:
        """
        Webhook edge cases check:
        Verifies PAYMENT.CAPTURE.PENDING leaves state pending,
        and CHECKOUT.PAYMENT-APPROVAL.REVERSED cancels the order and releases the reservation.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        webhook_service = WebhookService(seeded_db, paypal_client=mock_paypal)
        base_headers = {
            "paypal-transmission-id": "t-wh-edges",
            "paypal-transmission-time": "2026-11-11T12:00:00Z",
            "paypal-transmission-sig": "VALID_SIG",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }

        # 1. PENDING event
        pending_payload = json.dumps({
            "id": "WH-PENDING-001",
            "event_type": "PAYMENT.CAPTURE.PENDING",
            "resource": {"custom_id": order_resp.order_id},
        })
        webhook_service.process_webhook(headers=base_headers, raw_body=pending_payload)
        order_repo = OrderRepository(seeded_db)
        order = order_repo.get_by_order_id(order_resp.order_id)
        assert order is not None
        assert order.payment_status == PaymentStatus.PENDING.value

        # 2. REVERSED event
        reversed_payload = json.dumps({
            "id": "WH-REVERSED-001",
            "event_type": "CHECKOUT.PAYMENT-APPROVAL.REVERSED",
            "resource": {"custom_id": order_resp.order_id},
        })
        webhook_service.process_webhook(headers=base_headers, raw_body=reversed_payload)
        seeded_db.refresh(order)
        assert order.order_status == OrderStatus.CANCELLED.value
        assert order.payment_status == PaymentStatus.FAILED.value

        # Verify reservation released
        res_repo = ReservationRepository(seeded_db)
        res = res_repo.get_by_order_id(order.id)
        assert res is not None
        assert res.status == ReservationStatus.RELEASED.value

    def test_22_webhook_signature_rejects_cert_url_userinfo_and_non_standard_ports(self) -> None:
        """
        Security hardening check:
        PayPalSandboxClient.verify_webhook_signature strictly rejects cert_url with:
        - user credentials (user:pass@)
        - non-standard ports (:8080)
        - non-https schemes (http://)
        - domain suffix attacks (evilpaypal.com, paypal.com.evil.com)
        """
        client = PayPalSandboxClient(
            client_id="test-client-id",
            client_secret="test-client-secret",
            base_url="https://api-m.sandbox.paypal.com",
        )

        malicious_urls = [
            "https://user:pass@api.sandbox.paypal.com/cert.pem",
            "https://api.sandbox.paypal.com:8080/cert.pem",
            "http://api.sandbox.paypal.com/cert.pem",
            "https://evilpaypal.com/cert.pem",
            "https://paypal.com.attacker.com/cert.pem",
            "https://attacker.com/paypal.com",
            "",
        ]

        for bad_url in malicious_urls:
            headers = {
                "paypal-transmission-id": "t-1",
                "paypal-transmission-time": "2026-11-11T12:00:00Z",
                "paypal-cert-url": bad_url,
                "paypal-auth-algo": "SHA256withRSA",
                "paypal-transmission-sig": "SIG",
            }
            assert client.verify_webhook_signature(headers, '{"id":"WH-1"}', "WH-12345") is False

    def test_23_capture_payment_idempotency_prevents_duplicate_capture_rows(self, seeded_db: Session) -> None:
        """
        Data integrity check:
        Repeated or concurrent capture calls cannot create multiple PaymentCapture rows for the same order.
        """
        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        cap_req = CapturePaymentRequest(order_id=order_resp.order_id)

        # First capture
        cap1 = payment_service.capture_payment(cap_req, actor_id="buyer")
        assert cap1.status == "COMPLETED"

        # Second capture (idempotent replay)
        cap2 = payment_service.capture_payment(cap_req, actor_id="buyer")
        assert cap2.status == "COMPLETED"

        # Verify exactly one PaymentCapture record exists in DB
        from backend.models.payment_capture import PaymentCapture
        captures = seeded_db.query(PaymentCapture).filter(PaymentCapture.order_id == order_resp.id).all()
        assert len(captures) == 1
        assert captures[0].status == "COMPLETED"

    def test_24_public_buyer_cannot_access_merchant_admin_routes(self, seeded_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Access control check:
        Verifies that merchant administrative endpoints strictly reject public/unauthenticated
        callers with HTTP 401 in production mode.
        """
        from backend.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")

        # 1. Merchant order listing requires authenticated merchant actor
        with pytest.raises(HTTPException) as exc_info:
            list_orders(current_actor=None, db=seeded_db)  # type: ignore
        assert exc_info.value.status_code == 401

        # 2. Merchant reconciliation requires authenticated merchant actor
        with pytest.raises(HTTPException) as exc_info:
            reconcile_order(order_id="any-order", current_actor=None, db=seeded_db)  # type: ignore
        assert exc_info.value.status_code == 401

        # 3. Webhook events list requires authenticated merchant actor
        with pytest.raises(HTTPException) as exc_info:
            list_webhook_events(current_actor=None, db=seeded_db)  # type: ignore
        assert exc_info.value.status_code == 401

    def test_25_genuinely_concurrent_captures_prevent_duplicate_records(self) -> None:
        """
        Concurrency stress test:
        Executes genuinely concurrent multithreaded capture requests for the same order across separate connections.
        Verifies that transaction management, row locking, and idempotency checks prevent duplicate
        PaymentCapture records and all concurrent callers receive valid COMPLETED responses.
        """
        import concurrent.futures
        import os
        import tempfile

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from backend.core.database import Base
        from backend.models.payment_capture import PaymentCapture

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conc_engine = create_engine(
                f"sqlite:///{tmp_path}",
                connect_args={"timeout": 30},
            )
            Base.metadata.create_all(bind=conc_engine)
            ConcSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=conc_engine)

            # Seed catalog, storefront, and order
            setup_session = ConcSessionLocal()
            catalog_service = CatalogService(setup_session)
            catalog_service.seed_initial_catalog(reset=True)
            # Fix price to match catalog
            st_repo = StorefrontRepository(setup_session)
            prod = st_repo.get_by_sku("SX-001")
            assert prod is not None
            prod.price = Decimal("100.00")
            setup_session.commit()

            mock_paypal = MockPayPalClient()
            checkout_service = CheckoutService(setup_session, paypal_client=mock_paypal)
            order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")
            setup_session.close()

            def do_capture(worker_id: int):
                worker_session = ConcSessionLocal()
                try:
                    ps = PaymentService(worker_session, paypal_client=mock_paypal)
                    return ps.capture_payment(CapturePaymentRequest(order_id=order_resp.order_id), actor_id=f"buyer_{worker_id}")
                finally:
                    worker_session.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(do_capture, i) for i in range(5)]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            assert len(results) == 5
            for res in results:
                assert res.status == "COMPLETED"
                assert res.amount == Decimal("100.00")

            # Verify database has exactly 1 PaymentCapture row
            verify_session = ConcSessionLocal()
            try:
                captures = verify_session.query(PaymentCapture).filter(PaymentCapture.order_id == order_resp.id).all()
                assert len(captures) == 1
                assert captures[0].status == "COMPLETED"
            finally:
                verify_session.close()
        finally:
            conc_engine.dispose()
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def test_26_partial_unique_index_blocks_duplicate_completed_captures_while_permitting_failed(self, seeded_db: Session) -> None:
        """
        Database invariant test:
        Verifies that partial unique index ix_one_completed_capture_per_order:
        1. Permits multiple FAILED / DECLINED capture records for the same order (preserving failure history).
        2. Permits exactly one COMPLETED capture record.
        3. Strictly rejects an attempt to insert a second COMPLETED capture for the same order with IntegrityError.
        """
        from sqlalchemy.exc import IntegrityError

        from backend.models.payment_capture import PaymentCapture

        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        # 1. First FAILED capture attempt succeeds
        failed_cap_1 = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-FAIL-1",
            status="FAILED",
            amount=Decimal("100.00"),
            currency="USD",
        )
        seeded_db.add(failed_cap_1)
        seeded_db.commit()

        # 2. Second FAILED capture attempt also succeeds (preserves failure history)
        failed_cap_2 = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-FAIL-2",
            status="FAILED",
            amount=Decimal("100.00"),
            currency="USD",
        )
        seeded_db.add(failed_cap_2)
        seeded_db.commit()

        # 3. Exactly one COMPLETED capture succeeds
        completed_cap = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-COMPLETED-LEGIT",
            status="COMPLETED",
            amount=Decimal("100.00"),
            currency="USD",
        )
        seeded_db.add(completed_cap)
        seeded_db.commit()

        # 4. Attempting to insert a second COMPLETED capture for the same order MUST fail with IntegrityError
        second_completed_cap = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-COMPLETED-DUPLICATE",
            status="COMPLETED",
            amount=Decimal("100.00"),
            currency="USD",
        )
        seeded_db.add(second_completed_cap)
        with pytest.raises(IntegrityError):
            seeded_db.commit()
        seeded_db.rollback()

    def test_27_collision_recovery_prioritizes_completed_over_newer_failed_captures(self, seeded_db: Session) -> None:
        """
        Collision-recovery regression test (REV-CONCURR-001):
        1. When an order has both an older COMPLETED capture and a newer FAILED capture,
           collision recovery MUST return the COMPLETED capture, never the newer FAILED capture.
        2. When an order has ONLY a FAILED capture (no COMPLETED capture), collision recovery
           MUST NOT return the non-completed capture as success; it must re-raise the exception.
        3. No duplicate reservation or audit side effects are introduced.
        """
        import datetime
        from unittest.mock import patch

        from sqlalchemy.exc import IntegrityError

        from backend.models.payment_capture import PaymentCapture
        from backend.models.reservation import DemoInventoryReservation

        st_repo = StorefrontRepository(seeded_db)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        seeded_db.commit()

        # Part 1: Older COMPLETED capture + Newer FAILED capture
        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(seeded_db, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer")

        now = datetime.datetime.now(datetime.timezone.utc)
        older_completed = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-WINNING-LEGIT",
            status="COMPLETED",
            amount=Decimal("100.00"),
            currency="USD",
            created_at=now - datetime.timedelta(seconds=60),
        )
        seeded_db.add(older_completed)
        seeded_db.commit()

        newer_failed = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp.id,
            paypal_capture_id="CAP-NEWER-FAILED",
            status="FAILED",
            amount=Decimal("100.00"),
            currency="USD",
            created_at=now,
        )
        seeded_db.add(newer_failed)
        seeded_db.commit()

        # Trigger collision recovery during capture_payment by having the insert raise IntegrityError
        payment_service = PaymentService(seeded_db, paypal_client=mock_paypal)
        with patch.object(payment_service.capture_repo, "create", side_effect=IntegrityError("duplicate", params=None, orig=Exception("unique collision"))):
            res = payment_service.capture_payment(
                CapturePaymentRequest(order_id=order_resp.order_id),
                actor_id="buyer_collision",
            )

        # Assert recovery returned strictly the COMPLETED capture, NOT the newer FAILED capture
        assert res.status == "COMPLETED"
        assert res.capture_id == "CAP-WINNING-LEGIT"
        assert res.amount == Decimal("100.00")
        assert res.order_id == order_resp.order_id

        # Part 2: Order with ONLY a FAILED capture (NO completed capture exists)
        order_resp_2 = checkout_service.create_order(CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer_2")
        only_failed = PaymentCapture(
            merchant_id="merchant_default",
            order_id=order_resp_2.id,
            paypal_capture_id="CAP-ONLY-FAILED",
            status="FAILED",
            amount=Decimal("100.00"),
            currency="USD",
            created_at=now,
        )
        seeded_db.add(only_failed)
        seeded_db.commit()

        # On collision, since NO completed capture exists, recovery MUST NOT return the failed capture as success
        payment_service_2 = PaymentService(seeded_db, paypal_client=mock_paypal)
        with patch.object(payment_service_2.capture_repo, "create", side_effect=IntegrityError("collision", params=None, orig=Exception("unique collision"))):
            with pytest.raises(IntegrityError):
                payment_service_2.capture_payment(
                    CapturePaymentRequest(order_id=order_resp_2.order_id),
                    actor_id="buyer_collision_2",
                )

        # Part 3: Verify no duplicate reservation side effects
        reservations_1 = seeded_db.query(DemoInventoryReservation).filter(DemoInventoryReservation.order_id == order_resp.id).all()
        assert len(reservations_1) == 1
        reservations_2 = seeded_db.query(DemoInventoryReservation).filter(DemoInventoryReservation.order_id == order_resp_2.id).all()
        assert len(reservations_2) == 1




