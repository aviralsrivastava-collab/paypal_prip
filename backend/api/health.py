from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.health import HealthResponse
from backend.services.health import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Health check endpoint verifying system responsiveness and database connectivity.
    """
    return HealthService.check_health(db)


@router.get("/live")
def get_liveness():
    """
    Liveness probe verifying the application process is running.
    """
    return {"status": "alive"}


@router.get("/ready")
def get_readiness(db: Session = Depends(get_db)):
    """
    Readiness probe verifying database connectivity and essential dependencies.
    """
    report = HealthService.check_health(db)
    if report.status != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready. System status: {report.status}",
        )
    db_dep = report.dependencies.get("database") if report.dependencies else None
    return {"status": "ready", "database": db_dep}

