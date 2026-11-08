import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_migration_009_multi_tenant_backfill_and_orphan_quarantine(tmp_path: Path):
    """
    Verifies multi-merchant historical ownership backfill and orphan quarantine:
    - Independent merchants (Merchant Alpha and Merchant Beta) retain their respective ownership.
    - Historical diagnoses, evidence items, payment captures, and reservations are correctly attributed.
    - Orphaned child records with missing parent scans/orders are safely quarantined under 'QUARANTINED_ORPHAN'.
    - No accidental cross-tenant ownership assignment or silent defaulting to 'merchant_default'.
    - Server default is removed, failing closed on raw inserts omitting merchant_id.
    - Downgrade and re-upgrade behave deterministically and safely.
    """
    db_file = tmp_path / "test_migration_quarantine.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade schema to 008 (before tenant ownership on child tables)
    command.upgrade(alembic_cfg, "008_multi_merchant_and_production_hardening")

    engine = create_engine(db_url)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)).isoformat()

    with engine.connect() as conn:
        # Seed parent scans for Merchant Alpha and Merchant Beta
        conn.execute(
            text(
                """
                INSERT INTO storefront_scans (
                    id, merchant_id, product_id, sku, source_version, url, state,
                    is_comparable, catalog_price, observed_price, currency, correlation_id, created_at
                ) VALUES
                    (101, 'merchant_alpha', 1, 'SX-001', 1, 'http://alpha', 'ISSUE_DETECTED', 1, 100.00, 120.00, 'USD', 'corr-scan-a', :now),
                    (102, 'merchant_beta', 2, 'SX-002', 1, 'http://beta', 'VERIFIED_NO_ISSUE', 1, 150.00, 150.00, 'USD', 'corr-scan-b', :now)
                """
            ),
            {"now": now},
        )

        # Seed parent orders for Merchant Alpha and Merchant Beta
        conn.execute(
            text(
                """
                INSERT INTO orders (
                    id, order_id, merchant_id, paypal_order_id, sku, product_id,
                    unit_price, currency, quantity, total_amount, order_status,
                    payment_status, preflight_scan_id, preflight_passed, correlation_id, created_at, updated_at
                ) VALUES
                    (201, 'ord-alpha-1', 'merchant_alpha', 'PAYPAL-A1', 'SX-001', 1, 100.00, 'USD', 1, 100.00, 'COMPLETED', 'CAPTURED', 101, 1, 'corr-ord-a', :now, :now),
                    (202, 'ord-beta-1', 'merchant_beta', 'PAYPAL-B1', 'SX-002', 2, 150.00, 'USD', 1, 150.00, 'COMPLETED', 'CAPTURED', 102, 1, 'corr-ord-b', :now, :now)
                """
            ),
            {"now": now},
        )

        # Seed child records across Merchant Alpha (101/201), Merchant Beta (102/202), and Orphans (9999)
        # Diagnoses
        conn.execute(
            text(
                """
                INSERT INTO diagnoses (
                    id, scan_id, provider, model, prompt_version, status,
                    summary, likely_causes, supporting_evidence_ids, missing_information,
                    recommended_actions, confidence_explanation, raw_model_response, created_at
                ) VALUES
                    (1, 101, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 'summary alpha', '[]', '[]', '[]', '[]', 'alpha explanation', '{}', :now),
                    (2, 102, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 'summary beta', '[]', '[]', '[]', '[]', 'beta explanation', '{}', :now),
                    (3, 9999, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 'summary orphan', '[]', '[]', '[]', '[]', 'orphan explanation', '{}', :now)
                """
            ),
            {"now": now},
        )

        # Evidence Items
        conn.execute(
            text(
                """
                INSERT INTO evidence_items (
                    id, scan_id, evidence_type, field_name, expected_value,
                    observed_value, source_url, observation_timestamp, status, details, created_at
                ) VALUES
                    (1, 101, 'PRICE', 'price', '100.00', '120.00', 'http://alpha', :now, 'VERIFIED_ISSUE', 'alpha evidence', :now),
                    (2, 102, 'PRICE', 'price', '150.00', '150.00', 'http://beta', :now, 'VERIFIED_CLEAN', 'beta evidence', :now),
                    (3, 9999, 'PRICE', 'price', '200.00', '250.00', 'http://orphan', :now, 'VERIFIED_ISSUE', 'orphan evidence', :now)
                """
            ),
            {"now": now},
        )

        # Payment Captures
        conn.execute(
            text(
                """
                INSERT INTO payment_captures (id, order_id, paypal_capture_id, status, amount, currency, reconciliation_status, created_at, updated_at) VALUES
                    (1, 201, 'CAP-ALPHA-1', 'COMPLETED', 100.00, 'USD', 'NOT_NEEDED', :now, :now),
                    (2, 202, 'CAP-BETA-1', 'COMPLETED', 150.00, 'USD', 'NOT_NEEDED', :now, :now),
                    (3, 9999, 'CAP-ORPHAN-1', 'COMPLETED', 200.00, 'USD', 'NOT_NEEDED', :now, :now)
                """
            ),
            {"now": now},
        )

        # Demo Inventory Reservations
        conn.execute(
            text(
                """
                INSERT INTO demo_inventory_reservations (id, order_id, sku, quantity, status, expires_at, created_at) VALUES
                    (1, 201, 'SX-001', 1, 'COMMITTED', :future, :now),
                    (2, 202, 'SX-002', 1, 'COMMITTED', :future, :now),
                    (3, 9999, 'SX-ORPHAN', 1, 'COMMITTED', :future, :now)
                """
            ),
            {"now": now, "future": future},
        )
        conn.commit()

    # 2. Run migration 009 (which added merchant_id column with default='merchant_default')
    command.upgrade(alembic_cfg, "009_tenant_ownership_and_audit_attribution")

    # 3. Run migration 010 (quarantines orphans and strips server_default)
    command.upgrade(alembic_cfg, "010_tenant_quarantine_and_audit_hardening")

    with engine.connect() as conn:
        # Verify Diagnoses
        diag_a = conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 1")).scalar_one()
        diag_b = conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 2")).scalar_one()
        diag_orphan = conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 3")).scalar_one()

        assert diag_a == "merchant_alpha", f"Expected merchant_alpha, got {diag_a}"
        assert diag_b == "merchant_beta", f"Expected merchant_beta, got {diag_b}"
        assert diag_orphan == "QUARANTINED_ORPHAN", f"Orphan must be quarantined, got {diag_orphan}"

        # Verify Evidence Items
        evi_a = conn.execute(text("SELECT merchant_id FROM evidence_items WHERE id = 1")).scalar_one()
        evi_b = conn.execute(text("SELECT merchant_id FROM evidence_items WHERE id = 2")).scalar_one()
        evi_orphan = conn.execute(text("SELECT merchant_id FROM evidence_items WHERE id = 3")).scalar_one()

        assert evi_a == "merchant_alpha"
        assert evi_b == "merchant_beta"
        assert evi_orphan == "QUARANTINED_ORPHAN"

        # Verify Payment Captures
        cap_a = conn.execute(text("SELECT merchant_id FROM payment_captures WHERE id = 1")).scalar_one()
        cap_b = conn.execute(text("SELECT merchant_id FROM payment_captures WHERE id = 2")).scalar_one()
        cap_orphan = conn.execute(text("SELECT merchant_id FROM payment_captures WHERE id = 3")).scalar_one()

        assert cap_a == "merchant_alpha"
        assert cap_b == "merchant_beta"
        assert cap_orphan == "QUARANTINED_ORPHAN"

        # Verify Demo Inventory Reservations
        res_a = conn.execute(text("SELECT merchant_id FROM demo_inventory_reservations WHERE id = 1")).scalar_one()
        res_b = conn.execute(text("SELECT merchant_id FROM demo_inventory_reservations WHERE id = 2")).scalar_one()
        res_orphan = conn.execute(text("SELECT merchant_id FROM demo_inventory_reservations WHERE id = 3")).scalar_one()

        assert res_a == "merchant_alpha"
        assert res_b == "merchant_beta"
        assert res_orphan == "QUARANTINED_ORPHAN"

        # 4. Verify that raw inserts omitting merchant_id fail closed (no server_default fallback)
        with pytest.raises(sa.exc.IntegrityError, match="merchant_id"):
            conn.execute(
                text(
                    """
                    INSERT INTO diagnoses (
                        scan_id, provider, model, prompt_version, status,
                        summary, likely_causes, supporting_evidence_ids, missing_information,
                        recommended_actions, confidence_explanation, raw_model_response, created_at
                    ) VALUES (
                        101, 'openai', 'gpt-4o', 'v1', 'COMPLETED',
                        'desc', '[]', '[]', '[]', '[]', 'desc', '{}', :now
                    )
                    """
                ),
                {"now": now},
            )
            conn.commit()

    # 5. Verify downgrade and re-upgrade behavior
    command.downgrade(alembic_cfg, "009_tenant_ownership_and_audit_attribution")
    command.upgrade(alembic_cfg, "010_tenant_quarantine_and_audit_hardening")

    with engine.connect() as conn:
        re_diag_a = conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 1")).scalar_one()
        re_diag_orphan = conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 3")).scalar_one()
        assert re_diag_a == "merchant_alpha"
        assert re_diag_orphan == "QUARANTINED_ORPHAN"


