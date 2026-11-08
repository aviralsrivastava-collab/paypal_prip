"""
PRIP Backend Policies Module
============================
Deterministic business rule evaluators and validation gates.
"""

from backend.policies.checkout_policy import (
    CaptureStatus,
    OrderStatus,
    PaymentStatus,
    PreflightPolicyResult,
    ReconciliationStatus,
    ReservationStatus,
    WebhookEventStatus,
    validate_checkout_preflight,
    validate_order_transition,
    validate_payment_transition,
)
from backend.policies.comparability import (
    CatalogProductFacts,
    ComparabilityResult,
    StorefrontObservationFacts,
    evaluate_comparability,
)
from backend.policies.correction_policy import (
    SUPPORTED_PROPOSAL_TYPES,
    ApprovalStatus,
    CorrectionPolicyResult,
    ExecutionStatus,
    PolicyValidationStatus,
    validate_correction_proposal,
    validate_execution_lifecycle_transition,
    validate_proposal_lifecycle_transition,
)
from backend.policies.diagnosis_validator import (
    DiagnosisValidationError,
    validate_diagnosis_payload,
)
from backend.policies.evidence_integrity import (
    compute_evidence_hash,
    compute_request_hash,
    verify_evidence_hash,
)
from backend.policies.inspection_state import InspectionState, classify_outcome

__all__ = [
    "CatalogProductFacts",
    "StorefrontObservationFacts",
    "ComparabilityResult",
    "evaluate_comparability",
    "InspectionState",
    "classify_outcome",
    "compute_evidence_hash",
    "compute_request_hash",
    "verify_evidence_hash",
    "DiagnosisValidationError",
    "validate_diagnosis_payload",
    "ApprovalStatus",
    "ExecutionStatus",
    "PolicyValidationStatus",
    "SUPPORTED_PROPOSAL_TYPES",
    "CorrectionPolicyResult",
    "validate_correction_proposal",
    "validate_proposal_lifecycle_transition",
    "validate_execution_lifecycle_transition",
    "OrderStatus",
    "PaymentStatus",
    "CaptureStatus",
    "ReconciliationStatus",
    "ReservationStatus",
    "WebhookEventStatus",
    "PreflightPolicyResult",
    "validate_checkout_preflight",
    "validate_order_transition",
    "validate_payment_transition",
]
