import datetime
import threading
from decimal import Decimal
from typing import List

import pytest
from sqlalchemy.orm import Session

from backend.api.corrections import (
    approve_proposal,
    create_proposal,
    execute_proposal,
    get_proposal,
    get_proposal_history,
    list_proposals,
)
from backend.core.security import AuthenticatedActor
from backend.models.proposal import CorrectionProposal
from backend.models.scan import StorefrontScan
from backend.policies.correction_policy import (
    ApprovalStatus,
    ExecutionStatus,
    PolicyValidationStatus,
)
from backend.repositories.evidence import EvidenceRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.proposal import (
    CorrectionProposalApproveRequest,
    CorrectionProposalCreateRequest,
    CorrectionProposalExecuteRequest,
    CorrectionProposalRejectRequest,
)
from backend.schemas.scan import ScanCreateRequest
from backend.services.catalog import CatalogService
from backend.services.inspection import InspectionService
from backend.services.proposal import ProposalService
from backend.services.remediation import RemediationService


@pytest.fixture
def merchant_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="merchant-jane", role="merchant_operator", actor_type="merchant")


@pytest.fixture
def ordinary_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="random-user", role="ordinary_user", actor_type="customer")


@pytest.fixture
def ai_actor() -> AuthenticatedActor:
    return AuthenticatedActor(actor_id="ai", role="ai_assistant", actor_type="ai")


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    catalog_service = CatalogService(db_session)
    catalog_service.seed_initial_catalog(reset=True)
    return db_session


@pytest.fixture
def completed_scan(seeded_db: Session, merchant_actor: AuthenticatedActor) -> StorefrontScan:
    service = InspectionService(seeded_db)
    detail = service.run_inspection(ScanCreateRequest(sku="SX-001"), merchant_actor)
    scan = seeded_db.query(StorefrontScan).filter_by(id=detail.id).first()
    assert scan is not None
    return scan


@pytest.fixture
def evidence_ids(seeded_db: Session, completed_scan: StorefrontScan) -> List[int]:
    ev_repo = EvidenceRepository(seeded_db)
    items = ev_repo.list_by_scan_id(completed_scan.id)
    return [i.id for i in items]


