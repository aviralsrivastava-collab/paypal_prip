import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class EvidenceItem(Base):
    """
    Immutable structured evidence item produced during a storefront inspection.
    Provides complete provenance: scan reference, observed vs expected values, timestamps, and hashes.
    """

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("storefront_scans.id"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)  # PRICE, CURRENCY, IDENTITY, AVAILABILITY, EXTRACTION
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observed_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(255), nullable=False)
    observation_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # MATCH, MISMATCH, MISSING, BLOCKED
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_evidence_items_scan_type", "scan_id", "evidence_type"),
    )
