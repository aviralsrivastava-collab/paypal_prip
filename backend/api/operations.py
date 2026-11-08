import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.metrics import get_metrics_collector
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_merchant_access,
)
from backend.repositories.reconciliation import PaymentReconciliationRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository
from backend.schemas.checkout import OrderResponse
from backend.schemas.operations import (
    OperationsOverviewResponse,
    ReconciliationRecordResponse,
    ReplayWebhookRequest,
    ReplayWebhookResponse,
    StuckWebhookEventResponse,
    TriggerReconciliationRequest,
    TriggerReconciliationResponse,
    WorkerHeartbeatResponse,
)
from backend.services.payment import PaymentService
from backend.services.webhook_worker import WebhookWorkerService

router = APIRouter(prefix="/api/operations", tags=["Operations"])


def is_platform_admin(actor: AuthenticatedActor) -> bool:
    """Returns True if actor holds platform-wide superadmin authorization."""
    return actor.role in {"superadmin", "system_admin"}


def require_operator_role(actor: AuthenticatedActor) -> AuthenticatedActor:
    """Verifies caller has operator or administrative permissions."""
    if actor.role not in {"demo_operator", "merchant_admin", "superadmin", "system_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Actor '{actor.actor_id}' with role '{actor.role}' is not authorized to perform administrative recovery actions.",
        )
    return actor


def get_actor_merchant_scope(actor: AuthenticatedActor) -> Optional[str]:
    """Returns None for platform superadmins (global visibility), or actor.merchant_id for tenant operators."""
    if is_platform_admin(actor):
        return None
    return actor.merchant_id


@router.get("/overview", response_model=OperationsOverviewResponse)
def get_operations_overview(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> OperationsOverviewResponse:
    """
    Returns consolidated operational health, queue depths, worker heartbeats, and alert states.
    Enforces multi-merchant tenant boundary: merchant admins see strictly their tenant metrics.
    """
    require_operator_role(current_actor)
    merchant_scope = get_actor_merchant_scope(current_actor)

    now = datetime.datetime.now(datetime.timezone.utc)
    wh_repo = WebhookEventRepository(db)
    rec_repo = PaymentReconciliationRepository(db)
    hb_repo = WorkerHeartbeatRepository(db)

    # 1. Webhook metrics (scoped by merchant)
    wh_counts = wh_repo.get_counts_by_status(merchant_id=merchant_scope)
    dead_letter_count = wh_counts.get("DEAD_LETTER", 0)
    retryable_failure_count = wh_counts.get("RETRYABLE_FAILURE", 0)
    stuck_events = wh_repo.list_failed_or_stuck_events(limit=20, merchant_id=merchant_scope)

    # 2. Reconciliation metrics (scoped by merchant)
    pending_orders = rec_repo.list_orders_requiring_reconciliation(limit=50, merchant_id=merchant_scope)
    pending_reconciliations_count = len(pending_orders)
    reconciliations_history = rec_repo.list_history(limit=20, merchant_id=merchant_scope)
    reconciliation_counts = rec_repo.get_counts(merchant_id=merchant_scope)
    completed_reconciliations = sum(reconciliation_counts.values())

    # 3. Worker heartbeats
    heartbeats = hb_repo.list_heartbeats()
    active_workers = 0
    stale_workers = 0
    worker_responses = []

    for hb in heartbeats:
        hb_time = hb.last_heartbeat_at
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=datetime.timezone.utc)
        age_sec = (now - hb_time).total_seconds()
        is_stale = age_sec > 120.0
        if is_stale:
            stale_workers += 1
            effective_status = "STALE"
        else:
            active_workers += 1
            effective_status = hb.status

        worker_responses.append(
            WorkerHeartbeatResponse(
                id=hb.id,
                worker_id=hb.worker_id,
                worker_type=hb.worker_type,
                status=effective_status,
                last_heartbeat_at=hb.last_heartbeat_at,
                last_successful_run_at=hb.last_successful_run_at,
                age_seconds=round(age_sec, 1),
            )
        )

    # 4. Classify overall system status
    if dead_letter_count > 0:
        system_status = "DEAD_LETTERED"
    elif pending_reconciliations_count > 0:
        system_status = "RECONCILIATION_REQUIRED"
    elif retryable_failure_count > 0:
        system_status = "DELAYED"
    elif stale_workers > 0:
        system_status = "REQUIRES_ATTENTION"
    else:
        system_status = "HEALTHY"

    return OperationsOverviewResponse(
        system_status=system_status,
        webhook_counts=wh_counts,
        dead_letter_count=dead_letter_count,
        retryable_failure_count=retryable_failure_count,
        pending_reconciliations_count=pending_reconciliations_count,
        reconciliations_completed_count=completed_reconciliations,
        active_workers_count=active_workers,
        stale_workers_count=stale_workers,
        workers=worker_responses,
        recent_reconciliations=[
            ReconciliationRecordResponse.model_validate(r) for r in reconciliations_history
        ],
        stuck_webhooks=[
            StuckWebhookEventResponse.model_validate(e) for e in stuck_events
        ],
    )


