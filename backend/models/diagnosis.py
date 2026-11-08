import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class Diagnosis(Base):
    """
    Advisory AI diagnosis record analyzing a completed storefront inspection scan.
    Maintains strict provenance: model, prompt version, supporting evidence IDs,
    and confidence explanation. Has zero execution authority.
    """

    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="merchant_default", index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("storefront_scans.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # COMPLETED, INSUFFICIENT_EVIDENCE, FAILED
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    likely_causes: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded List[str]
    supporting_evidence_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded List[int]
    missing_information: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded List[str]
    recommended_actions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded List[str]
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    raw_model_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_diagnoses_scan_created_at", "scan_id", "created_at"),
    )
