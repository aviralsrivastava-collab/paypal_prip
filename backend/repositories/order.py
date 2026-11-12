from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.order import Order


class OrderRepository:
    """
    Persistence layer for checkout orders.
    Enforces transactional persistence and queries by local order ID,
    PayPal order ID, and idempotency key.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, order: Order) -> Order:
        self.session.add(order)
        self.session.flush()
        return order

    def get_by_id(self, id: int) -> Optional[Order]:
        return self.session.get(Order, id)

    def get_by_order_id(self, order_id: str, merchant_id: Optional[str] = None) -> Optional[Order]:
        stmt = select(Order).where(Order.order_id == order_id)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_paypal_order_id(self, paypal_order_id: str, merchant_id: Optional[str] = None) -> Optional[Order]:
        stmt = select(Order).where(Order.paypal_order_id == paypal_order_id)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_idempotency_key(self, idempotency_key: str, merchant_id: Optional[str] = None) -> Optional[Order]:
        stmt = select(Order).where(Order.idempotency_key == idempotency_key)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_orders(self, limit: int = 50, merchant_id: Optional[str] = None) -> Sequence[Order]:
        stmt = select(Order)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        stmt = stmt.order_by(Order.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def get_all(self, merchant_id: Optional[str] = None) -> Sequence[Order]:
        stmt = select(Order)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        stmt = stmt.order_by(Order.id.asc())
        return self.session.execute(stmt).scalars().all()
