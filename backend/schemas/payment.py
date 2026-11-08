import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CapturePaymentRequest(BaseModel):
    order_id: str = Field(..., description="Local order_id or PayPal order_id")
    idempotency_key: Optional[str] = None
    simulate_timeout: bool = False
    simulate_decline: bool = False


class CapturePaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    capture_id: Optional[str] = None
    order_id: str
    paypal_order_id: Optional[str] = None
    status: str
    amount: Decimal
    currency: str
    fee_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    reconciliation_status: str
    error_message: Optional[str] = None
    created_at: datetime.datetime


class ReconcilePaymentRequest(BaseModel):
    order_id: str = Field(..., description="Local order_id or PayPal order_id")


class ReconcilePaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    paypal_order_id: Optional[str] = None
    order_status: str
    payment_status: str
    reconciliation_status: str
    message: str
