import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class Order(Base):
    """
    Order entity representing a checkout intent / order in PRIP.
    Maintains payment lifecycle states, preflight discrepancy gate results,
    and linkage to PayPal Orders v2 identifiers.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    order_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    paypal_order_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)

    order_status: Mapped[str] = mapped_column(String(50), nullable=False, default="CREATED")
    payment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")

    preflight_scan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("storefront_scans.id", ondelete="SET NULL"), nullable=True)
    preflight_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

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