class TestCorrectionsAndRemediation:

    # 1. Proposal creation tests
    def test_1_valid_proposal_creation(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="Synchronize storefront price to catalog ground truth (USD 100.00)",
            supporting_evidence_ids=evidence_ids,
            idempotency_key="prop-key-1",
        )
        res = service.create_proposal(req, merchant_actor)

        assert res.id is not None
        assert res.sku == "SX-001"
        assert res.proposed_value == Decimal("100.00")
        assert res.current_value == Decimal("120.00")
        assert res.approval_status == ApprovalStatus.PENDING_APPROVAL
        assert res.policy_validation_status == PolicyValidationStatus.VALID
        assert res.execution_status == ExecutionStatus.NOT_STARTED

        # Audit events check
        history = service.get_proposal_history(res.id)
        actions = [h.action for h in history]
        assert "CORRECTION_PROPOSED" in actions
        assert "CORRECTION_VALIDATED" in actions

    def test_2_invalid_sku_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="NON_EXISTENT_SKU",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="Fix non-existent product",
            supporting_evidence_ids=evidence_ids,
        )
        with pytest.raises(ValueError, match="does not exist"):
            service.create_proposal(req, merchant_actor)

    def test_3_invalid_currency_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("100.00"),
            currency="EUR",
            reason="Mismatched currency",
            supporting_evidence_ids=evidence_ids,
        )
        with pytest.raises(ValueError, match="violates correction policy"):
            service.create_proposal(req, merchant_actor)

    def test_4_invalid_price_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        # Price differing from catalog price
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("85.00"),
            currency="USD",
            reason="Arbitrary price reduction",
            supporting_evidence_ids=evidence_ids,
        )
        with pytest.raises(ValueError, match="Proposed price 85.00 must match authoritative catalog price"):
            service.create_proposal(req, merchant_actor)

    def test_5_missing_evidence_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="No evidence cited",
            supporting_evidence_ids=[],
        )
        with pytest.raises(ValueError, match="must reference at least one valid supporting evidence record"):
            service.create_proposal(req, merchant_actor)

        # Unknown evidence ID
        req_unknown = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="PRICE_SYNCHRONIZATION",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="Fake evidence",
            supporting_evidence_ids=[99999],
        )
        with pytest.raises(ValueError, match="Referenced evidence ID 99999 is not present"):
            service.create_proposal(req_unknown, merchant_actor)

    def test_6_unsupported_correction_type_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposal_type="ARBITRARY_MUTATION",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="Arbitrary change",
            supporting_evidence_ids=evidence_ids,
        )
        with pytest.raises(ValueError, match="Unsupported proposal type"):
            service.create_proposal(req, merchant_actor)

    # 2. Approval workflow tests
    def test_7_authorized_merchant_approval(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="Fix price mismatch",
            supporting_evidence_ids=evidence_ids,
        )
        proposal = service.create_proposal(req, merchant_actor)

        approved = service.approve_proposal(
            proposal.id, merchant_actor, CorrectionProposalApproveRequest(reason="Merchant reviewed and confirmed")
        )

        assert approved.approval_status == ApprovalStatus.APPROVED
        assert approved.approved_by == merchant_actor.actor_id

        # Verify audit event
        history = service.get_proposal_history(proposal.id)
        assert any(h.action == "CORRECTION_APPROVED" for h in history)

    def test_8_unauthorized_approval_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor, ordinary_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        with pytest.raises(PermissionError, match="Unauthorized"):
            service.approve_proposal(proposal.id, ordinary_actor)

    def test_9_client_actor_impersonation_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], ordinary_actor: AuthenticatedActor
    ):
        """Ordinary user cannot approve proposals even if they claim merchant status."""
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            AuthenticatedActor(actor_id="test-operator", role="demo_operator", actor_type="merchant"),
        )

        with pytest.raises(PermissionError):
            service.approve_proposal(proposal.id, ordinary_actor)

    def test_10_expired_proposal_approval_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
                expires_in_hours=1,
            ),
            merchant_actor,
        )

        # Manually backdate expiration
        entity = seeded_db.query(CorrectionProposal).filter_by(id=proposal.id).first()
        assert entity is not None
        entity.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        seeded_db.commit()

        with pytest.raises(ValueError, match="proposal expired"):
            service.approve_proposal(proposal.id, merchant_actor)

        # Check proposal status transitioned to EXPIRED
        refreshed = service.get_proposal(proposal.id)
        assert refreshed is not None
        assert refreshed.approval_status == ApprovalStatus.EXPIRED

    def test_11_stale_proposal_approval_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        # Simulate storefront product version change in background
        sf_repo = StorefrontRepository(seeded_db)
        sf_product = sf_repo.get_by_sku("SX-001")
        assert sf_product is not None
        sf_product.version = sf_product.version + 1
        seeded_db.commit()

        with pytest.raises(ValueError, match="data is stale"):
            service.approve_proposal(proposal.id, merchant_actor)

        # Proposal policy status becomes STALE
        refreshed = service.get_proposal(proposal.id)
        assert refreshed is not None
        assert refreshed.policy_validation_status == PolicyValidationStatus.STALE

    def test_12_ai_cannot_approve_its_own_proposal(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor, ai_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix proposed by AI",
                supporting_evidence_ids=evidence_ids,
            ),
            ai_actor,
        )

        with pytest.raises(PermissionError, match="Critical Invariant Violation: AI agents are strictly forbidden from approving corrections"):
            service.approve_proposal(proposal.id, ai_actor)

    def test_13_duplicate_approval_idempotency(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        approved1 = service.approve_proposal(proposal.id, merchant_actor)
        assert approved1.approval_status == ApprovalStatus.APPROVED

        approved2 = service.approve_proposal(proposal.id, merchant_actor)
        assert approved2.approval_status == ApprovalStatus.APPROVED
        assert approved2.id == approved1.id

    def test_14_concurrent_approval_requests(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        results = []
        errors = []
        engine = seeded_db.get_bind()

        def worker():
            with Session(bind=engine) as w_session:
                w_service = ProposalService(w_session)
                try:
                    res = w_service.approve_proposal(proposal.id, merchant_actor)
                    results.append(res)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # At least one succeeded or both succeeded idempotently
        assert len(results) >= 1, f"Worker errors: {errors}"
        refreshed = service.get_proposal(proposal.id)
        assert refreshed is not None
        assert refreshed.approval_status == ApprovalStatus.APPROVED

    # 3. Rejection workflow tests
    def test_15_rejection_with_reason(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        rej = service.reject_proposal(
            proposal.id,
            merchant_actor,
            CorrectionProposalRejectRequest(reason="Discrepancy is deliberate promotional testing"),
        )
        assert rej.approval_status == ApprovalStatus.REJECTED
        assert rej.rejected_by == merchant_actor.actor_id
        assert rej.rejection_reason == "Discrepancy is deliberate promotional testing"

        history = service.get_proposal_history(proposal.id)
        assert any(h.action == "CORRECTION_REJECTED" for h in history)

    def test_16_rejected_proposal_cannot_execute(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.reject_proposal(proposal.id, merchant_actor, CorrectionProposalRejectRequest(reason="No fix needed"))

        rem_service = RemediationService(seeded_db)
        with pytest.raises(ValueError, match="Only APPROVED proposals may be executed"):
            rem_service.execute_correction(proposal.id, merchant_actor)

    def test_17_unauthorized_rejection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor, ordinary_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        with pytest.raises(PermissionError, match="Unauthorized"):
            service.reject_proposal(proposal.id, ordinary_actor, CorrectionProposalRejectRequest(reason="Rejected by random"))

    # 4. Controlled Execution & Remediation tests
    def test_18_successful_storefront_correction(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align with catalog",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        executed, followup_scan = rem_service.execute_correction(proposal.id, merchant_actor)

        assert executed.execution_status == ExecutionStatus.SUCCEEDED
        assert executed.executed_at is not None

        # Verify storefront product was mutated to USD 100.00
        sf_repo = StorefrontRepository(seeded_db)
        sf_product = sf_repo.get_by_sku("SX-001")
        assert sf_product is not None
        assert sf_product.price == Decimal("100.00")

        # Verify follow-up inspection is VERIFIED_NO_ISSUE!
        assert followup_scan is not None
        assert followup_scan.state == "VERIFIED_NO_ISSUE"
        assert followup_scan.catalog_price == followup_scan.observed_price == "100.00"

        # Audit events check
        history = service.get_proposal_history(proposal.id)
        actions = [h.action for h in history]
        assert "CORRECTION_EXECUTION_STARTED" in actions
        assert "CORRECTION_EXECUTION_SUCCEEDED" in actions

    def test_19_execution_of_unapproved_proposal_rejected(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )

        rem_service = RemediationService(seeded_db)
        with pytest.raises(ValueError, match="Only APPROVED proposals may be executed"):
            rem_service.execute_correction(proposal.id, merchant_actor)

    def test_20_expired_proposal_execution_rejected(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        # Backdate expiration
        entity = seeded_db.query(CorrectionProposal).filter_by(id=proposal.id).first()
        assert entity is not None
        entity.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        seeded_db.commit()

        rem_service = RemediationService(seeded_db)
        with pytest.raises(ValueError, match="proposal expired"):
            rem_service.execute_correction(proposal.id, merchant_actor)

    def test_21_stale_version_execution_rejected(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        # Storefront version increments unexpectedly
        sf_repo = StorefrontRepository(seeded_db)
        sf_product = sf_repo.get_by_sku("SX-001")
        assert sf_product is not None
        sf_product.version = sf_product.version + 1
        seeded_db.commit()

        rem_service = RemediationService(seeded_db)
        with pytest.raises(ValueError, match="data is stale"):
            rem_service.execute_correction(proposal.id, merchant_actor)

    def test_22_duplicate_execution_protection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        exec1, _ = rem_service.execute_correction(proposal.id, merchant_actor)
        assert exec1.execution_status == ExecutionStatus.SUCCEEDED

        # Second execute call returns cleanly without re-executing
        exec2, _ = rem_service.execute_correction(proposal.id, merchant_actor)
        assert exec2.execution_status == ExecutionStatus.SUCCEEDED
        assert exec2.id == exec1.id

    def test_23_concurrent_execution_protection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        # Simulate IN_PROGRESS state
        entity = seeded_db.query(CorrectionProposal).filter_by(id=proposal.id).first()
        assert entity is not None
        entity.execution_status = ExecutionStatus.IN_PROGRESS.value
        seeded_db.commit()

        rem_service = RemediationService(seeded_db)
        with pytest.raises(ValueError, match="Execution already in progress"):
            rem_service.execute_correction(proposal.id, merchant_actor)

    def test_24_storefront_failure_handling(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        req = CorrectionProposalExecuteRequest(simulate_storefront_error=True)

        with pytest.raises(RuntimeError, match="Storefront correction execution failed"):
            rem_service.execute_correction(proposal.id, merchant_actor, req)

        refreshed = service.get_proposal(proposal.id)
        assert refreshed is not None
        assert refreshed.execution_status == ExecutionStatus.FAILED
        assert refreshed.execution_error is not None

        history = service.get_proposal_history(proposal.id)
        assert any(h.action == "CORRECTION_EXECUTION_FAILED" for h in history)

    def test_25_timeout_resulting_in_reconciliation_required(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        req = CorrectionProposalExecuteRequest(simulate_timeout=True)

        with pytest.raises(RuntimeError, match="Status set to RECONCILIATION_REQUIRED"):
            rem_service.execute_correction(proposal.id, merchant_actor, req)

        refreshed = service.get_proposal(proposal.id)
        assert refreshed is not None
        assert refreshed.execution_status == ExecutionStatus.RECONCILIATION_REQUIRED

        history = service.get_proposal_history(proposal.id)
        assert any(h.action == "CORRECTION_RECONCILIATION_REQUIRED" for h in history)

    def test_26_reconciliation_after_uncertain_external_outcome(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Align",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        # 1. Encounter timeout
        with pytest.raises(RuntimeError):
            rem_service.execute_correction(proposal.id, merchant_actor, CorrectionProposalExecuteRequest(simulate_timeout=True))

        # 2. Simulate that the storefront actually updated to 100.00 before the timeout
        sf_repo = StorefrontRepository(seeded_db)
        sf_product = sf_repo.get_by_sku("SX-001")
        assert sf_product is not None
        sf_product.price = Decimal("100.00")
        seeded_db.commit()

        # 3. Reconcile
        reconciled, followup = rem_service.reconcile_proposal(proposal.id, merchant_actor)
        assert reconciled.execution_status == ExecutionStatus.SUCCEEDED
        assert followup is not None
        assert followup.state == "VERIFIED_NO_ISSUE"

        history = service.get_proposal_history(proposal.id)
        assert any(h.action == "CORRECTION_RECONCILED" for h in history)

    def test_27_successful_followup_inspection(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)

        rem_service = RemediationService(seeded_db)
        _, followup_scan = rem_service.execute_correction(proposal.id, merchant_actor)

        assert followup_scan is not None
        assert followup_scan.state == "VERIFIED_NO_ISSUE"
        assert followup_scan.catalog_price == "100.00"
        assert followup_scan.observed_price == "100.00"

    def test_28_audit_event_consistency_after_execution(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        service = ProposalService(seeded_db)
        proposal = service.create_proposal(
            CorrectionProposalCreateRequest(
                scan_id=completed_scan.id,
                sku="SX-001",
                proposed_value=Decimal("100.00"),
                currency="USD",
                reason="Fix",
                supporting_evidence_ids=evidence_ids,
            ),
            merchant_actor,
        )
        service.approve_proposal(proposal.id, merchant_actor)
        rem_service = RemediationService(seeded_db)
        rem_service.execute_correction(proposal.id, merchant_actor)

        history = service.get_proposal_history(proposal.id)
        actions = [h.action for h in history]
        expected_sequence = [
            "CORRECTION_PROPOSED",
            "CORRECTION_VALIDATED",
            "CORRECTION_APPROVED",
            "CORRECTION_EXECUTION_STARTED",
            "CORRECTION_EXECUTION_SUCCEEDED",
        ]
        for act in expected_sequence:
            assert act in actions

    def test_29_api_route_handlers_for_corrections(
        self, seeded_db: Session, completed_scan: StorefrontScan, evidence_ids: List[int], merchant_actor: AuthenticatedActor
    ):
        # 1. Create via API
        req = CorrectionProposalCreateRequest(
            scan_id=completed_scan.id,
            sku="SX-001",
            proposed_value=Decimal("100.00"),
            currency="USD",
            reason="API Route test",
            supporting_evidence_ids=evidence_ids,
        )
        created = create_proposal(req, merchant_actor, seeded_db)
        assert created.id > 0

        # 2. Get by ID
        fetched = get_proposal(created.id, seeded_db)
        assert fetched.id == created.id

        # 3. List
        list_res = list_proposals(sku="SX-001", approval_status=None, execution_status=None, db=seeded_db)
        assert any(p.id == created.id for p in list_res)

        # 4. Approve via API
        app_res = approve_proposal(created.id, CorrectionProposalApproveRequest(reason="API approval"), merchant_actor, seeded_db)
        assert app_res.approval_status == ApprovalStatus.APPROVED

        # 5. Execute via API
        exec_res = execute_proposal(created.id, CorrectionProposalExecuteRequest(), merchant_actor, seeded_db)
        assert exec_res.proposal.execution_status == ExecutionStatus.SUCCEEDED
        assert exec_res.followup_scan is not None

        # 6. History via API
        hist = get_proposal_history(created.id, seeded_db)
        assert len(hist) >= 5
