from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Application health status (e.g. 'healthy', 'degraded')")
    environment: str = Field(..., description="Operating environment (development/sandbox/production)")
    version: str = Field(..., description="Service version")
    database_connected: bool = Field(..., description="Database connectivity confirmation")
    timestamp: datetime = Field(..., description="UTC verification timestamp")

    # Structured operational visibility
    dependencies: Optional[Dict[str, Any]] = Field(
        default=None, description="Granular health and latency status of underlying dependencies"
    )
    worker_health: Optional[Dict[str, Any]] = Field(
        default=None, description="Background worker status, heartbeat timestamps and staleness"
    )
    operational_metrics: Optional[Dict[str, Any]] = Field(
        default=None, description="Event queue lengths, dead letter counts, and reconciliation backlogs"
    )
