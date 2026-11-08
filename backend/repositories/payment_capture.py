from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.payment_capture import PaymentCapture


class PaymentCaptureRepository:
    """
    Persistence layer for payment captures.
    Provides atomic storage, lookups by capture ID, and order linkage.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, capture: PaymentCapture) -> PaymentCapture:
        self.session.add(capture)
        self.session.flush()
        return capture

    def get_by_id(self, id: int, include_quarantined: bool = False) -> Optional[PaymentCapture]:
        capture = self.session.get(PaymentCapture, id)
        if capture and capture.merchant_id == "QUARANTINED_ORPHAN" and not include_quarantined:
            return None
        return capture

    def get_by_order_id(self, order_id: int, include_quarantined: bool = False) -> Optional[PaymentCapture]:
        stmt = select(PaymentCapture).where(PaymentCapture.order_id == order_id)
        if not include_quarantined:
            stmt = stmt.where(PaymentCapture.merchant_id != "QUARANTINED_ORPHAN")
        stmt = stmt.order_by(PaymentCapture.created_at.desc())
        return self.session.execute(stmt).scalars().first()

    def get_by_paypal_capture_id(self, paypal_capture_id: str, include_quarantined: bool = False) -> Optional[PaymentCapture]:
        stmt = select(PaymentCapture).where(PaymentCapture.paypal_capture_id == paypal_capture_id)
        if not include_quarantined:
            stmt = stmt.where(PaymentCapture.merchant_id != "QUARANTINED_ORPHAN")
        return self.session.execute(stmt).scalar_one_or_none()
