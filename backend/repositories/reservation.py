import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.reservation import DemoInventoryReservation


class ReservationRepository:
    """
    Persistence layer for controlled demo inventory reservations.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, reservation: DemoInventoryReservation) -> DemoInventoryReservation:
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def get_by_order_id(self, order_id: int, include_quarantined: bool = False) -> Optional[DemoInventoryReservation]:
        stmt = select(DemoInventoryReservation).where(DemoInventoryReservation.order_id == order_id)
        if not include_quarantined:
            stmt = stmt.where(DemoInventoryReservation.merchant_id != "QUARANTINED_ORPHAN")
        stmt = stmt.order_by(DemoInventoryReservation.created_at.desc())
        return self.session.execute(stmt).scalars().first()

    def get_reserved_quantity(self, sku: str) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = (
            select(func.sum(DemoInventoryReservation.quantity))
            .where(DemoInventoryReservation.sku == sku)
            .where(DemoInventoryReservation.status == "RESERVED")
            .where(DemoInventoryReservation.merchant_id != "QUARANTINED_ORPHAN")
            .where(DemoInventoryReservation.expires_at > now)
        )
        result = self.session.execute(stmt).scalar()
        return int(result or 0)
