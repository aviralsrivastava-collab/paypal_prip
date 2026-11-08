import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StuckWebhookEventResponse(BaseModel):
    """
    Safe operational view of a stuck, retryable, or dead-letter webhook event.
    Explicitly omits sensitive raw_payload data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    paypal_event_id: str
    event_type: str
    resource_type: str
    status: str
    attempt_count: int
    max_attempts: int
    error_category: Optional[str] = None
    last_error: Optional[str] = None
    last_attempt_at: Optional[datetime.datetime] = None
    next_retry_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime


class ReplayWebhookRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Operator reason for requesting replay")


class ReplayWebhookResponse(BaseModel):
    id: int
    paypal_event_id: str
    status: str
    message: str
    replayed_at: datetime.datetime


class ReconciliationRecordResponse(BaseModel):
    """
    Safe operational record of a completed reconciliation inquiry.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    outcome: str
    previous_payment_status: str
    new_payment_status: str
    provider_status: str
    details: Optional[str] = None
    actor_id: str
    actor_type: str
    reconciled_at: datetime.datetime


class TriggerReconciliationRequest(BaseModel):
    order_id: Optional[str] = Field(default=None, description="Specific order_id to reconcile. If omitted, reconciles all pending.")


class TriggerReconciliationResponse(BaseModel):
    reconciled_count: int
    results: List[Dict[str, Any]]


class WorkerHeartbeatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    worker_id: str
    worker_type: str
    status: str
    last_heartbeat_at: datetime.datetime
    last_successful_run_at: Optional[datetime.datetime] = None
    age_seconds: Optional[float] = None


class OperationsOverviewResponse(BaseModel):
    """
    High-level operational dashboard overview.
    """

    system_status: str  # "HEALTHY", "DELAYED", "REQUIRES_ATTENTION", "DEAD_LETTERED", "RECONCILIATION_REQUIRED"
    webhook_counts: Dict[str, int]
    dead_letter_count: int
    retryable_failure_count: int
    pending_reconciliations_count: int
    reconciliations_completed_count: int
    active_workers_count: int
    stale_workers_count: int
    workers: List[WorkerHeartbeatResponse]
    recent_reconciliations: List[ReconciliationRecordResponse]
    stuck_webhooks: List[StuckWebhookEventResponse]
