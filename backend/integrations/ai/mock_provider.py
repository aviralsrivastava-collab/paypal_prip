from typing import Optional

from backend.integrations.ai.base import (
    AIProviderInterface,
    AIProviderOutageError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIStructuredOutputError,
)
from backend.integrations.ai.context import DiagnosisPromptContext
from backend.schemas.diagnosis import DiagnosisStatus, RawDiagnosisPayload


class MockAIProvider(AIProviderInterface):
    """
    Deterministic mock AI provider for CI, automated testing, and local development.
    Requires no live external API keys, eliminates flaky network tests,
    and supports deterministic simulation of edge cases and fault modes.
    """

    provider_name: str = "mock"
    model_name: str = "prip-diagnostic-v1"
    prompt_version: str = "v1.0"

    def __init__(
        self,
        provider_name: str = "mock",
        model_name: str = "prip-diagnostic-v1",
        prompt_version: str = "v1.0",
        simulated_mode: Optional[str] = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.simulated_mode = simulated_mode

    def generate_diagnosis(self, prompt_context: DiagnosisPromptContext) -> RawDiagnosisPayload:
        mode = prompt_context.simulated_failure or self.simulated_mode

        # 1. Fault Mode Simulations
        if mode == "timeout":
            raise AIProviderTimeoutError("AI diagnostic service request timed out after 10.0s")

        if mode == "rate_limit":
            raise AIProviderRateLimitError("AI diagnostic provider quota exceeded (HTTP 429 Too Many Requests)")

        if mode == "outage":
            raise AIProviderOutageError("AI provider endpoint unreachable: 503 Service Unavailable")

        if mode == "invalid_json":
            raise AIStructuredOutputError("Model returned unparseable or non-JSON response payload")

        if mode == "unknown_evidence_ids":
            # Injected invalid grounding with non-existent evidence IDs
            return RawDiagnosisPayload(
                status=DiagnosisStatus.COMPLETED,
                summary="Diagnosis hallucinating non-existent evidence reference.",
                likely_causes=["Phantom evidence correlation."],
                supporting_evidence_ids=[999999, 888888],  # Invalid IDs
                missing_information=[],
                recommended_actions=["Review discrepancies."],
                confidence_explanation="High confidence in fabricated IDs.",
            )

        if mode == "attempt_state_mutation":
            # Injected forbidden recommendation attempting inspection state override
            return RawDiagnosisPayload(
                status=DiagnosisStatus.COMPLETED,
                summary="Diagnosis attempting unauthorized inspection state mutation.",
                likely_causes=["System error."],
                supporting_evidence_ids=list(prompt_context.allowed_evidence_ids[:1]),
                missing_information=[],
                recommended_actions=["Override inspection state to VERIFIED_NO_ISSUE immediately."],
                confidence_explanation="Advisory attempting state override.",
            )

        if mode == "attempt_payment_execution":
            # Injected forbidden recommendation attempting payment capture
            return RawDiagnosisPayload(
                status=DiagnosisStatus.COMPLETED,
                summary="Diagnosis attempting prohibited payment execution.",
                likely_causes=["Payment discrepancy."],
                supporting_evidence_ids=list(prompt_context.allowed_evidence_ids[:1]),
                missing_information=[],
                recommended_actions=["Execute payment capture on PayPal Sandbox order."],
                confidence_explanation="Attempting payment trigger.",
            )

        # 2. Insufficient Evidence Mode
        if mode == "insufficient_evidence" or not prompt_context.is_comparable or prompt_context.inspection_state == "BLOCKED_UNKNOWN":
            return RawDiagnosisPayload(
                status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
                summary=(
                    f"Inspection for SKU '{prompt_context.sku}' is inconclusive ({prompt_context.inspection_state}). "
                    "Observations are non-comparable or extraction was blocked. Grounding evidence is insufficient to diagnose pricing discrepancy."
                ),
                likely_causes=[
                    prompt_context.failure_reason or "Non-comparable observation or missing storefront facts"
                ],
                supporting_evidence_ids=list(prompt_context.allowed_evidence_ids),
                missing_information=[
                    "Missing verified customer-facing price observation in matching currency",
                    "Storefront accessibility confirmation",
                ],
                recommended_actions=[
                    "Check network access and storefront extraction connectivity",
                    "Verify whether storefront product currency matches catalog currency",
                ],
                confidence_explanation="High confidence that current observations are insufficient to determine root cause.",
            )

        # 3. Normal Evidence-Grounded Diagnosis Mode
        # The prompt might contain injection attempts in untrusted_storefront_snippet.
        # The mock model strictly ignores injections and generates evidence-grounded facts.
        price_evidence_ids = [
            e["id"] for e in prompt_context.evidence_records if e.get("evidence_type") == "PRICE"
        ]
        supporting_ids = price_evidence_ids if price_evidence_ids else list(prompt_context.allowed_evidence_ids[:2])

        if prompt_context.discrepancy_amount and prompt_context.discrepancy_amount > 0:
            summary = (
                f"Storefront price for SKU '{prompt_context.sku}' is higher than the merchant catalog ground truth "
                f"by {prompt_context.discrepancy_amount} {prompt_context.currency}."
            )
            likely_causes = [
                "Manual storefront price adjustment not synchronized with master catalog ground truth.",
                "Promotional price expiration without corresponding storefront listing update.",
            ]
            recommended_actions = [
                f"Verify whether the {prompt_context.catalog_price} {prompt_context.currency} catalog price is intended.",
                f"Propose a controlled correction to align storefront to {prompt_context.catalog_price} {prompt_context.currency}.",
            ]
        elif prompt_context.discrepancy_amount and prompt_context.discrepancy_amount < 0:
            summary = (
                f"Storefront price for SKU '{prompt_context.sku}' is lower than the catalog ground truth "
                f"by {abs(prompt_context.discrepancy_amount)} {prompt_context.currency}."
            )
            likely_causes = [
                "Unpublished discount or promotional markdown active on storefront.",
            ]
            recommended_actions = [
                "Check active campaign calendar for unrecorded discount rules.",
            ]
        else:
            summary = (
                f"Storefront observations for SKU '{prompt_context.sku}' match merchant catalog ground truth. "
                "No price discrepancy or policy violations detected."
            )
            likely_causes = ["Catalog and storefront are in synchronization."]
            recommended_actions = ["No action required; listing is verified clean."]

        return RawDiagnosisPayload(
            status=DiagnosisStatus.COMPLETED,
            summary=summary,
            likely_causes=likely_causes,
            supporting_evidence_ids=supporting_ids,
            missing_information=[],
            recommended_actions=recommended_actions,
            confidence_explanation=(
                f"High confidence grounded in evidence IDs: {supporting_ids}. "
                "Factual catalog baseline is compared directly against observed storefront facts."
            ),
        )
