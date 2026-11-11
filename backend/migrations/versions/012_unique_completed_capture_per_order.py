"""Add partial unique index on payment_captures for COMPLETED status per order

Revision ID: 012_unique_completed_capture_per_order
Revises: 011_revalidate_parent_tenant_ownership
Create Date: 2026-11-11 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_unique_completed_capture_per_order"
down_revision: Union[str, None] = "011_revalidate_parent_tenant_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Precondition check: verify no duplicate COMPLETED captures exist for any order_id
    duplicate_check = conn.execute(
        sa.text(
            "SELECT order_id, COUNT(id) AS count "
            "FROM payment_captures "
            "WHERE status = 'COMPLETED' "
            "GROUP BY order_id "
            "HAVING COUNT(id) > 1"
        )
    ).fetchall()

    if duplicate_check:
        dup_summary = ", ".join(f"order_id={row[0]} (count={row[1]})" for row in duplicate_check)
        raise RuntimeError(
            f"Precondition failed for migration '012_unique_completed_capture_per_order': "
            f"Found duplicate COMPLETED captures in 'payment_captures': [{dup_summary}]. "
            "Resolve duplicate records prior to applying this unique index constraint."
        )

    op.create_index(
        "ix_one_completed_capture_per_order",
        "payment_captures",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'COMPLETED'"),
        sqlite_where=sa.text("status = 'COMPLETED'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_one_completed_capture_per_order",
        table_name="payment_captures",
    )