@router.get("/webhooks/stuck", response_model=List[StuckWebhookEventResponse])
def list_stuck_webhooks(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[StuckWebhookEventResponse]:
    """
    Lists failed, stuck, retryable, or dead-lettered webhook events without sensitive payloads.
    Scoped to caller's merchant tenant unless caller has platform superadmin role.
    """
    require_operator_role(current_actor)
    merchant_scope = get_actor_merchant_scope(current_actor)
    wh_repo = WebhookEventRepository(db)
    events = wh_repo.list_failed_or_stuck_events(limit=50, merchant_id=merchant_scope)
    return [StuckWebhookEventResponse.model_validate(e) for e in events]


@router.post("/webhooks/{event_id}/replay", response_model=ReplayWebhookResponse)
def replay_webhook_event(
    event_id: int,
    request: ReplayWebhookRequest = ReplayWebhookRequest(),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ReplayWebhookResponse:
    """
    Authorized operator endpoint to replay a dead-letter or failed webhook event.
    Enforces tenant ownership before triggering replay.
    """
    require_operator_role(current_actor)

    wh_repo = WebhookEventRepository(db)
    event_record = wh_repo.get_by_id(event_id)
    if not event_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook event #{event_id} not found.",
        )

    if not is_platform_admin(current_actor):
        require_merchant_access(current_actor, event_record.merchant_id)

    worker = WebhookWorkerService(db)
    try:
        event = worker.replay_event(
            event_id=event_id,
            actor_id=current_actor.actor_id,
            actor_type=current_actor.actor_type,
        )
        return ReplayWebhookResponse(
            id=event.id,
            paypal_event_id=event.paypal_event_id,
            status=event.status,
            message=f"Event replayed with resulting status '{event.status}'.",
            replayed_at=datetime.datetime.now(datetime.timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/reconciliations/pending", response_model=List[OrderResponse])
def list_pending_reconciliations(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[OrderResponse]:
    """
    Lists orders with ambiguous capture outcomes (UNKNOWN) requiring authoritative reconciliation.
    Scoped to caller's merchant tenant unless caller has platform superadmin role.
    """
    require_operator_role(current_actor)
    merchant_scope = get_actor_merchant_scope(current_actor)
    rec_repo = PaymentReconciliationRepository(db)
    orders = rec_repo.list_orders_requiring_reconciliation(limit=50, merchant_id=merchant_scope)
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/reconciliations/history", response_model=List[ReconciliationRecordResponse])
def list_reconciliation_history(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[ReconciliationRecordResponse]:
    """
    Lists historical reconciliation outcomes and audit details.
    Scoped to caller's merchant tenant unless caller has platform superadmin role.
    """
    require_operator_role(current_actor)
    merchant_scope = get_actor_merchant_scope(current_actor)
    rec_repo = PaymentReconciliationRepository(db)
    records = rec_repo.list_history(limit=50, merchant_id=merchant_scope)
    return [ReconciliationRecordResponse.model_validate(r) for r in records]


@router.post("/reconciliations/trigger", response_model=TriggerReconciliationResponse)
def trigger_reconciliation(
    request: TriggerReconciliationRequest = TriggerReconciliationRequest(),
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> TriggerReconciliationResponse:
    """
    Trigger controlled authoritative reconciliation for a specific order or all pending orders.
    Enforces multi-merchant tenant ownership.
    """
    require_operator_role(current_actor)

    service = PaymentService(db)
    results: List[Dict[str, Any]] = []

    if request.order_id:
        order = service.order_repo.get_by_order_id(request.order_id)
        if not order:
            order = service.order_repo.get_by_paypal_order_id(request.order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{request.order_id}' not found.",
            )
        if not is_platform_admin(current_actor):
            require_merchant_access(current_actor, order.merchant_id)

        try:
            res = service.reconcile_payment(
                order_id=order.order_id,
                actor_id=current_actor.actor_id,
                actor_type=current_actor.actor_type,
                trusted_actor=current_actor,
            )
            results.append({
                "order_id": res.order_id,
                "order_status": res.order_status,
                "payment_status": res.payment_status,
                "message": res.message,
            })
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    else:
        merchant_scope = get_actor_merchant_scope(current_actor)
        batch_results = service.reconcile_all_pending(
            actor_id=current_actor.actor_id,
            actor_type=current_actor.actor_type,
            merchant_id=merchant_scope,
            trusted_actor=current_actor,
        )
        for b in batch_results:
            results.append({
                "order_id": b.order_id,
                "order_status": b.order_status,
                "payment_status": b.payment_status,
                "message": b.message,
            })

    return TriggerReconciliationResponse(
        reconciled_count=len(results),
        results=results,
    )


@router.get("/workers", response_model=List[WorkerHeartbeatResponse])
def list_workers(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> List[WorkerHeartbeatResponse]:
    """
    Lists registered background workers, heartbeat freshness, and execution status.
    """
    require_operator_role(current_actor)
    now = datetime.datetime.now(datetime.timezone.utc)
    hb_repo = WorkerHeartbeatRepository(db)
    heartbeats = hb_repo.list_heartbeats()
    results = []

    for hb in heartbeats:
        hb_time = hb.last_heartbeat_at
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=datetime.timezone.utc)
        age_sec = (now - hb_time).total_seconds()
        effective_status = "STALE" if age_sec > 120.0 else hb.status

        results.append(
            WorkerHeartbeatResponse(
                id=hb.id,
                worker_id=hb.worker_id,
                worker_type=hb.worker_type,
                status=effective_status,
                last_heartbeat_at=hb.last_heartbeat_at,
                last_successful_run_at=hb.last_successful_run_at,
                age_seconds=round(age_sec, 1),
            )
        )
    return results


@router.get("/metrics")
def get_operations_metrics(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
) -> Dict[str, Any]:
    """Returns application operational metrics collected in-process."""
    require_operator_role(current_actor)
    collector = get_metrics_collector()
    return {
        "status": "healthy",
        "metrics": collector.get_metrics(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
