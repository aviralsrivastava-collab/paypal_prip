"""Add merchants, users, and merchant_memberships tables with seed backfill

Revision ID: 013_merchants_and_memberships
Revises: 012_unique_completed_capture_per_order
Create Date: 2026-11-12 18:30:00.000000

"""

import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_merchants_and_memberships"
down_revision: Union[str, None] = "012_unique_completed_capture_per_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("iss", sa.String(length=255), nullable=False),
        sa.Column("sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("iss", "sub", name="uq_users_iss_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. Create merchants table
    op.create_table(
        "merchants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("paypal_merchant_id", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_merchants_slug"),
    )
    op.create_index("ix_merchants_slug", "merchants", ["slug"])

    # 3. Create merchant_memberships table
    op.create_table(
        "merchant_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("merchant_id", sa.String(length=64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="VIEWER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", "user_id", name="uq_merchant_membership"),
    )
    op.create_index("ix_merchant_memberships_merchant_id", "merchant_memberships", ["merchant_id"])
    op.create_index("ix_merchant_memberships_user_id", "merchant_memberships", ["user_id"])

    # 4. Seed default merchant, operator user, and owner membership
    conn = op.get_bind()

    # Seed merchant_default if absent
    conn.execute(
        sa.text(
            """
            INSERT INTO merchants (id, slug, name, status, currency, created_at, updated_at)
            SELECT 'merchant_default', 'default', 'StrideX Sports (Default)', 'ACTIVE', 'USD', :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM merchants WHERE id = 'merchant_default')
            """
        ),
        {"now": now},
    )

    # Seed demo user if absent
    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, iss, sub, email, full_name, is_active, created_at, updated_at)
            SELECT 'usr_demo_operator', 'https://accounts.google.com', 'demo-operator-1', 'operator@prip.local', 'Demo Operator', 1, :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'usr_demo_operator')
            """
        ),
        {"now": now},
    )

    # Seed default membership if absent
    conn.execute(
        sa.text(
            """
            INSERT INTO merchant_memberships (id, merchant_id, user_id, role, is_active, created_at, updated_at)
            SELECT 'mem_default_owner', 'merchant_default', 'usr_demo_operator', 'OWNER', 1, :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM merchant_memberships WHERE id = 'mem_default_owner')
            """
        ),
        {"now": now},
    )


def downgrade() -> None:
    op.drop_table("merchant_memberships")
    op.drop_table("merchants")
    op.drop_table("users")
