import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class CorrectionProposal(Base):
    """
    Structured correction proposal representing an advisory or merchant-initiated remediation.
    Maintains strict provenance, policy validation, approval status, and execution state.
    AI can only create/recommend proposals; humans must explicitly authorize them.
    """

    __tablename__ = "correction_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("storefront_scans.id", ondelete="CASCADE"), nullable=False, index=True)
    diagnosis_id: Mapped[Optional[int]] = mapped_column(ForeignKey("diagnoses.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    proposal_type: Mapped[str] = mapped_column(String(50), nullable=False, default="PRICE_SYNCHRONIZATION")
    current_value: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    proposed_value: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Lifecycle states
    policy_validation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="VALID")
    approval_status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING_APPROVAL")
    execution_status: Mapped[str] = mapped_column(String(50), nullable=False, default="NOT_STARTED")

    # Timestamps & Actors
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
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rejected_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic concurrency & idempotency
    expected_catalog_version: Mapped[int] = mapped_column(nullable=False, default=1)
    expected_storefront_version: Mapped[int] = mapped_column(nullable=False, default=1)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    execution_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_correction_proposals_sku_status", "sku", "approval_status"),
        Index("ix_correction_proposals_expires_at", "expires_at"),
    )
