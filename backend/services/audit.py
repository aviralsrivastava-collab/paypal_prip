from typing import List, Optional

from sqlalchemy.orm import Session

from backend.core.security import (
    RESERVED_SYSTEM_TENANTS,
    AuthenticatedActor,
    require_merchant_access,
)
from backend.repositories.audit import AuditRepository
from backend.schemas.audit import AuditEventCreate, AuditEventResponse


class AuditService:
    @staticmethod
    def log_event(
        session: Session,
        event_data: AuditEventCreate,
        merchant_id: Optional[str] = None,
    ) -> AuditEventResponse:
        """
        Appends an audit record within the current session/transaction.
        Propagates explicit merchant_id context to ensure strict tenant attribution.
        """
        if event_data.merchant_id and merchant_id and event_data.merchant_id.strip() != merchant_id.strip():
            raise ValueError(
                f"Conflicting merchant attribution: event has '{event_data.merchant_id}' but context supplied '{merchant_id}'."
            )
        resolved_merchant = event_data.merchant_id or merchant_id
        if not resolved_merchant or not resolved_merchant.strip():
            raise ValueError("Audit event requires explicit merchant_id or platform scope attribution.")
        db_event = AuditRepository.append(session, event_data, merchant_id=resolved_merchant.strip())
        return AuditEventResponse.model_validate(db_event)

    @staticmethod
    def list_events_by_entity(
        session: Session,
        entity_type: str,
        entity_id: str,
        actor: AuthenticatedActor,
        include_system: bool = False,
    ) -> List[AuditEventResponse]:
        """
        Authorized service boundary for querying audit events by entity.
        Ordinary merchant queries are constrained to actor's merchant scope.
        Privileged queries (include_system) require platform admin role.
        """
        is_platform_admin = actor.is_authenticated and actor.role in {"superadmin", "system_admin"}
        if include_system and not is_platform_admin:
            raise PermissionError("Unauthorized: actor lacks platform administrative privileges for include_system query.")

        merchant_filter = None if is_platform_admin and include_system else actor.merchant_id
        events = AuditRepository.list_by_entity(
            session=session,
            entity_type=entity_type,
            entity_id=entity_id,
            merchant_id=merchant_filter,
            include_system=include_system,
            authorized_actor=actor,
        )
        return [AuditEventResponse.model_validate(e) for e in events]

    @staticmethod
    def list_events_by_correlation_id(
        session: Session,
        correlation_id: str,
        actor: AuthenticatedActor,
        include_system: bool = False,
    ) -> List[AuditEventResponse]:
        """
        Authorized service boundary for querying audit events by correlation ID.
        Ordinary merchant queries are constrained to actor's merchant scope.
        Privileged queries (include_system) require platform admin role.
        """
        is_platform_admin = actor.is_authenticated and actor.role in {"superadmin", "system_admin"}
        if include_system and not is_platform_admin:
            raise PermissionError("Unauthorized: actor lacks platform administrative privileges for include_system query.")

        merchant_filter = None if is_platform_admin and include_system else actor.merchant_id
        events = AuditRepository.list_by_correlation_id(
            session=session,
            correlation_id=correlation_id,
            merchant_id=merchant_filter,
            include_system=include_system,
            authorized_actor=actor,
        )
        return [AuditEventResponse.model_validate(e) for e in events]

    @staticmethod
    def list_events_by_merchant(
        session: Session,
        merchant_id: str,
        actor: AuthenticatedActor,
        limit: int = 50,
        allow_quarantined: bool = False,
    ) -> List[AuditEventResponse]:
        """
        Authorized service boundary for querying audit events by merchant tenant.
        Enforces tenant access controls; querying reserved tenants requires platform admin role.
        """
        is_platform_admin = actor.is_authenticated and actor.role in {"superadmin", "system_admin"}

        if (allow_quarantined or merchant_id in RESERVED_SYSTEM_TENANTS) and not is_platform_admin:
            raise PermissionError(
                f"Unauthorized: access to reserved tenant '{merchant_id}' requires platform administrative authorization."
            )

        if not is_platform_admin:
            require_merchant_access(actor, merchant_id)

        events = AuditRepository.list_by_merchant(
            session=session,
            merchant_id=merchant_id,
            limit=limit,
            allow_quarantined=allow_quarantined,
            authorized_actor=actor,
        )
        return [AuditEventResponse.model_validate(e) for e in events]
