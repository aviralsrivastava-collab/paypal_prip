import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class PaymentCapture(Base):
    """
    Payment capture record representing server-side captured funds via PayPal Orders v2.
    Tracks authorization, settlement, provider capture IDs, net amounts, and reconciliation status.
    """

    __tablename__ = "payment_captures"
    __table_args__ = (
        Index(
            "ix_one_completed_capture_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'COMPLETED'"),
            sqlite_where=text("status = 'COMPLETED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=True)
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reconciliation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="NOT_NEEDED")
    reconciled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
