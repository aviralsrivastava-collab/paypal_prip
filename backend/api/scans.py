from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_merchant_access,
)
from backend.schemas.scan import (
    EvidenceItemResponse,
    ScanCreateRequest,
    ScanDetailResponse,
    ScanSummaryResponse,
)
from backend.services.inspection import IdempotencyConflictError, InspectionService

router = APIRouter(prefix="/api/scans", tags=["Storefront Inspections"])


@router.post("", response_model=ScanDetailResponse, status_code=status.HTTP_201_CREATED, summary="Trigger storefront inspection")
def trigger_scan(
    request: ScanCreateRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ScanDetailResponse:
    """
    Initiates a deterministic inspection comparing merchant catalog ground truth
    against controlled storefront observations. Produces structured evidence and
    assigns an outcome in the mandatory 4-state model.
    """
    service = InspectionService(db)
    raw_key = idempotency_key if isinstance(idempotency_key, str) else request.idempotency_key
    try:
        return service.run_inspection(
            request=request,
            trusted_actor=current_actor,
            idempotency_key=raw_key,
        )
    except IdempotencyConflictError as ex:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ex))
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex))


@router.get("/{scan_id}", response_model=ScanDetailResponse, summary="Get inspection scan detail")
def get_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_current_actor),
) -> ScanDetailResponse:
    """
    Returns scan results with comparability metrics and structured evidence items.
    """
    service = InspectionService(db)
    scan = service.get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection scan with ID {scan_id} not found.",
        )
    if isinstance(current_actor, AuthenticatedActor):
        require_merchant_access(current_actor, scan.merchant_id)
    return scan


@router.get("/{scan_id}/evidence", response_model=List[EvidenceItemResponse], summary="Get inspection evidence")
def get_scan_evidence(
    scan_id: int,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_current_actor),
) -> List[EvidenceItemResponse]:
    """
    Returns the immutable structured evidence items produced by the specified scan.
    """
    service = InspectionService(db)
    # Verify scan exists
    scan = service.get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection scan with ID {scan_id} not found.",
        )
    if isinstance(current_actor, AuthenticatedActor):
        require_merchant_access(current_actor, scan.merchant_id)
    return service.get_scan_evidence(scan_id)


@router.get("/product/{sku}", response_model=List[ScanSummaryResponse], summary="List inspection history for a SKU")
def list_product_scans(
    sku: str,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_current_actor),
) -> List[ScanSummaryResponse]:
    """
    Returns the historical inspection timeline for a given product SKU.
    """
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else None
    merchant_id = actor.merchant_id if actor else None
    service = InspectionService(db)
    scans = service.scan_repo.list_by_sku(sku, merchant_id=merchant_id)
    return [ScanSummaryResponse.from_orm_model(s) for s in scans]
