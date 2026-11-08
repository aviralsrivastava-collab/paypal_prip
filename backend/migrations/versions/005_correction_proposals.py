"""Correction proposals and remediation schema

Revision ID: 005_correction_proposals
Revises: 004_diagnoses
Create Date: 2026-11-07 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_correction_proposals"
down_revision: Union[str, None] = "004_diagnoses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "correction_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("diagnosis_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("proposal_type", sa.String(length=50), nullable=False),
        sa.Column("current_value", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=False),
        sa.Column("proposed_value", sa.Numeric(precision=10, scale=2, asdecimal=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("supporting_evidence_ids", sa.Text(), nullable=False),
        sa.Column("policy_validation_status", sa.String(length=50), nullable=False),
        sa.Column("approval_status", sa.String(length=50), nullable=False),
        sa.Column("execution_status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("rejected_by", sa.String(length=100), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_catalog_version", sa.Integer(), nullable=False),
        sa.Column("expected_storefront_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("execution_correlation_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["storefront_scans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnoses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_correction_proposals_scan_id", "correction_proposals", ["scan_id"], unique=False)
    op.create_index("ix_correction_proposals_product_id", "correction_proposals", ["product_id"], unique=False)
    op.create_index("ix_correction_proposals_sku", "correction_proposals", ["sku"], unique=False)
    op.create_index("ix_correction_proposals_idempotency_key", "correction_proposals", ["idempotency_key"], unique=True)
    op.create_index("ix_correction_proposals_sku_status", "correction_proposals", ["sku", "approval_status"], unique=False)
    op.create_index("ix_correction_proposals_expires_at", "correction_proposals", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_correction_proposals_expires_at", table_name="correction_proposals")
    op.drop_index("ix_correction_proposals_sku_status", table_name="correction_proposals")
    op.drop_index("ix_correction_proposals_idempotency_key", table_name="correction_proposals")
    op.drop_index("ix_correction_proposals_sku", table_name="correction_proposals")
    op.drop_index("ix_correction_proposals_product_id", table_name="correction_proposals")
    op.drop_index("ix_correction_proposals_scan_id", table_name="correction_proposals")
    op.drop_table("correction_proposals")
