import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class StorefrontScan(Base):
    """
    Storefront scan entity recording one inspection attempt.
    Produces honest four-state classifications based on comparability and extraction evidence.
    """

    __tablename__ = "storefront_scans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_version: Mapped[int] = mapped_column(nullable=False, default=1)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)  # ISSUE_DETECTED, VERIFIED_NO_ISSUE, BLOCKED_UNKNOWN, NOT_TESTED
    is_comparable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    catalog_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=True)
    observed_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    discrepancy_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_storefront_scans_sku_created_at", "sku", "created_at"),
    )
