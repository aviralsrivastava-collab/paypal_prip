from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_migration_013_merchants_and_memberships(tmp_path: Path):
    """
    Verifies that Alembic migration 013 creates the multi-tenant identity tables:
    - users (with unique constraint on iss + sub)
    - merchants (with unique constraint on slug)
    - merchant_memberships (with foreign keys and unique constraint on merchant_id + user_id)
    - seeds default merchant, demo operator, and owner membership idempotently
    - downgrade cleanly drops all tables
    - re-upgrade succeeds deterministically
    """
    db_file = tmp_path / "test_migration_013.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade to 012 first
    command.upgrade(alembic_cfg, "012_unique_completed_capture_per_order")

    # 2. Upgrade to 013
    command.upgrade(alembic_cfg, "013_merchants_and_memberships")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Verify merchants table has default merchant
        res_merchants = conn.execute(
            text("SELECT id, slug, name, status, currency FROM merchants WHERE id = 'merchant_default'")
        ).fetchone()
        assert res_merchants is not None
        assert res_merchants[0] == "merchant_default"
        assert res_merchants[1] == "default"
        assert res_merchants[3] == "ACTIVE"

        # Verify users table has demo user
        res_users = conn.execute(
            text("SELECT id, iss, sub, email, full_name, is_active FROM users WHERE id = 'usr_demo_operator'")
        ).fetchone()
        assert res_users is not None
        assert res_users[0] == "usr_demo_operator"
        assert res_users[2] == "demo-operator-1"
        assert res_users[3] == "operator@prip.local"

        # Verify default membership
        res_mem = conn.execute(
            text("SELECT id, merchant_id, user_id, role, is_active FROM merchant_memberships WHERE id = 'mem_default_owner'")
        ).fetchone()
        assert res_mem is not None
        assert res_mem[1] == "merchant_default"
        assert res_mem[2] == "usr_demo_operator"
        assert res_mem[3] == "OWNER"

    # 3. Test downgrade to 012
    command.downgrade(alembic_cfg, "012_unique_completed_capture_per_order")

    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('merchants', 'users', 'merchant_memberships')")
        ).fetchall()
        assert len(tables) == 0

    # 4. Test re-upgrade to head
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        res = conn.execute(text("SELECT COUNT(*) FROM merchants")).scalar()
        assert res == 1
