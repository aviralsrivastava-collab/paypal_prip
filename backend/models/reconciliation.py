import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class PaymentReconciliation(Base):
    """
    Durable log of payment reconciliation attempts, authoritative provider status checks,
    and state alignment outcomes.
    """

    __tablename__ = "payment_reconciliations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    paypal_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_payment_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_payment_status: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    actor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="MERCHANT")
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False, default="MERCHANT")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    reconciled_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
        index=True,
    )
