import json
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import RESERVED_SYSTEM_TENANTS, AuthenticatedActor
from backend.repositories.audit import AuditRepository
from backend.repositories.demo_state import DemoStateRepository
from backend.schemas.audit import AuditEventCreate, AuditEventResponse
from backend.schemas.demo_state import StateResponse, StateUpdateRequest


class StateMutationError(Exception):
    pass


class UnauthorizedError(StateMutationError):
    pass


class DemoStateService:
    """
    Coordinates state transitions with atomic audit trail logging.
    Guarantees all-or-nothing atomicity via atomic_transaction boundaries.
    """

    @staticmethod
    def initialize_state(session: Session, key: str, value: str) -> StateResponse:
        with atomic_transaction(session):
            state = DemoStateRepository.get_by_key(session, key)
            if not state:
                state = DemoStateRepository.create(session, key, value)
            return StateResponse.model_validate(state)

    @staticmethod
    def get_state(session: Session, key: str) -> StateResponse:
        state = DemoStateRepository.get_by_key(session, key)
        if not state:
            raise KeyError(f"State key '{key}' not found")
        return StateResponse.model_validate(state)

    @staticmethod
    def update_state_with_audit(
        session: Session,
        key: str,
        request: StateUpdateRequest,
        merchant_id: Optional[str] = None,
        trusted_actor: Optional[AuthenticatedActor] = None,
        fail_audit: bool = False,
    ) -> Tuple[StateResponse, AuditEventResponse]:
        """
        Atomically updates state and records an audit event.
        Requires trusted authenticated actor context for attribution.
        Actor identity and merchant attribution come from trusted_actor (or validated context).
        Client-supplied actor_id or merchant_id in request cannot override trusted attribution;
        any tenant or actor mismatch is rejected. Missing trusted attribution fails closed.
        """
        # Support positional 4th argument passing of trusted_actor or merchant_id
        if isinstance(merchant_id, AuthenticatedActor):
            trusted_actor = merchant_id
            merchant_id = None

        if trusted_actor is None:
            raise UnauthorizedError("Unauthorized: actor identity required for mutation (missing trusted actor context)")

        if not trusted_actor.is_authenticated or not trusted_actor.actor_id or trusted_actor.actor_id == "anonymous":
            raise UnauthorizedError("Unauthorized: actor identity required for mutation")

        if trusted_actor.merchant_id in RESERVED_SYSTEM_TENANTS:
            raise UnauthorizedError(f"Reserved tenant '{trusted_actor.merchant_id}' cannot mutate demo state")

        # Verify no tenant mismatch if client-supplied merchant_id or parameter is present
        if request.merchant_id and request.merchant_id.strip() != trusted_actor.merchant_id.strip():
            raise ValueError(
                f"Tenant mismatch: request specifies '{request.merchant_id}' but trusted actor belongs to '{trusted_actor.merchant_id}'"
            )
        if merchant_id and merchant_id.strip() != trusted_actor.merchant_id.strip():
            raise ValueError(
                f"Tenant mismatch: context specifies '{merchant_id}' but trusted actor belongs to '{trusted_actor.merchant_id}'"
            )

        # Verify no actor mismatch if client-supplied actor_id is present
        if request.actor_id and request.actor_id.strip() != trusted_actor.actor_id.strip():
            raise UnauthorizedError(
                f"Actor mismatch: request specifies '{request.actor_id}' but trusted actor is '{trusted_actor.actor_id}'"
            )

        resolved_actor_id = trusted_actor.actor_id.strip()
        resolved_merchant = trusted_actor.merchant_id.strip()
        if not resolved_merchant:
            raise ValueError("Audit event requires explicit merchant_id or platform scope attribution.")

        with atomic_transaction(session):
            state = DemoStateRepository.get_by_key(session, key)
            if not state:
                raise KeyError(f"State key '{key}' not found")

            before_snapshot = json.dumps({"value": state.value, "version": state.version})

            # Update the entity (increments version)
            updated_state = DemoStateRepository.update(
                session=session,
                state=state,
                new_value=request.value,
                expected_version=request.expected_version,
            )

            after_snapshot = json.dumps(
                {"value": updated_state.value, "version": updated_state.version}
            )

            # Simulate an intentional failure during audit persistence if requested
            if fail_audit:
                raise RuntimeError(
                    "Simulated audit logging failure triggering transaction rollback"
                )

            # Create the corresponding audit entry using trusted actor identity
            audit_in = AuditEventCreate(
                merchant_id=resolved_merchant,
                actor_type="MERCHANT",
                actor_id=resolved_actor_id,
                action="STATE_UPDATED",
                entity_type="DEMO_STATE",
                entity_id=key,
                approval_id=None,
                correlation_id=request.correlation_id,
                before_state=before_snapshot,
                after_state=after_snapshot,
                details=json.dumps({"idempotency_key": request.idempotency_key}),
            )
            audit_event = AuditRepository.append(session, audit_in, merchant_id=resolved_merchant)

            return (
                StateResponse.model_validate(updated_state),
                AuditEventResponse.model_validate(audit_event),
            )
