from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StateUpdateRequest(BaseModel):
    value: str = Field(..., max_length=255)
    expected_version: int = Field(..., ge=1)
    correlation_id: str = Field(..., max_length=100)
    actor_id: Optional[str] = Field(default=None, max_length=100)
    merchant_id: Optional[str] = Field(default=None, max_length=100)
    idempotency_key: Optional[str] = None


class StateResponse(BaseModel):
    id: int
    key: str
    value: str
    version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
