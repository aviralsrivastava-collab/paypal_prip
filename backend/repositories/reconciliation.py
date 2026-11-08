from typing import Dict, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.order import Order
from backend.models.reconciliation import PaymentReconciliation
from backend.policies.checkout_policy import PaymentStatus


class PaymentReconciliationRepository:
    """
    Persistence layer for payment reconciliation runs and history.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, reconciliation: PaymentReconciliation) -> PaymentReconciliation:
        self.session.add(reconciliation)
        self.session.flush()
        return reconciliation

    def list_history(self, limit: int = 50, merchant_id: Optional[str] = None) -> Sequence[PaymentReconciliation]:
        stmt = select(PaymentReconciliation)
        if merchant_id is not None:
            stmt = stmt.where(PaymentReconciliation.merchant_id == merchant_id)
        stmt = stmt.order_by(PaymentReconciliation.reconciled_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def list_orders_requiring_reconciliation(self, limit: int = 50, merchant_id: Optional[str] = None) -> Sequence[Order]:
        """
        Returns orders with ambiguous capture outcome (UNKNOWN) requiring authoritative reconciliation.
        """
        stmt = select(Order).where(Order.payment_status == PaymentStatus.UNKNOWN.value)
        if merchant_id is not None:
            stmt = stmt.where(Order.merchant_id == merchant_id)
        stmt = stmt.order_by(Order.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def get_counts(self, merchant_id: Optional[str] = None) -> Dict[str, int]:
        stmt = select(PaymentReconciliation.outcome, func.count(PaymentReconciliation.id))
        if merchant_id is not None:
            stmt = stmt.where(PaymentReconciliation.merchant_id == merchant_id)
        stmt = stmt.group_by(PaymentReconciliation.outcome)
        rows = self.session.execute(stmt).all()
        return {outcome: count for outcome, count in rows}
