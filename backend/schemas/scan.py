import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.policies.inspection_state import InspectionState


class ScanCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50, description="Product SKU to inspect")
    correlation_id: Optional[str] = Field(default=None, description="Optional request correlation ID")
    idempotency_key: Optional[str] = Field(default=None, max_length=100, description="Optional idempotency key")
    simulated_scenario: Optional[str] = Field(
        default=None,
        description="Optional fault-injection scenario for testing (timeout, missing, blocked, unsupported)",
    )


class EvidenceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: str = "merchant_default"
    scan_id: int
    evidence_type: str
    field_name: str
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    source_url: str
    observation_timestamp: datetime.datetime
    content_hash: Optional[str] = None
    status: str
    details: Optional[str] = None
    integrity_verified: bool = Field(default=True, description="Whether stored content matches canonical SHA-256 hash")
    created_at: datetime.datetime

    @classmethod
    def from_orm_model(cls, item: Any) -> "EvidenceItemResponse":
        from backend.policies.evidence_integrity import verify_evidence_hash

        return cls(
            id=item.id,
            merchant_id=getattr(item, "merchant_id", None) or "merchant_default",
            scan_id=item.scan_id,
            evidence_type=item.evidence_type,
            field_name=item.field_name,
            expected_value=item.expected_value,
            observed_value=item.observed_value,
            source_url=item.source_url,
            observation_timestamp=item.observation_timestamp,
            content_hash=item.content_hash,
            status=item.status,
            details=item.details,
            integrity_verified=verify_evidence_hash(item),
            created_at=item.created_at,
        )


class ScanSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: str = "merchant_default"
    product_id: int
    sku: str
    source_version: int
    state: InspectionState
    is_comparable: bool
    catalog_price: Optional[str] = None
    observed_price: Optional[str] = None
    currency: Optional[str] = None
    discrepancy_amount: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime.datetime

    @classmethod
    def from_orm_model(cls, scan: Any) -> "ScanSummaryResponse":
        return cls(
            id=scan.id,
            merchant_id=getattr(scan, "merchant_id", "merchant_default"),
            product_id=scan.product_id,
            sku=scan.sku,
            source_version=scan.source_version,
            state=InspectionState(scan.state),
            is_comparable=scan.is_comparable,
            catalog_price=f"{scan.catalog_price:.2f}" if scan.catalog_price is not None else None,
            observed_price=f"{scan.observed_price:.2f}" if scan.observed_price is not None else None,
            currency=scan.currency,
            discrepancy_amount=f"{scan.discrepancy_amount:+.2f}" if scan.discrepancy_amount is not None else None,
            idempotency_key=getattr(scan, "idempotency_key", None),
            created_at=scan.created_at,
        )


class ScanDetailResponse(ScanSummaryResponse):
    url: str
    failure_reason: Optional[str] = None
    correlation_id: str
    comparability_reasons: List[str] = Field(default_factory=list)
    evidence_items: List[EvidenceItemResponse] = Field(default_factory=list)

    @classmethod
    def from_orm_model_with_evidence(
        cls,
        scan: Any,
        evidence_items: List[Any],
        comparability_reasons: Optional[List[str]] = None,
    ) -> "ScanDetailResponse":
        return cls(
            id=scan.id,
            merchant_id=getattr(scan, "merchant_id", "merchant_default"),
            product_id=scan.product_id,
            sku=scan.sku,
            source_version=scan.source_version,
            state=InspectionState(scan.state),
            is_comparable=scan.is_comparable,
            catalog_price=f"{scan.catalog_price:.2f}" if scan.catalog_price is not None else None,
            observed_price=f"{scan.observed_price:.2f}" if scan.observed_price is not None else None,
            currency=scan.currency,
            discrepancy_amount=f"{scan.discrepancy_amount:+.2f}" if scan.discrepancy_amount is not None else None,
            idempotency_key=getattr(scan, "idempotency_key", None),
            created_at=scan.created_at,
            url=scan.url,
            failure_reason=scan.failure_reason,
            correlation_id=scan.correlation_id,
            comparability_reasons=comparability_reasons or [],
            evidence_items=[EvidenceItemResponse.from_orm_model(item) for item in evidence_items],
        )
