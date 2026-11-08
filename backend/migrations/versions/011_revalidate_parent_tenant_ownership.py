"""Revalidate parent tenant ownership and quarantine invalid or blank parents

Revision ID: 011_revalidate_parent_tenant_ownership
Revises: 010_tenant_quarantine_and_audit_hardening
Create Date: 2026-11-08 08:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_revalidate_parent_tenant_ownership"
down_revision: Union[str, None] = "010_tenant_quarantine_and_audit_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    ("diagnoses", "scan_id", "storefront_scans", "id"),
    ("evidence_items", "scan_id", "storefront_scans", "id"),
    ("payment_captures", "order_id", "orders", "id"),
    ("demo_inventory_reservations", "order_id", "orders", "id"),
]


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = (conn.dialect.name == "sqlite")

    # Temporarily drop append-only triggers on evidence_items during migration update
    if is_sqlite:
        conn.execute(sa.text("DROP TRIGGER IF EXISTS prevent_evidence_items_update;"))
        conn.execute(sa.text("DROP TRIGGER IF EXISTS prevent_evidence_items_delete;"))

    try:
        for child_table, fk_col, parent_table, pk_col in TABLES:
            # 1. Update child where parent exists and has valid non-empty merchant_id
            conn.execute(
                sa.text(
                    f"UPDATE {child_table} "
                    f"SET merchant_id = ("
                    f"    SELECT TRIM({parent_table}.merchant_id) "
                    f"    FROM {parent_table} "
                    f"    WHERE {parent_table}.{pk_col} = {child_table}.{fk_col}"
                    f") "
                    f"WHERE {fk_col} IS NOT NULL "
                    f"  AND EXISTS ("
                    f"    SELECT 1 "
                    f"    FROM {parent_table} "
                    f"    WHERE {parent_table}.{pk_col} = {child_table}.{fk_col} "
                    f"      AND {parent_table}.merchant_id IS NOT NULL "
                    f"      AND TRIM({parent_table}.merchant_id) != '' "
                    f"      AND TRIM({parent_table}.merchant_id) NOT IN ('QUARANTINED_ORPHAN', 'platform_system', 'platform')"
                    f")"
                )
            )

            # 2. Quarantine records where parent is missing, foreign key is null,
            # or parent merchant ID is null, empty, or whitespace-only.
            conn.execute(
                sa.text(
                    f"UPDATE {child_table} "
                    f"SET merchant_id = 'QUARANTINED_ORPHAN' "
                    f"WHERE {fk_col} IS NULL "
                    f"   OR NOT EXISTS ("
                    f"       SELECT 1 "
                    f"       FROM {parent_table} "
                    f"       WHERE {parent_table}.{pk_col} = {child_table}.{fk_col}"
                    f"   ) "
                    f"   OR EXISTS ("
                    f"       SELECT 1 "
                    f"       FROM {parent_table} "
                    f"       WHERE {parent_table}.{pk_col} = {child_table}.{fk_col} "
                    f"         AND ({parent_table}.merchant_id IS NULL "
                    f"              OR TRIM({parent_table}.merchant_id) = '')"
                    f"   ) "
                    f"   OR merchant_id IS NULL "
                    f"   OR TRIM(merchant_id) = ''"
                )
            )
    finally:
        # Re-establish immutable append-only triggers on evidence_items
        if is_sqlite:
            conn.execute(
                sa.text(
                    """
                    CREATE TRIGGER IF NOT EXISTS prevent_evidence_items_update
                    BEFORE UPDATE ON evidence_items
                    BEGIN
                        SELECT RAISE(ABORT, 'evidence_items is append-only: updates are prohibited');
                    END;
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    CREATE TRIGGER IF NOT EXISTS prevent_evidence_items_delete
                    BEFORE DELETE ON evidence_items
                    BEGIN
                        SELECT RAISE(ABORT, 'evidence_items is append-only: deletions are prohibited');
                    END;
                    """
                )
            )


def downgrade() -> None:
    pass
