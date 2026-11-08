from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditEventCreate(BaseModel):
    merchant_id: Optional[str] = Field(default=None, max_length=100)
    actor_type: str = Field(..., max_length=50)
    actor_id: str = Field(..., max_length=100)
    action: str = Field(..., max_length=100)
    entity_type: str = Field(..., max_length=100)
    entity_id: str = Field(..., max_length=100)
    approval_id: Optional[str] = Field(default=None, max_length=100)
    correlation_id: str = Field(..., max_length=100)
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    details: Optional[str] = None


class AuditEventResponse(BaseModel):
    id: int
    merchant_id: str = Field(..., max_length=100)
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    approval_id: Optional[str] = None
    correlation_id: str
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
