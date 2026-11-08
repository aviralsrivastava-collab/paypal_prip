import datetime
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx

from backend.integrations.paypal.base import (
    PayPalApiError,
    PayPalAuthError,
    PayPalCaptureResponse,
    PayPalClientInterface,
    PayPalError,
    PayPalOrderResponse,
    PayPalTimeoutError,
)

logger = logging.getLogger(__name__)


class PayPalSandboxClient(PayPalClientInterface):
    """
    Live PayPal Sandbox HTTP adapter using Orders v2 and official webhook signature verification.
    Strictly isolated to Sandbox endpoints only.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://api-m.sandbox.paypal.com",
        timeout_seconds: float = 15.0,
    ) -> None:
        if "sandbox" not in base_url.lower():
            raise PayPalError(
                f"Security violation: Base URL '{base_url}' is not a PayPal Sandbox domain. "
                "Phase 6 strictly forbids non-sandbox PayPal endpoints."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime.datetime] = None

    def _get_access_token(self) -> str:
        """Acquires or refreshes OAuth2 token via client_credentials grant."""
        now = datetime.datetime.now(datetime.timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise PayPalAuthError("PayPal client ID and client secret must be configured for Sandbox.")

        token_url = f"{self.base_url}/v1/oauth2/token"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(
                    token_url,
                    data={"grant_type": "client_credentials"},
                    auth=(self.client_id, self.client_secret),
                    headers={"Accept": "application/json", "Accept-Language": "en_US"},
                )
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"OAuth token request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise PayPalAuthError(f"OAuth token network error: {exc}") from exc

        if resp.status_code != 200:
            raise PayPalAuthError(
                f"Failed to obtain OAuth token from PayPal: [{resp.status_code}] {resp.text}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        # Add safety buffer of 60 seconds
        self._token_expires_at = now + datetime.timedelta(seconds=max(expires_in - 60, 60))
        return self._access_token

    def _headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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
        url = f"{self.base_url}/v2/checkout/orders"
        payload: Dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "custom_id": sku,
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                }
            ],
        }
        if return_url and cancel_url:
            payload["application_context"] = {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "user_action": "PAY_NOW",
            }

        headers = self._headers()
        if paypal_request_id:
            headers["PayPal-Request-Id"] = paypal_request_id

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"Order creation timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise PayPalApiError(500, "REQUEST_ERROR", str(exc)) from exc

        if resp.status_code not in (200, 201):
            raise PayPalApiError(
                resp.status_code,
                "CREATE_ORDER_FAILED",
                resp.text,
                resp.headers.get("paypal-debug-id"),
            )

        data = resp.json()
        paypal_order_id = data["id"]
        status = data.get("status", "CREATED")

        approve_url = None
        for link in data.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                break

        return PayPalOrderResponse(
            paypal_order_id=paypal_order_id,
            status=status,
            intent="CAPTURE",
            amount=amount,
            currency=currency,
            approve_url=approve_url,
            raw_response=data,
        )

    def get_order_details(self, paypal_order_id: str) -> PayPalOrderResponse:
        url = f"{self.base_url}/v2/checkout/orders/{paypal_order_id}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"Get order details timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise PayPalApiError(500, "REQUEST_ERROR", str(exc)) from exc

        if resp.status_code != 200:
            raise PayPalApiError(
                resp.status_code,
                "GET_ORDER_FAILED",
                resp.text,
                resp.headers.get("paypal-debug-id"),
            )

        data = resp.json()
        pu = data.get("purchase_units", [{}])[0]
        amt_obj = pu.get("amount", {})
        amount = Decimal(amt_obj.get("value", "0.00"))
        currency = amt_obj.get("currency_code", "USD")

        approve_url = None
        for link in data.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                break

        return PayPalOrderResponse(
            paypal_order_id=data["id"],
            status=data.get("status", "CREATED"),
            intent=data.get("intent", "CAPTURE"),
            amount=amount,
            currency=currency,
            approve_url=approve_url,
            raw_response=data,
        )

    def capture_order(
        self,
        paypal_order_id: str,
        paypal_request_id: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        url = f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture"
        headers = self._headers()
        if paypal_request_id:
            headers["PayPal-Request-Id"] = paypal_request_id

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json={}, headers=headers)
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"Order capture timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise PayPalApiError(500, "REQUEST_ERROR", str(exc)) from exc

        if resp.status_code not in (200, 201):
            raise PayPalApiError(
                resp.status_code,
                "CAPTURE_FAILED",
                resp.text,
                resp.headers.get("paypal-debug-id"),
            )

        data = resp.json()
        status = data.get("status", "COMPLETED")
        pu = data.get("purchase_units", [{}])[0]
        payments = pu.get("payments", {})
        captures = payments.get("captures", [{}])
        first_capture = captures[0] if captures else {}

        capture_id = first_capture.get("id", f"CAP-{paypal_order_id}")
        capture_status = first_capture.get("status", status)

        amt_obj = first_capture.get("amount", {})
        amount = Decimal(amt_obj.get("value", "0.00"))
        currency = amt_obj.get("currency_code", "USD")

        breakdown = first_capture.get("seller_receivable_breakdown", {})
        fee_obj = breakdown.get("paypal_fee", {})
        fee_amount = Decimal(fee_obj.get("value")) if fee_obj.get("value") else None
        net_obj = breakdown.get("net_amount", {})
        net_amount = Decimal(net_obj.get("value")) if net_obj.get("value") else None

        return PayPalCaptureResponse(
            paypal_capture_id=capture_id,
            paypal_order_id=paypal_order_id,
            status=capture_status,
            amount=amount,
            currency=currency,
            fee_amount=fee_amount,
            net_amount=net_amount,
            raw_response=data,
        )

    def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        raw_body: str,
        webhook_id: str,
    ) -> bool:
        """
        Calls official PayPal verify-webhook-signature REST endpoint.
        Preserves raw body JSON and passes exact transmission headers.
        """
        norm_headers = {k.lower(): v for k, v in headers.items()}
        try:
            webhook_event = json.loads(raw_body)
        except Exception:
            logger.warning("Failed to parse raw webhook body for signature verification")
            return False

        verification_payload = {
            "transmission_id": norm_headers.get("paypal-transmission-id"),
            "transmission_time": norm_headers.get("paypal-transmission-time"),
            "cert_url": norm_headers.get("paypal-cert-url"),
            "auth_algo": norm_headers.get("paypal-auth-algo"),
            "transmission_sig": norm_headers.get("paypal-transmission-sig"),
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }

        url = f"{self.base_url}/v1/notifications/verify-webhook-signature"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json=verification_payload, headers=self._headers())
        except Exception as exc:
            logger.error(f"Error calling PayPal webhook verification endpoint: {exc}")
            return False

        if resp.status_code != 200:
            logger.warning(f"PayPal webhook verification returned [{resp.status_code}]: {resp.text}")
            return False

        result = resp.json()
        return bool(result.get("verification_status") == "SUCCESS")
