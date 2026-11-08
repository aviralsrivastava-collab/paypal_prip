import datetime
import json
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.models.audit import AuditEvent
from backend.models.proposal import CorrectionProposal
from backend.policies.correction_policy import (
    ApprovalStatus,
    ExecutionStatus,
    PolicyValidationStatus,
    validate_correction_proposal,
    validate_proposal_lifecycle_transition,
)
from backend.repositories.evidence import EvidenceRepository
from backend.repositories.product import ProductRepository
from backend.repositories.proposal import ProposalRepository
from backend.repositories.scan import ScanRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.proposal import (
    CorrectionProposalApproveRequest,
    CorrectionProposalCreateRequest,
    CorrectionProposalRejectRequest,
    CorrectionProposalResponse,
    ProposalHistoryItem,
)
from backend.services.audit import AuditService


class ProposalService:
    """
    Business service managing the lifecycle of merchant correction proposals.
    Enforces deterministic validation, merchant authorization, expiration, and append-only audit tracking.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.proposal_repo = ProposalRepository(session)
        self.catalog_repo = ProductRepository(session)
        self.storefront_repo = StorefrontRepository(session)
        self.scan_repo = ScanRepository(session)
        self.evidence_repo = EvidenceRepository(session)

    def create_proposal(
        self,
        request: CorrectionProposalCreateRequest,
        trusted_actor: AuthenticatedActor,
    ) -> CorrectionProposalResponse:
        """
        Creates and deterministically validates a new correction proposal.
        Enforces idempotency, evidence-grounding, version pinning, and audit logging.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Check idempotency key
        if request.idempotency_key:
            existing = self.proposal_repo.get_by_idempotency_key(request.idempotency_key)
            if existing:
                if (
                    existing.sku == request.sku
                    and existing.proposed_value == request.proposed_value
                    and existing.proposal_type == request.proposal_type
                ):
                    return CorrectionProposalResponse.from_orm_model(existing)
                raise ValueError(
                    f"Idempotency conflict: key '{request.idempotency_key}' was previously used with different request parameters."
                )

        # 2. Retrieve inspection scan
        scan = self.scan_repo.get_by_id(request.scan_id)
        if not scan:
            raise ValueError(f"Referenced inspection scan #{request.scan_id} does not exist.")

        # 3. Retrieve catalog ground truth and storefront products
        catalog_product = self.catalog_repo.get_by_sku(request.sku)
        if not catalog_product:
            raise ValueError(f"Catalog product with SKU '{request.sku}' does not exist.")

        storefront_product = self.storefront_repo.get_by_sku(request.sku)
        if not storefront_product:
            raise ValueError(f"Storefront product with SKU '{request.sku}' does not exist.")

        # 4. Retrieve structured evidence for scan
        evidence_items = self.evidence_repo.list_by_scan_id(scan.id)
        available_evidence_ids = {e.id for e in evidence_items}

        expires_at = now + datetime.timedelta(hours=request.expires_in_hours)

        # 5. Deterministic Policy Validation
        policy_result = validate_correction_proposal(
            sku=request.sku,
            proposal_type=request.proposal_type,
            proposed_value=request.proposed_value,
            currency=request.currency,
            supporting_evidence_ids=request.supporting_evidence_ids,
            catalog_sku=catalog_product.sku,
            catalog_price=catalog_product.price,
            catalog_currency=catalog_product.currency,
            storefront_sku=storefront_product.sku,
            storefront_price=storefront_product.price,
            storefront_currency=storefront_product.currency,
            inspection_state=scan.state,
            is_comparable=scan.is_comparable,
            available_evidence_ids=available_evidence_ids,
            expected_catalog_version=catalog_product.source_version,
            current_catalog_version=catalog_product.source_version,
            expected_storefront_version=storefront_product.version,
            current_storefront_version=storefront_product.version,
            expires_at=expires_at,
            current_time=now,
            execution_status=ExecutionStatus.NOT_STARTED,
        )

        if not policy_result.is_valid:
            raise ValueError(f"Proposal violates correction policy: {policy_result.error_summary}")

        # 6. Atomically persist Proposal and Audit Events
        actor_merchant = getattr(trusted_actor, "merchant_id", None)
        if not actor_merchant or not actor_merchant.strip():
            raise ValueError("Proposal creation requires trusted actor with explicit merchant_id attribution.")
        resolved_merchant_id = actor_merchant.strip()
        if scan.merchant_id != resolved_merchant_id and getattr(trusted_actor, "role", "") not in ("superadmin", "system"):
            raise ValueError(
                f"Merchant mismatch: actor from '{resolved_merchant_id}' cannot create proposal for scan belonging to '{scan.merchant_id}'."
            )

        correlation_id = f"prop-{uuid.uuid4()}"
        with atomic_transaction(self.session):
            proposal = CorrectionProposal(
                merchant_id=resolved_merchant_id,
                scan_id=scan.id,
                diagnosis_id=None,
                product_id=catalog_product.id,
                sku=request.sku,
                proposal_type=request.proposal_type,
                current_value=storefront_product.price,
                proposed_value=request.proposed_value,
                currency=request.currency,
                reason=request.reason,
                supporting_evidence_ids=json.dumps(request.supporting_evidence_ids),
                policy_validation_status=policy_result.status.value,
                approval_status=ApprovalStatus.PENDING_APPROVAL.value,
                execution_status=ExecutionStatus.NOT_STARTED.value,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
                created_by=trusted_actor.actor_id,
                approved_by=None,
                rejected_by=None,
                rejection_reason=None,
                executed_at=None,
                expected_catalog_version=catalog_product.source_version,
                expected_storefront_version=storefront_product.version,
                idempotency_key=request.idempotency_key,
                execution_error=None,
                execution_correlation_id=None,
            )
            self.proposal_repo.create(proposal)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_PROPOSED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=None,
                    correlation_id=correlation_id,
                    before_state=None,
                    after_state=json.dumps(
                        {
                            "sku": proposal.sku,
                            "current_value": str(proposal.current_value),
                            "proposed_value": str(proposal.proposed_value),
                            "currency": proposal.currency,
                        }
                    ),
                    details=f"Correction proposed for SKU {proposal.sku}: {proposal.reason}",
                ),
            )

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type="system",
                    actor_id="policy_engine",
                    action="CORRECTION_VALIDATED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=None,
                    correlation_id=correlation_id,
                    before_state=None,
                    after_state=policy_result.status.value,
                    details="Deterministic policy validation succeeded (status: VALID).",
                ),
            )

        return CorrectionProposalResponse.from_orm_model(proposal)

    def approve_proposal(
        self,
        proposal_id: int,
        trusted_actor: AuthenticatedActor,
        request: Optional[CorrectionProposalApproveRequest] = None,
    ) -> CorrectionProposalResponse:
        """
        Approves a pending correction proposal with strict authorization and freshness verification.
        AI agents are strictly forbidden from approving proposals.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Authorization check
        if trusted_actor.role == "ordinary_user":
            raise PermissionError(
                f"Unauthorized: actor '{trusted_actor.actor_id}' with role '{trusted_actor.role}' cannot approve corrections."
            )
        if trusted_actor.actor_id in {"ai", "ai_advisory", "system-ai"} or trusted_actor.actor_type == "ai":
            raise PermissionError("Critical Invariant Violation: AI agents are strictly forbidden from approving corrections.")

        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Correction proposal #{proposal_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, proposal.merchant_id)

        # Idempotency check: if already approved by same actor, return current
        if proposal.approval_status == ApprovalStatus.APPROVED.value:
            return CorrectionProposalResponse.from_orm_model(proposal)

        # 2. Lifecycle transition check
        if not validate_proposal_lifecycle_transition(
            ApprovalStatus(proposal.approval_status), ApprovalStatus.APPROVED
        ):
            raise ValueError(
                f"Cannot approve proposal #{proposal_id} currently in '{proposal.approval_status}' state."
            )

        # 3. Expiration check
        expires = proposal.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        if now >= expires:
            with atomic_transaction(self.session):
                proposal.approval_status = ApprovalStatus.EXPIRED.value
                proposal.updated_at = now
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type="system",
                        actor_id="policy_engine",
                        action="CORRECTION_EXPIRED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=None,
                        correlation_id=f"exp-{uuid.uuid4()}",
                        details=f"Proposal #{proposal.id} expired at {expires.isoformat()}.",
                    ),
                )
            raise ValueError(f"Cannot approve proposal #{proposal_id}: proposal expired at {expires.isoformat()}.")

        # 4. Freshness and Stale Data Revalidation
        catalog_product = self.catalog_repo.get_by_sku(proposal.sku)
        storefront_product = self.storefront_repo.get_by_sku(proposal.sku)

        if not catalog_product or not storefront_product:
            raise ValueError(f"Associated products for SKU '{proposal.sku}' no longer exist.")

        if (
            catalog_product.source_version != proposal.expected_catalog_version
            or storefront_product.version != proposal.expected_storefront_version
        ):
            with atomic_transaction(self.session):
                proposal.policy_validation_status = PolicyValidationStatus.STALE.value
                proposal.updated_at = now
            raise ValueError(
                f"Cannot approve proposal #{proposal_id}: data is stale: underlying product versions have changed. "
                f"Expected catalog v{proposal.expected_catalog_version}/storefront v{proposal.expected_storefront_version}, "
                f"current catalog v{catalog_product.source_version}/storefront v{storefront_product.version}."
            )

        if catalog_product.price != proposal.proposed_value:
            with atomic_transaction(self.session):
                proposal.policy_validation_status = PolicyValidationStatus.STALE.value
                proposal.updated_at = now
            raise ValueError(
                f"Cannot approve proposal #{proposal_id}: catalog source-of-truth price changed to {catalog_product.price}."
            )

        # 5. Atomically commit approval
        correlation_id = f"appr-{uuid.uuid4()}"
        reason = (request.reason if request and request.reason else "Merchant authorized correction")
        with atomic_transaction(self.session):
            proposal.approval_status = ApprovalStatus.APPROVED.value
            proposal.approved_by = trusted_actor.actor_id
            proposal.updated_at = now

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_APPROVED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=str(proposal.id),
                    correlation_id=correlation_id,
                    before_state=ApprovalStatus.PENDING_APPROVAL.value,
                    after_state=ApprovalStatus.APPROVED.value,
                    details=f"Proposal #{proposal.id} approved by merchant '{trusted_actor.actor_id}': {reason}",
                ),
            )

        return CorrectionProposalResponse.from_orm_model(proposal)

    def reject_proposal(
        self,
        proposal_id: int,
        trusted_actor: AuthenticatedActor,
        request: CorrectionProposalRejectRequest,
    ) -> CorrectionProposalResponse:
        """
        Rejects a proposal with mandatory reason recording.
        Guarantees that rejected proposals can never be approved or executed.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Authorization check
        if trusted_actor.role == "ordinary_user":
            raise PermissionError(
                f"Unauthorized: actor '{trusted_actor.actor_id}' cannot reject proposals."
            )

        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Correction proposal #{proposal_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, proposal.merchant_id)

        # 2. Lifecycle transition check
        if not validate_proposal_lifecycle_transition(
            ApprovalStatus(proposal.approval_status), ApprovalStatus.REJECTED
        ):
            raise ValueError(
                f"Cannot reject proposal #{proposal_id} currently in '{proposal.approval_status}' state."
            )

        # 3. Mandatory rejection reason
        if not request.reason or len(request.reason.strip()) < 3:
            raise ValueError("A clear, substantive rejection reason is mandatory.")

        # 4. Atomically commit rejection
        correlation_id = f"rej-{uuid.uuid4()}"
        with atomic_transaction(self.session):
            proposal.approval_status = ApprovalStatus.REJECTED.value
            proposal.rejected_by = trusted_actor.actor_id
            proposal.rejection_reason = request.reason.strip()
            proposal.updated_at = now

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_REJECTED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=None,
                    correlation_id=correlation_id,
                    before_state=ApprovalStatus.PENDING_APPROVAL.value,
                    after_state=ApprovalStatus.REJECTED.value,
                    details=f"Proposal #{proposal.id} rejected by '{trusted_actor.actor_id}': {request.reason.strip()}",
                ),
            )

        return CorrectionProposalResponse.from_orm_model(proposal)

    def cancel_proposal(
        self,
        proposal_id: int,
        trusted_actor: AuthenticatedActor,
        reason: Optional[str] = None,
    ) -> CorrectionProposalResponse:
        """Cancels a pending proposal."""
        now = datetime.datetime.now(datetime.timezone.utc)
        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Correction proposal #{proposal_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, proposal.merchant_id)

        if not validate_proposal_lifecycle_transition(
            ApprovalStatus(proposal.approval_status), ApprovalStatus.CANCELLED
        ):
            raise ValueError(f"Cannot cancel proposal currently in '{proposal.approval_status}' state.")

        correlation_id = f"canc-{uuid.uuid4()}"
        with atomic_transaction(self.session):
            proposal.approval_status = ApprovalStatus.CANCELLED.value
            proposal.updated_at = now

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_CANCELLED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=None,
                    correlation_id=correlation_id,
                    before_state=ApprovalStatus.PENDING_APPROVAL.value,
                    after_state=ApprovalStatus.CANCELLED.value,
                    details=reason or "Proposal cancelled by operator.",
                ),
            )

        return CorrectionProposalResponse.from_orm_model(proposal)

    def get_proposal(self, proposal_id: int) -> Optional[CorrectionProposalResponse]:
        """Retrieves proposal with automatic dynamic expiration evaluation."""
        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            return None

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = proposal.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)

        if proposal.approval_status == ApprovalStatus.PENDING_APPROVAL.value and now >= expires:
            with atomic_transaction(self.session):
                proposal.approval_status = ApprovalStatus.EXPIRED.value
                proposal.updated_at = now
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type="system",
                        actor_id="policy_engine",
                        action="CORRECTION_EXPIRED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=None,
                        correlation_id=f"exp-{uuid.uuid4()}",
                        details=f"Proposal #{proposal.id} automatically marked expired at {expires.isoformat()}.",
                    ),
                )

        return CorrectionProposalResponse.from_orm_model(proposal)

    def list_proposals(
        self,
        sku: Optional[str] = None,
        approval_status: Optional[str] = None,
        execution_status: Optional[str] = None,
    ) -> List[CorrectionProposalResponse]:
        proposals = self.proposal_repo.list_proposals(
            sku=sku, approval_status=approval_status, execution_status=execution_status
        )
        return [CorrectionProposalResponse.from_orm_model(p) for p in proposals]

    def get_proposal_history(self, proposal_id: int) -> List[ProposalHistoryItem]:
        """Retrieves append-only audit trail records for a correction proposal."""
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "correction_proposal",
                AuditEvent.entity_id == str(proposal_id),
            )
            .order_by(AuditEvent.created_at.asc())
        )
        records = self.session.execute(stmt).scalars().all()
        return [
            ProposalHistoryItem(
                id=r.id,
                action=r.action,
                actor_id=r.actor_id,
                actor_type=r.actor_type,
                created_at=r.created_at,
                details=r.details,
                before_state=r.before_state,
                after_state=r.after_state,
            )
            for r in records
        ]
