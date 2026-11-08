import datetime
import json
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.proposal import CorrectionProposal
from backend.policies.correction_policy import (
    ApprovalStatus,
    ExecutionStatus,
    PolicyValidationStatus,
)


class CorrectionProposalCreateRequest(BaseModel):
    scan_id: int
    sku: str = Field(..., max_length=50)
    proposal_type: str = "PRICE_SYNCHRONIZATION"
    proposed_value: Decimal
    currency: str = "USD"
    reason: str
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    expires_in_hours: int = 24


class CorrectionProposalApproveRequest(BaseModel):
    reason: Optional[str] = None
    expected_catalog_version: Optional[int] = None
    expected_storefront_version: Optional[int] = None


class CorrectionProposalRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory reason for rejecting proposal.")


class CorrectionProposalCancelRequest(BaseModel):
    reason: Optional[str] = None


class CorrectionProposalExecuteRequest(BaseModel):
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    simulate_timeout: bool = False
    simulate_storefront_error: bool = False


class CorrectionProposalReconcileRequest(BaseModel):
    correlation_id: Optional[str] = None


class CorrectionProposalResponse(BaseModel):
    id: int
    merchant_id: str = "merchant_default"
    scan_id: int
    diagnosis_id: Optional[int] = None
    product_id: int
    sku: str
    proposal_type: str
    current_value: Decimal
    proposed_value: Decimal
    currency: str
    reason: str
    supporting_evidence_ids: List[int]
    policy_validation_status: PolicyValidationStatus
    approval_status: ApprovalStatus
    execution_status: ExecutionStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
    expires_at: datetime.datetime
    created_by: str
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    executed_at: Optional[datetime.datetime] = None
    expected_catalog_version: int
    expected_storefront_version: int
    idempotency_key: Optional[str] = None
    execution_error: Optional[str] = None
    execution_correlation_id: Optional[str] = None
    is_expired: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, proposal: CorrectionProposal) -> "CorrectionProposalResponse":
        ev_ids: List[int] = []
        if proposal.supporting_evidence_ids:
            try:
                ev_ids = json.loads(proposal.supporting_evidence_ids)
            except Exception:
                ev_ids = []

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = proposal.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        is_expired = now >= expires

        return cls(
            id=proposal.id,
            merchant_id=getattr(proposal, "merchant_id", "merchant_default"),
            scan_id=proposal.scan_id,
            diagnosis_id=proposal.diagnosis_id,
            product_id=proposal.product_id,
            sku=proposal.sku,
            proposal_type=proposal.proposal_type,
            current_value=proposal.current_value,
            proposed_value=proposal.proposed_value,
            currency=proposal.currency,
            reason=proposal.reason,
            supporting_evidence_ids=ev_ids,
            policy_validation_status=PolicyValidationStatus(proposal.policy_validation_status),
            approval_status=ApprovalStatus(proposal.approval_status),
            execution_status=ExecutionStatus(proposal.execution_status),
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
            expires_at=proposal.expires_at,
            created_by=proposal.created_by,
            approved_by=proposal.approved_by,
            rejected_by=proposal.rejected_by,
            rejection_reason=proposal.rejection_reason,
            executed_at=proposal.executed_at,
            expected_catalog_version=proposal.expected_catalog_version,
            expected_storefront_version=proposal.expected_storefront_version,
            idempotency_key=proposal.idempotency_key,
            execution_error=proposal.execution_error,
            execution_correlation_id=proposal.execution_correlation_id,
            is_expired=is_expired,
        )


class ProposalHistoryItem(BaseModel):
    id: int
    action: str
    actor_id: str
    actor_type: str
    created_at: datetime.datetime
    details: Optional[str] = None
    before_state: Optional[str] = None
    after_state: Optional[str] = None


class CorrectionExecutionResponse(BaseModel):
    proposal: CorrectionProposalResponse
    followup_scan: Optional[Any] = None
