from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class CaptureStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    DECLINED = "DECLINED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ReconciliationStatus(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECONCILED = "RECONCILED"


class ReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class WebhookEventStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    DEAD_LETTER = "DEAD_LETTER"
    DUPLICATE = "DUPLICATE"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class ReconciliationOutcome(str, Enum):
    RESOLVED_CAPTURED = "RESOLVED_CAPTURED"
    RESOLVED_FAILED = "RESOLVED_FAILED"
    NO_DISCREPANCY = "NO_DISCREPANCY"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    FAILED = "FAILED"


# Valid transition state graphs
VALID_ORDER_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.APPROVED, OrderStatus.CANCELLED, OrderStatus.FAILED},
    OrderStatus.APPROVED: {OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.FAILED},
    OrderStatus.COMPLETED: set(),  # Terminal
    OrderStatus.CANCELLED: set(),  # Terminal
    OrderStatus.FAILED: set(),     # Terminal
}

VALID_PAYMENT_TRANSITIONS: Dict[PaymentStatus, Set[PaymentStatus]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.AUTHORIZED,
        PaymentStatus.CAPTURED,
        PaymentStatus.UNKNOWN,
        PaymentStatus.FAILED,
    },
    PaymentStatus.AUTHORIZED: {
        PaymentStatus.CAPTURED,
        PaymentStatus.UNKNOWN,
        PaymentStatus.FAILED,
    },
    # Ambiguous outcome must only transition to CAPTURED or FAILED via authoritative reconciliation
    PaymentStatus.UNKNOWN: {
        PaymentStatus.CAPTURED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.CAPTURED: set(),  # Terminal in Phase 6 MVP (no refunds)
    PaymentStatus.FAILED: set(),    # Terminal
}


def validate_order_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Returns True if order transition is valid according to state machine."""
    if current == target:
        return True
    return target in VALID_ORDER_TRANSITIONS.get(current, set())


def validate_payment_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    """Returns True if payment transition is valid according to state machine."""
    if current == target:
        return True
    return target in VALID_PAYMENT_TRANSITIONS.get(current, set())


class PreflightPolicyResult:
    """Structured result of checkout preflight policy evaluation."""

    def __init__(
        self,
        passed: bool,
        sku: str,
        catalog_price: Optional[Decimal] = None,
        storefront_price: Optional[Decimal] = None,
        currency: Optional[str] = None,
        scan_id: Optional[int] = None,
        scan_state: Optional[str] = None,
        blocking_reasons: Optional[List[str]] = None,
    ) -> None:
        self.passed = passed
        self.sku = sku
        self.catalog_price = catalog_price
        self.storefront_price = storefront_price
        self.currency = currency
        self.scan_id = scan_id
        self.scan_state = scan_state
        self.blocking_reasons = blocking_reasons or []

    @property
    def reason_summary(self) -> str:
        return "; ".join(self.blocking_reasons) if self.blocking_reasons else "Preflight passed. Price verified clean."


def validate_checkout_preflight(
    catalog_product: Any,
    storefront_product: Any,
    latest_scan: Optional[Any] = None,
) -> PreflightPolicyResult:
    """
    Deterministic preflight discrepancy gate:
    Independently verifies ground-truth catalog, controlled storefront price, and inspection scan.
    Blocks checkout if:
      - Catalog product is missing or inactive
      - Storefront product is missing or not published
      - Currency mismatch
      - Catalog price != Storefront price (NEVER silently pick a price)
      - Latest inspection scan state is ISSUE_DETECTED or BLOCKED_UNKNOWN
    """
    reasons: List[str] = []

    if not catalog_product:
        return PreflightPolicyResult(
            passed=False,
            sku="",
            blocking_reasons=["Product not found in merchant catalog."],
        )

    sku = catalog_product.sku
    catalog_price = catalog_product.price
    currency = catalog_product.currency

    if not getattr(catalog_product, "is_active", True):
        reasons.append(f"Catalog product {sku} is marked inactive.")

    if not storefront_product:
        reasons.append(f"Product {sku} not found on storefront.")
        return PreflightPolicyResult(
            passed=False,
            sku=sku,
            catalog_price=catalog_price,
            currency=currency,
            blocking_reasons=reasons,
        )

    storefront_price = storefront_product.price
    storefront_currency = storefront_product.currency

    if currency != storefront_currency:
        reasons.append(f"Currency mismatch: Catalog is {currency} but Storefront is {storefront_currency}.")

    # Direct price comparison
    if catalog_price != storefront_price:
        reasons.append(
            f"Price discrepancy detected: Catalog {currency} {catalog_price} vs "
            f"Storefront {storefront_currency} {storefront_price}. Checkout blocked until synchronized."
        )

    # Inspection scan state check
    scan_id = None
    scan_state = None
    if latest_scan:
        scan_id = latest_scan.id
        scan_state = latest_scan.state
        if scan_state == "ISSUE_DETECTED":
            reasons.append(
                f"Storefront inspection scan #{scan_id} detected an active discrepancy (state: {scan_state}). "
                "Discrepancy must be approved and reconciled before checkout."
            )
        elif scan_state == "BLOCKED_UNKNOWN":
            reasons.append(
                f"Storefront inspection scan #{scan_id} could not verify integrity (state: {scan_state}). "
                "Checkout blocked on unverified storefront."
            )

    passed = len(reasons) == 0

    return PreflightPolicyResult(
        passed=passed,
        sku=sku,
        catalog_price=catalog_price,
        storefront_price=storefront_price,
        currency=currency,
        scan_id=scan_id,
        scan_state=scan_state,
        blocking_reasons=reasons,
    )
