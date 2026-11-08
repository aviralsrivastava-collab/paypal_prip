import pytest
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedActor
from backend.repositories.audit import AuditRepository
from backend.repositories.demo_state import DemoStateRepository
from backend.schemas.demo_state import StateUpdateRequest
from backend.services.demo_state import (
    DemoStateService,
    UnauthorizedError,
)


class TestDatabaseAndAuditReliability:
    def test_1_successful_operation_commits_state_and_audit(self, db_session: Session):
        """1. Successful operations save both state and audit event atomically."""
        # Setup initial state
        initial = DemoStateService.initialize_state(db_session, "storefront_price", "100.00")
        assert initial.value == "100.00"
        assert initial.version == 1

        # Perform state update with audit
        request = StateUpdateRequest(
            value="120.00",
            expected_version=1,
            actor_id="merchant_admin_1",
            correlation_id="corr-test-001",
            merchant_id="merchant_default",
            idempotency_key="idemp-key-001",
        )
        actor = AuthenticatedActor(actor_id=request.actor_id or "merchant_admin_1", merchant_id="merchant_default")
        updated_state, audit_event = DemoStateService.update_state_with_audit(
            db_session, "storefront_price", request, trusted_actor=actor
        )

        assert updated_state.value == "120.00"
        assert updated_state.version == 2
        assert audit_event.action == "STATE_UPDATED"
        assert audit_event.actor_id == "merchant_admin_1"
        assert audit_event.entity_id == "storefront_price"
        assert audit_event.correlation_id == "corr-test-001"

        # Verify persisted database records
        persisted_state = DemoStateRepository.get_by_key(db_session, "storefront_price")
        assert persisted_state is not None
        assert persisted_state.value == "120.00"
        assert persisted_state.version == 2

        persisted_audits = AuditRepository.list_by_entity(
            db_session, "DEMO_STATE", "storefront_price"
        )
        assert len(persisted_audits) == 1
        assert persisted_audits[0].id == audit_event.id

    def test_2_audit_insertion_failure_rolls_back_state(self, db_session: Session):
        """2. Audit insertion failure rolls back the associated state change."""
        # Setup initial state
        DemoStateService.initialize_state(db_session, "catalog_stock", "50")

        request = StateUpdateRequest(
            value="45",
            expected_version=1,
            actor_id="system_inventory",
            correlation_id="corr-test-002",
            merchant_id="merchant_default",
        )

        # Trigger simulated audit failure
        actor = AuthenticatedActor(actor_id=request.actor_id or "merchant_admin_1", merchant_id="merchant_default")
        with pytest.raises(RuntimeError, match="Simulated audit logging failure"):
            DemoStateService.update_state_with_audit(
                db_session, "catalog_stock", request, trusted_actor=actor, fail_audit=True
            )

        # State MUST have been rolled back to initial value and version
        state = DemoStateRepository.get_by_key(db_session, "catalog_stock")
        assert state is not None
        assert state.value == "50"
        assert state.version == 1

        # No audit record should have been committed
        audits = AuditRepository.list_by_entity(db_session, "DEMO_STATE", "catalog_stock")
        assert len(audits) == 0

    def test_3_failed_validation_creates_no_mutation(self, db_session: Session):
        """3. Failed validation creates no successful mutation."""
        DemoStateService.initialize_state(db_session, "currency", "USD")

        # Validation error: version conflict (expected 99, but current is 1)
        request = StateUpdateRequest(
            value="EUR",
            expected_version=99,
            actor_id="merchant_admin",
            correlation_id="corr-test-003",
            merchant_id="merchant_default",
        )

        actor = AuthenticatedActor(actor_id=request.actor_id or "merchant_admin_1", merchant_id="merchant_default")
        with pytest.raises(ValueError, match="Optimistic lock conflict"):
            DemoStateService.update_state_with_audit(db_session, "currency", request, trusted_actor=actor)

        # Confirm currency remained unchanged
        state = DemoStateRepository.get_by_key(db_session, "currency")
        assert state is not None
        assert state.value == "USD"
        assert state.version == 1

    def test_4_unauthorized_operations_cannot_modify_data(self, db_session: Session):
        """4. Unauthorized operations cannot modify data."""
        DemoStateService.initialize_state(db_session, "prip_policy_mode", "STRICT")

        request = StateUpdateRequest(
            value="LENIENT",
            expected_version=1,
            actor_id="anonymous",
            correlation_id="corr-test-004",
        )

        with pytest.raises(UnauthorizedError, match="actor identity required"):
            DemoStateService.update_state_with_audit(db_session, "prip_policy_mode", request)

        state = DemoStateRepository.get_by_key(db_session, "prip_policy_mode")
        assert state is not None
        assert state.value == "STRICT"

    def test_5_duplicate_requests_safely_handled(self, db_session: Session):
        """5. Duplicate requests are handled safely without duplicate state corruption."""
        DemoStateService.initialize_state(db_session, "order_item", "initial")

        request = StateUpdateRequest(
            value="updated",
            expected_version=1,
            actor_id="merchant_admin",
            correlation_id="corr-test-005",
            merchant_id="merchant_default",
            idempotency_key="unique-idemp-005",
        )

        actor = AuthenticatedActor(actor_id=request.actor_id or "merchant_admin_1", merchant_id="merchant_default")
        # First request succeeds
        updated, audit = DemoStateService.update_state_with_audit(
            db_session, "order_item", request, trusted_actor=actor
        )
        assert updated.version == 2

        # Replayed request with stale expected_version=1 fails safely
        with pytest.raises(ValueError, match="Optimistic lock conflict"):
            DemoStateService.update_state_with_audit(
                db_session, "order_item", request, trusted_actor=actor
            )

        # Verify only one audit record exists
        audits = AuditRepository.list_by_entity(db_session, "DEMO_STATE", "order_item")
        assert len(audits) == 1

    def test_6_audit_records_are_append_only(self, db_session: Session):
        """6. Audit records cannot be modified or deleted through normal repository interfaces."""
        # Inspect AuditRepository methods
        repo_methods = dir(AuditRepository)
        assert "append" in repo_methods
        assert "get_by_id" in repo_methods
        assert "list_by_entity" in repo_methods
        assert "list_by_correlation_id" in repo_methods

        # Enforce that no mutating/destructive methods exist on the repository
        assert "update" not in repo_methods
        assert "delete" not in repo_methods
        assert "remove" not in repo_methods
        assert "clear" not in repo_methods
