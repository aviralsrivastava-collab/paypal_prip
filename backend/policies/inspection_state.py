from enum import Enum
from typing import Optional


class InspectionState(str, Enum):
    """
    Mandatory four-state inspection model for PRIP.
    Strict Invariant: BLOCKED_UNKNOWN must NEVER silently become VERIFIED_NO_ISSUE.
    Missing evidence must never be interpreted as evidence of correctness.
    """

    ISSUE_DETECTED = "ISSUE_DETECTED"
    VERIFIED_NO_ISSUE = "VERIFIED_NO_ISSUE"
    BLOCKED_UNKNOWN = "BLOCKED_UNKNOWN"
    NOT_TESTED = "NOT_TESTED"


def classify_outcome(
    extraction_successful: bool,
    is_comparable: bool,
    discrepancy_detected: bool,
    extraction_error: Optional[str] = None,
) -> InspectionState:
    """
    Deterministic four-state classifier.

    Rules:
    1. If extraction failed, timed out, or had errors -> BLOCKED_UNKNOWN.
    2. If observations are not comparable -> BLOCKED_UNKNOWN.
    3. If extraction succeeded, comparability passed, and discrepancy detected -> ISSUE_DETECTED.
    4. If extraction succeeded, comparability passed, and NO discrepancy detected -> VERIFIED_NO_ISSUE.
    """
    if not extraction_successful or extraction_error:
        return InspectionState.BLOCKED_UNKNOWN

    if not is_comparable:
        return InspectionState.BLOCKED_UNKNOWN

    if discrepancy_detected:
        return InspectionState.ISSUE_DETECTED

    return InspectionState.VERIFIED_NO_ISSUE
