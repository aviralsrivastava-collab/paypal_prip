import datetime
import json
import logging
import uuid
from typing import Dict, Optional

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import atomic_transaction
from backend.integrations.paypal import PayPalClientInterface, get_paypal_client
from backend.models.webhook import WebhookEvent
from backend.policies.checkout_policy import (
    WebhookEventStatus,
)
from backend.repositories.order import OrderRepository
from backend.repositories.payment_capture import PaymentCaptureRepository
from backend.repositories.webhook import WebhookEventRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.webhook import WebhookEventResponse
from backend.services.audit import AuditService

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Webhook processing business service.
    Enforces raw-body cryptographic signature verification,
    event deduplication on paypal_event_id, and idempotent state transitions.
    """

    def __init__(
        self,
        session: Session,
        paypal_client: Optional[PayPalClientInterface] = None,
    ) -> None:
        self.session = session
        self.paypal_client = paypal_client or get_paypal_client()
        self.settings = get_settings()
        self.webhook_repo = WebhookEventRepository(session)
        self.order_repo = OrderRepository(session)
        self.capture_repo = PaymentCaptureRepository(session)

    def process_webhook(
        self,
        headers: Dict[str, str],
        raw_body: str,
    ) -> WebhookEventResponse:
        """
        Validates raw cryptographic signature and idempotently processes event.
        """
        # 1. Cryptographic signature check against official PayPal documentation
        webhook_id = self.settings.paypal_webhook_id
        is_verified = self.paypal_client.verify_webhook_signature(
            headers=headers,
            raw_body=raw_body,
            webhook_id=webhook_id,
        )

        if not is_verified:
            logger.warning("Rejected unverified PayPal webhook transmission")
            raise ValueError("Cryptographic webhook signature verification failed.")

        # 2. Parse payload
        try:
            payload = json.loads(raw_body)
        except Exception as exc:
            raise ValueError(f"Malformed JSON in webhook body: {exc}") from exc

        event_id = payload.get("id")
        if not event_id:
            raise ValueError("Missing 'id' field in PayPal webhook payload.")

        event_type = payload.get("event_type", "UNKNOWN")
        resource_type = payload.get("resource_type", "UNKNOWN")
        summary = payload.get("summary")
        norm_headers = {k.lower(): v for k, v in headers.items()}
        transmission_id = norm_headers.get("paypal-transmission-id")
        correlation_id = f"wh_corr_{uuid.uuid4().hex[:12]}"

        # 3. Deduplication check
        existing_event = self.webhook_repo.get_by_paypal_event_id(event_id)
        if existing_event:
            logger.info(f"Duplicate webhook event {event_id} ignored.")
            with atomic_transaction(self.session):
                dup_merchant = (
                    existing_event.merchant_id
                    if existing_event.merchant_id and existing_event.merchant_id not in ("merchant_default", "QUARANTINED_ORPHAN")
                    else "platform_system"
                )
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=dup_merchant,
                        action="WEBHOOK_DUPLICATE_IGNORED",
                        entity_type="WebhookEvent",
                        entity_id=event_id,
                        approval_id=None,
                        actor_type="PAYPAL_WEBHOOK",
                        actor_id=event_id,
                        correlation_id=correlation_id,
                        before_state=existing_event.status,
                        after_state=existing_event.status,
                        details=f"Duplicate event {event_id} ({event_type}) safely ignored.",
                    ),
                )
            return WebhookEventResponse(
                id=existing_event.id,
                paypal_event_id=existing_event.paypal_event_id,
                event_type=existing_event.event_type,
                resource_type=existing_event.resource_type,
                status=WebhookEventStatus.DUPLICATE.value,
                summary=existing_event.summary,
                created_at=existing_event.created_at,
            )

        # 4. Durable persistence as PENDING before processing/acknowledgement
        now = datetime.datetime.now(datetime.timezone.utc)
        with atomic_transaction(self.session):
            event_record = WebhookEvent(
                merchant_id="platform_system",
                paypal_event_id=event_id,
                event_type=event_type,
                resource_type=resource_type,
                summary=summary,
                status=WebhookEventStatus.PENDING.value,
                raw_payload=raw_body,
                transmission_id=transmission_id,
                attempt_count=0,
                max_attempts=5,
                next_retry_at=now,
            )
            self.webhook_repo.create(event_record)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id="platform_system",
                    action="WEBHOOK_RECEIVED",
                    entity_type="WebhookEvent",
                    entity_id=event_id,
                    approval_id=None,
                    actor_type="PAYPAL_WEBHOOK",
                    actor_id=event_id,
                    correlation_id=correlation_id,
                    before_state=None,
                    after_state=WebhookEventStatus.PENDING.value,
                    details=f"Durably persisted incoming {event_type} notification as PENDING.",
                ),
            )

        # 5. Process through the resilient worker processing engine
        from backend.services.webhook_worker import WebhookWorkerService
        worker = WebhookWorkerService(self.session)
        worker.process_event(event_record)

        return WebhookEventResponse.model_validate(event_record)
