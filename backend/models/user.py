import datetime
import uuid
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class User(Base):
    """
    User entity representing an authenticated human operator or system identity.
    Identified externally by immutable (iss, sub) tuple; email is a mutable profile attribute.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("iss", "sub", name="uq_user_iss_sub"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    iss: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sub: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
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
