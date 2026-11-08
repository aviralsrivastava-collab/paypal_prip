import datetime
import json
import logging
import random
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.metrics import get_metrics_collector
from backend.models.webhook import WebhookEvent
from backend.policies.checkout_policy import (
    OrderStatus,
    PaymentStatus,
    ReservationStatus,
    WebhookEventStatus,
)
from backend.repositories.order import OrderRepository
from backend.repositories.payment_capture import PaymentCaptureRepository
from backend.repositories.reservation import ReservationRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository
from backend.schemas.audit import AuditEventCreate
from backend.services.audit import AuditService

logger = logging.getLogger(__name__)


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 300.0,
    jitter_factor: float = 0.25,
) -> float:
    """
    Computes bounded exponential backoff with jitter.
    Formula: min(max_delay, base_delay * 2^(attempt-1)) + Uniform(-jitter, +jitter)
    """
    exp = min(max(0, attempt - 1), 10)
    delay = min(max_delay, base_delay * (2 ** exp))
    jitter = random.uniform(-jitter_factor * delay, jitter_factor * delay)
    return float(max(0.1, round(delay + jitter, 2)))


class WebhookWorkerService:
    """
    Background worker service for reliable, durable processing of PayPal webhook events.
    Enforces atomic lease claiming, worker crash recovery, exponential backoff with jitter,
    dead-letter isolation, and idempotent operator replay.
    """

    def __init__(
        self,
        session: Session,
        worker_id: Optional[str] = None,
    ) -> None:
        self.session = session
        self.worker_id = worker_id or f"wh_worker_{uuid.uuid4().hex[:8]}"
        self.webhook_repo = WebhookEventRepository(session)
        self.order_repo = OrderRepository(session)
        self.capture_repo = PaymentCaptureRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.heartbeat_repo = WorkerHeartbeatRepository(session)
        self.metrics = get_metrics_collector()

    def send_heartbeat(self, status: str = "ACTIVE", successful_run: bool = False) -> None:
        """Persists worker heartbeat to database."""
        with atomic_transaction(self.session):
            metrics_summary = json.dumps(self.metrics.get_metrics())
            self.heartbeat_repo.upsert_heartbeat(
                worker_id=self.worker_id,
                worker_type="WEBHOOK_PROCESSOR",
                status=status,
                metrics_json=metrics_summary,
                successful_run=successful_run,
            )

    def process_event(self, event: WebhookEvent) -> bool:
        """
        Executes business transitions for a claimed webhook event.
        Returns True on success; on failure schedules retry or moves to dead letter.
        """
        correlation_id = f"wh_exec_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc)

        try:
            # 1. Parse raw payload safely
            try:
                payload = json.loads(event.raw_payload)
            except Exception as exc:
                raise ValueError(f"Malformed JSON payload: {exc}") from exc

            event_type = payload.get("event_type") or event.event_type
            resource = payload.get("resource", {})
            initial_event_merchant = getattr(event, "merchant_id", None)
            resolved_merchant_id = (
                initial_event_merchant
                if initial_event_merchant and initial_event_merchant not in ("merchant_default", "QUARANTINED_ORPHAN")
                else "platform_system"
            )

            # 2. Execute domain transitions inside atomic transaction
            with atomic_transaction(self.session):
                order = None
                if event_type == "CHECKOUT.ORDER.APPROVED":
                    paypal_order_id = resource.get("id")
                    if paypal_order_id:
                        order = self.order_repo.get_by_paypal_order_id(paypal_order_id)
                        if order:
                            resolved_merchant_id = order.merchant_id
                            event.merchant_id = order.merchant_id
                            if order.order_status == OrderStatus.CREATED.value:
                                order.order_status = OrderStatus.APPROVED.value
                                AuditService.log_event(
                                    self.session,
                                    AuditEventCreate(
                                        merchant_id=order.merchant_id,
                                        action="ORDER_APPROVED_BY_WEBHOOK",
                                        entity_type="Order",
                                        entity_id=order.order_id,
                                        approval_id=None,
                                        actor_type="PAYPAL_WEBHOOK",
                                        actor_id=event.paypal_event_id,
                                        correlation_id=correlation_id,
                                        before_state=OrderStatus.CREATED.value,
                                        after_state=OrderStatus.APPROVED.value,
                                        details=f"Order {order.order_id} approved via webhook notification.",
                                    ),
                                )

                elif event_type == "PAYMENT.CAPTURE.COMPLETED":
                    custom_id = resource.get("custom_id")
                    if custom_id:
                        order = self.order_repo.get_by_order_id(custom_id)
                    if not order:
                        order_id_ref = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
                        if order_id_ref:
                            order = self.order_repo.get_by_paypal_order_id(order_id_ref)

                    if order:
                        resolved_merchant_id = order.merchant_id
                        event.merchant_id = order.merchant_id
                        if order.payment_status != PaymentStatus.CAPTURED.value:
                            order.payment_status = PaymentStatus.CAPTURED.value
                            order.order_status = OrderStatus.COMPLETED.value

                            # Commit demo inventory reservation
                            reservation = self.reservation_repo.get_by_order_id(order.id)
                            if reservation:
                                reservation.status = ReservationStatus.COMMITTED.value

                            AuditService.log_event(
                                self.session,
                                AuditEventCreate(
                                    merchant_id=order.merchant_id,
                                    action="PAYMENT_CAPTURED_BY_WEBHOOK",
                                    entity_type="Order",
                                    entity_id=order.order_id,
                                    approval_id=None,
                                    actor_type="PAYPAL_WEBHOOK",
                                    actor_id=event.paypal_event_id,
                                    correlation_id=correlation_id,
                                    before_state=PaymentStatus.PENDING.value,
                                    after_state=PaymentStatus.CAPTURED.value,
                                    details=f"Payment captured via webhook for order {order.order_id}.",
                                ),
                            )

                elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
                    custom_id = resource.get("custom_id")
                    order = self.order_repo.get_by_order_id(custom_id) if custom_id else None
                    if order:
                        resolved_merchant_id = order.merchant_id
                        event.merchant_id = order.merchant_id
                        if order.payment_status != PaymentStatus.FAILED.value:
                            order.payment_status = PaymentStatus.FAILED.value
                            order.order_status = OrderStatus.FAILED.value

                            # Release reservation
                            reservation = self.reservation_repo.get_by_order_id(order.id)
                            if reservation:
                                reservation.status = ReservationStatus.RELEASED.value

                            AuditService.log_event(
                                self.session,
                                AuditEventCreate(
                                    merchant_id=order.merchant_id,
                                    action="PAYMENT_DECLINED_BY_WEBHOOK",
                                    entity_type="Order",
                                    entity_id=order.order_id,
                                    approval_id=None,
                                    actor_type="PAYPAL_WEBHOOK",
                                    actor_id=event.paypal_event_id,
                                    correlation_id=correlation_id,
                                    before_state=PaymentStatus.PENDING.value,
                                    after_state=PaymentStatus.FAILED.value,
                                    details=f"Payment declined via webhook for order {order.order_id}.",
                                ),
                            )

                # 3. Mark event PROCESSED and record audit log
                event.status = WebhookEventStatus.PROCESSED.value
                event.processed_at = now
                event.locked_by = None
                event.processing_lease_expires_at = None
                event.error_category = None
                event.last_error = None

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=resolved_merchant_id,
                        action="WEBHOOK_PROCESSED",
                        entity_type="WebhookEvent",
                        entity_id=event.paypal_event_id,
                        approval_id=None,
                        actor_type="WORKER",
                        actor_id=self.worker_id,
                        correlation_id=correlation_id,
                        before_state=WebhookEventStatus.PROCESSING.value,
                        after_state=WebhookEventStatus.PROCESSED.value,
                        details=f"Successfully processed webhook event {event.paypal_event_id} ({event_type})",
                    ),
                )

            self.metrics.increment("webhook_events.processed")
            return True

        except Exception as exc:
            # Determine error category
            err_msg = str(exc)
            category = "UNHANDLED_EXCEPTION"
            if "Malformed JSON" in err_msg or "Missing" in err_msg:
                category = "INVALID_PAYLOAD"
            elif "not found" in err_msg.lower():
                category = "ORDER_NOT_FOUND"
            elif "timeout" in err_msg.lower() or "network" in err_msg.lower():
                category = "NETWORK_ERROR"

            logger.error(
                f"Error processing webhook event {event.id} ({event.paypal_event_id}) [{category}]: {err_msg}"
            )

            with atomic_transaction(self.session):
                if event.attempt_count >= event.max_attempts:
                    # Move to DEAD_LETTER
                    event.status = WebhookEventStatus.DEAD_LETTER.value
                    event.locked_by = None
                    event.processing_lease_expires_at = None
                    event.error_category = category
                    event.last_error = err_msg

                    worker_merchant = (
                        event.merchant_id
                        if getattr(event, "merchant_id", None) and event.merchant_id not in ("merchant_default", "QUARANTINED_ORPHAN")
                        else "platform_system"
                    )
                    AuditService.log_event(
                        self.session,
                        AuditEventCreate(
                            merchant_id=worker_merchant,
                            action="WEBHOOK_DEAD_LETTERED",
                            entity_type="WebhookEvent",
                            entity_id=event.paypal_event_id,
                            approval_id=None,
                            actor_type="WORKER",
                            actor_id=self.worker_id,
                            correlation_id=correlation_id,
                            before_state=WebhookEventStatus.PROCESSING.value,
                            after_state=WebhookEventStatus.DEAD_LETTER.value,
                            details=f"Event {event.paypal_event_id} moved to DEAD_LETTER after {event.attempt_count} failed attempts. Category: {category}",
                        ),
                    )
                    self.metrics.increment("webhook_events.dead_letter")
                else:
                    # Schedule retry with exponential backoff and jitter
                    backoff_secs = calculate_backoff(event.attempt_count)
                    event.status = WebhookEventStatus.RETRYABLE_FAILURE.value
                    event.next_retry_at = now + datetime.timedelta(seconds=backoff_secs)
                    event.locked_by = None
                    event.processing_lease_expires_at = None
                    event.error_category = category
                    event.last_error = err_msg

                    worker_merchant = (
                        event.merchant_id
                        if getattr(event, "merchant_id", None) and event.merchant_id not in ("merchant_default", "QUARANTINED_ORPHAN")
                        else "platform_system"
                    )
                    AuditService.log_event(
                        self.session,
                        AuditEventCreate(
                            merchant_id=worker_merchant,
                            action="WEBHOOK_PROCESSING_FAILED",
                            entity_type="WebhookEvent",
                            entity_id=event.paypal_event_id,
                            approval_id=None,
                            actor_type="WORKER",
                            actor_id=self.worker_id,
                            correlation_id=correlation_id,
                            before_state=WebhookEventStatus.PROCESSING.value,
                            after_state=WebhookEventStatus.RETRYABLE_FAILURE.value,
                            details=f"Attempt {event.attempt_count} failed ({category}). Retrying in {backoff_secs}s.",
                        ),
                    )
                    self.metrics.increment("webhook_events.retryable_failure")

            return False

    def tick(self, batch_size: int = 10, lease_seconds: int = 60) -> int:
        """
        Executes a worker iteration: discovers, claims, and processes pending/retryable events.
        Recovers expired leases automatically.
        """
        processed_count = 0
        self.send_heartbeat(status="ACTIVE")

        for _ in range(batch_size):
            # Atomic claim
            event = self.webhook_repo.claim_eligible_event(
                worker_id=self.worker_id,
                lease_seconds=lease_seconds,
            )
            if not event:
                break

            success = self.process_event(event)
            if success:
                processed_count += 1

        if processed_count > 0:
            self.send_heartbeat(status="ACTIVE", successful_run=True)

        return processed_count

    def replay_event(
        self,
        event_id: int,
        actor_id: str = "MERCHANT",
        actor_type: str = "MERCHANT",
    ) -> WebhookEvent:
        """
        Controlled operator replay for a DEAD_LETTER or RETRYABLE_FAILURE event.
        Guarantees idempotency and safe state transitions without duplicate captures.
        """
        with atomic_transaction(self.session):
            event = self.webhook_repo.mark_for_replay(event_id)
            if not event:
                raise ValueError(f"Webhook event {event_id} not found or not eligible for replay.")

            correlation_id = f"wh_replay_{uuid.uuid4().hex[:12]}"
            replay_merchant = (
                event.merchant_id
                if getattr(event, "merchant_id", None) and event.merchant_id not in ("merchant_default", "QUARANTINED_ORPHAN")
                else "platform_system"
            )
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=replay_merchant,
                    action="WEBHOOK_REPLAY_REQUESTED",
                    entity_type="WebhookEvent",
                    entity_id=event.paypal_event_id,
                    approval_id=None,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    before_state=WebhookEventStatus.DEAD_LETTER.value,
                    after_state=WebhookEventStatus.PENDING.value,
                    details=f"Operator '{actor_id}' requested replay for event {event.paypal_event_id}.",
                ),
            )

        # Process replayed event immediately
        self.process_event(event)

        with atomic_transaction(self.session):
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=replay_merchant,
                    action="WEBHOOK_REPLAY_COMPLETED",
                    entity_type="WebhookEvent",
                    entity_id=event.paypal_event_id,
                    approval_id=None,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    before_state=WebhookEventStatus.PENDING.value,
                    after_state=event.status,
                    details=f"Replay execution completed with status '{event.status}'.",
                ),
            )

        return event
