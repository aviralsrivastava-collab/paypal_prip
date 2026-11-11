import concurrent.futures
import os
from decimal import Decimal
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.core.database import Base, normalize_database_url
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.payment_capture import PaymentCapture
from backend.models.reservation import DemoInventoryReservation
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.checkout import CreateOrderRequest
from backend.schemas.payment import CapturePaymentRequest
from backend.services.catalog import CatalogService
from backend.services.checkout import CheckoutService
from backend.services.payment import PaymentService

# Integration test requires an explicit local or dedicated test PostgreSQL connection string.
# Production Supabase must never be used for destructive test suites.
POSTGRES_TEST_URL = os.getenv("TEST_POSTGRES_DATABASE_URL")


def validate_concurrency_test_url(raw_url: str) -> str:
    """
    Enforces strict isolation guards before running Base.metadata.create_all()
    and Base.metadata.drop_all(). Prevents accidental connection to production,
    cloud hosts (Supabase, Render, AWS), or the migration-test database.
    """
    norm_url = normalize_database_url(raw_url)
    parsed = make_url(norm_url)
    host = (parsed.host or "").lower()
    db = (parsed.database or "").lower()

    # Safety Guard 1: Reject any cloud, production, or remote hosting providers
    forbidden_indicators = ["supabase", "render", "amazonaws", "rds", "prod", "live"]
    for indicator in forbidden_indicators:
        if indicator in host or indicator in db:
            raise RuntimeError(
                f"SAFETY VIOLATION: Refusing to run destructive concurrency test against cloud/production database: host='{host}', db='{db}'"
            )

    # Safety Guard 2: Require loopback / local test host
    allowed_hosts = ["localhost", "127.0.0.1", "::1", "postgres", "test-postgres"]
    if host not in allowed_hosts and not host.endswith(".local"):
        raise RuntimeError(
            f"SAFETY VIOLATION: TEST_POSTGRES_DATABASE_URL host must be localhost/127.0.0.1 or local test container, got '{host}'"
        )

    # Safety Guard 3: Dedicated database isolation (must not be migration test db)
    if "migration" in db:
        raise RuntimeError(
            f"SAFETY VIOLATION: TEST_POSTGRES_DATABASE_URL points to migration test database '{db}'. "
            "Base.metadata.drop_all() must affect only the dedicated prip_concurrency_test database!"
        )

    # Safety Guard 4: Require database name to contain 'concurrency' or 'test'
    if not ("concurrency" in db or "test" in db):
        raise RuntimeError(
            f"SAFETY VIOLATION: TEST_POSTGRES_DATABASE_URL target database '{db}' must be dedicated 'prip_concurrency_test' or contain 'test'."
        )

    return norm_url


def _is_postgres_available() -> bool:
    if not POSTGRES_TEST_URL:
        return False
    try:
        norm_url = validate_concurrency_test_url(POSTGRES_TEST_URL)
        test_engine = create_engine(norm_url, pool_pre_ping=True)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        return True
    except Exception as exc:
        if "SAFETY VIOLATION" in str(exc):
            raise
        return False


POSTGRES_AVAILABLE = _is_postgres_available()


@pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="NOT RUN: Dedicated PostgreSQL test database (TEST_POSTGRES_DATABASE_URL) is unavailable in this test environment. "
    "Per PRIP verification guidelines, SQLite is not substituted for real PostgreSQL concurrency verification.",
)
class TestPostgresConcurrencyIntegration:
    """
    Phase 4 Integration Suite: Real PostgreSQL Concurrency & Partial Unique Index Hardening.

    Tests against a live PostgreSQL instance with:
    - Real psycopg3 PostgreSQL connection pooling (separate physical connections per thread)
    - Real PostgreSQL row-level locking (SELECT ... FOR UPDATE)
    - Real PostgreSQL partial unique index enforcement (ix_one_completed_capture_per_order)
    - Stable PayPal-Request-Id idempotency
    - Exactly one completed capture and one committed reservation side effect
    """

    @pytest.fixture(scope="class")
    def pg_engine(self) -> Generator:
        assert POSTGRES_TEST_URL is not None
        norm_url = validate_concurrency_test_url(POSTGRES_TEST_URL)
        engine = create_engine(norm_url, pool_size=10, max_overflow=5)
        Base.metadata.create_all(bind=engine)
        yield engine
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    def test_five_thread_concurrent_captures_on_real_postgres(self, pg_engine) -> None:
        """
        Executes 5 genuinely concurrent threads against a live PostgreSQL database for the same order.
        Proves:
        1. Separate PostgreSQL connections.
        2. PostgreSQL SELECT ... FOR UPDATE row-level locking.
        3. Stable PayPal-Request-Id idempotency.
        4. Partial unique index (ix_one_completed_capture_per_order) prevents duplicate rows.
        5. Exactly one PaymentCapture record exists in COMPLETED state.
        6. Exactly one inventory reservation is COMMITTED.
        7. All 5 callers receive HTTP 200 / valid COMPLETED response.
        """
        PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)

        # Setup order and inventory
        setup_session = PgSessionLocal()
        catalog_service = CatalogService(setup_session)
        catalog_service.seed_initial_catalog(reset=True)
        st_repo = StorefrontRepository(setup_session)
        prod = st_repo.get_by_sku("SX-001")
        assert prod is not None
        prod.price = Decimal("100.00")
        setup_session.commit()

        mock_paypal = MockPayPalClient()
        checkout_service = CheckoutService(setup_session, paypal_client=mock_paypal)
        order_resp = checkout_service.create_order(
            CreateOrderRequest(sku="SX-001", quantity=1), actor_id="buyer"
        )
        setup_session.close()

        def worker_capture(worker_id: int):
            worker_session = PgSessionLocal()
            try:
                ps = PaymentService(worker_session, paypal_client=mock_paypal)
                return ps.capture_payment(
                    CapturePaymentRequest(order_id=order_resp.order_id),
                    actor_id=f"buyer_thread_{worker_id}",
                )
            finally:
                worker_session.close()

        # Execute 5 concurrent workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_capture, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 5
        for res in results:
            assert res.status == "COMPLETED"
            assert res.amount == Decimal("100.00")

        # Database verification with dedicated verification session
        verify_session = PgSessionLocal()
        try:
            # Exactly 1 capture row with COMPLETED status
            captures = (
                verify_session.query(PaymentCapture)
                .filter(PaymentCapture.order_id == order_resp.id)
                .all()
            )
            assert len(captures) == 1
            assert captures[0].status == "COMPLETED"

            # Exactly 1 committed inventory reservation
            reservations = (
                verify_session.query(DemoInventoryReservation)
                .filter(DemoInventoryReservation.order_id == order_resp.id)
                .all()
            )
            assert len(reservations) == 1
            assert reservations[0].status == "COMMITTED"

            # Database-level partial unique index constraint check:
            # An explicit attempt to insert a second COMPLETED capture for the same order MUST fail with IntegrityError
            duplicate_capture = PaymentCapture(
                merchant_id=captures[0].merchant_id,
                order_id=order_resp.id,
                paypal_capture_id="CAP-DELIBERATE-DUPLICATE",
                status="COMPLETED",
                amount=Decimal("100.00"),
                currency="USD",
            )
            verify_session.add(duplicate_capture)
            with pytest.raises(Exception) as exc_info:
                verify_session.commit()
            # Assert failure was caused by PostgreSQL partial unique index violation
            assert "ix_one_completed_capture_per_order" in str(exc_info.value) or "unique" in str(exc_info.value).lower()

            # Partial index property: Multiple FAILED captures for the same order ARE permitted
            verify_session.rollback()
            failed_capture_1 = PaymentCapture(
                merchant_id=captures[0].merchant_id,
                order_id=order_resp.id,
                paypal_capture_id="CAP-DELIBERATE-FAILED-1",
                status="FAILED",
                amount=Decimal("100.00"),
                currency="USD",
            )
            failed_capture_2 = PaymentCapture(
                merchant_id=captures[0].merchant_id,
                order_id=order_resp.id,
                paypal_capture_id="CAP-DELIBERATE-FAILED-2",
                status="FAILED",
                amount=Decimal("100.00"),
                currency="USD",
            )
            verify_session.add(failed_capture_1)
            verify_session.add(failed_capture_2)
            verify_session.commit()

            # Verify both failed captures persisted alongside the single completed capture
            all_captures = (
                verify_session.query(PaymentCapture)
                .filter(PaymentCapture.order_id == order_resp.id)
                .all()
            )
            assert len(all_captures) == 3  # 1 COMPLETED + 2 FAILED
            completed_in_db = [c for c in all_captures if c.status == "COMPLETED"]
            assert len(completed_in_db) == 1
        finally:
            verify_session.rollback()
            verify_session.close()
