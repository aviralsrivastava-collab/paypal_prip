from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_merchant_access,
)
from backend.schemas.proposal import (
    CorrectionExecutionResponse,
    CorrectionProposalApproveRequest,
    CorrectionProposalCancelRequest,
    CorrectionProposalCreateRequest,
    CorrectionProposalExecuteRequest,
    CorrectionProposalReconcileRequest,
    CorrectionProposalRejectRequest,
    CorrectionProposalResponse,
    ProposalHistoryItem,
)
from backend.services.proposal import ProposalService
from backend.services.remediation import RemediationService

router = APIRouter(prefix="/api/corrections", tags=["Corrections & Remediation"])


@router.post(
    "/proposals",
    response_model=CorrectionProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new correction proposal",
)
def create_proposal(
    request: CorrectionProposalCreateRequest,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionProposalResponse:
    """
    Submits a new correction proposal for merchant review.
    Enforces deterministic policy validation, version pinning, and idempotency.
    """
    service = ProposalService(db)
    try:
        return service.create_proposal(request, current_actor)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "Idempotency conflict" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get(
    "/proposals",
    response_model=List[CorrectionProposalResponse],
    summary="List correction proposals",
)
def list_proposals(
    sku: Optional[str] = Query(None, description="Filter by product SKU"),
    approval_status: Optional[str] = Query(None, description="Filter by approval status"),
    execution_status: Optional[str] = Query(None, description="Filter by execution status"),
    db: Session = Depends(get_db),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
) -> List[CorrectionProposalResponse]:
    """Retrieves correction proposals with optional status, SKU, and tenant filtering."""
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else get_current_actor()
    merchant_id = actor.merchant_id if actor else None
    service = ProposalService(db)
    proposals = service.proposal_repo.list_proposals(
        sku=sku,
        approval_status=approval_status,
        execution_status=execution_status,
        merchant_id=merchant_id,
    )
    return [CorrectionProposalResponse.from_orm_model(p) for p in proposals]


@router.get(
    "/proposals/{proposal_id}",
    response_model=CorrectionProposalResponse,
    summary="Get correction proposal details",
)
def get_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
) -> CorrectionProposalResponse:
    """Retrieves full details for a correction proposal."""
    service = ProposalService(db)
    proposal_entity = service.proposal_repo.get_by_id(proposal_id)
    if not proposal_entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} not found.")
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else get_current_actor()
    require_merchant_access(actor, proposal_entity.merchant_id)
    proposal_res = service.get_proposal(proposal_id)
    if not proposal_res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} not found.")
    return proposal_res


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=CorrectionProposalResponse,
    summary="Approve a correction proposal",
)
def approve_proposal(
    proposal_id: int,
    request: Optional[CorrectionProposalApproveRequest] = None,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionProposalResponse:
    """
    Approves a pending proposal.
    Requires merchant operator authorization. AI agents cannot approve proposals.
    """
    service = ProposalService(db)
    proposal = service.proposal_repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} does not exist.")
    require_merchant_access(current_actor, proposal.merchant_id)
    try:
        return service.approve_proposal(proposal_id, current_actor, request)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=CorrectionProposalResponse,
    summary="Reject a correction proposal",
)
def reject_proposal(
    proposal_id: int,
    request: CorrectionProposalRejectRequest,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionProposalResponse:
    """
    Rejects a proposal with mandatory reason recording.
    Rejected proposals can never be executed.
    """
    service = ProposalService(db)
    proposal = service.proposal_repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} does not exist.")
    require_merchant_access(current_actor, proposal.merchant_id)
    try:
        return service.reject_proposal(proposal_id, current_actor, request)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/proposals/{proposal_id}/cancel",
    response_model=CorrectionProposalResponse,
    summary="Cancel a correction proposal",
)
def cancel_proposal(
    proposal_id: int,
    request: Optional[CorrectionProposalCancelRequest] = None,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionProposalResponse:
    """Cancels a pending proposal."""
    service = ProposalService(db)
    proposal = service.proposal_repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} does not exist.")
    require_merchant_access(current_actor, proposal.merchant_id)
    try:
        reason = request.reason if request else None
        return service.cancel_proposal(proposal_id, current_actor, reason)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/proposals/{proposal_id}/execute",
    response_model=CorrectionExecutionResponse,
    summary="Execute an approved correction proposal",
)
def execute_proposal(
    proposal_id: int,
    request: Optional[CorrectionProposalExecuteRequest] = None,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionExecutionResponse:
    """
    Executes an approved proposal against the controlled storefront.
    External mutations occur outside open transactions.
    Reinspection verifies post-remediation alignment.
    """
    service = RemediationService(db)
    proposal = service.proposal_repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} does not exist.")
    require_merchant_access(current_actor, proposal.merchant_id)
    try:
        proposal_res, followup_scan = service.execute_correction(proposal_id, current_actor, request)
        return CorrectionExecutionResponse(proposal=proposal_res, followup_scan=followup_scan)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except RuntimeError as ex:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(ex))


@router.post(
    "/proposals/{proposal_id}/reconcile",
    response_model=CorrectionExecutionResponse,
    summary="Reconcile a proposal requiring reconciliation",
)
def reconcile_proposal(
    proposal_id: int,
    request: Optional[CorrectionProposalReconcileRequest] = None,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CorrectionExecutionResponse:
    """Reconciles an uncertain external outcome by verifying actual storefront state."""
    service = RemediationService(db)
    proposal = service.proposal_repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal #{proposal_id} does not exist.")
    require_merchant_access(current_actor, proposal.merchant_id)
    try:
        proposal_res, followup_scan = service.reconcile_proposal(proposal_id, current_actor, request)
        return CorrectionExecutionResponse(proposal=proposal_res, followup_scan=followup_scan)
    except PermissionError as ex:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(ex))
    except ValueError as ex:
        msg = str(ex)
        if "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get(
    "/proposals/{proposal_id}/history",
    response_model=List[ProposalHistoryItem],
    summary="Retrieve audit trail for a proposal",
)
def get_proposal_history(
    proposal_id: int,
    db: Session = Depends(get_db),
) -> List[ProposalHistoryItem]:
    """Retrieves the complete append-only audit trail for a proposal."""
    service = ProposalService(db)
    return service.get_proposal_history(proposal_id)
