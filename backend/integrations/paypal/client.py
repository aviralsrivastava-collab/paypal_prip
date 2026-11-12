import datetime
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import urlparse

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
            return str(self._access_token)

        if not self.client_id or not self.client_secret:
            raise PayPalAuthError("PayPal client ID and client secret must be configured for Sandbox.")

        token_url = f"{self.base_url}/v1/oauth2/token"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
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

        data: Dict[str, Any] = resp.json()
        token: str = str(data["access_token"])
        self._access_token = token
        expires_in = int(data.get("expires_in", 3600))
        # Add safety buffer of 60 seconds
        self._token_expires_at = now + datetime.timedelta(seconds=max(expires_in - 60, 60))
        return token

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
        payee_merchant_id: Optional[str] = None,
    ) -> PayPalOrderResponse:
        url = f"{self.base_url}/v2/checkout/orders"
        # Enforce PayPal AI Hackathon currency specification (canonical USD default)
        valid_paypal_currencies = {"USD", "EUR", "GBP", "CAD", "AUD"}
        canonical_currency = (currency or "USD").upper().strip()
        if canonical_currency not in valid_paypal_currencies:
            canonical_currency = "USD"

        purchase_unit: Dict[str, Any] = {
            "reference_id": reference_id,
            "custom_id": sku,
            "amount": {
                "currency_code": canonical_currency,
                "value": f"{amount:.2f}",
            },
        }
        if payee_merchant_id:
            purchase_unit["payee"] = {"merchant_id": payee_merchant_id}

        payload: Dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [purchase_unit],
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
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
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

        data: Dict[str, Any] = resp.json()
        paypal_order_id: str = str(data["id"])
        status: str = str(data.get("status", "CREATED"))

        approve_url: Optional[str] = None
        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            for link in raw_links:
                if isinstance(link, dict) and link.get("rel") == "approve":
                    approve_url = str(link.get("href"))
                    break

        return PayPalOrderResponse(
            paypal_order_id=paypal_order_id,
            status=status,
            intent="CAPTURE",
            amount=amount,
            currency=canonical_currency,
            approve_url=approve_url,
            raw_response=dict(data),
        )

    def get_order_details(self, paypal_order_id: str) -> PayPalOrderResponse:
        url = f"{self.base_url}/v2/checkout/orders/{paypal_order_id}"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
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

        data: Dict[str, Any] = resp.json()
        pu_list = data.get("purchase_units", [{}])
        pu: Dict[str, Any] = pu_list[0] if isinstance(pu_list, list) and pu_list else {}
        amt_obj: Dict[str, Any] = pu.get("amount", {}) if isinstance(pu.get("amount"), dict) else {}
        amount = Decimal(str(amt_obj.get("value", "0.00")))
        currency: str = str(amt_obj.get("currency_code", "USD"))

        approve_url: Optional[str] = None
        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            for link in raw_links:
                if isinstance(link, dict) and link.get("rel") == "approve":
                    approve_url = str(link.get("href"))
                    break

        return PayPalOrderResponse(
            paypal_order_id=str(data["id"]),
            status=str(data.get("status", "CREATED")),
            intent=str(data.get("intent", "CAPTURE")),
            amount=amount,
            currency=currency,
            approve_url=approve_url,
            raw_response=dict(data),
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
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
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

        data: Dict[str, Any] = resp.json()
        status: str = str(data.get("status", "COMPLETED"))
        pu_list = data.get("purchase_units", [{}])
        pu: Dict[str, Any] = pu_list[0] if isinstance(pu_list, list) and pu_list else {}
        payments: Dict[str, Any] = pu.get("payments", {}) if isinstance(pu.get("payments"), dict) else {}
        captures_list = payments.get("captures", [{}])
        first_capture: Dict[str, Any] = captures_list[0] if isinstance(captures_list, list) and captures_list else {}

        capture_id: str = str(first_capture.get("id", f"CAP-{paypal_order_id}"))
        capture_status: str = str(first_capture.get("status", status))

        amt_obj: Dict[str, Any] = first_capture.get("amount", {}) if isinstance(first_capture.get("amount"), dict) else {}
        amount = Decimal(str(amt_obj.get("value", "0.00")))
        currency: str = str(amt_obj.get("currency_code", "USD"))

        breakdown: Dict[str, Any] = first_capture.get("seller_receivable_breakdown", {}) if isinstance(first_capture.get("seller_receivable_breakdown"), dict) else {}
        fee_obj: Dict[str, Any] = breakdown.get("paypal_fee", {}) if isinstance(breakdown.get("paypal_fee"), dict) else {}
        fee_amount = Decimal(str(fee_obj.get("value"))) if fee_obj.get("value") else None
        net_obj: Dict[str, Any] = breakdown.get("net_amount", {}) if isinstance(breakdown.get("net_amount"), dict) else {}
        net_amount = Decimal(str(net_obj.get("value"))) if net_obj.get("value") else None

        return PayPalCaptureResponse(
            paypal_capture_id=capture_id,
            paypal_order_id=paypal_order_id,
            status=capture_status,
            amount=amount,
            currency=currency,
            fee_amount=fee_amount,
            net_amount=net_amount,
            raw_response=dict(data),
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
        Validates presence of all 5 signature headers, cert_url host authority, and webhook_id.
        """
        norm_headers = {k.lower(): (v or "").strip() for k, v in headers.items()}

        required_headers = (
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
            "paypal-transmission-sig",
        )
        if not all(norm_headers.get(h) for h in required_headers):
            logger.warning("Missing required PayPal signature headers in incoming webhook transmission")
            return False

        if not webhook_id or not webhook_id.strip():
            logger.warning("Configured PayPal webhook ID is empty; cannot verify signature")
            return False

        # Cert URL security: must be HTTPS, no userinfo, standard port 443, and belong to legitimate PayPal domain
        cert_url = norm_headers.get("paypal-cert-url", "")
        try:
            parsed_cert = urlparse(cert_url)
            cert_host = (parsed_cert.hostname or "").lower()
            if (
                parsed_cert.scheme != "https"
                or parsed_cert.username is not None
                or parsed_cert.password is not None
                or (parsed_cert.port is not None and parsed_cert.port != 443)
                or not cert_host
                or not (cert_host == "paypal.com" or cert_host.endswith(".paypal.com"))
            ):
                logger.warning(f"Rejected untrusted paypal-cert-url: {cert_url}")
                return False
        except Exception as exc:
            logger.warning(f"Failed to parse paypal-cert-url '{cert_url}': {exc}")
            return False

        try:
            webhook_event = json.loads(raw_body)
        except Exception:
            logger.warning("Failed to parse raw webhook body for signature verification")
            return False

        verification_payload = {
            "transmission_id": norm_headers.get("paypal-transmission-id"),
            "transmission_time": norm_headers.get("paypal-transmission-time"),
            "cert_url": cert_url,
            "auth_algo": norm_headers.get("paypal-auth-algo"),
            "transmission_sig": norm_headers.get("paypal-transmission-sig"),
            "webhook_id": webhook_id.strip(),
            "webhook_event": webhook_event,
        }

        url = f"{self.base_url}/v1/notifications/verify-webhook-signature"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                resp = client.post(url, json=verification_payload, headers=self._headers())
        except Exception as exc:
            logger.error(f"Error calling PayPal webhook verification endpoint: {exc}")
            return False

        if resp.status_code != 200:
            logger.warning(f"PayPal webhook verification returned [{resp.status_code}]: {resp.text}")
            return False

        result: Dict[str, Any] = resp.json()
        status_val: Any = result.get("verification_status")
        return bool(status_val == "SUCCESS")
