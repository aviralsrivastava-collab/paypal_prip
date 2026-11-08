"""
Diagnosis Validation Policy
===========================
Deterministic validation rules enforcing AI output constraints:
1. Evidence-grounding check: All supporting_evidence_ids must exist in the inspection scan.
2. Authority boundary check: Rejects any recommendation that attempts prohibited state mutations
   (e.g., executing payments, modifying catalog/storefront directly, altering inspection states).
3. Insufficient-evidence rule: If status is INSUFFICIENT_EVIDENCE, missing_information must be declared.
"""

from typing import Set

from backend.schemas.diagnosis import DiagnosisStatus, RawDiagnosisPayload

PROHIBITED_ACTION_TERMS = [
    "capture payment",
    "execute payment",
    "initiate payment",
    "refund",
    "reconcile payment",
    "charge card",
    "change inspection state",
    "override inspection state",
    "override state",
    "set state",
    "override comparability",
    "mutate catalog",
    "modify catalog directly",
    "bypass merchant approval",
    "approve correction automatically",
]


class DiagnosisValidationError(ValueError):
    """Raised when an AI-generated diagnosis violates structural or authority policies."""

    pass


def validate_diagnosis_payload(
    payload: RawDiagnosisPayload,
    allowed_evidence_ids: Set[int],
) -> None:
    """
    Validates that the AI model output respects all PRIP authority and grounding constraints.
    Rejects malformed outputs or rule violations rather than guessing or silently repairing.
    """
    # 1. Grounding check: verify that all referenced evidence IDs are real and observed
    for ev_id in payload.supporting_evidence_ids:
        if ev_id not in allowed_evidence_ids:
            raise DiagnosisValidationError(
                f"Grounding violation: supporting evidence ID {ev_id} is unknown or was not observed in this scan. "
                f"Allowed IDs: {sorted(list(allowed_evidence_ids))}"
            )

    # 2. Authority boundary check: verify recommendations are strictly advisory and do not attempt mutations
    for action in payload.recommended_actions:
        action_lower = action.lower()
        for prohibited in PROHIBITED_ACTION_TERMS:
            if prohibited in action_lower:
                raise DiagnosisValidationError(
                    f"Authority boundary violation: recommended action '{action}' attempts prohibited domain mutation "
                    f"matching rule '{prohibited}'. AI recommendations must be strictly advisory."
                )

    # 3. Completeness check for inconclusive diagnoses
    if payload.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE:
        if not payload.missing_information:
            raise DiagnosisValidationError(
                "Incomplete diagnosis: status is INSUFFICIENT_EVIDENCE, but missing_information was not specified."
            )
