import datetime
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.integrations.storefront.adapter import ControlledStorefrontAdapter
from backend.policies.correction_policy import (
    ApprovalStatus,
    ExecutionStatus,
    PolicyValidationStatus,
)
from backend.repositories.product import ProductRepository
from backend.repositories.proposal import ProposalRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.proposal import (
    CorrectionProposalExecuteRequest,
    CorrectionProposalReconcileRequest,
    CorrectionProposalResponse,
)
from backend.schemas.scan import ScanCreateRequest, ScanDetailResponse
from backend.services.audit import AuditService
from backend.services.inspection import InspectionService


class RemediationService:
    """
    Controlled remediation service executing merchant-approved storefront corrections.
    Guarantees:
    - External storefront calls occur OUTSIDE of open database transactions.
    - Uncertainty during external mutation transitions to RECONCILIATION_REQUIRED, never blind retries.
    - Post-remediation follow-up inspection runs automatically to verify ground-truth alignment.
    - Append-only audit logging preserves all lifecycle events.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.proposal_repo = ProposalRepository(session)
        self.catalog_repo = ProductRepository(session)
        self.storefront_repo = StorefrontRepository(session)
        self.storefront_adapter = ControlledStorefrontAdapter(session)
        self.inspection_service = InspectionService(session)

    def execute_correction(
        self,
        proposal_id: int,
        trusted_actor: AuthenticatedActor,
        request: Optional[CorrectionProposalExecuteRequest] = None,
    ) -> Tuple[CorrectionProposalResponse, Optional[ScanDetailResponse]]:
        """
        Executes an approved correction proposal.
        Enforces optimistic concurrency, isolated database transactions, reconciliation handling,
        and post-correction reinspection.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        req = request or CorrectionProposalExecuteRequest()

        # 1. Authorization check
        if trusted_actor.role == "ordinary_user":
            raise PermissionError(
                f"Unauthorized: actor '{trusted_actor.actor_id}' cannot execute corrections."
            )
        if trusted_actor.actor_id in {"ai", "ai_advisory", "system-ai"} or trusted_actor.actor_type == "ai":
            raise PermissionError("Critical Invariant Violation: AI agents cannot execute corrections.")

        # 2. Retrieve proposal
        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Correction proposal #{proposal_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, proposal.merchant_id)

        # 3. Idempotency check: if already successfully executed, return current state
        if proposal.execution_status == ExecutionStatus.SUCCEEDED.value:
            return CorrectionProposalResponse.from_orm_model(proposal), None

        if proposal.execution_status == ExecutionStatus.IN_PROGRESS.value:
            raise ValueError(f"Execution already in progress for proposal #{proposal_id}.")

        # 4. Verify approval status
        if proposal.approval_status != ApprovalStatus.APPROVED.value:
            raise ValueError(
                f"Cannot execute proposal #{proposal_id} with approval status '{proposal.approval_status}'. "
                "Only APPROVED proposals may be executed."
            )

        # 5. Verify expiration
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
            raise ValueError(f"Cannot execute proposal #{proposal_id}: proposal expired at {expires.isoformat()}.")

        # 6. Revalidate current ground truth and storefront facts immediately before apply (Freshness check)
        catalog_product = self.catalog_repo.get_by_sku(proposal.sku)
        storefront_product = self.storefront_repo.get_by_sku(proposal.sku)

        if not catalog_product or not storefront_product:
            raise ValueError(f"Underlying products for SKU '{proposal.sku}' no longer exist.")

        if (
            catalog_product.source_version != proposal.expected_catalog_version
            or storefront_product.version != proposal.expected_storefront_version
        ):
            with atomic_transaction(self.session):
                proposal.policy_validation_status = PolicyValidationStatus.STALE.value
                proposal.updated_at = now
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type="system",
                        actor_id="policy_engine",
                        action="CORRECTION_VALIDATED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=str(proposal.id),
                        correlation_id=f"stale-{uuid.uuid4()}",
                        before_state=PolicyValidationStatus.VALID.value,
                        after_state=PolicyValidationStatus.STALE.value,
                        details="Pre-execution revalidation failed: product or storefront version changed.",
                    ),
                )
            raise ValueError(
                f"Cannot execute proposal #{proposal_id}: data is stale. "
                f"Expected catalog v{proposal.expected_catalog_version}/storefront v{proposal.expected_storefront_version}, "
                f"observed catalog v{catalog_product.source_version}/storefront v{storefront_product.version}."
            )

        correlation_id = req.correlation_id or f"exec-{uuid.uuid4()}"

        # 7. Transition execution status to IN_PROGRESS atomically
        with atomic_transaction(self.session):
            proposal.execution_status = ExecutionStatus.IN_PROGRESS.value
            proposal.execution_correlation_id = correlation_id
            proposal.updated_at = now

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_EXECUTION_STARTED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=str(proposal.id),
                    correlation_id=correlation_id,
                    before_state=ExecutionStatus.NOT_STARTED.value,
                    after_state=ExecutionStatus.IN_PROGRESS.value,
                    details=f"Starting correction execution on storefront for SKU {proposal.sku} -> {proposal.proposed_value} {proposal.currency}",
                ),
            )

        # 8. Execute external storefront mutation OUTSIDE database transaction
        # Critical rule: Network timeout does not prove failure.
        try:
            self.storefront_adapter.update_product_price(
                sku=proposal.sku,
                new_price=proposal.proposed_value,
                currency=proposal.currency,
                expected_version=proposal.expected_storefront_version,
                simulate_timeout=req.simulate_timeout,
                simulate_error=req.simulate_storefront_error,
            )
        except TimeoutError as timeout_err:
            # Ambiguous external outcome: transition to RECONCILIATION_REQUIRED
            with atomic_transaction(self.session):
                proposal.execution_status = ExecutionStatus.RECONCILIATION_REQUIRED.value
                proposal.execution_error = str(timeout_err)
                proposal.updated_at = datetime.datetime.now(datetime.timezone.utc)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type="system",
                        actor_id="storefront_adapter",
                        action="CORRECTION_RECONCILIATION_REQUIRED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=str(proposal.id),
                        correlation_id=correlation_id,
                        before_state=ExecutionStatus.IN_PROGRESS.value,
                        after_state=ExecutionStatus.RECONCILIATION_REQUIRED.value,
                        details=f"Storefront timeout encountered. Blind retries blocked. Status: RECONCILIATION_REQUIRED. Error: {timeout_err}",
                    ),
                )
            raise RuntimeError(
                f"External storefront operation timed out. Status set to RECONCILIATION_REQUIRED: {timeout_err}"
            )
        except Exception as exc:
            with atomic_transaction(self.session):
                proposal.execution_status = ExecutionStatus.FAILED.value
                proposal.execution_error = str(exc)
                proposal.updated_at = datetime.datetime.now(datetime.timezone.utc)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type="system",
                        actor_id="storefront_adapter",
                        action="CORRECTION_EXECUTION_FAILED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=str(proposal.id),
                        correlation_id=correlation_id,
                        before_state=ExecutionStatus.IN_PROGRESS.value,
                        after_state=ExecutionStatus.FAILED.value,
                        details=f"Storefront mutation failed: {exc}",
                    ),
                )
            raise RuntimeError(f"Storefront correction execution failed: {exc}")

        # 9. Successful Storefront Update Persistence
        with atomic_transaction(self.session):
            proposal.execution_status = ExecutionStatus.SUCCEEDED.value
            proposal.executed_at = datetime.datetime.now(datetime.timezone.utc)
            proposal.execution_error = None
            proposal.updated_at = proposal.executed_at

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type=trusted_actor.actor_type,
                    actor_id=trusted_actor.actor_id,
                    action="CORRECTION_EXECUTION_SUCCEEDED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=str(proposal.id),
                    correlation_id=correlation_id,
                    before_state=ExecutionStatus.IN_PROGRESS.value,
                    after_state=ExecutionStatus.SUCCEEDED.value,
                    details=f"Successfully applied price correction {proposal.proposed_value} {proposal.currency} to storefront.",
                ),
            )

        # 10. Mandatory Post-Correction Reinspection
        followup_scan: Optional[ScanDetailResponse] = None
        try:
            followup_scan = self.inspection_service.run_inspection(
                request=ScanCreateRequest(
                    sku=proposal.sku,
                    correlation_id=f"reinspect-{uuid.uuid4()}",
                ),
                trusted_actor=trusted_actor,
            )
        except Exception as insp_err:
            # Reinspection failure is recorded but does not undo successful execution
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=proposal.merchant_id,
                    actor_type="system",
                    actor_id="inspection_engine",
                    action="REINSPECTION_FAILED",
                    entity_type="correction_proposal",
                    entity_id=str(proposal.id),
                    approval_id=str(proposal.id),
                    correlation_id=correlation_id,
                    details=f"Post-remediation follow-up inspection failed to complete: {insp_err}",
                ),
            )

        return CorrectionProposalResponse.from_orm_model(proposal), followup_scan

    def reconcile_proposal(
        self,
        proposal_id: int,
        trusted_actor: AuthenticatedActor,
        request: Optional[CorrectionProposalReconcileRequest] = None,
    ) -> Tuple[CorrectionProposalResponse, Optional[ScanDetailResponse]]:
        """
        Reconciles a proposal stuck in RECONCILIATION_REQUIRED by inspecting actual storefront state.
        Determines whether the timeout occurred after or before the external change was committed.
        """
        proposal = self.proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Correction proposal #{proposal_id} does not exist.")

        # Tenancy authorization check
        require_merchant_access(trusted_actor, proposal.merchant_id)

        if proposal.execution_status != ExecutionStatus.RECONCILIATION_REQUIRED.value:
            raise ValueError(
                f"Cannot reconcile proposal #{proposal_id} with execution status '{proposal.execution_status}'. "
                "Only RECONCILIATION_REQUIRED proposals can be reconciled."
            )

        correlation_id = (request.correlation_id if request and request.correlation_id else f"recon-{uuid.uuid4()}")
        current_storefront = self.storefront_adapter.get_product(proposal.sku)
        if not current_storefront:
            raise ValueError(f"Storefront product '{proposal.sku}' not found during reconciliation.")

        now = datetime.datetime.now(datetime.timezone.utc)
        followup_scan: Optional[ScanDetailResponse] = None

        # Check if actual storefront price matches proposed value
        if current_storefront.price == proposal.proposed_value:
            # External mutation actually succeeded before timeout
            with atomic_transaction(self.session):
                proposal.execution_status = ExecutionStatus.SUCCEEDED.value
                proposal.executed_at = now
                proposal.execution_error = None
                proposal.updated_at = now

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type=trusted_actor.actor_type,
                        actor_id=trusted_actor.actor_id,
                        action="CORRECTION_RECONCILED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=str(proposal.id),
                        correlation_id=correlation_id,
                        before_state=ExecutionStatus.RECONCILIATION_REQUIRED.value,
                        after_state=ExecutionStatus.SUCCEEDED.value,
                        details=f"Reconciliation verified storefront price matches proposed value {proposal.proposed_value}.",
                    ),
                )

            followup_scan = self.inspection_service.run_inspection(
                request=ScanCreateRequest(sku=proposal.sku, correlation_id=f"reinspect-{uuid.uuid4()}"),
                trusted_actor=trusted_actor,
            )
        else:
            # Mutation did not take effect on storefront
            with atomic_transaction(self.session):
                proposal.execution_status = ExecutionStatus.FAILED.value
                proposal.updated_at = now

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=proposal.merchant_id,
                        actor_type=trusted_actor.actor_type,
                        actor_id=trusted_actor.actor_id,
                        action="CORRECTION_RECONCILED",
                        entity_type="correction_proposal",
                        entity_id=str(proposal.id),
                        approval_id=str(proposal.id),
                        correlation_id=correlation_id,
                        before_state=ExecutionStatus.RECONCILIATION_REQUIRED.value,
                        after_state=ExecutionStatus.FAILED.value,
                        details=f"Reconciliation confirmed storefront price ({current_storefront.price}) did not update to {proposal.proposed_value}.",
                    ),
                )

        return CorrectionProposalResponse.from_orm_model(proposal), followup_scan
