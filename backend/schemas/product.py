import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50, description="Stock Keeping Unit")
    title: str = Field(..., min_length=1, max_length=200, description="Product Title")
    description: Optional[str] = Field(default=None, description="Product description")
    price: Decimal = Field(..., gt=Decimal("0.00"), description="Merchant-authorized price")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 Currency Code")
    availability: str = Field(default="IN_STOCK", description="Availability status")

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


class ProductCreate(ProductBase):
    storefront_price: Optional[Decimal] = Field(default=None, description="Initial controlled storefront price")


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=Decimal("0.00"))
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    availability: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        upper_v = v.upper().strip()
        if upper_v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Currency '{v}' is not supported. Must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return upper_v

    @field_validator("price")
    @classmethod
    def validate_monetary_precision(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return None
        exp = v.as_tuple().exponent
        if isinstance(exp, int) and exp < -2:
            raise ValueError(f"Monetary price '{v}' cannot exceed 2 decimal places of precision")
        if v <= Decimal("0.00"):
            raise ValueError("Price must be greater than zero")
        return v


class StorefrontPriceUpdate(BaseModel):
    price: Decimal = Field(..., gt=Decimal("0.00"), description="Controlled storefront price")
    currency: str = Field(default="USD", min_length=3, max_length=3)

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


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: str = "merchant_default"
    sku: str
    title: str
    description: Optional[str] = None
    price: str
    currency: str
    availability: str
    source_version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_orm_model(cls, product: Any) -> "ProductResponse":
        return cls(
            id=product.id,
            merchant_id=getattr(product, "merchant_id", "merchant_default"),
            sku=product.sku,
            title=product.title,
            description=product.description,
            price=f"{product.price:.2f}",
            currency=product.currency,
            availability=product.availability,
            source_version=product.source_version,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class ProductComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: str = "merchant_default"
    sku: str
    title: str
    description: Optional[str] = None
    merchant_price: str
    merchant_currency: str
    storefront_price: Optional[str] = None
    storefront_currency: Optional[str] = None
    price_discrepancy: Optional[str] = None
    has_discrepancy: bool
    is_comparable: bool = True
    comparability_reason: Optional[str] = None
    availability: str
    source_version: int
    storefront_version: Optional[int] = None
    updated_at: datetime.datetime
