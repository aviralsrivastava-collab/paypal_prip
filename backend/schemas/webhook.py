import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class WebhookEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paypal_event_id: str
    event_type: str
    resource_type: str
    status: str
    summary: Optional[str] = None
    created_at: datetime.datetime


class WebhookSimulationRequest(BaseModel):
    event_type: str = Field(..., description="e.g. PAYMENT.CAPTURE.COMPLETED")
    paypal_event_id: Optional[str] = None
    resource: Dict[str, Any] = Field(default_factory=dict)
