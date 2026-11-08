import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PreflightCheckRequest(BaseModel):
    sku: str = Field(..., max_length=50)


class PreflightCheckResponse(BaseModel):
    passed: bool
    sku: str
    catalog_price: Optional[Decimal] = None
    storefront_price: Optional[Decimal] = None
    currency: Optional[str] = None
    scan_id: Optional[int] = None
    scan_state: Optional[str] = None
    blocking_reasons: List[str] = Field(default_factory=list)
    message: str


class CreateOrderRequest(BaseModel):
    sku: str = Field(..., max_length=50)
    quantity: int = Field(default=1, ge=1, le=10)
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None
    idempotency_key: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: str
    paypal_order_id: Optional[str] = None
    sku: str
    unit_price: Decimal
    currency: str
    quantity: int
    total_amount: Decimal
    order_status: str
    payment_status: str
    preflight_passed: bool
    approve_url: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
