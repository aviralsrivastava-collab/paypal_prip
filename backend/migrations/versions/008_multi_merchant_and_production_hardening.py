"""Multi-merchant isolation and production hardening schema

Revision ID: 008_multi_merchant_and_production_hardening
Revises: 007_operational_resilience
Create Date: 2026-11-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_multi_merchant_and_production_hardening"
down_revision: Union[str, None] = "007_operational_resilience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "products",
    "orders",
    "storefront_products",
    "storefront_scans",
    "correction_proposals",
    "audit_events",
    "webhook_events",
    "payment_reconciliations",
]


def upgrade() -> None:
    for table_name in TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "merchant_id",
                    sa.String(length=100),
                    nullable=False,
                    server_default="merchant_default",
                )
            )
            batch_op.create_index(
                f"ix_{table_name}_merchant_id",
                ["merchant_id"],
                unique=False,
            )


def downgrade() -> None:
    for table_name in TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_merchant_id")
            batch_op.drop_column("merchant_id")
