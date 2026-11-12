import datetime
import uuid
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class MerchantRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    VIEWER = "VIEWER"


class MerchantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ONBOARDING = "ONBOARDING"


class Merchant(Base):
    """
    Merchant organization representing an isolated tenant workspace.
    Owns products, storefront configs, scans, proposals, orders, and captures.
    """

    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=MerchantStatus.ACTIVE.value)
    paypal_merchant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

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

    memberships: Mapped[list["MerchantMembership"]] = relationship(
        "MerchantMembership",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )


class MerchantMembership(Base):
    """
    Membership linking a User to a Merchant with specific RBAC role.
    A user can belong to multiple merchants with different roles.
    """

    __tablename__ = "merchant_memberships"
    __table_args__ = (
        UniqueConstraint("merchant_id", "user_id", name="uq_membership_merchant_user"),
        Index("ix_membership_user_id", "user_id"),
        Index("ix_membership_merchant_id", "merchant_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    merchant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=MerchantRole.VIEWER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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

    merchant: Mapped["Merchant"] = relationship("Merchant", back_populates="memberships")
