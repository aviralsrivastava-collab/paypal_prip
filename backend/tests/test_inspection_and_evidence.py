import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.scans import get_scan, get_scan_evidence, list_product_scans, trigger_scan
from backend.core.security import AuthenticatedActor
from backend.models.storefront import StorefrontProduct
from backend.policies.comparability import (
    CatalogProductFacts,
    StorefrontObservationFacts,
    evaluate_comparability,
)
from backend.policies.inspection_state import InspectionState, classify_outcome
from backend.repositories.audit import AuditRepository
from backend.repositories.evidence import EvidenceRepository
from backend.schemas.scan import ScanCreateRequest
from backend.schemas.storefront import StorefrontUpdatePriceRequest
from backend.services.catalog import CatalogService
from backend.services.inspection import InspectionService
from backend.services.storefront import StorefrontService


@pytest.fixture
def test_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="test-operator", role="demo_operator", actor_type="MERCHANT")


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    """Pre-seeds the database with the standard Phase 2 scenario (catalog: 100, storefront: 120)."""
    catalog_service = CatalogService(db_session)
    catalog_service.seed_initial_catalog(reset=True)
    return db_session


class TestInspectionAndEvidence:

    def test_1_comparable_usd_discrepancy_results_in_issue_detected(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 1: Comparable USD with price discrepancy (100.00 vs 120.00)
        Must classify as ISSUE_DETECTED with discrepancy +20.00 and structured evidence.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.ISSUE_DETECTED.value
        assert result.is_comparable is True
        assert result.catalog_price == "100.00"
        assert result.observed_price == "120.00"
        assert result.discrepancy_amount == "+20.00"
        assert result.currency == "USD"
        assert len(result.evidence_items) >= 4

        # Verify structured evidence items
        evidence_by_type = {item.evidence_type: item for item in result.evidence_items}
        assert "EXTRACTION" in evidence_by_type
        assert evidence_by_type["EXTRACTION"].status == "MATCH"
        assert evidence_by_type["EXTRACTION"].content_hash is not None
        assert len(evidence_by_type["EXTRACTION"].content_hash) == 64

        assert "IDENTITY" in evidence_by_type
        assert evidence_by_type["IDENTITY"].status == "MATCH"
        assert evidence_by_type["IDENTITY"].expected_value == "SX-001"
        assert evidence_by_type["IDENTITY"].observed_value == "SX-001"

        assert "CURRENCY" in evidence_by_type
        assert evidence_by_type["CURRENCY"].status == "MATCH"
        assert evidence_by_type["CURRENCY"].expected_value == "USD"
        assert evidence_by_type["CURRENCY"].observed_value == "USD"

        assert "PRICE" in evidence_by_type
        assert evidence_by_type["PRICE"].status == "MISMATCH"
        assert evidence_by_type["PRICE"].expected_value == "100.00"
        assert evidence_by_type["PRICE"].observed_value == "120.00"

    def test_2_comparable_matching_price_results_in_verified_no_issue(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 2: Storefront price matches catalog price (100.00 vs 100.00).
        Must classify as VERIFIED_NO_ISSUE.
        """
        # Align storefront price to catalog price
        storefront_service = StorefrontService(seeded_db)
        storefront_service.update_price(
            sku="SX-001",
            request=StorefrontUpdatePriceRequest(price=Decimal("100.00"), expected_version=1),
            trusted_actor=test_actor,
        )

        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.VERIFIED_NO_ISSUE.value
        assert result.is_comparable is True
        assert result.catalog_price == "100.00"
        assert result.observed_price == "100.00"
        assert result.discrepancy_amount == "+0.00"
        assert result.failure_reason is None

        evidence_by_type = {item.evidence_type: item for item in result.evidence_items}
        assert evidence_by_type["PRICE"].status == "MATCH"

    def test_3_currency_mismatch_results_in_blocked_unknown_no_discrepancy(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 3: Currency mismatch (catalog: USD, storefront: EUR).
        Must be BLOCKED_UNKNOWN. Discrepancy must NEVER be computed across currencies!
        """
        # Change storefront product currency to EUR
        sf_prod = seeded_db.query(StorefrontProduct).filter_by(sku="SX-001").first()
        assert sf_prod is not None
        sf_prod.currency = "EUR"
        seeded_db.commit()

        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.BLOCKED_UNKNOWN.value
        assert result.is_comparable is False
        assert result.discrepancy_amount is None  # CRITICAL: no numerical discrepancy
        assert "CURRENCY_MISMATCH" in (result.failure_reason or "")

        evidence_by_type = {item.evidence_type: item for item in result.evidence_items}
        assert evidence_by_type["CURRENCY"].status == "MISMATCH"
        assert evidence_by_type["PRICE"].status == "BLOCKED"

    def test_4_missing_storefront_product_results_in_blocked_unknown(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 4: Product missing from storefront (404/not found).
        Must be BLOCKED_UNKNOWN.
        """
        # Delete storefront product
        seeded_db.query(StorefrontProduct).filter_by(sku="SX-001").delete()
        seeded_db.commit()

        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.BLOCKED_UNKNOWN.value
        assert result.is_comparable is False
        assert result.discrepancy_amount is None
        assert "MISSING_PRODUCT" in (result.failure_reason or "")

    def test_5_extraction_timeout_simulation_results_in_blocked_unknown(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 5: External storefront extraction timeout.
        Must classify as BLOCKED_UNKNOWN.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", simulated_scenario="timeout")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.BLOCKED_UNKNOWN.value
        assert result.is_comparable is False
        assert result.discrepancy_amount is None
        assert "TIMEOUT" in (result.failure_reason or "")

        evidence_by_type = {item.evidence_type: item for item in result.evidence_items}
        assert evidence_by_type["EXTRACTION"].status == "BLOCKED"

    def test_6_unsupported_content_simulation_results_in_blocked_unknown(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 6: Storefront returns malformed / unsupported content.
        Must classify as BLOCKED_UNKNOWN.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", simulated_scenario="unsupported")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.BLOCKED_UNKNOWN.value
        assert result.is_comparable is False
        assert "UNSUPPORTED_CONTENT" in (result.failure_reason or "")

    def test_7_blocked_access_simulation_results_in_blocked_unknown(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Scenario 7: Bot challenge / 403 Forbidden.
        Must classify as BLOCKED_UNKNOWN.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", simulated_scenario="blocked")
        result = service.run_inspection(request=request, trusted_actor=test_actor)

        assert result.state == InspectionState.BLOCKED_UNKNOWN.value
        assert result.is_comparable is False
        assert "BLOCKED_ACCESS" in (result.failure_reason or "")

    def test_8_critical_invariant_blocked_unknown_cannot_become_verified_no_issue(self):
        """
        CRITICAL INVARIANT TEST:
        Under NO circumstances can an inconclusive or non-comparable inspection
        collapse into VERIFIED_NO_ISSUE. Missing evidence is NOT evidence of correctness.
        """
        # Case A: Extraction succeeded but comparability failed with 0 discrepancy
        outcome = classify_outcome(
            extraction_successful=True,
            is_comparable=False,
            discrepancy_detected=False,
        )
        assert outcome == InspectionState.BLOCKED_UNKNOWN
        assert outcome != InspectionState.VERIFIED_NO_ISSUE

        # Case B: Extraction failed completely
        outcome_fail = classify_outcome(
            extraction_successful=False,
            is_comparable=False,
            discrepancy_detected=False,
            extraction_error="Timeout",
        )
        assert outcome_fail == InspectionState.BLOCKED_UNKNOWN
        assert outcome_fail != InspectionState.VERIFIED_NO_ISSUE

        # Case C: Direct comparability policy check for differing variants
        cat = CatalogProductFacts("SX-001", "StrideX", Decimal("100.00"), "USD")
        obs = StorefrontObservationFacts("SX-001", "StrideX", Decimal("100.00"), "USD", variant="Size 11 (Catalog is Size 10)")
        res = evaluate_comparability(cat, obs)
        assert res.is_comparable is False
        # When evaluated for state:
        final_state = classify_outcome(True, res.is_comparable, res.has_discrepancy)
        assert final_state == InspectionState.BLOCKED_UNKNOWN

    def test_9_not_tested_state_representation(self):
        """
        Confirms the 4-state enum contains NOT_TESTED as an explicit first-class state.
        """
        assert InspectionState.NOT_TESTED.value == "NOT_TESTED"
        assert InspectionState.ISSUE_DETECTED.value == "ISSUE_DETECTED"
        assert InspectionState.VERIFIED_NO_ISSUE.value == "VERIFIED_NO_ISSUE"
        assert InspectionState.BLOCKED_UNKNOWN.value == "BLOCKED_UNKNOWN"

    def test_10_evidence_item_integrity_and_sha256_content_hash(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Verifies that evidence items include SHA-256 content hashes, valid timestamps,
        and foreign key links to the scan entity.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001")
        detail = service.run_inspection(request=request, trusted_actor=test_actor)

        evidence_repo = EvidenceRepository(seeded_db)
        items = evidence_repo.list_by_scan_id(detail.id)
        assert len(items) >= 4

        for item in items:
            assert item.scan_id == detail.id
            assert item.content_hash is not None
            assert len(item.content_hash) == 64
            # SHA-256 hex string validation
            int(item.content_hash, 16)
            assert item.observation_timestamp is not None
            assert item.status in ["MATCH", "MISMATCH", "BLOCKED"]

    def test_11_audit_trail_logging_on_inspection(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Verifies that an atomic INSPECTION_COMPLETED audit event is recorded.
        """
        service = InspectionService(seeded_db)
        request = ScanCreateRequest(sku="SX-001", correlation_id="test-corr-42")
        detail = service.run_inspection(request=request, trusted_actor=test_actor)

        events = AuditRepository.list_by_entity(seeded_db, "storefront_scan", str(detail.id))
        assert len(events) == 1
        event = events[0]
        assert event.action == "INSPECTION_COMPLETED"
        assert event.actor_id == test_actor.actor_id
        assert event.correlation_id == "test-corr-42"
        assert event.after_state is not None
        after_data = json.loads(event.after_state)
        assert after_data["sku"] == "SX-001"
        assert after_data["state"] == InspectionState.ISSUE_DETECTED.value

    def test_12_api_endpoints_trigger_detail_evidence_and_history(
        self, seeded_db: Session, test_actor: AuthenticatedActor
    ):
        """
        Tests API handlers:
        POST /api/scans
        GET /api/scans/{id}
        GET /api/scans/{id}/evidence
        GET /api/scans/product/{sku}
        """
        # 1. Trigger scan via API route handler
        create_req = ScanCreateRequest(sku="SX-001")
        scan_detail = trigger_scan(request=create_req, current_actor=test_actor, db=seeded_db)
        assert scan_detail.id > 0
        assert scan_detail.sku == "SX-001"
        assert scan_detail.state == "ISSUE_DETECTED"

        # 2. Get scan detail via API route handler
        fetched_detail = get_scan(scan_id=scan_detail.id, db=seeded_db)
        assert fetched_detail.id == scan_detail.id
        assert fetched_detail.sku == "SX-001"
        assert len(fetched_detail.evidence_items) >= 4

        # 3. Get evidence via API route handler
        evidence_list = get_scan_evidence(scan_id=scan_detail.id, db=seeded_db)
        assert len(evidence_list) == len(fetched_detail.evidence_items)
        assert all(e.scan_id == scan_detail.id for e in evidence_list)

        # 4. List product scans via API route handler
        history = list_product_scans(sku="SX-001", db=seeded_db)
        assert len(history) >= 1
        assert history[0].sku == "SX-001"

        # 5. Non-existent scan detail raises 404
        with pytest.raises(HTTPException) as exc_info:
            get_scan(scan_id=99999, db=seeded_db)
        assert exc_info.value.status_code == 404

        # 6. Non-existent product scan trigger raises 404
        with pytest.raises(HTTPException) as exc_info2:
            trigger_scan(
                request=ScanCreateRequest(sku="NON-EXISTENT"),
                current_actor=test_actor,
                db=seeded_db,
            )
        assert exc_info2.value.status_code == 404
