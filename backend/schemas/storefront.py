import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.product import SUPPORTED_CURRENCIES


class StorefrontProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    title: str
    price: str
    currency: str
    availability: str
    url_path: str
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_orm_model(cls, product: Any) -> "StorefrontProductResponse":
        return cls(
            id=product.id,
            sku=product.sku,
            title=product.title,
            price=f"{product.price:.2f}",
            currency=product.currency,
            availability=product.availability,
            url_path=product.url_path,
            version=product.version,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class StorefrontUpdatePriceRequest(BaseModel):
    price: Decimal = Field(..., gt=Decimal("0.00"), description="Updated storefront price")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 Currency Code")
    actor_id: Optional[str] = Field(default=None, max_length=100, description="Untrusted client actor hint (overridden by server auth)")
    expected_version: int = Field(..., ge=1, description="Optimistic locking expected version")
    reason: Optional[str] = Field(default="Storefront price correction", description="Audit justification")
    correlation_id: Optional[str] = Field(default=None, description="Request correlation identifier")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        upper_v = v.upper().strip()
        if upper_v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Currency '{v}' is not supported. Must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return upper_v

    @field_validator("price")
    @classmethod
    def validate_monetary_precision(cls, v: Decimal) -> Decimal:
        exp = v.as_tuple().exponent
        if isinstance(exp, int) and exp < -2:
            raise ValueError(f"Monetary price '{v}' cannot exceed 2 decimal places of precision")
        if v <= Decimal("0.00"):
            raise ValueError("Price must be greater than zero")
        return v
