import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from backend.integrations.paypal.base import (
    PayPalApiError,
    PayPalCaptureResponse,
    PayPalClientInterface,
    PayPalOrderResponse,
    PayPalTimeoutError,
)


class MockPayPalClient(PayPalClientInterface):
    """
    Deterministic offline mock PayPal client for automated testing and local development.
    Simulates Orders v2 lifecycle, buyer approval, server-side capture,
    timeout handling, and webhook verification without contacting external PayPal servers.
    """

    _shared_orders: Dict[str, Dict[str, Any]] = {}
    _shared_orders_by_request_id: Dict[str, str] = {}
    received_request_ids: list[str] = []

    def __init__(
        self,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
        simulate_decline: bool = False,
        simulate_invalid_signature: bool = False,
        simulate_missing_fee_breakdown: bool = False,
    ) -> None:
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.simulate_decline = simulate_decline
        self.simulate_invalid_signature = simulate_invalid_signature
        self.simulate_missing_fee_breakdown = simulate_missing_fee_breakdown
        self._orders = self._shared_orders
        self._orders_by_req_id = self._shared_orders_by_request_id

    def create_order(
        self,
        sku: str,
        amount: Decimal,
        currency: str,
        reference_id: str,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        paypal_request_id: Optional[str] = None,
    ) -> PayPalOrderResponse:
        if paypal_request_id:
            self.received_request_ids.append(paypal_request_id)
            if paypal_request_id in self._orders_by_req_id:
                existing_id = self._orders_by_req_id[paypal_request_id]
                return self.get_order_details(existing_id)

        if self.simulate_error:
            raise PayPalApiError(500, "INTERNAL_SERVER_ERROR", "Simulated order creation error")

        paypal_order_id = f"MOCK-ORD-{uuid.uuid4().hex[:8].upper()}"
        approve_url = f"https://www.sandbox.paypal.com/checkoutnow?token={paypal_order_id}"

        order_record = {
            "paypal_order_id": paypal_order_id,
            "sku": sku,
            "amount": amount,
            "currency": currency,
            "reference_id": reference_id,
            "status": "CREATED",
            "approve_url": approve_url,
            "return_url": return_url,
            "cancel_url": cancel_url,
            "paypal_request_id": paypal_request_id,
        }
        self._orders[paypal_order_id] = order_record
        if paypal_request_id:
            self._orders_by_req_id[paypal_request_id] = paypal_order_id

        return PayPalOrderResponse(
            paypal_order_id=paypal_order_id,
            status="CREATED",
            intent="CAPTURE",
            amount=amount,
            currency=currency,
            approve_url=approve_url,
            raw_response=order_record,
        )

    def mock_buyer_approve(self, paypal_order_id: str) -> None:
        """Simulate buyer approving the order on PayPal Sandbox."""
        if paypal_order_id in self._orders:
            self._orders[paypal_order_id]["status"] = "APPROVED"

    def mock_set_order_status(self, paypal_order_id: str, status: str) -> None:
        """Simulate authoritative PayPal order status for reconciliation testing."""
        if paypal_order_id in self._orders:
            self._orders[paypal_order_id]["status"] = status
        else:
            self._orders[paypal_order_id] = {
                "id": paypal_order_id,
                "status": status,
                "amount": Decimal("100.00"),
                "currency": "USD",
            }

    def get_order_details(self, paypal_order_id: str) -> PayPalOrderResponse:
        order = self._orders.get(paypal_order_id)
        if not order:
            raise PayPalApiError(404, "ORDER_NOT_FOUND", f"Mock order {paypal_order_id} not found")

        return PayPalOrderResponse(
            paypal_order_id=paypal_order_id,
            status=order["status"],
            intent="CAPTURE",
            amount=order["amount"],
            currency=order["currency"],
            approve_url=order.get("approve_url"),
            raw_response=order,
        )

    def capture_order(
        self,
        paypal_order_id: str,
        paypal_request_id: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        if paypal_request_id:
            self.received_request_ids.append(paypal_request_id)

        if self.simulate_timeout:
            raise PayPalTimeoutError("Simulated PayPal capture network timeout")

        if self.simulate_error:
            raise PayPalApiError(500, "INTERNAL_SERVER_ERROR", "Simulated capture failure")

        order = self._orders.get(paypal_order_id)
        amount = order["amount"] if order else Decimal("100.00")
        currency = order["currency"] if order else "USD"

        if self.simulate_decline:
            capture_id = f"MOCK-CAP-DECLINED-{uuid.uuid4().hex[:6].upper()}"
            if order:
                order["status"] = "DECLINED"
            return PayPalCaptureResponse(
                paypal_capture_id=capture_id,
                paypal_order_id=paypal_order_id,
                status="DECLINED",
                amount=amount,
                currency=currency,
                fee_amount=Decimal("0.00"),
                net_amount=Decimal("0.00"),
                raw_response={"status": "DECLINED", "reason": "INSTRUMENT_DECLINED"},
            )

        capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:8].upper()}"
        if self.simulate_missing_fee_breakdown:
            fee_amount = None
            net_amount = None
            receivable_breakdown = {}
        else:
            fee_amount = Decimal("3.49")
            net_amount = amount - fee_amount
            receivable_breakdown = {
                "gross_amount": {"value": str(amount), "currency_code": currency},
                "paypal_fee": {"value": str(fee_amount), "currency_code": currency},
                "net_amount": {"value": str(net_amount), "currency_code": currency},
            }

        if order:
            order["status"] = "COMPLETED"

        raw_payload = {
            "id": capture_id,
            "status": "COMPLETED",
            "amount": {"value": str(amount), "currency_code": currency},
            "seller_receivable_breakdown": receivable_breakdown,
        }

        return PayPalCaptureResponse(
            paypal_capture_id=capture_id,
            paypal_order_id=paypal_order_id,
            status="COMPLETED",
            amount=amount,
            currency=currency,
            fee_amount=fee_amount,
            net_amount=net_amount,
            raw_response=raw_payload,
        )

    def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        raw_body: str,
        webhook_id: str,
    ) -> bool:
        if self.simulate_invalid_signature:
            return False

        # Normalize headers to lowercase
        norm_headers = {k.lower(): v for k, v in headers.items()}

        required_headers = [
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-transmission-sig",
            "paypal-cert-url",
            "paypal-auth-algo",
        ]

        for h in required_headers:
            if not norm_headers.get(h):
                return False

        sig = norm_headers.get("paypal-transmission-sig", "")
        if sig in ("INVALID", "FORGED", "CORRUPTED"):
            return False

        if not webhook_id:
            return False

        return True
