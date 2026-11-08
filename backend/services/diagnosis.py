import json
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.integrations.ai.base import AIProviderInterface
from backend.integrations.ai.context import DiagnosisPromptContext
from backend.integrations.ai.factory import get_ai_provider
from backend.models.diagnosis import Diagnosis
from backend.policies.diagnosis_validator import validate_diagnosis_payload
from backend.repositories.diagnosis import DiagnosisRepository
from backend.repositories.evidence import EvidenceRepository
from backend.repositories.scan import ScanRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.diagnosis import DiagnosisResponse, RawDiagnosisPayload
from backend.services.audit import AuditService


class DiagnosisService:
    """
    Orchestrates evidence-grounded AI-assisted diagnosis for completed storefront scans.
    Enforces strict authority boundaries: AI is advisory-only and cannot mutate domain state.
    Enforces multi-merchant tenant ownership.
    """

    def __init__(
        self,
        session: Session,
        ai_provider: Optional[AIProviderInterface] = None,
    ) -> None:
        self.session = session
        self.scan_repo = ScanRepository(session)
        self.evidence_repo = EvidenceRepository(session)
        self.diagnosis_repo = DiagnosisRepository(session)
        self.ai_provider = ai_provider or get_ai_provider()

    def diagnose_scan(
        self,
        scan_id: int,
        trusted_actor: AuthenticatedActor,
        correlation_id: Optional[str] = None,
        simulated_failure: Optional[str] = None,
    ) -> DiagnosisResponse:
        """
        Executes a diagnostic evaluation for a completed inspection scan.
        Guarantees:
        - Tenant ownership is verified before any AI invocation or persistence.
        - AI provider failure never alters or invalidates the underlying scan or state.
        - Outputs are strictly schema-validated and grounded in actual evidence IDs.
        - Recommendations are advisory only and cannot mutate business state.
        """
        cid = correlation_id or f"diag-{uuid.uuid4()}"

        # 1. Fetch completed inspection scan
        scan = self.scan_repo.get_by_id(scan_id)
        if not scan:
            raise ValueError(f"Cannot diagnose: inspection scan with ID {scan_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, scan.merchant_id)

        # 2. Fetch structured evidence items
        evidence_items = self.evidence_repo.list_by_scan_id(scan_id)
        allowed_ids = {e.id for e in evidence_items}

        evidence_records = [
            {
                "id": e.id,
                "evidence_type": e.evidence_type,
                "field_name": e.field_name,
                "expected_value": e.expected_value,
                "observed_value": e.observed_value,
                "status": e.status,
                "content_hash": e.content_hash,
            }
            for e in evidence_items
        ]

        # Extract sanitized snippet from extraction evidence if present
        storefront_snippet = None
        for e in evidence_items:
            if e.evidence_type == "EXTRACTION" and e.details:
                storefront_snippet = e.details
                break

        # 3. Build safely-delimited prompt context
        context = DiagnosisPromptContext(
            scan_id=scan.id,
            sku=scan.sku,
            inspection_state=scan.state,
            is_comparable=scan.is_comparable,
            failure_reason=scan.failure_reason,
            catalog_price=scan.catalog_price,
            observed_price=scan.observed_price,
            currency=scan.currency,
            discrepancy_amount=scan.discrepancy_amount,
            evidence_records=evidence_records,
            allowed_evidence_ids=sorted(list(allowed_ids)),
            untrusted_storefront_snippet=storefront_snippet,
            simulated_failure=simulated_failure,
        )

        # 4. Invoke AI diagnostic provider
        raw_payload: RawDiagnosisPayload = self.ai_provider.generate_diagnosis(context)

        # 5. Deterministic Policy Validation
        validate_diagnosis_payload(raw_payload, allowed_ids)

        # 6. Atomically persist Diagnosis and Audit Event
        with atomic_transaction(self.session):
            diagnosis_entity = Diagnosis(
                merchant_id=scan.merchant_id,
                scan_id=scan.id,
                provider=self.ai_provider.provider_name,
                model=self.ai_provider.model_name,
                prompt_version=self.ai_provider.prompt_version,
                status=raw_payload.status.value,
                summary=raw_payload.summary,
                likely_causes=json.dumps(raw_payload.likely_causes),
                supporting_evidence_ids=json.dumps(raw_payload.supporting_evidence_ids),
                missing_information=json.dumps(raw_payload.missing_information),
                recommended_actions=json.dumps(raw_payload.recommended_actions),
                confidence_explanation=raw_payload.confidence_explanation,
                raw_model_response=raw_payload.model_dump_json(),
            )
            self.diagnosis_repo.create(diagnosis_entity)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=scan.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="DIAGNOSIS_COMPLETED",
                    entity_type="diagnosis",
                    entity_id=str(diagnosis_entity.id),
                    approval_id=None,
                    correlation_id=cid,
                    details=f"Advisory AI diagnosis completed with status {raw_payload.status.value} for scan #{scan.id}",
                ),
            )

        return DiagnosisResponse.from_orm_model(diagnosis_entity)

    def get_diagnosis(
        self,
        diagnosis_id: int,
        current_actor: Optional[AuthenticatedActor] = None,
    ) -> Optional[DiagnosisResponse]:
        """Fetch diagnosis by ID with optional tenant check."""
        entity = self.diagnosis_repo.get_by_id(diagnosis_id)
        if not entity:
            return None
        if current_actor:
            require_merchant_access(current_actor, entity.merchant_id)
        return DiagnosisResponse.from_orm_model(entity)

    def list_diagnoses_by_scan(
        self,
        scan_id: int,
        current_actor: Optional[AuthenticatedActor] = None,
    ) -> List[DiagnosisResponse]:
        """List historical diagnoses for a scan with optional tenant check."""
        scan = self.scan_repo.get_by_id(scan_id)
        if not scan:
            return []
        if current_actor:
            require_merchant_access(current_actor, scan.merchant_id)
        records = self.diagnosis_repo.list_by_scan_id(scan_id)
        return [DiagnosisResponse.from_orm_model(d) for d in records]
