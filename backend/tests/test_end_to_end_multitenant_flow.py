from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedActor
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.order import Order
from backend.models.reservation import DemoInventoryReservation
from backend.policies.checkout_policy import OrderStatus, PaymentStatus, ReservationStatus
from backend.policies.correction_policy import ApprovalStatus, ExecutionStatus
from backend.schemas.checkout import CreateOrderRequest
from backend.schemas.payment import CapturePaymentRequest
from backend.schemas.proposal import (
    CorrectionProposalApproveRequest,
    CorrectionProposalCreateRequest,
)
from backend.schemas.scan import ScanCreateRequest
from backend.services.audit import AuditService
from backend.services.catalog import CatalogService
from backend.services.checkout import CheckoutService
from backend.services.diagnosis import DiagnosisService
from backend.services.identity import IdentityService
from backend.services.inspection import InspectionService
from backend.services.payment import PaymentService
from backend.services.proposal import ProposalService
from backend.services.remediation import RemediationService


def test_complete_end_to_end_multi_tenant_workflow(db_session: Session):
    """
    Master End-to-End Test executing the complete 13-step PRIP workflow:
    1. Tenant workspace created.
    2. Catalog product created with initial discrepancy.
    3. Inspection detects ISSUE_DETECTED.
    4. AI diagnosis classifies root cause.
    5. Correction proposal generated.
    6. Preflight BLOCKS checkout before correction.
    7. Merchant Owner approves proposal.
    8. Remediation applies approved correction to storefront.
    9. Reinspection verifies VERIFIED_NO_ISSUE.
    10. Preflight PASSES.
    11. PayPal Sandbox order created.
    12. Payment captured and inventory committed.
    13. Universal audit trail verified.
    """
    # 1. Tenant workspace creation
    identity_svc = IdentityService(db_session)
    merchant = identity_svc.create_merchant_workspace(
        actor_id="usr_founder",
        user_id=None,
        email="founder@apex-gear.local",
        name="Apex Gear Athletics",
        slug="apex-gear",
    )
    assert merchant.slug == "apex-gear"
    merchant_id = merchant.id

    owner_actor = AuthenticatedActor(
        actor_id="usr_founder",
        role="OWNER",
        merchant_id=merchant_id,
        email="founder@apex-gear.local",
    )

    # 2. Product creation with storefront discrepancy: Catalog $100.00 vs Storefront $130.00
    catalog_svc = CatalogService(db_session)
    product_resp = catalog_svc.create_product(
        merchant_id=merchant_id,
        sku="APEX-PRO-1",
        title="Apex Pro Carbon Runner",
        price=Decimal("100.00"),
        currency="USD",
        storefront_price=Decimal("130.00"),
        actor_id=owner_actor.actor_id,
    )
    assert product_resp.sku == "APEX-PRO-1"

    # 3. Storefront inspection
    inspection_svc = InspectionService(db_session)
    scan_detail = inspection_svc.run_inspection(
        request=ScanCreateRequest(sku="APEX-PRO-1"),
        trusted_actor=owner_actor,
    )
    assert scan_detail.state == "ISSUE_DETECTED"
    assert scan_detail.is_comparable is True
    assert scan_detail.discrepancy_amount == "+30.00"

    # 4. AI Diagnosis
    diagnosis_svc = DiagnosisService(db_session)
    diag_resp = diagnosis_svc.diagnose_scan(
        scan_id=scan_detail.id,
        trusted_actor=owner_actor,
    )
    assert diag_resp.status.value == "COMPLETED"
    assert diag_resp.scan_id == scan_detail.id

    # 5. Create correction proposal
    proposal_svc = ProposalService(db_session)
    prop_req = CorrectionProposalCreateRequest(
        scan_id=scan_detail.id,
        sku="APEX-PRO-1",
        proposed_value=Decimal("100.00"),
        currency="USD",
        reason="Align storefront price with catalog ground-truth",
        supporting_evidence_ids=diag_resp.supporting_evidence_ids,
    )
    proposal_resp = proposal_svc.create_proposal(
        request=prop_req,
        trusted_actor=owner_actor,
    )
    assert proposal_resp.approval_status == ApprovalStatus.PENDING_APPROVAL.value
    assert proposal_resp.proposed_value == Decimal("100.00")

    # 6. Preflight BLOCKS checkout while discrepancy exists
    mock_paypal = MockPayPalClient()
    checkout_svc = CheckoutService(db_session, paypal_client=mock_paypal)
    preflight_check = checkout_svc.preflight_check(sku="APEX-PRO-1")
    assert preflight_check.passed is False
    assert len(preflight_check.blocking_reasons) > 0

    with pytest.raises(ValueError) as exc_info:
        checkout_svc.create_order(
            CreateOrderRequest(sku="APEX-PRO-1", quantity=1),
            actor_id=owner_actor.actor_id,
            merchant_id=merchant_id,
        )
    assert "Checkout blocked" in str(exc_info.value)

    # 7. Merchant Owner approves proposal
    approve_req = CorrectionProposalApproveRequest(
        reason="Owner verified catalog pricing",
    )
    approved_proposal = proposal_svc.approve_proposal(
        proposal_id=proposal_resp.id,
        request=approve_req,
        trusted_actor=owner_actor,
    )
    assert approved_proposal.approval_status == ApprovalStatus.APPROVED.value

    # 8. Remediation applies approved correction to storefront
    remediation_svc = RemediationService(db_session)
    exec_proposal, followup_scan = remediation_svc.execute_correction(
        proposal_id=proposal_resp.id,
        trusted_actor=owner_actor,
    )
    assert exec_proposal.execution_status == ExecutionStatus.SUCCEEDED.value

    # 9. Post-correction reinspection verifies clean storefront state
    assert followup_scan is not None
    assert followup_scan.state == "VERIFIED_NO_ISSUE"
    assert followup_scan.discrepancy_amount == "+0.00"

    # 10. Preflight now PASSES
    preflight_after = checkout_svc.preflight_check(sku="APEX-PRO-1")
    assert preflight_after.passed is True

    # 11. PayPal Sandbox order created
    order_resp = checkout_svc.create_order(
        CreateOrderRequest(sku="APEX-PRO-1", quantity=1),
        actor_id=owner_actor.actor_id,
        merchant_id=merchant_id,
    )
    assert order_resp.order_id is not None
    assert order_resp.paypal_order_id is not None
    assert order_resp.order_status == OrderStatus.CREATED.value

    # 12. Payment captured and inventory committed
    payment_svc = PaymentService(db_session, paypal_client=mock_paypal)
    cap_resp = payment_svc.capture_payment(
        CapturePaymentRequest(order_id=order_resp.order_id),
        actor_id=owner_actor.actor_id,
        trusted_actor=owner_actor,
    )
    assert cap_resp.status == "COMPLETED"

    # Verify order and inventory commit in database
    db_order = db_session.query(Order).filter(Order.order_id == order_resp.order_id).one()
    assert db_order.payment_status == PaymentStatus.CAPTURED.value
    assert db_order.order_status == OrderStatus.COMPLETED.value

    resv = db_session.query(DemoInventoryReservation).filter(DemoInventoryReservation.order_id == db_order.id).one()
    assert resv.status == ReservationStatus.COMMITTED.value

    # 13. Universal audit trail verified
    audit_events = AuditService.list_events_by_merchant(
        session=db_session,
        merchant_id=merchant_id,
        actor=owner_actor,
    )
    actions = [e.action for e in audit_events]
    assert "CATALOG_PRODUCT_CREATED" in actions
    assert "CORRECTION_APPROVED" in actions
    assert "CORRECTION_EXECUTION_SUCCEEDED" in actions
    assert "ORDER_CREATED" in actions
    assert "PAYMENT_CAPTURED" in actions
