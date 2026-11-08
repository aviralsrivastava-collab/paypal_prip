import datetime
from typing import Dict, Optional, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.models.webhook import WebhookEvent
from backend.policies.checkout_policy import WebhookEventStatus


class WebhookEventRepository:
    """
    Persistence layer for incoming webhook notifications.
    Enforces deduplication on paypal_event_id, atomic leasing for concurrent background workers,
    and dead-letter tracking. Supports multi-tenant scoping and PostgreSQL SKIP LOCKED concurrency.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, event: WebhookEvent) -> WebhookEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def get_by_id(self, event_id: int) -> Optional[WebhookEvent]:
        stmt = select(WebhookEvent).where(WebhookEvent.id == event_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_paypal_event_id(self, paypal_event_id: str) -> Optional[WebhookEvent]:
        stmt = select(WebhookEvent).where(WebhookEvent.paypal_event_id == paypal_event_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_events(self, limit: int = 50, merchant_id: Optional[str] = None) -> Sequence[WebhookEvent]:
        stmt = select(WebhookEvent)
        if merchant_id is not None:
            stmt = stmt.where(WebhookEvent.merchant_id == merchant_id)
        stmt = stmt.order_by(WebhookEvent.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def list_failed_or_stuck_events(self, limit: int = 50, merchant_id: Optional[str] = None) -> Sequence[WebhookEvent]:
        """
        Returns events that are in RETRYABLE_FAILURE, DEAD_LETTER, or currently PROCESSING.
        """
        stmt = (
            select(WebhookEvent)
            .where(
                WebhookEvent.status.in_([
                    WebhookEventStatus.DEAD_LETTER.value,
                    WebhookEventStatus.RETRYABLE_FAILURE.value,
                    WebhookEventStatus.PROCESSING.value,
                ])
            )
        )
        if merchant_id is not None:
            stmt = stmt.where(WebhookEvent.merchant_id == merchant_id)
        stmt = stmt.order_by(WebhookEvent.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def claim_eligible_event(
        self,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> Optional[WebhookEvent]:
        """
        Atomically discovers and claims one eligible event for processing.
        Eligible events are:
        1. PENDING or RETRYABLE_FAILURE where next_retry_at is null or in the past.
        2. PROCESSING where processing_lease_expires_at is in the past (crashed/expired worker lease).
        Uses PostgreSQL SELECT FOR UPDATE SKIP LOCKED when available; falls back to atomic conditional update on SQLite.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        lease_expires = now + datetime.timedelta(seconds=lease_seconds)

        condition = or_(
            # Pending or retryable event whose backoff delay has elapsed
            WebhookEvent.status.in_([
                WebhookEventStatus.PENDING.value,
                WebhookEventStatus.RETRYABLE_FAILURE.value,
            ])
            & or_(
                WebhookEvent.next_retry_at.is_(None),
                WebhookEvent.next_retry_at <= now,
            ),
            # Expired lease / crashed worker recovery
            (WebhookEvent.status == WebhookEventStatus.PROCESSING.value)
            & (WebhookEvent.processing_lease_expires_at < now),
        )

        bind = self.session.get_bind()
        if bind and bind.dialect.name == "postgresql":
            # PostgreSQL-optimized lock skipping without thundering herd
            stmt = (
                select(WebhookEvent)
                .where(condition)
                .order_by(WebhookEvent.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            event = self.session.execute(stmt).scalar_one_or_none()
            if not event:
                return None
            event.status = WebhookEventStatus.PROCESSING.value
            event.locked_by = worker_id
            event.processing_lease_expires_at = lease_expires
            event.attempt_count += 1
            event.last_attempt_at = now
            self.session.flush()
            return event

        # Standard SQLite/portable atomic conditional update
        sqlite_stmt = select(WebhookEvent.id, WebhookEvent.status).where(condition).order_by(WebhookEvent.id.asc()).limit(1)
        candidate = self.session.execute(sqlite_stmt).first()
        if not candidate:
            return None

        candidate_id: int = candidate[0]
        candidate_status: str = candidate[1]

        update_stmt = (
            update(WebhookEvent)
            .where(
                WebhookEvent.id == candidate_id,
                WebhookEvent.status == candidate_status,
            )
            .values(
                status=WebhookEventStatus.PROCESSING.value,
                locked_by=worker_id,
                processing_lease_expires_at=lease_expires,
                attempt_count=WebhookEvent.attempt_count + 1,
                last_attempt_at=now,
            )
        )
        res = self.session.execute(update_stmt)
        self.session.flush()

        rowcount = getattr(res, "rowcount", 0)
        if rowcount == 1:
            return self.get_by_id(candidate_id)
        return None

    def mark_for_replay(self, event_id: int) -> Optional[WebhookEvent]:
        """
        Marks a DEAD_LETTER or RETRYABLE_FAILURE event for controlled operator replay.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        event = self.get_by_id(event_id)
        if not event:
            return None

        if event.status not in (
            WebhookEventStatus.DEAD_LETTER.value,
            WebhookEventStatus.RETRYABLE_FAILURE.value,
        ):
            raise ValueError(
                f"Event {event_id} has status '{event.status}'. Only DEAD_LETTER or RETRYABLE_FAILURE events are eligible for replay."
            )

        event.status = WebhookEventStatus.PENDING.value
        event.next_retry_at = now
        event.locked_by = None
        event.processing_lease_expires_at = None
        event.last_error = f"[Replay requested at {now.isoformat()}]"
        self.session.flush()
        return event

    def get_counts_by_status(self, merchant_id: Optional[str] = None) -> Dict[str, int]:
        stmt = select(WebhookEvent.status, func.count(WebhookEvent.id))
        if merchant_id is not None:
            stmt = stmt.where(WebhookEvent.merchant_id == merchant_id)
        stmt = stmt.group_by(WebhookEvent.status)
        rows = self.session.execute(stmt).all()
        return {status: count for status, count in rows}
