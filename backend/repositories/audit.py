from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import RESERVED_SYSTEM_TENANTS, AuthenticatedActor
from backend.models.audit import AuditEvent
from backend.schemas.audit import AuditEventCreate


class AuditRepository:
    """
    Append-only repository for audit events.
    Mutations (UPDATE) and deletions (DELETE) are strictly prohibited and unsupported.
    Enforces tenant attribution and scoped historical retrieval.
    """

    @staticmethod
    def append(
        session: Session,
        event: AuditEventCreate,
        merchant_id: Optional[str] = None,
    ) -> AuditEvent:
        if event.merchant_id and merchant_id and event.merchant_id.strip() != merchant_id.strip():
            raise ValueError(
                f"Conflicting merchant attribution: event has '{event.merchant_id}' but context supplied '{merchant_id}'."
            )
        resolved_merchant_id = event.merchant_id or merchant_id
        if not resolved_merchant_id or not resolved_merchant_id.strip():
            raise ValueError("Audit event requires explicit merchant_id or platform scope attribution.")

        db_event = AuditEvent(
            merchant_id=resolved_merchant_id.strip(),
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            approval_id=event.approval_id,
            correlation_id=event.correlation_id,
            before_state=event.before_state,
            after_state=event.after_state,
            details=event.details,
        )
        session.add(db_event)
        session.flush()  # Assigns primary key within the current transaction
        return db_event

    @staticmethod
    def get_by_id(session: Session, event_id: int) -> Optional[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.id == event_id)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _is_privileged_actor(actor: Optional[AuthenticatedActor]) -> bool:
        return (
            actor is not None
            and actor.is_authenticated
            and actor.role in {"superadmin", "system_admin"}
        )

    @staticmethod
    def list_by_entity(
        session: Session,
        entity_type: str,
        entity_id: str,
        merchant_id: Optional[str] = None,
        include_system: bool = False,
        authorized_actor: Optional[AuthenticatedActor] = None,
    ) -> List[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        )
        is_privileged = AuditRepository._is_privileged_actor(authorized_actor)

        if include_system:
            if not is_privileged:
                raise PermissionError(
                    "Unauthorized: include_system flag requires platform administrative authorization."
                )
            if merchant_id:
                stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
        else:
            if merchant_id:
                if merchant_id in RESERVED_SYSTEM_TENANTS and not is_privileged:
                    return []
                stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
            else:
                stmt = stmt.where(AuditEvent.merchant_id.notin_(RESERVED_SYSTEM_TENANTS))

        stmt = stmt.order_by(AuditEvent.created_at.asc())
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def list_by_correlation_id(
        session: Session,
        correlation_id: str,
        merchant_id: Optional[str] = None,
        include_system: bool = False,
        authorized_actor: Optional[AuthenticatedActor] = None,
    ) -> List[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
        )
        is_privileged = AuditRepository._is_privileged_actor(authorized_actor)

        if include_system:
            if not is_privileged:
                raise PermissionError(
                    "Unauthorized: include_system flag requires platform administrative authorization."
                )
            if merchant_id:
                stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
        else:
            if merchant_id:
                if merchant_id in RESERVED_SYSTEM_TENANTS and not is_privileged:
                    return []
                stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
            else:
                stmt = stmt.where(AuditEvent.merchant_id.notin_(RESERVED_SYSTEM_TENANTS))

        stmt = stmt.order_by(AuditEvent.created_at.asc())
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def list_by_merchant(
        session: Session,
        merchant_id: str,
        limit: int = 50,
        allow_quarantined: bool = False,
        authorized_actor: Optional[AuthenticatedActor] = None,
    ) -> List[AuditEvent]:
        is_privileged = AuditRepository._is_privileged_actor(authorized_actor)

        if allow_quarantined and not is_privileged:
            raise PermissionError(
                "Unauthorized: allow_quarantined flag requires platform administrative authorization."
            )

        if merchant_id in RESERVED_SYSTEM_TENANTS and not is_privileged:
            return []

        stmt = (
            select(AuditEvent)
            .where(AuditEvent.merchant_id == merchant_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())
