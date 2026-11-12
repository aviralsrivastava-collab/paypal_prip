from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional


class PayPalError(Exception):
    """Base exception for all PayPal integration errors."""

    pass


class PayPalApiError(PayPalError):
    """Raised when PayPal returns an HTTP error or error payload."""

    def __init__(
        self,
        status_code: int,
        error_name: str,
        error_message: str,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(f"PayPal API Error [{status_code}] {error_name}: {error_message}")
        self.status_code = status_code
        self.error_name = error_name
        self.error_message = error_message
        self.correlation_id = correlation_id


class PayPalTimeoutError(PayPalError):
    """Raised when a PayPal API request times out."""

    pass


class PayPalAuthError(PayPalError):
    """Raised when PayPal OAuth2 token acquisition fails."""

    pass


@dataclass
class PayPalOrderResponse:
    paypal_order_id: str
    status: str
    intent: str
    amount: Decimal
    currency: str
    approve_url: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PayPalCaptureResponse:
    paypal_capture_id: str
    paypal_order_id: str
    status: str
    amount: Decimal
    currency: str
    fee_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PayPalWebhookVerificationResult:
    verification_status: str  # "SUCCESS" or "FAILURE"
    raw_response: Dict[str, Any] = field(default_factory=dict)


class PayPalClientInterface(ABC):
    """
    Abstract interface for PayPal integration adapter.
    Encapsulates OAuth authentication, Orders v2 creation, capture, and webhook signature verification.
    All network I/O must remain outside database transactions.
    """

    @abstractmethod
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
        """Create a PayPal order (intent: CAPTURE). Supports PayPal-Request-Id header and payee routing."""
        pass

    @abstractmethod
    def get_order_details(self, paypal_order_id: str) -> PayPalOrderResponse:
        """Retrieve authoritative order status and details from PayPal."""
        pass

    @abstractmethod
    def capture_order(
        self,
        paypal_order_id: str,
        paypal_request_id: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        """Capture payment for an approved order. Supports PayPal-Request-Id header."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        raw_body: str,
        webhook_id: str,
    ) -> bool:
        """
        Verify the raw cryptographic webhook signature against official PayPal guidelines.
        Returns True if signature is cryptographically verified as authentic.
        """
        pass
