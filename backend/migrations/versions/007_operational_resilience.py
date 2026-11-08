"""Operational resilience, background worker leasing and reconciliation schema

Revision ID: 007_operational_resilience
Revises: 006_payment_and_orders
Create Date: 2026-11-07 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_operational_resilience"
down_revision: Union[str, None] = "006_payment_and_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add background leasing, retry, and error tracking fields to webhook_events
    with op.batch_alter_table("webhook_events") as batch_op:
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("locked_by", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("error_category", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_error", sa.Text(), nullable=True)
        )
        batch_op.create_index(
            "ix_webhook_events_status", ["status"], unique=False
        )
        batch_op.create_index(
            "ix_webhook_events_next_retry_at", ["next_retry_at"], unique=False
        )
        batch_op.create_index(
            "ix_webhook_events_processing_lease_expires_at",
            ["processing_lease_expires_at"],
            unique=False,
        )

    # 2. Payment reconciliations table
    op.create_table(
        "payment_reconciliations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("paypal_order_id", sa.String(length=100), nullable=True),
        sa.Column("paypal_capture_id", sa.String(length=100), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("previous_payment_status", sa.String(length=50), nullable=False),
        sa.Column("new_payment_status", sa.String(length=50), nullable=False),
        sa.Column("provider_status", sa.String(length=50), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=False, server_default="MERCHANT"),
        sa.Column("actor_id", sa.String(length=100), nullable=False, server_default="MERCHANT"),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_reconciliations_order_id"), "payment_reconciliations", ["order_id"], unique=False)
    op.create_index(op.f("ix_payment_reconciliations_paypal_order_id"), "payment_reconciliations", ["paypal_order_id"], unique=False)
    op.create_index(op.f("ix_payment_reconciliations_reconciled_at"), "payment_reconciliations", ["reconciled_at"], unique=False)

    # 3. Worker heartbeats table
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("worker_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_worker_heartbeats_worker_id"), "worker_heartbeats", ["worker_id"], unique=True)


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_table("payment_reconciliations")

    with op.batch_alter_table("webhook_events") as batch_op:
        batch_op.drop_index("ix_webhook_events_processing_lease_expires_at")
        batch_op.drop_index("ix_webhook_events_next_retry_at")
        batch_op.drop_index("ix_webhook_events_status")
        batch_op.drop_column("last_error")
        batch_op.drop_column("error_category")
        batch_op.drop_column("processing_lease_expires_at")
        batch_op.drop_column("locked_by")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("max_attempts")
        batch_op.drop_column("attempt_count")
