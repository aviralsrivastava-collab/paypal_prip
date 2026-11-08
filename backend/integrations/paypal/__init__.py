"""
PRIP Backend PayPal Integration Module
======================================
Provides provider-agnostic abstractions and concrete Sandbox / Mock adapters for PayPal.
"""

from backend.integrations.paypal.base import (
    PayPalApiError,
    PayPalAuthError,
    PayPalCaptureResponse,
    PayPalClientInterface,
    PayPalError,
    PayPalOrderResponse,
    PayPalTimeoutError,
    PayPalWebhookVerificationResult,
)
from backend.integrations.paypal.client import PayPalSandboxClient
from backend.integrations.paypal.factory import get_paypal_client
from backend.integrations.paypal.mock_client import MockPayPalClient

__all__ = [
    "PayPalError",
    "PayPalApiError",
    "PayPalTimeoutError",
    "PayPalAuthError",
    "PayPalOrderResponse",
    "PayPalCaptureResponse",
    "PayPalWebhookVerificationResult",
    "PayPalClientInterface",
    "PayPalSandboxClient",
    "MockPayPalClient",
    "get_paypal_client",
]
