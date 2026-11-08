from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.api.products import seed_catalog
from backend.core.config import get_settings
from backend.core.security import AuthenticatedActor, require_demo_operator
from backend.models.product import Product
from backend.models.storefront import StorefrontProduct
from backend.repositories.audit import AuditRepository
from backend.schemas.storefront import StorefrontUpdatePriceRequest
from backend.services.catalog import CatalogService
from backend.services.storefront import StorefrontService


# -----------------------------------------------------------------------------
# Check 1: Seed / Reset Endpoint Protection
# -----------------------------------------------------------------------------
class TestSeedResetEndpointProtection:

    def test_seed_reset_forbidden_in_production(self, db_session: Session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")

        actor = AuthenticatedActor(actor_id="admin-1", role="demo_operator")
        with pytest.raises(HTTPException) as exc_info:
            require_demo_operator(current_actor=actor)

        assert exc_info.value.status_code == 403
        assert "forbidden in production" in exc_info.value.detail.lower()

    def test_seed_reset_unauthorized_user_forbidden(self, db_session: Session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")

        ordinary_user = AuthenticatedActor(actor_id="guest-user", role="ordinary_user")
        with pytest.raises(HTTPException) as exc_info:
            require_demo_operator(current_actor=ordinary_user)

        assert exc_info.value.status_code == 403
        assert "not authorized" in exc_info.value.detail.lower()

    def test_seed_reset_allowed_for_demo_operator_in_demo_env(self, db_session: Session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")

        operator = AuthenticatedActor(actor_id="demo-op-1", role="demo_operator")
        authorized_actor = require_demo_operator(current_actor=operator)
        assert authorized_actor.actor_id == "demo-op-1"

        res = seed_catalog(reset=True, actor=authorized_actor, db=db_session)
        assert res["status"] == "success"
        assert res["catalog_price"] == "100.00"
        assert res["storefront_price"] == "120.00"


# -----------------------------------------------------------------------------
# Check 2: Trusted Audit Actor Identity (Anti-Impersonation)
# -----------------------------------------------------------------------------
class TestTrustedAuditActorIdentity:

    def test_forged_actor_id_in_request_body_is_rejected_from_audit_trail(self, db_session: Session):
        catalog_service = CatalogService(db_session)
        catalog_service.seed_initial_catalog(actor_id="system-seed")

        # Client submits payload with forged actor_id "fake_executive"
        forged_request = StorefrontUpdatePriceRequest(
            price=Decimal("115.00"),
            currency="USD",
            actor_id="fake_executive",  # Forged identity in body
            expected_version=1,
            reason="Unsanctioned discount",
        )

        # Server-side security context identifies actual authenticated caller
        trusted_identity = AuthenticatedActor(
            actor_id="authenticated-clerk-99",
            actor_type="merchant",
            role="merchant_operator",
        )

        service = StorefrontService(db_session)
        service.update_price("SX-001", forged_request, trusted_actor=trusted_identity)

        # Verify audit trail: MUST record authenticated-clerk-99, NEVER fake_executive
        audit_events = AuditRepository.list_by_entity(db_session, "storefront_product", "SX-001")
        price_events = [e for e in audit_events if e.action == "STOREFRONT_PRICE_UPDATED"]
        assert len(price_events) == 1

        event = price_events[0]
        assert event.actor_id == "authenticated-clerk-99"
        assert event.actor_id != "fake_executive"
        assert event.details is not None
        assert "overridden by trusted identity" in event.details

    def test_production_environment_rejects_unauthenticated_header_mutation(self, monkeypatch):
        from backend.core.security import get_current_actor

        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")

        with pytest.raises(HTTPException) as exc_info:
            get_current_actor(x_actor_id="demo-user", x_actor_role="merchant_operator")

        assert exc_info.value.status_code == 401
        assert "production authentication" in exc_info.value.detail.lower()


# -----------------------------------------------------------------------------
# Check 3: Currency Comparability
# -----------------------------------------------------------------------------
class TestCurrencyComparability:

    def test_case_1_matching_currency_discrepancy_calculated(self, db_session: Session):
        # Catalog USD 100.00, Storefront USD 120.00: comparable, discrepancy +20.00
        service = CatalogService(db_session)
        service.seed_initial_catalog()

        comp = service.get_product_by_sku("SX-001")
        assert comp is not None
        assert comp.is_comparable is True
        assert comp.comparability_reason is None
        assert comp.merchant_price == "100.00"
        assert comp.storefront_price == "120.00"
        assert comp.price_discrepancy == "+20.00"
        assert comp.has_discrepancy is True

    def test_case_2_differing_currencies_explicitly_non_comparable(self, db_session: Session):
        # Catalog USD 100.00, Storefront EUR 120.00: non-comparable
        p = Product(
            sku="SX-DIFF-CURR",
            title="Cross-border Runner",
            price=Decimal("100.00"),
            currency="USD",
        )
        sf = StorefrontProduct(
            sku="SX-DIFF-CURR",
            title="Cross-border Runner",
            price=Decimal("120.00"),
            currency="EUR",  # Differing currency!
        )
        db_session.add(p)
        db_session.add(sf)
        db_session.commit()

        service = CatalogService(db_session)
        comp = service.get_product_by_sku("SX-DIFF-CURR")
        assert comp is not None
        assert comp.is_comparable is False
        assert comp.price_discrepancy is None  # MUST NOT compute a numerical discrepancy!
        assert comp.has_discrepancy is True   # Flagged as an issue/mismatch
        assert comp.comparability_reason is not None
        assert "CURRENCY_MISMATCH" in comp.comparability_reason

    def test_case_3_matching_gbp_clean_no_discrepancy(self, db_session: Session):
        # Catalog GBP 100.00, Storefront GBP 100.00: comparable, discrepancy 0.00
        p = Product(
            sku="SX-GBP-MATCH",
            title="UK Runner",
            price=Decimal("100.00"),
            currency="GBP",
        )
        sf = StorefrontProduct(
            sku="SX-GBP-MATCH",
            title="UK Runner",
            price=Decimal("100.00"),
            currency="GBP",
        )
        db_session.add(p)
        db_session.add(sf)
        db_session.commit()

        service = CatalogService(db_session)
        comp = service.get_product_by_sku("SX-GBP-MATCH")
        assert comp is not None
        assert comp.is_comparable is True
        assert comp.comparability_reason is None
        assert comp.merchant_price == "100.00"
        assert comp.storefront_price == "100.00"
        assert comp.price_discrepancy == "+0.00"
        assert comp.has_discrepancy is False


# -----------------------------------------------------------------------------
# Check 4: SQLite Audit Immutability Triggers
# -----------------------------------------------------------------------------
class TestSQLiteAuditImmutabilityTriggers:

    def test_triggers_prevent_sql_update_and_delete_on_disposable_database(self, tmp_path: Path):
        db_file = tmp_path / "disposable_audit_trigger_test.db"
        db_url = f"sqlite:///{db_file.as_posix()}"

        # 1. Run migrations up to head on disposable DB
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Verify triggers exist in sqlite_master
            triggers = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            ).scalars().all()
            assert "prevent_audit_events_update" in triggers
            assert "prevent_audit_events_delete" in triggers

            # 2. INSERT into audit_events must succeed
            conn.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        actor_type, actor_id, action, entity_type, entity_id,
                        correlation_id, created_at
                    ) VALUES (
                        'merchant', 'test-actor-1', 'TEST_EVENT', 'product', 'SX-001',
                        'corr-123', '2026-11-07 12:00:00'
                    )
                    """
                )
            )
            conn.commit()

            # Verify row inserted
            count = conn.execute(text("SELECT count(*) FROM audit_events")).scalar()
            assert count == 1

            # 3. Direct SQL UPDATE must fail because of SQLite trigger
            with pytest.raises(Exception) as exc_update:
                conn.execute(
                    text("UPDATE audit_events SET action = 'TAMPERED_ACTION' WHERE id = 1")
                )
                conn.commit()
            assert "audit_events is append-only: updates are prohibited" in str(exc_update.value)

            # 4. Direct SQL DELETE must fail because of SQLite trigger
            with pytest.raises(Exception) as exc_delete:
                conn.execute(
                    text("DELETE FROM audit_events WHERE id = 1")
                )
                conn.commit()
            assert "audit_events is append-only: deletions are prohibited" in str(exc_delete.value)

        # 5. Downgrade migration cleanly removes triggers
        command.downgrade(alembic_cfg, "001_initial")
        with engine.connect() as conn:
            triggers_after = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            ).scalars().all()
            assert "prevent_audit_events_update" not in triggers_after
            assert "prevent_audit_events_delete" not in triggers_after
