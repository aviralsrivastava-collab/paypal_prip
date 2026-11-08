from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class CatalogProductFacts:
    sku: str
    title: str
    price: Decimal
    currency: str
    availability: str = "IN_STOCK"
    variant: Optional[str] = None
    market: str = "US"
    price_basis: str = "LIST_PRICE"


@dataclass
class StorefrontObservationFacts:
    sku: Optional[str]
    title: Optional[str]
    price: Optional[Decimal]
    currency: Optional[str]
    availability: Optional[str] = None
    variant: Optional[str] = None
    market: Optional[str] = "US"
    price_basis: Optional[str] = "LIST_PRICE"
    promotion_context: Optional[str] = None


@dataclass
class ComparabilityResult:
    is_comparable: bool
    comparability_reasons: List[str] = field(default_factory=list)
    checked_dimensions: Dict[str, bool] = field(default_factory=dict)
    price_discrepancy: Optional[Decimal] = None
    has_discrepancy: bool = False


def evaluate_comparability(
    catalog: CatalogProductFacts,
    observed: StorefrontObservationFacts,
) -> ComparabilityResult:
    """
    Pure deterministic comparability evaluator.
    Evaluates:
    1. Product Identity / SKU match
    2. Currency match
    3. Price presence and validity
    4. Variant match (if specified)
    5. Price basis match
    6. Promotion context
    7. Availability match
    """
    reasons: List[str] = []
    checked: Dict[str, bool] = {}

    # 1. Product Identity / SKU
    if not observed.sku:
        reasons.append("MISSING_PRODUCT_IDENTITY: Observed storefront product has no identifiable SKU.")
        checked["identity"] = False
    elif observed.sku.strip().upper() != catalog.sku.strip().upper():
        reasons.append(
            f"SKU_MISMATCH: Catalog SKU '{catalog.sku}' does not match observed storefront SKU '{observed.sku}'."
        )
        checked["identity"] = False
    else:
        checked["identity"] = True

    # 2. Currency Equality
    if not observed.currency:
        reasons.append("MISSING_CURRENCY: Observed storefront product has no currency specified.")
        checked["currency"] = False
    elif observed.currency.strip().upper() != catalog.currency.strip().upper():
        reasons.append(
            f"CURRENCY_MISMATCH: Catalog currency '{catalog.currency}' does not match observed currency '{observed.currency}'."
        )
        checked["currency"] = False
    else:
        checked["currency"] = True

    # 3. Price Presence
    if observed.price is None:
        reasons.append("MISSING_PRICE: Observed storefront product does not display a valid price.")
        checked["price_presence"] = False
    else:
        checked["price_presence"] = True

    # 4. Variant Comparability
    if catalog.variant or observed.variant:
        if (catalog.variant or "").strip().lower() != (observed.variant or "").strip().lower():
            reasons.append(
                f"VARIANT_MISMATCH: Catalog variant '{catalog.variant}' does not match observed variant '{observed.variant}'."
            )
            checked["variant"] = False
        else:
            checked["variant"] = True
    else:
        checked["variant"] = True

    # 5. Price Basis Comparability
    if catalog.price_basis and observed.price_basis:
        if catalog.price_basis.strip().upper() != observed.price_basis.strip().upper():
            reasons.append(
                f"PRICE_BASIS_MISMATCH: Catalog price basis '{catalog.price_basis}' differs from storefront basis '{observed.price_basis}'."
            )
            checked["price_basis"] = False
        else:
            checked["price_basis"] = True
    else:
        checked["price_basis"] = True

    # 6. Promotion Context
    if observed.promotion_context:
        # If storefront has an unverified active promotion that could explain difference
        reasons.append(
            f"AMBIGUOUS_PROMOTION_CONTEXT: Storefront reports active promotion '{observed.promotion_context}' which may explain difference."
        )
        checked["promotion"] = False
    else:
        checked["promotion"] = True

    # 7. Availability
    if catalog.availability and observed.availability:
        checked["availability"] = (
            catalog.availability.strip().upper() == observed.availability.strip().upper()
        )
    else:
        checked["availability"] = True

    is_comparable = len(reasons) == 0

    price_discrepancy: Optional[Decimal] = None
    has_discrepancy = False

    if is_comparable and observed.price is not None:
        price_discrepancy = observed.price - catalog.price
        has_discrepancy = price_discrepancy != Decimal("0.00")

    return ComparabilityResult(
        is_comparable=is_comparable,
        comparability_reasons=reasons,
        checked_dimensions=checked,
        price_discrepancy=price_discrepancy,
        has_discrepancy=has_discrepancy,
    )
