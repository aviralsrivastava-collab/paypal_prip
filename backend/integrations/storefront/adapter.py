from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.storefront import StorefrontProduct
from backend.repositories.storefront import StorefrontRepository


class ControlledStorefrontAdapter:
    """
    Adapter for communicating with and modifying the controlled demo storefront.
    Ensures storefront mutations are isolated from merchant catalog data.
    """

    def __init__(self, session: Session) -> None:
        self.repository = StorefrontRepository(session)

    def get_product(self, sku: str) -> Optional[StorefrontProduct]:
        """Fetch current storefront product data."""
        return self.repository.get_by_sku(sku)

    def update_product_price(
        self,
        sku: str,
        new_price: Decimal,
        currency: str,
        expected_version: int,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
    ) -> StorefrontProduct:
        """
        Updates the storefront price.
        Guarantees that only the storefront model is mutated.
        Supports simulated failure injection for test verification.
        """
        if simulate_timeout:
            raise TimeoutError(f"Simulated external network timeout updating price for SKU {sku}")
        if simulate_error:
            raise RuntimeError(f"Simulated external storefront gateway failure for SKU {sku}")

        return self.repository.update_price(
            sku=sku,
            new_price=new_price,
            currency=currency,
            expected_version=expected_version,
        )
