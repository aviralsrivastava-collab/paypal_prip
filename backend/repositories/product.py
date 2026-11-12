from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.product import Product


class ProductRepository:
    """
    Repository for merchant-authorized catalog products.
    Encapsulates all database operations for catalog records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return self.session.get(Product, product_id)

    def get_by_sku(self, sku: str, merchant_id: Optional[str] = None) -> Optional[Product]:
        statement = select(Product).where(Product.sku == sku)
        if merchant_id is not None:
            statement = statement.where(Product.merchant_id == merchant_id)
        return self.session.execute(statement).scalar_one_or_none()

    def get_all(self, merchant_id: Optional[str] = None) -> Sequence[Product]:
        statement = select(Product)
        if merchant_id is not None:
            statement = statement.where(Product.merchant_id == merchant_id)
        statement = statement.order_by(Product.id.asc())
        return self.session.execute(statement).scalars().all()

    def create(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        return product

    def update(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        return product

    def delete(self, product: Product) -> None:
        self.session.delete(product)
        self.session.flush()
