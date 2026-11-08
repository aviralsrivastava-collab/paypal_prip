import json
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor
from backend.integrations.storefront.extractor import (
    ExtractionStatus,
    StorefrontExtractor,
    StorefrontObservation,
)
from backend.models.evidence import EvidenceItem
from backend.models.scan import StorefrontScan
from backend.policies.comparability import (
    CatalogProductFacts,
    ComparabilityResult,
    StorefrontObservationFacts,
    evaluate_comparability,
)
from backend.policies.evidence_integrity import compute_evidence_hash, compute_request_hash
from backend.policies.inspection_state import InspectionState, classify_outcome
from backend.repositories.evidence import EvidenceRepository
from backend.repositories.product import ProductRepository
from backend.repositories.scan import ScanRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.scan import (
    EvidenceItemResponse,
    ScanCreateRequest,
    ScanDetailResponse,
    ScanSummaryResponse,
)
from backend.services.audit import AuditService


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with differing request parameters."""

    pass


class InspectionService:
    """
    Orchestrates deterministic product inspection:
    1. Reads catalog facts
    2. Performs external extraction outside database transaction
    3. Runs deterministic comparability policies
    4. Classifies into mandatory 4-state model
    5. Persists scan, structured evidence, and audit trail atomically
    """

    def __init__(self, session: Session, extractor: Optional[StorefrontExtractor] = None) -> None:
        self.session = session
        self.product_repo = ProductRepository(session)
        self.scan_repo = ScanRepository(session)
        self.evidence_repo = EvidenceRepository(session)
        if extractor is not None:
            self.extractor = extractor
        else:
            from sqlalchemy.orm import sessionmaker
            session_factory = sessionmaker(autocommit=False, autoflush=False, bind=session.get_bind())
            self.extractor = StorefrontExtractor(session_factory=session_factory)

    def run_inspection(
        self,
        request: ScanCreateRequest,
        trusted_actor: AuthenticatedActor,
        idempotency_key: Optional[str] = None,
    ) -> ScanDetailResponse:
        """
        Executes a complete inspection lifecycle for the given SKU.
        Guarantees that database transactions are NOT held during external extraction.
        Supports idempotency keys to ensure replay safety and prevent duplicates.
        """
        effective_idempotency_key = idempotency_key or request.idempotency_key
        request_hash = None
        if effective_idempotency_key:
            request_hash = compute_request_hash(request.sku, request.simulated_scenario)
            existing = self.scan_repo.get_by_idempotency_key(effective_idempotency_key)
            if existing:
                if existing.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        f"Idempotency key '{effective_idempotency_key}' was previously used with different request parameters."
                    )
                evidence = self.evidence_repo.list_by_scan_id(existing.id)
                return ScanDetailResponse.from_orm_model_with_evidence(existing, list(evidence))

        correlation_id = request.correlation_id or f"scan-{uuid.uuid4()}"

        # 1. Retrieve catalog ground truth
        catalog_product = self.product_repo.get_by_sku(request.sku)
        if not catalog_product:
            raise ValueError(f"Cannot inspect: product with SKU '{request.sku}' does not exist in catalog.")

        catalog_facts = CatalogProductFacts(
            sku=catalog_product.sku,
            title=catalog_product.title,
            price=catalog_product.price,
            currency=catalog_product.currency,
            availability=catalog_product.availability,
        )
        catalog_product_id = catalog_product.id
        catalog_source_version = catalog_product.source_version
        source_url = f"/products/{catalog_facts.sku.lower()}"

        # Ensure no open database transaction is held during external I/O
        if self.session.in_transaction():
            self.session.commit()

        # 2. Extract storefront observations OUTSIDE any database transaction
        observation: StorefrontObservation = self.extractor.extract_from_storefront(
            sku=catalog_facts.sku,
            source_url=source_url,
            simulated_scenario=request.simulated_scenario,
        )

        # 3. Deterministic Comparability Evaluation
        if observation.status == ExtractionStatus.SUCCESS:
            observed_facts = StorefrontObservationFacts(
                sku=observation.observed_sku,
                title=observation.observed_title,
                price=observation.observed_price,
                currency=observation.observed_currency,
                availability=observation.observed_availability,
                variant=observation.observed_variant,
                promotion_context=observation.observed_promotion,
            )
            comp_result: ComparabilityResult = evaluate_comparability(catalog_facts, observed_facts)
            failure_reason = "; ".join(comp_result.comparability_reasons) if not comp_result.is_comparable else None
        else:
            comp_result = ComparabilityResult(
                is_comparable=False,
                comparability_reasons=[f"EXTRACTION_FAILED: {observation.error_message or observation.status.value}"],
                checked_dimensions={"extraction": False},
                price_discrepancy=None,
                has_discrepancy=False,
            )
            failure_reason = f"Extraction status {observation.status.value}: {observation.error_message}"

        # 4. Mandatory Four-State Classification
        state: InspectionState = classify_outcome(
            extraction_successful=(observation.status == ExtractionStatus.SUCCESS),
            is_comparable=comp_result.is_comparable,
            discrepancy_detected=comp_result.has_discrepancy,
            extraction_error=observation.error_message if observation.status != ExtractionStatus.SUCCESS else None,
        )

        # 5. Build Structured Evidence Items with Canonical SHA-256 Hashes
        evidence_items_to_persist: List[EvidenceItem] = []

        # Evidence: Extraction Metadata
        extraction_status = "MATCH" if observation.status == ExtractionStatus.SUCCESS else "BLOCKED"
        extraction_details = observation.raw_content_snippet or observation.error_message
        extraction_hash = compute_evidence_hash(
            evidence_type="EXTRACTION",
            field_name="storefront_status",
            expected_value="SUCCESS",
            observed_value=observation.status.value,
            source_url=observation.source_url,
            observation_timestamp=observation.observation_timestamp,
            status=extraction_status,
            details=extraction_details,
        )
        evidence_items_to_persist.append(
            EvidenceItem(
                scan_id=0,
                evidence_type="EXTRACTION",
                field_name="storefront_status",
                expected_value="SUCCESS",
                observed_value=observation.status.value,
                source_url=observation.source_url,
                observation_timestamp=observation.observation_timestamp,
                content_hash=extraction_hash,
                status=extraction_status,
                details=extraction_details,
            )
        )

        # Evidence: Product Identity
        identity_status = "MATCH" if observation.observed_sku == catalog_facts.sku else "MISMATCH"
        identity_details = f"Catalog Title: '{catalog_facts.title}' vs Observed Title: '{observation.observed_title}'"
        identity_hash = compute_evidence_hash(
            evidence_type="IDENTITY",
            field_name="sku",
            expected_value=catalog_facts.sku,
            observed_value=observation.observed_sku,
            source_url=observation.source_url,
            observation_timestamp=observation.observation_timestamp,
            status=identity_status,
            details=identity_details,
        )
        evidence_items_to_persist.append(
            EvidenceItem(
                scan_id=0,
                evidence_type="IDENTITY",
                field_name="sku",
                expected_value=catalog_facts.sku,
                observed_value=observation.observed_sku,
                source_url=observation.source_url,
                observation_timestamp=observation.observation_timestamp,
                content_hash=identity_hash,
                status=identity_status,
                details=identity_details,
            )
        )

        # Evidence: Price & Currency
        currency_status = "MATCH" if observation.observed_currency == catalog_facts.currency else "MISMATCH"
        currency_hash = compute_evidence_hash(
            evidence_type="CURRENCY",
            field_name="currency",
            expected_value=catalog_facts.currency,
            observed_value=observation.observed_currency,
            source_url=observation.source_url,
            observation_timestamp=observation.observation_timestamp,
            status=currency_status,
            details=None,
        )
        evidence_items_to_persist.append(
            EvidenceItem(
                scan_id=0,
                evidence_type="CURRENCY",
                field_name="currency",
                expected_value=catalog_facts.currency,
                observed_value=observation.observed_currency,
                source_url=observation.source_url,
                observation_timestamp=observation.observation_timestamp,
                content_hash=currency_hash,
                status=currency_status,
                details=None,
            )
        )

        price_status = "MISMATCH" if comp_result.has_discrepancy else ("MATCH" if comp_result.is_comparable else "BLOCKED")
        price_expected = f"{catalog_facts.price:.2f}"
        price_observed = f"{observation.observed_price:.2f}" if observation.observed_price is not None else None
        price_details = f"Discrepancy: {comp_result.price_discrepancy}" if comp_result.price_discrepancy is not None else failure_reason
        price_hash = compute_evidence_hash(
            evidence_type="PRICE",
            field_name="price",
            expected_value=price_expected,
            observed_value=price_observed,
            source_url=observation.source_url,
            observation_timestamp=observation.observation_timestamp,
            status=price_status,
            details=price_details,
        )
        evidence_items_to_persist.append(
            EvidenceItem(
                scan_id=0,
                evidence_type="PRICE",
                field_name="price",
                expected_value=price_expected,
                observed_value=price_observed,
                source_url=observation.source_url,
                observation_timestamp=observation.observation_timestamp,
                content_hash=price_hash,
                status=price_status,
                details=price_details,
            )
        )

        # 6. Atomically Persist Scan + Evidence + Audit Event
        actor_merchant = getattr(trusted_actor, "merchant_id", None)
        if not actor_merchant or not actor_merchant.strip():
            raise ValueError("Inspection requires trusted actor with explicit merchant_id attribution.")
        resolved_merchant_id = actor_merchant.strip()

        try:
            with atomic_transaction(self.session):
                scan_entity = StorefrontScan(
                    merchant_id=resolved_merchant_id,
                    product_id=catalog_product_id,
                    sku=catalog_facts.sku,
                    source_version=catalog_source_version,
                    url=source_url,
                    state=state.value,
                    is_comparable=comp_result.is_comparable,
                    failure_reason=failure_reason,
                    catalog_price=catalog_facts.price,
                    observed_price=observation.observed_price,
                    currency=catalog_facts.currency,
                    discrepancy_amount=comp_result.price_discrepancy,
                    correlation_id=correlation_id,
                    idempotency_key=effective_idempotency_key,
                    request_hash=request_hash,
                )
                self.scan_repo.create(scan_entity)

                for item in evidence_items_to_persist:
                    item.scan_id = scan_entity.id
                    item.merchant_id = scan_entity.merchant_id
                self.evidence_repo.create_many(evidence_items_to_persist)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=scan_entity.merchant_id,
                        actor_type=trusted_actor.actor_type,
                        actor_id=trusted_actor.actor_id,
                        action="INSPECTION_COMPLETED",
                        entity_type="storefront_scan",
                        entity_id=str(scan_entity.id),
                        approval_id=None,
                        correlation_id=correlation_id,
                        before_state=None,
                        after_state=json.dumps(
                            {
                                "sku": scan_entity.sku,
                                "state": scan_entity.state,
                                "discrepancy": str(scan_entity.discrepancy_amount),
                            }
                        ),
                        details=f"Inspection finished with outcome {state.value}. Comparable: {comp_result.is_comparable}",
                    ),
                )
        except IntegrityError:
            # Handle concurrent duplicate requests with the same idempotency key
            if effective_idempotency_key:
                existing = self.scan_repo.get_by_idempotency_key(effective_idempotency_key)
                if existing:
                    if existing.request_hash != request_hash:
                        raise IdempotencyConflictError(
                            f"Idempotency key '{effective_idempotency_key}' was previously used with different request parameters."
                        )
                    evidence = self.evidence_repo.list_by_scan_id(existing.id)
                    return ScanDetailResponse.from_orm_model_with_evidence(existing, list(evidence))
            raise

        persisted_evidence = self.evidence_repo.list_by_scan_id(scan_entity.id)
        return ScanDetailResponse.from_orm_model_with_evidence(
            scan=scan_entity,
            evidence_items=list(persisted_evidence),
            comparability_reasons=comp_result.comparability_reasons,
        )

    def get_scan_by_id(self, scan_id: int) -> Optional[ScanDetailResponse]:
        """Fetch scan with its evidence items by ID."""
        scan = self.scan_repo.get_by_id(scan_id)
        if not scan:
            return None
        evidence = self.evidence_repo.list_by_scan_id(scan_id)
        return ScanDetailResponse.from_orm_model_with_evidence(scan, list(evidence))

    def list_scans_by_sku(self, sku: str) -> List[ScanSummaryResponse]:
        """Fetch historical scans for a product."""
        scans = self.scan_repo.list_by_sku(sku)
        return [ScanSummaryResponse.from_orm_model(s) for s in scans]

    def get_scan_evidence(self, scan_id: int) -> List[EvidenceItemResponse]:
        """Fetch evidence items for a given scan ID."""
        evidence = self.evidence_repo.list_by_scan_id(scan_id)
        return [EvidenceItemResponse.from_orm_model(e) for e in evidence]
