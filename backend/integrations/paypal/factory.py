from typing import Optional

from backend.core.config import get_settings
from backend.integrations.paypal.base import PayPalClientInterface, PayPalError
from backend.integrations.paypal.client import PayPalSandboxClient
from backend.integrations.paypal.mock_client import MockPayPalClient


def get_paypal_client(client_override: Optional[str] = None) -> PayPalClientInterface:
    """
    Factory creating a PayPalClientInterface implementation.
    Enforces that only Sandbox is allowed, and defaults to deterministic MockPayPalClient
    during development and testing.
    """
    settings = get_settings()
    client_type = (client_override or settings.paypal_client_type or "mock").lower()

    if client_type == "mock":
        return MockPayPalClient()

    if client_type == "sandbox":
        if "sandbox" not in settings.paypal_base_url.lower():
            raise PayPalError(
                f"Configuration safety violation: {settings.paypal_base_url} is not a valid Sandbox endpoint."
            )
        return PayPalSandboxClient(
            client_id=settings.paypal_client_id,
            client_secret=settings.paypal_client_secret,
            base_url=settings.paypal_base_url,
        )

    # Fallback to mock client
    return MockPayPalClient()
