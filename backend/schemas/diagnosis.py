import datetime
import json
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DiagnosisStatus(str, Enum):
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class DiagnosisCreateRequest(BaseModel):
    correlation_id: Optional[str] = Field(default=None, description="Optional request correlation identifier")


class RawDiagnosisPayload(BaseModel):
    """
    Schema-validated structured output expected from an AI model provider.
    Strictly enforced before any diagnosis record can be persisted.
    """
    status: DiagnosisStatus
    summary: str = Field(..., min_length=5, max_length=1500, description="Brief factual summary of diagnosis")
    likely_causes: List[str] = Field(default_factory=list, description="Hypothesized root causes for observation")
    supporting_evidence_ids: List[int] = Field(default_factory=list, description="IDs of evidence items directly grounding diagnosis")
    missing_information: List[str] = Field(default_factory=list, description="Missing observations or facts preventing complete certainty")
    recommended_actions: List[str] = Field(default_factory=list, description="Strictly advisory human operator actions")
    confidence_explanation: str = Field(..., min_length=5, description="Explanation of model confidence and known uncertainties")


class DiagnosisResponse(BaseModel):
    """
    Client-facing response for an AI-assisted diagnostic evaluation.
    Clearly marked as advisory; separated from deterministic inspection states.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: str = "merchant_default"
    scan_id: int
    provider: str
    model: str
    prompt_version: str
    status: DiagnosisStatus
    summary: str
    likely_causes: List[str] = Field(default_factory=list)
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    confidence_explanation: str
    is_advisory: bool = Field(default=True, description="Strictly advisory indicator; zero autonomous execution authority")
    created_at: datetime.datetime

    @classmethod
    def from_orm_model(cls, diagnosis: Any) -> "DiagnosisResponse":
        def parse_json_list(val: Any) -> List[Any]:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return []

        return cls(
            id=diagnosis.id,
            merchant_id=getattr(diagnosis, "merchant_id", None) or "merchant_default",
            scan_id=diagnosis.scan_id,
            provider=diagnosis.provider,
            model=diagnosis.model,
            prompt_version=diagnosis.prompt_version,
            status=DiagnosisStatus(diagnosis.status),
            summary=diagnosis.summary,
            likely_causes=parse_json_list(diagnosis.likely_causes),
            supporting_evidence_ids=parse_json_list(diagnosis.supporting_evidence_ids),
            missing_information=parse_json_list(diagnosis.missing_information),
            recommended_actions=parse_json_list(diagnosis.recommended_actions),
            confidence_explanation=diagnosis.confidence_explanation,
            is_advisory=True,
            created_at=diagnosis.created_at,
        )
