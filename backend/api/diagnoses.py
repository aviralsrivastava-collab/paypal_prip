from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_merchant_access,
)
from backend.integrations.ai.base import (
    AIProviderOutageError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIStructuredOutputError,
)
from backend.policies.diagnosis_validator import DiagnosisValidationError
from backend.schemas.diagnosis import DiagnosisCreateRequest, DiagnosisResponse
from backend.services.diagnosis import DiagnosisService

router = APIRouter(prefix="/api/diagnoses", tags=["AI Diagnosis"])


@router.post(
    "/scan/{scan_id}",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request advisory AI diagnosis for an inspection",
)
def create_diagnosis(
    scan_id: int,
    request: Optional[DiagnosisCreateRequest] = None,
    simulated_failure: Optional[str] = Query(None, description="Fault injection hook for automated testing"),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> DiagnosisResponse:
    """
    Generates an evidence-grounded, explainable AI diagnosis analyzing inspection discrepancies.
    Results are strictly advisory and provide no authority to mutate domain data or payments.
    Enforces multi-merchant tenant ownership.
    """
    service = DiagnosisService(db)
    scan = service.scan_repo.get_by_id(scan_id)
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection scan with ID {scan_id} does not exist.",
        )
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else get_current_actor()
    require_merchant_access(actor, scan.merchant_id)

    cid = request.correlation_id if request else None
    try:
        return service.diagnose_scan(
            scan_id=scan_id,
            trusted_actor=actor,
            correlation_id=cid,
            simulated_failure=simulated_failure,
        )
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex))
    except DiagnosisValidationError as ex:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ex))
    except AIProviderTimeoutError as ex:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(ex))
    except AIProviderRateLimitError as ex:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(ex))
    except AIProviderOutageError as ex:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(ex))
    except AIStructuredOutputError as ex:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(ex))


@router.get(
    "/{diagnosis_id}",
    response_model=DiagnosisResponse,
    summary="Retrieve diagnosis by ID",
)
def get_diagnosis(
    diagnosis_id: int,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> DiagnosisResponse:
    """
    Retrieves an existing advisory AI diagnosis record by ID.
    Enforces server-side authentication and multi-merchant tenant boundary.
    """
    service = DiagnosisService(db)
    diag = service.diagnosis_repo.get_by_id(diagnosis_id)
    if not diag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis with ID {diagnosis_id} not found.",
        )
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else get_current_actor()
    require_merchant_access(actor, diag.merchant_id)
    return DiagnosisResponse.from_orm_model(diag)


@router.get(
    "/scan/{scan_id}",
    response_model=List[DiagnosisResponse],
    summary="List diagnoses for an inspection scan",
)
def list_scan_diagnoses(
    scan_id: int,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[DiagnosisResponse]:
    """
    Returns all historical diagnoses associated with a given storefront scan ID.
    Enforces server-side authentication and multi-merchant tenant boundary.
    """
    service = DiagnosisService(db)
    scan = service.scan_repo.get_by_id(scan_id)
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection scan with ID {scan_id} does not exist.",
        )
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else get_current_actor()
    require_merchant_access(actor, scan.merchant_id)
    return service.list_diagnoses_by_scan(scan_id, current_actor=actor)
