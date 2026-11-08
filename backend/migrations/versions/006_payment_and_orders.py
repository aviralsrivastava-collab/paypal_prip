"""Payment and orders schema

Revision ID: 006_payment_and_orders
Revises: 005_correction_proposals
Create Date: 2026-11-07 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_payment_and_orders"
down_revision: Union[str, None] = "005_correction_proposals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("paypal_order_id", sa.String(length=100), nullable=True),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=False),
        sa.Column("order_status", sa.String(length=50), nullable=False, server_default="CREATED"),
        sa.Column("payment_status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("preflight_scan_id", sa.Integer(), nullable=True),
        sa.Column("preflight_passed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preflight_scan_id"], ["storefront_scans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_order_id"), "orders", ["order_id"], unique=True)
    op.create_index(op.f("ix_orders_paypal_order_id"), "orders", ["paypal_order_id"], unique=True)
    op.create_index(op.f("ix_orders_sku"), "orders", ["sku"], unique=False)
    op.create_index(op.f("ix_orders_product_id"), "orders", ["product_id"], unique=False)
    op.create_index(op.f("ix_orders_idempotency_key"), "orders", ["idempotency_key"], unique=True)

    # 2. Payment captures table
    op.create_table(
        "payment_captures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("paypal_capture_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("amount", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fee_amount", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=True),
        sa.Column("net_amount", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=50), nullable=False, server_default="NOT_NEEDED"),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_captures_order_id"), "payment_captures", ["order_id"], unique=False)
    op.create_index(op.f("ix_payment_captures_paypal_capture_id"), "payment_captures", ["paypal_capture_id"], unique=True)

    # 3. Webhook events table
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paypal_event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RECEIVED"),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("transmission_id", sa.String(length=100), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_webhook_events_paypal_event_id"), "webhook_events", ["paypal_event_id"], unique=True)
    op.create_index(op.f("ix_webhook_events_event_type"), "webhook_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_webhook_events_transmission_id"), "webhook_events", ["transmission_id"], unique=False)

    # 4. Demo inventory reservations table
    op.create_table(
        "demo_inventory_reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RESERVED"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_demo_inventory_reservations_order_id"), "demo_inventory_reservations", ["order_id"], unique=False)
    op.create_index(op.f("ix_demo_inventory_reservations_sku"), "demo_inventory_reservations", ["sku"], unique=False)


def downgrade() -> None:
    op.drop_table("demo_inventory_reservations")
    op.drop_table("webhook_events")
    op.drop_table("payment_captures")
    op.drop_table("orders")
