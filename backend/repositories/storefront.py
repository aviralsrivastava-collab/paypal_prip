import datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.storefront import StorefrontProduct


class StorefrontRepository:
    """
    Repository for controlled demo storefront products.
    Encapsulates all database operations for storefront records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_sku(self, sku: str) -> Optional[StorefrontProduct]:
        statement = select(StorefrontProduct).where(StorefrontProduct.sku == sku)
        return self.session.execute(statement).scalar_one_or_none()

    def get_all(self) -> Sequence[StorefrontProduct]:
        statement = select(StorefrontProduct).order_by(StorefrontProduct.id.asc())
        return self.session.execute(statement).scalars().all()

    def create(self, product: StorefrontProduct) -> StorefrontProduct:
        self.session.add(product)
        self.session.flush()
        return product

    def update_price(
        self,
        sku: str,
        new_price: Decimal,
        currency: str,
        expected_version: int,
    ) -> StorefrontProduct:
        """
        Updates storefront price enforcing optimistic concurrency versioning.
        Raises ValueError if product not found or version mismatch occurs.
        """
        product = self.get_by_sku(sku)
        if not product:
            raise ValueError(f"Storefront product with SKU '{sku}' not found.")

        if product.version != expected_version:
            raise ValueError(
                f"Concurrency conflict: expected version {expected_version}, current version is {product.version}."
            )

        product.price = new_price
        product.currency = currency
        product.version += 1
        product.updated_at = datetime.datetime.now(datetime.timezone.utc)
        self.session.add(product)
        self.session.flush()
        return product
