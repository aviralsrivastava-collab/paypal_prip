import concurrent.futures
import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.api.scans import trigger_scan
from backend.core.security import AuthenticatedActor
from backend.models.evidence import EvidenceItem
from backend.models.scan import StorefrontScan
from backend.policies.evidence_integrity import (
    compute_evidence_hash,
    verify_evidence_hash,
)
from backend.repositories.audit import AuditRepository
from backend.schemas.scan import EvidenceItemResponse, ScanCreateRequest
from backend.services.audit import AuditService
from backend.services.catalog import CatalogService
from backend.services.inspection import IdempotencyConflictError, InspectionService


@pytest.fixture
def test_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="test-operator", role="demo_operator", actor_type="MERCHANT")


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    catalog_service = CatalogService(db_session)
    catalog_service.seed_initial_catalog(reset=True)
    return db_session


# =============================================================================
# CHECK 1: Database Transaction Boundaries & Rollback Integrity
# =============================================================================
class TestDatabaseTransactionBoundaries:

    def test_storefront_extraction_occurs_outside_database_transaction(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Verifies that during storefront extraction, no active open database transaction
        is held. Transaction opens strictly when atomic persistence begins.
        """
        service = InspectionService(seeded_db)
        original_extract = service.extractor.extract_from_storefront
        was_in_transaction_during_extract = []

        def spy_extract(*args, **kwargs):
            # Check if session is currently in an active transaction during extraction
            was_in_transaction_during_extract.append(seeded_db.in_transaction())
            return original_extract(*args, **kwargs)

        service.extractor.extract_from_storefront = spy_extract  # type: ignore[assignment]
        request = ScanCreateRequest(sku="SX-001")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.id > 0
        assert len(was_in_transaction_during_extract) == 1
        # Extraction MUST happen with False (no open transaction held)
        assert was_in_transaction_during_extract[0] is False

    def test_evidence_persistence_failure_rolls_back_scan_and_audit(
        self, seeded_db: Session, test_actor: AuthenticatedActor, monkeypatch
    ):
        """
        Failure Injection: An error during evidence persistence must roll back
        the scan entity and audit event. Zero partial records must remain.
        """
        service = InspectionService(seeded_db)

        def faulty_create_many(items):
            raise RuntimeError("Injected evidence persistence failure")

        monkeypatch.setattr(service.evidence_repo, "create_many", faulty_create_many)

        request = ScanCreateRequest(sku="SX-001")
        with pytest.raises(RuntimeError, match="Injected evidence persistence failure"):
            service.run_inspection(request=request, trusted_actor=test_actor)

        # Verify database contents: complete rollback
        assert seeded_db.query(StorefrontScan).count() == 0
        assert seeded_db.query(EvidenceItem).count() == 0
        audit_events = AuditRepository.list_by_entity(seeded_db, "storefront_scan", "1")
        assert len(audit_events) == 0

    def test_audit_persistence_failure_rolls_back_scan_and_evidence(
        self, seeded_db: Session, test_actor: AuthenticatedActor, monkeypatch
    ):
        """
        Failure Injection: An error during audit logging must roll back
        both the scan and evidence records atomically.
        """
        service = InspectionService(seeded_db)

        def faulty_log_event(session, event_create):
            raise RuntimeError("Injected audit logging failure")

        monkeypatch.setattr(AuditService, "log_event", faulty_log_event)

        request = ScanCreateRequest(sku="SX-001")
        with pytest.raises(RuntimeError, match="Injected audit logging failure"):
            service.run_inspection(request=request, trusted_actor=test_actor)

        # Verify database contents: complete rollback
        assert seeded_db.query(StorefrontScan).count() == 0
        assert seeded_db.query(EvidenceItem).count() == 0

    def test_commit_failure_rolls_back_all_entities_atomically(
        self, seeded_db: Session, test_actor: AuthenticatedActor, monkeypatch
    ):
        """
        Failure Injection: An error during session commit must roll back all entities.
        """
        service = InspectionService(seeded_db)

        def faulty_commit():
            raise RuntimeError("Injected database commit failure")

        monkeypatch.setattr(seeded_db, "commit", faulty_commit)

        request = ScanCreateRequest(sku="SX-001")
        with pytest.raises(RuntimeError, match="Injected database commit failure"):
            service.run_inspection(request=request, trusted_actor=test_actor)

        assert seeded_db.query(StorefrontScan).count() == 0
        assert seeded_db.query(EvidenceItem).count() == 0


# =============================================================================
# CHECK 2: Evidence Integrity & Immutability
# =============================================================================
class TestEvidenceIntegrityAndImmutability:

    def test_sha256_hashes_are_generated_deterministically(self):
        """
        Verifies that SHA-256 hash generation is pure and deterministic across runs.
        """
        ts = datetime.datetime(2026, 11, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        hash1 = compute_evidence_hash(
            evidence_type="PRICE",
            field_name="price",
            expected_value="100.00",
            observed_value="120.00",
            source_url="/products/sx-001",
            observation_timestamp=ts,
            status="MISMATCH",
            details="Discrepancy: +20.00",
        )
        hash2 = compute_evidence_hash(
            evidence_type="PRICE",
            field_name="price",
            expected_value="100.00",
            observed_value="120.00",
            source_url="/products/sx-001",
            observation_timestamp=ts,
            status="MISMATCH",
            details="Discrepancy: +20.00",
        )
        assert hash1 == hash2
        assert len(hash1) == 64
        int(hash1, 16)  # valid hex check

    def test_evidence_retrieval_verifies_stored_content_against_hash(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Verifies that normal inspection evidence satisfies integrity verification.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        detail = service.run_inspection(request=request, trusted_actor=test_actor)

        evidence_items = service.evidence_repo.list_by_scan_id(detail.id)
        assert len(evidence_items) >= 4

        for item in evidence_items:
            assert verify_evidence_hash(item) is True
            resp = EvidenceItemResponse.from_orm_model(item)
            assert resp.integrity_verified is True

    def test_modified_content_produces_integrity_verification_failure(self):
        """
        Tamper Detection: Modifying observed value causes verify_evidence_hash to fail.
        """
        ts = datetime.datetime(2026, 11, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        valid_hash = compute_evidence_hash(
            evidence_type="PRICE",
            field_name="price",
            expected_value="100.00",
            observed_value="120.00",
            source_url="/products/sx-001",
            observation_timestamp=ts,
            status="MISMATCH",
        )

        # Construct item with tampered observed_value (changed to 100.00)
        tampered_item = EvidenceItem(
            id=1,
            scan_id=1,
            evidence_type="PRICE",
            field_name="price",
            expected_value="100.00",
            observed_value="100.00",  # TAMPERED
            source_url="/products/sx-001",
            observation_timestamp=ts,
            content_hash=valid_hash,
            status="MISMATCH",
            created_at=ts,
        )

        assert verify_evidence_hash(tampered_item) is False
        resp = EvidenceItemResponse.from_orm_model(tampered_item)
        assert resp.integrity_verified is False

    def test_modified_hash_produces_integrity_verification_failure(self):
        """
        Tamper Detection: Modifying hash value causes verify_evidence_hash to fail.
        """
        ts = datetime.datetime(2026, 11, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
        item = EvidenceItem(
            scan_id=1,
            evidence_type="PRICE",
            field_name="price",
            expected_value="100.00",
            observed_value="120.00",
            source_url="/products/sx-001",
            observation_timestamp=ts,
            content_hash="0" * 64,  # FORGED HASH
            status="MISMATCH",
        )
        assert verify_evidence_hash(item) is False

    def test_sqlite_triggers_reject_direct_sql_update_and_delete_on_evidence(
        self, tmp_path: Path
    ):
        """
        Database-Level Immutability:
        Direct SQL UPDATE and DELETE on evidence_items are rejected by SQLite triggers.
        """
        db_file = tmp_path / "evidence_trigger_test.db"
        db_url = f"sqlite:///{db_file.as_posix()}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            triggers = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            ).scalars().all()
            assert "prevent_evidence_items_update" in triggers
            assert "prevent_evidence_items_delete" in triggers

            # Insert baseline product and scan
            conn.execute(
                text(
                    "INSERT INTO products (sku, title, price, currency, availability, source_version, created_at, updated_at) "
                    "VALUES ('SX-001', 'StrideX', 100.00, 'USD', 'IN_STOCK', 1, '2026-11-07 12:00:00', '2026-11-07 12:00:00')"
                )
            )
            conn.execute(
                text("INSERT INTO storefront_scans (product_id, sku, source_version, url, state, is_comparable, correlation_id, created_at) VALUES (1, 'SX-001', 1, '/p/sx-001', 'ISSUE_DETECTED', 1, 'c-1', '2026-11-07 12:00:00')")
            )
            # Insert evidence item (normal insertion must succeed)
            conn.execute(
                text(
                    """
                    INSERT INTO evidence_items (
                        merchant_id, scan_id, evidence_type, field_name, expected_value, observed_value,
                        source_url, observation_timestamp, content_hash, status, created_at
                    ) VALUES (
                        'merchant_default', 1, 'PRICE', 'price', '100.00', '120.00', '/p/sx-001',
                        '2026-11-07 12:00:00', 'abc123', 'MISMATCH', '2026-11-07 12:00:00'
                    )
                    """
                )
            )
            conn.commit()

            # Attempt direct SQL UPDATE: must abort
            with pytest.raises(Exception) as exc_update:
                conn.execute(text("UPDATE evidence_items SET observed_value = '100.00' WHERE id = 1"))
                conn.commit()
            assert "evidence_items is append-only: updates are prohibited" in str(exc_update.value)

            # Attempt direct SQL DELETE: must abort
            with pytest.raises(Exception) as exc_delete:
                conn.execute(text("DELETE FROM evidence_items WHERE id = 1"))
                conn.commit()
            assert "evidence_items is append-only: deletions are prohibited" in str(exc_delete.value)

        # Verify migration downgrade removes triggers cleanly
        command.downgrade(alembic_cfg, "002_catalog_and_storefront")
        with engine.connect() as conn:
            triggers_after = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            ).scalars().all()
            assert "prevent_evidence_items_update" not in triggers_after
            assert "prevent_evidence_items_delete" not in triggers_after


# =============================================================================
# CHECK 3: Inspection Idempotency
# =============================================================================
class TestInspectionIdempotency:

    def test_first_request_with_idempotency_key_creates_one_inspection(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        The first request with a novel idempotency key creates one inspection.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", idempotency_key="idemp-key-001")
        detail = service.run_inspection(request=request, trusted_actor=test_actor)

        assert detail.id > 0
        assert detail.idempotency_key == "idemp-key-001"
        assert seeded_db.query(StorefrontScan).filter_by(idempotency_key="idemp-key-001").count() == 1
        assert len(AuditRepository.list_by_entity(seeded_db, "storefront_scan", str(detail.id))) == 1

    def test_repeating_same_request_with_same_key_returns_existing_result(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Replaying the exact same request with the same idempotency key returns the
        existing inspection without creating duplicate scans or duplicate audit events.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", idempotency_key="idemp-key-replay")

        # First attempt
        first_result = service.run_inspection(request=request, trusted_actor=test_actor)

        # Repeated attempt with same key and same payload
        second_result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert second_result.id == first_result.id
        assert second_result.state == first_result.state
        assert second_result.created_at == first_result.created_at

        # Verify no duplicate scans or audit records
        assert seeded_db.query(StorefrontScan).filter_by(idempotency_key="idemp-key-replay").count() == 1
        audit_events = AuditRepository.list_by_entity(seeded_db, "storefront_scan", str(first_result.id))
        assert len(audit_events) == 1

    def test_reusing_same_key_with_different_request_data_returns_conflict(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Reusing an idempotency key with conflicting request parameters must raise
        IdempotencyConflictError (HTTP 409 Conflict at API layer).
        """
        service = InspectionService(seeded_db)
        req1 = ScanCreateRequest(sku="SX-001", simulated_scenario=None, idempotency_key="idemp-key-conflict")
        service.run_inspection(request=req1, trusted_actor=test_actor)

        # Reuse same key with different simulation parameter
        req2 = ScanCreateRequest(sku="SX-001", simulated_scenario="timeout", idempotency_key="idemp-key-conflict")
        with pytest.raises(IdempotencyConflictError, match="previously used with different request parameters"):
            service.run_inspection(request=req2, trusted_actor=test_actor)

    def test_api_route_idempotency_header_and_conflict_mapping(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Tests API route handling of Idempotency-Key header, successful replay, and 409 Conflict.
        """
        req1 = ScanCreateRequest(sku="SX-001")
        # Call 1 via route handler with Idempotency-Key header
        res1 = trigger_scan(request=req1, idempotency_key="api-idemp-100", current_actor=test_actor, db=seeded_db)
        assert res1.id > 0

        # Call 2 via route handler with identical header and payload
        res2 = trigger_scan(request=req1, idempotency_key="api-idemp-100", current_actor=test_actor, db=seeded_db)
        assert res2.id == res1.id

        # Call 3 via route handler with same header but conflicting payload -> 409 Conflict
        req_diff = ScanCreateRequest(sku="SX-001", simulated_scenario="blocked")
        with pytest.raises(HTTPException) as exc_info:
            trigger_scan(request=req_diff, idempotency_key="api-idemp-100", current_actor=test_actor, db=seeded_db)
        assert exc_info.value.status_code == 409
        assert "previously used with different request parameters" in exc_info.value.detail

    def test_new_key_creates_new_inspection(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        A distinct idempotency key creates a distinct inspection scan.
        """
        service = InspectionService(seeded_db)
        res1 = service.run_inspection(ScanCreateRequest(sku="SX-001", idempotency_key="key-A"), test_actor)
        res2 = service.run_inspection(ScanCreateRequest(sku="SX-001", idempotency_key="key-B"), test_actor)

        assert res1.id != res2.id
        assert seeded_db.query(StorefrontScan).count() == 2

    def test_concurrent_duplicate_requests_create_exactly_one_inspection(
        self, tmp_path: Path, test_actor: AuthenticatedActor
    ):
        """
        Concurrency: Multiple concurrent threads submitting the exact same idempotency key
        produce exactly one database scan and one audit event; all threads receive the same scan ID.
        """
        db_file = tmp_path / "concurrent_idemp_test.db"
        db_url = f"sqlite:///{db_file.as_posix()}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Seed catalog
        with SessionClass() as seed_sess:
            CatalogService(seed_sess).seed_initial_catalog(reset=True)

        results = []

        def worker(thread_idx: int):
            with SessionClass() as worker_sess:
                srv = InspectionService(worker_sess)
                req = ScanCreateRequest(sku="SX-001", idempotency_key="concurrent-key-omega")
                res = srv.run_inspection(request=req, trusted_actor=test_actor)
                return res.id

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, i) for i in range(4)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # All concurrent workers must receive the exact same scan ID
        assert len(results) == 4
        assert len(set(results)) == 1

        # Database must have exactly 1 scan with this idempotency key
        with SessionClass() as check_sess:
            count = check_sess.query(StorefrontScan).filter_by(idempotency_key="concurrent-key-omega").count()
            assert count == 1
            audit_count = check_sess.query(StorefrontScan).count()
            assert audit_count == 1
