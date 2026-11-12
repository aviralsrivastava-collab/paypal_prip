from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from backend.integrations.paypal.base import PayPalCaptureResponse
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.merchant import Merchant, MerchantStatus
from backend.models.order import Order
from backend.models.product import Product
from backend.models.reservation import DemoInventoryReservation
from backend.models.storefront import StorefrontProduct
from backend.policies.checkout_policy import OrderStatus, PaymentStatus, ReservationStatus
from backend.schemas.checkout import CreateOrderRequest
from backend.schemas.payment import CapturePaymentRequest
from backend.services.checkout import CheckoutService
from backend.services.payment import PaymentService


class TrackingMockPayPalClient(MockPayPalClient):
    def __init__(self):
        super().__init__()
        self.created_orders = []
        self.mock_capture_amount = None
        self.mock_capture_currency = None

    def create_order(self, sku, amount, currency, reference_id, return_url=None, cancel_url=None, paypal_request_id=None, payee_merchant_id=None):
        self.created_orders.append({
            "sku": sku,
            "amount": amount,
            "currency": currency,
            "payee_merchant_id": payee_merchant_id,
        })
        return super().create_order(sku, amount, currency, reference_id, return_url, cancel_url, paypal_request_id, payee_merchant_id)

    def capture_order(self, paypal_order_id, paypal_request_id=None):
        if self.mock_capture_amount is not None:
            return PayPalCaptureResponse(
                paypal_capture_id=f"CAP-{paypal_order_id}",
                paypal_order_id=paypal_order_id,
                status="COMPLETED",
                amount=self.mock_capture_amount,
                currency=self.mock_capture_currency or "USD",
                fee_amount=Decimal("1.50"),
                net_amount=self.mock_capture_amount - Decimal("1.50"),
            )
        return super().capture_order(paypal_order_id, paypal_request_id)


@pytest.fixture
def routing_fixtures(db_session: Session):
    m = Merchant(
        id="merch_connected",
        slug="connected-seller",
        name="Connected Seller LLC",
        status=MerchantStatus.ACTIVE.value,
        paypal_merchant_id="PAYPAL_BIZ_ACC_12345",
    )
    p = Product(
        merchant_id="merch_connected",
        sku="SX-ROUTED-1",
        title="Routed Product",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    sf = StorefrontProduct(
        merchant_id="merch_connected",
        sku="SX-ROUTED-1",
        title="Routed Product",
        price=Decimal("100.00"),
        currency="USD",
        availability="IN_STOCK",
        url_path="/products/routed",
        version=1,
    )
    db_session.add_all([m, p, sf])
    db_session.commit()
    return m, p, sf


def test_order_creation_routes_payee_merchant_id(db_session: Session, routing_fixtures, monkeypatch):
    from backend.core.config import get_settings
    settings = get_settings()

    # 1. Default mode: custom routing disabled -> platform-controlled seller flow
    monkeypatch.setattr(settings, "paypal_enable_payee_routing", False)
    mock_client = TrackingMockPayPalClient()
    checkout_svc = CheckoutService(db_session, paypal_client=mock_client)
    res = checkout_svc.create_order(CreateOrderRequest(sku="SX-ROUTED-1", quantity=1), merchant_id="merch_connected")
    assert res.order_id is not None
    assert mock_client.created_orders[-1]["payee_merchant_id"] is None

    # 2. Partner-enabled mode: custom routing enabled -> routes to merchant's PayPal account
    monkeypatch.setattr(settings, "paypal_enable_payee_routing", True)
    res2 = checkout_svc.create_order(CreateOrderRequest(sku="SX-ROUTED-1", quantity=1), merchant_id="merch_connected")
    assert res2.order_id is not None
    assert mock_client.created_orders[-1]["payee_merchant_id"] == "PAYPAL_BIZ_ACC_12345"
    assert mock_client.created_orders[-1]["amount"] == Decimal("100.00")


def test_capture_invariant_violation_amount_mismatch_fails_closed(db_session: Session, routing_fixtures):
    mock_client = TrackingMockPayPalClient()
    # Simulate a rogue or mismatched capture response with different amount ($80 instead of $100)
    mock_client.mock_capture_amount = Decimal("80.00")
    mock_client.mock_capture_currency = "USD"

    checkout_svc = CheckoutService(db_session, paypal_client=mock_client)
    res = checkout_svc.create_order(CreateOrderRequest(sku="SX-ROUTED-1", quantity=1), merchant_id="merch_connected")

    payment_svc = PaymentService(db_session, paypal_client=mock_client)
    cap_res = payment_svc.capture_payment(CapturePaymentRequest(order_id=res.order_id))

    # Payment capture must fail closed
    assert cap_res.status != "COMPLETED"

    # Order must NOT be marked CAPTURED
    order = db_session.query(Order).filter(Order.order_id == res.order_id).one()
    assert order.payment_status != PaymentStatus.CAPTURED.value

    # Inventory reservation must NOT be COMMITTED
    resv = db_session.query(DemoInventoryReservation).filter(DemoInventoryReservation.order_id == order.id).one()
    assert resv.status != ReservationStatus.COMMITTED.value


def test_capture_invariant_success_commits_inventory(db_session: Session, routing_fixtures):
    mock_client = TrackingMockPayPalClient()
    mock_client.mock_capture_amount = Decimal("100.00")
    mock_client.mock_capture_currency = "USD"

    checkout_svc = CheckoutService(db_session, paypal_client=mock_client)
    res = checkout_svc.create_order(CreateOrderRequest(sku="SX-ROUTED-1", quantity=1), merchant_id="merch_connected")

    payment_svc = PaymentService(db_session, paypal_client=mock_client)
    cap_res = payment_svc.capture_payment(CapturePaymentRequest(order_id=res.order_id))

    assert cap_res.status == "COMPLETED"

    order = db_session.query(Order).filter(Order.order_id == res.order_id).one()
    assert order.payment_status == PaymentStatus.CAPTURED.value
    assert order.order_status == OrderStatus.COMPLETED.value

    resv = db_session.query(DemoInventoryReservation).filter(DemoInventoryReservation.order_id == order.id).one()
    assert resv.status == ReservationStatus.COMMITTED.value