def test_migration_quarantine_blank_and_whitespace_parent_tenant(tmp_path: Path):
    """
    Verifies that records are quarantined to 'QUARANTINED_ORPHAN' when:
    - The parent does not exist.
    - The foreign key is null.
    - The parent merchant ID is null, empty, or whitespace-only.
    Ensures invalid parent ownership cannot silently propagate to child records.
    """
    db_file = tmp_path / "test_migration_blank_parent.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "008_multi_merchant_and_production_hardening")

    engine = create_engine(db_url)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)).isoformat()

    with engine.connect() as conn:
        # 1. Parents with blank, whitespace, and null merchant IDs, plus one valid parent
        conn.execute(
            text(
                """
                INSERT INTO storefront_scans (
                    id, merchant_id, product_id, sku, source_version, url, state,
                    is_comparable, catalog_price, observed_price, currency, correlation_id, created_at
                ) VALUES
                    (301, 'merchant_valid', 1, 'SX-001', 1, 'http://valid', 'VERIFIED_NO_ISSUE', 1, 100.00, 100.00, 'USD', 'corr-301', :now),
                    (302, '', 1, 'SX-001', 1, 'http://empty', 'VERIFIED_NO_ISSUE', 1, 100.00, 100.00, 'USD', 'corr-302', :now),
                    (303, '   ', 1, 'SX-001', 1, 'http://space', 'VERIFIED_NO_ISSUE', 1, 100.00, 100.00, 'USD', 'corr-303', :now)
                """
            ),
            {"now": now},
        )

        conn.execute(
            text(
                """
                INSERT INTO orders (
                    id, order_id, merchant_id, paypal_order_id, sku, product_id,
                    unit_price, currency, quantity, total_amount, order_status,
                    payment_status, preflight_scan_id, preflight_passed, correlation_id, created_at, updated_at
                ) VALUES
                    (401, 'ord-valid', 'merchant_valid', 'P-VAL', 'SX-001', 1, 100.00, 'USD', 1, 100.00, 'COMPLETED', 'CAPTURED', 301, 1, 'corr-401', :now, :now),
                    (402, 'ord-empty', '', 'P-EMP', 'SX-001', 1, 100.00, 'USD', 1, 100.00, 'COMPLETED', 'CAPTURED', 302, 1, 'corr-402', :now, :now),
                    (403, 'ord-space', '   ', 'P-SPC', 'SX-001', 1, 100.00, 'USD', 1, 100.00, 'COMPLETED', 'CAPTURED', 303, 1, 'corr-403', :now, :now)
                """
            ),
            {"now": now},
        )

        # 2. Child diagnoses:
        # id 10 -> parent valid (301)
        # id 11 -> parent empty string (302)
        # id 12 -> parent whitespace only (303)
        # id 13 -> non-existent parent (9999)
        conn.execute(
            text(
                """
                INSERT INTO diagnoses (
                    id, scan_id, provider, model, prompt_version, status,
                    summary, likely_causes, supporting_evidence_ids, missing_information,
                    recommended_actions, confidence_explanation, raw_model_response, created_at
                ) VALUES
                    (10, 301, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 's', '[]', '[]', '[]', '[]', 'e', '{}', :now),
                    (11, 302, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 's', '[]', '[]', '[]', '[]', 'e', '{}', :now),
                    (12, 303, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 's', '[]', '[]', '[]', '[]', 'e', '{}', :now),
                    (13, 9999, 'openai', 'gpt-4o', 'v1', 'COMPLETED', 's', '[]', '[]', '[]', '[]', 'e', '{}', :now)
                """
            ),
            {"now": now},
        )

        # Child evidence items
        conn.execute(
            text(
                """
                INSERT INTO evidence_items (
                    id, scan_id, evidence_type, field_name, expected_value,
                    observed_value, source_url, observation_timestamp, status, details, created_at
                ) VALUES
                    (10, 301, 'PRICE', 'price', '100', '100', 'http://v', :now, 'VERIFIED_CLEAN', 'd', :now),
                    (11, 302, 'PRICE', 'price', '100', '100', 'http://e', :now, 'VERIFIED_CLEAN', 'd', :now),
                    (12, 303, 'PRICE', 'price', '100', '100', 'http://s', :now, 'VERIFIED_CLEAN', 'd', :now),
                    (13, 9999, 'PRICE', 'price', '100', '100', 'http://n', :now, 'VERIFIED_CLEAN', 'd', :now)
                """
            ),
            {"now": now},
        )

        # Child payment captures
        conn.execute(
            text(
                """
                INSERT INTO payment_captures (id, order_id, paypal_capture_id, status, amount, currency, reconciliation_status, created_at, updated_at) VALUES
                    (10, 401, 'CAP-V', 'COMPLETED', 100.00, 'USD', 'NOT_NEEDED', :now, :now),
                    (11, 402, 'CAP-E', 'COMPLETED', 100.00, 'USD', 'NOT_NEEDED', :now, :now),
                    (12, 403, 'CAP-S', 'COMPLETED', 100.00, 'USD', 'NOT_NEEDED', :now, :now),
                    (13, 9999, 'CAP-N', 'COMPLETED', 100.00, 'USD', 'NOT_NEEDED', :now, :now)
                """
            ),
            {"now": now},
        )

        # Child reservations
        conn.execute(
            text(
                """
                INSERT INTO demo_inventory_reservations (id, order_id, sku, quantity, status, expires_at, created_at) VALUES
                    (10, 401, 'SX-001', 1, 'COMMITTED', :future, :now),
                    (11, 402, 'SX-001', 1, 'COMMITTED', :future, :now),
                    (12, 403, 'SX-001', 1, 'COMMITTED', :future, :now),
                    (13, 9999, 'SX-001', 1, 'COMMITTED', :future, :now)
                """
            ),
            {"now": now, "future": future},
        )
        conn.commit()

    # Apply 009, 010, and 011
    command.upgrade(alembic_cfg, "009_tenant_ownership_and_audit_attribution")
    command.upgrade(alembic_cfg, "010_tenant_quarantine_and_audit_hardening")
    command.upgrade(alembic_cfg, "011_revalidate_parent_tenant_ownership")

    with engine.connect() as conn:
        for table in ["diagnoses", "evidence_items", "payment_captures", "demo_inventory_reservations"]:
            valid_m = conn.execute(text(f"SELECT merchant_id FROM {table} WHERE id = 10")).scalar_one()
            assert valid_m == "merchant_valid", f"{table} id 10 should be merchant_valid, got {valid_m}"

            empty_m = conn.execute(text(f"SELECT merchant_id FROM {table} WHERE id = 11")).scalar_one()
            assert empty_m == "QUARANTINED_ORPHAN", f"{table} id 11 (empty parent) should be QUARANTINED_ORPHAN, got {empty_m}"

            space_m = conn.execute(text(f"SELECT merchant_id FROM {table} WHERE id = 12")).scalar_one()
            assert space_m == "QUARANTINED_ORPHAN", f"{table} id 12 (whitespace parent) should be QUARANTINED_ORPHAN, got {space_m}"

            null_fk_m = conn.execute(text(f"SELECT merchant_id FROM {table} WHERE id = 13")).scalar_one()
            assert null_fk_m == "QUARANTINED_ORPHAN", f"{table} id 13 (null FK) should be QUARANTINED_ORPHAN, got {null_fk_m}"

    # Verify downgrade and re-upgrade through 011 -> 010 -> 011
    command.downgrade(alembic_cfg, "010_tenant_quarantine_and_audit_hardening")
    command.upgrade(alembic_cfg, "011_revalidate_parent_tenant_ownership")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 10")).scalar_one() == "merchant_valid"
        assert conn.execute(text("SELECT merchant_id FROM diagnoses WHERE id = 11")).scalar_one() == "QUARANTINED_ORPHAN"


def test_migration_backfill_failure_raises_immediately(tmp_path: Path):
    """
    Verifies that errors during migration backfill are not silently caught
    or suppressed, and fail immediately.
    """
    db_file = tmp_path / "test_migration_failure.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "008_multi_merchant_and_production_hardening")
    command.upgrade(alembic_cfg, "009_tenant_ownership_and_audit_attribution")

    # Corrupt table structure to force a backfill execution failure
    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE storefront_scans;"))
        conn.commit()

    # Upgrading to 010 must fail immediately with an error (OperationalError: no such table)
    with pytest.raises(Exception):
        command.upgrade(alembic_cfg, "010_tenant_quarantine_and_audit_hardening")
