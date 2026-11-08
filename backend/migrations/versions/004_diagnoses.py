"""AI-assisted diagnoses schema

Revision ID: 004_diagnoses
Revises: 003_scans_and_evidence
Create Date: 2026-11-07 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_diagnoses"
down_revision: Union[str, None] = "003_scans_and_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("likely_causes", sa.Text(), nullable=False),
        sa.Column("supporting_evidence_ids", sa.Text(), nullable=False),
        sa.Column("missing_information", sa.Text(), nullable=False),
        sa.Column("recommended_actions", sa.Text(), nullable=False),
        sa.Column("confidence_explanation", sa.Text(), nullable=False),
        sa.Column("raw_model_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["storefront_scans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagnoses_scan_id", "diagnoses", ["scan_id"], unique=False)
    op.create_index("ix_diagnoses_scan_created_at", "diagnoses", ["scan_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_diagnoses_scan_created_at", table_name="diagnoses")
    op.drop_index("ix_diagnoses_scan_id", table_name="diagnoses")
    op.drop_table("diagnoses")
