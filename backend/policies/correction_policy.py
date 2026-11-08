import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Set


class ApprovalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class PolicyValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


SUPPORTED_PROPOSAL_TYPES: Set[str] = {"PRICE_SYNCHRONIZATION"}


class CorrectionPolicyResult:
    """Structured result of deterministic correction policy validation."""

    def __init__(
        self,
        is_valid: bool,
        status: PolicyValidationStatus,
        errors: Optional[List[str]] = None,
    ) -> None:
        self.is_valid = is_valid
        self.status = status
        self.errors = errors or []

    @property
    def error_summary(self) -> str:
        return "; ".join(self.errors) if self.errors else "Policy validation passed."


def validate_proposal_lifecycle_transition(
    current_approval: ApprovalStatus,
    target_approval: ApprovalStatus,
) -> bool:
    """
    Validates legal approval state transitions.
    Terminal states: REJECTED, EXPIRED, CANCELLED cannot transition.
    APPROVED cannot be re-approved.
    """
    if current_approval == ApprovalStatus.PENDING_APPROVAL:
        return target_approval in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    return False


def validate_execution_lifecycle_transition(
    current_execution: ExecutionStatus,
    target_execution: ExecutionStatus,
) -> bool:
    """
    Validates legal execution state transitions.
    SUCCEEDED is terminal; a succeeded correction cannot be executed again.
    """
    if current_execution == ExecutionStatus.NOT_STARTED:
        return target_execution in {ExecutionStatus.IN_PROGRESS}
    if current_execution == ExecutionStatus.IN_PROGRESS:
        return target_execution in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.RECONCILIATION_REQUIRED,
        }
    if current_execution == ExecutionStatus.RECONCILIATION_REQUIRED:
        return target_execution in {
            ExecutionStatus.IN_PROGRESS,
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
        }
    return False


def validate_correction_proposal(
    sku: str,
    proposal_type: str,
    proposed_value: Decimal,
    currency: str,
    supporting_evidence_ids: List[int],
    catalog_sku: str,
    catalog_price: Optional[Decimal],
    catalog_currency: Optional[str],
    storefront_sku: str,
    storefront_price: Optional[Decimal],
    storefront_currency: Optional[str],
    inspection_state: str,
    is_comparable: bool,
    available_evidence_ids: Set[int],
    expected_catalog_version: int,
    current_catalog_version: int,
    expected_storefront_version: int,
    current_storefront_version: int,
    expires_at: Optional[datetime.datetime] = None,
    current_time: Optional[datetime.datetime] = None,
    execution_status: ExecutionStatus = ExecutionStatus.NOT_STARTED,
) -> CorrectionPolicyResult:
    """
    Pure deterministic validation of a proposed storefront correction.
    Validates 12 mandatory conditions independently of AI.
    """
    errors: List[str] = []
    now = current_time or datetime.datetime.now(datetime.timezone.utc)

    # 1. Proposal type allowlist
    if proposal_type not in SUPPORTED_PROPOSAL_TYPES:
        errors.append(f"Unsupported proposal type '{proposal_type}'. Allowed types: {SUPPORTED_PROPOSAL_TYPES}")
        return CorrectionPolicyResult(False, PolicyValidationStatus.INVALID, errors)

    # 2. Product identity and SKU match
    if sku != catalog_sku or sku != storefront_sku:
        errors.append(f"SKU mismatch: proposal '{sku}', catalog '{catalog_sku}', storefront '{storefront_sku}'")

    # 3. Catalog price and currency available
    if catalog_price is None or catalog_currency is None:
        errors.append("Catalog ground truth price or currency is missing.")

    # 4. Storefront price and currency available
    if storefront_price is None or storefront_currency is None:
        errors.append("Storefront observation price or currency is missing.")

    # 5. Currency comparability
    if catalog_currency and storefront_currency and catalog_currency != storefront_currency:
        errors.append(f"Currency mismatch: catalog {catalog_currency} != storefront {storefront_currency}")
        return CorrectionPolicyResult(False, PolicyValidationStatus.BLOCKED, errors)

    if currency != catalog_currency:
        errors.append(f"Proposal currency '{currency}' does not match catalog currency '{catalog_currency}'")

    # 6. Proposed price validity (positive, monetary precision <= 2 decimals)
    if proposed_value <= Decimal("0.00"):
        errors.append("Proposed price must be greater than zero.")
    exp = proposed_value.as_tuple().exponent
    if isinstance(exp, int) and exp < -2:
        errors.append("Proposed price precision cannot exceed 2 decimal places.")

    # 7. Configured merchant constraints (for PRICE_SYNCHRONIZATION: proposed_value must equal catalog price)
    if catalog_price is not None and proposed_value != catalog_price:
        errors.append(f"Proposed price {proposed_value} must match authoritative catalog price {catalog_price}")

    # 8. Supporting evidence validation
    if not supporting_evidence_ids:
        errors.append("Proposal must reference at least one valid supporting evidence record.")
    for ev_id in supporting_evidence_ids:
        if ev_id not in available_evidence_ids:
            errors.append(f"Referenced evidence ID {ev_id} is not present in the inspection scan.")

    # 9. Inspection outcome check
    if inspection_state != "ISSUE_DETECTED":
        errors.append(f"Inspection state '{inspection_state}' does not permit correction (must be ISSUE_DETECTED).")
    if not is_comparable:
        errors.append("Scan observations are not comparable; corrections are blocked.")
        return CorrectionPolicyResult(False, PolicyValidationStatus.BLOCKED, errors)

    # 10. Execution state check
    if execution_status != ExecutionStatus.NOT_STARTED and execution_status != ExecutionStatus.RECONCILIATION_REQUIRED:
        errors.append(f"Proposal has already been processed with execution status {execution_status.value}.")

    # 11. Expiration check
    if expires_at and now >= expires_at:
        errors.append(f"Proposal expired at {expires_at.isoformat()}. Current time is {now.isoformat()}.")
        return CorrectionPolicyResult(False, PolicyValidationStatus.STALE, errors)

    # 12. Optimistic concurrency version check
    if expected_catalog_version != current_catalog_version:
        errors.append(
            f"Catalog version mismatch: expected {expected_catalog_version}, current {current_catalog_version}"
        )
        return CorrectionPolicyResult(False, PolicyValidationStatus.STALE, errors)

    if expected_storefront_version != current_storefront_version:
        errors.append(
            f"Storefront version mismatch: expected {expected_storefront_version}, current {current_storefront_version}"
        )
        return CorrectionPolicyResult(False, PolicyValidationStatus.STALE, errors)

    if errors:
        return CorrectionPolicyResult(False, PolicyValidationStatus.INVALID, errors)

    return CorrectionPolicyResult(True, PolicyValidationStatus.VALID, [])
