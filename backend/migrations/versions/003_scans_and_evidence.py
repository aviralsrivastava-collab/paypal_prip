"""Inspection scans and structured evidence schema

Revision ID: 003_scans_and_evidence
Revises: 002_catalog_and_storefront
Create Date: 2026-11-07 16:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_scans_and_evidence"
down_revision: Union[str, None] = "002_catalog_and_storefront"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Storefront Scans Table
    op.create_table(
        "storefront_scans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("url", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("is_comparable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("catalog_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("observed_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("discrepancy_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storefront_scans_idempotency_key", "storefront_scans", ["idempotency_key"], unique=True)
    op.create_index("ix_storefront_scans_correlation_id", "storefront_scans", ["correlation_id"], unique=False)
    op.create_index("ix_storefront_scans_product_id", "storefront_scans", ["product_id"], unique=False)
    op.create_index("ix_storefront_scans_sku", "storefront_scans", ["sku"], unique=False)
    op.create_index(
        "ix_storefront_scans_sku_created_at",
        "storefront_scans",
        ["sku", "created_at"],
        unique=False,
    )

    # 2. Evidence Items Table
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("field_name", sa.String(length=50), nullable=False),
        sa.Column("expected_value", sa.String(length=255), nullable=True),
        sa.Column("observed_value", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=255), nullable=False),
        sa.Column("observation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["storefront_scans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_items_scan_id", "evidence_items", ["scan_id"], unique=False)
    op.create_index(
        "ix_evidence_items_scan_type",
        "evidence_items",
        ["scan_id", "evidence_type"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_evidence_items_update
            BEFORE UPDATE ON evidence_items
            BEGIN
                SELECT RAISE(ABORT, 'evidence_items is append-only: updates are prohibited');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_evidence_items_delete
            BEFORE DELETE ON evidence_items
            BEGIN
                SELECT RAISE(ABORT, 'evidence_items is append-only: deletions are prohibited');
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS prevent_evidence_items_delete;")
        op.execute("DROP TRIGGER IF EXISTS prevent_evidence_items_update;")

    op.drop_index("ix_evidence_items_scan_type", table_name="evidence_items")
    op.drop_index("ix_evidence_items_scan_id", table_name="evidence_items")
    op.drop_table("evidence_items")

    op.drop_index("ix_storefront_scans_idempotency_key", table_name="storefront_scans")
    op.drop_index("ix_storefront_scans_sku_created_at", table_name="storefront_scans")
    op.drop_index("ix_storefront_scans_sku", table_name="storefront_scans")
    op.drop_index("ix_storefront_scans_product_id", table_name="storefront_scans")
    op.drop_index("ix_storefront_scans_correlation_id", table_name="storefront_scans")
    op.drop_table("storefront_scans")
