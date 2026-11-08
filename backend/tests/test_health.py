from sqlalchemy.orm import Session

from backend.api.health import get_health
from backend.schemas.health import HealthResponse
from backend.services.health import HealthService


def test_health_route_handler_success(db_session: Session):
    """
    Verifies that the /api/health route handler returns a valid HealthResponse
    with database_connected=True and status='healthy'.
    """
    response: HealthResponse = get_health(db=db_session)
    assert response.status == "healthy"
    assert response.database_connected is True
    assert response.version == "0.1.0"
    assert response.environment in ["development", "sandbox"]
    assert response.timestamp is not None


def test_health_service_database_connectivity(db_session: Session):
    """
    Direct service verification of database connectivity check.
    """
    health = HealthService.check_health(db_session)
    assert health.status == "healthy"
    assert health.database_connected is True


def test_health_service_degraded_on_database_failure():
    """
    Verifies that when database connectivity fails, health status degrades honestly.
    """
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    mock_session.execute.side_effect = Exception("Database connection refused")

    health = HealthService.check_health(mock_session)
    assert health.status == "degraded"
    assert health.database_connected is False
