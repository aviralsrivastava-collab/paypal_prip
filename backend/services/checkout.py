import datetime
import json
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.integrations.paypal import PayPalClientInterface, get_paypal_client
from backend.models.order import Order
from backend.models.reservation import DemoInventoryReservation
from backend.policies.checkout_policy import (
    OrderStatus,
    PaymentStatus,
    ReservationStatus,
    validate_checkout_preflight,
)
from backend.repositories.merchant import MerchantRepository
from backend.repositories.order import OrderRepository
from backend.repositories.product import ProductRepository
from backend.repositories.reservation import ReservationRepository
from backend.repositories.scan import ScanRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.checkout import (
    CreateOrderRequest,
    OrderResponse,
    PreflightCheckResponse,
)
from backend.services.audit import AuditService


class CheckoutService:
    """
    Checkout business service.
    Orchestrates preflight discrepancy gating, inventory reservation,
    local order creation, and PayPal Orders v2 external integration.
    Guarantees that external PayPal calls occur OUTSIDE open database transactions.
    """

    def __init__(
        self,
        session: Session,
        paypal_client: Optional[PayPalClientInterface] = None,
    ) -> None:
        self.session = session
        self.paypal_client = paypal_client or get_paypal_client()
        self.product_repo = ProductRepository(session)
        self.storefront_repo = StorefrontRepository(session)
        self.scan_repo = ScanRepository(session)
        self.order_repo = OrderRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.merchant_repo = MerchantRepository(session)

    def preflight_check(self, sku: str) -> PreflightCheckResponse:
        """
        Runs deterministic preflight policy against ground-truth catalog,
        controlled storefront, and latest inspection scan.
        """
        catalog_product = self.product_repo.get_by_sku(sku)
        storefront_product = self.storefront_repo.get_by_sku(sku)
        latest_scan = self.scan_repo.get_latest_by_sku(sku)

        result = validate_checkout_preflight(
            catalog_product=catalog_product,
            storefront_product=storefront_product,
            latest_scan=latest_scan,
        )

        return PreflightCheckResponse(
            passed=result.passed,
            sku=sku,
            catalog_price=result.catalog_price,
            storefront_price=result.storefront_price,
            currency=result.currency,
            scan_id=result.scan_id,
            scan_state=result.scan_state,
            blocking_reasons=result.blocking_reasons,
            message=result.reason_summary,
        )

    def create_order(
        self,
        request: CreateOrderRequest,
        actor_id: str = "MERCHANT",
        actor_type: str = "MERCHANT",
        merchant_id: Optional[str] = None,
    ) -> OrderResponse:
        """
        Creates an order after passing preflight discrepancy gate.
        Calls PayPal Orders v2 outside database transactions, then commits
        local order, reservation, and audit event atomically.
        """
        # 1. Enforce preflight check gate
        preflight = self.preflight_check(request.sku)
        if not preflight.passed:
            raise ValueError(f"Checkout blocked: {preflight.message}")

        # 2. Check database-backed idempotency
        if request.idempotency_key:
            existing_order = self.order_repo.get_by_idempotency_key(str(request.idempotency_key))
            if existing_order:
                return OrderResponse.model_validate(existing_order)

        catalog_product = self.product_repo.get_by_sku(request.sku)
        if not catalog_product:
            raise ValueError(f"Product {request.sku} not found")

        resolved_merchant_id: str = str(merchant_id or catalog_product.merchant_id or "merchant_default")
        if merchant_id and catalog_product.merchant_id and merchant_id != str(catalog_product.merchant_id):
            raise ValueError(f"Merchant mismatch: order merchant '{merchant_id}' does not match product merchant '{catalog_product.merchant_id}'")

        total_amount = Decimal(str(catalog_product.price)) * Decimal(str(request.quantity))
        local_order_id = f"prip_ord_{uuid.uuid4().hex[:12]}"
        correlation_id = f"corr_{uuid.uuid4().hex[:12]}"

        # Resolve merchant payee routing only if partner permissions are confirmed/enabled
        from backend.core.config import get_settings
        settings = get_settings()
        payee_merchant_id: Optional[str] = None
        if settings.paypal_enable_payee_routing:
            merchant_record = self.merchant_repo.get_by_id(str(resolved_merchant_id))
            if merchant_record and merchant_record.paypal_merchant_id:
                payee_merchant_id = str(merchant_record.paypal_merchant_id)

        # 3. Call PayPal Orders v2 external REST endpoint OUTSIDE database transaction
        # Propagate stable PayPal-Request-Id for order creation idempotency
        # Enforce PayPal AI Hackathon currency standard (canonical USD default)
        valid_paypal_currencies = {"USD", "EUR", "GBP", "CAD", "AUD"}
        target_currency: str = (str(catalog_product.currency) if catalog_product.currency else "USD").upper().strip()
        if target_currency not in valid_paypal_currencies:
            target_currency = "USD"

        paypal_request_id = str(request.idempotency_key or local_order_id)
        paypal_order = self.paypal_client.create_order(
            sku=str(request.sku),
            amount=total_amount,
            currency=target_currency,
            reference_id=local_order_id,
            return_url=request.return_url,
            cancel_url=request.cancel_url,
            paypal_request_id=paypal_request_id,
            payee_merchant_id=payee_merchant_id,
        )

        # 4. Atomic database commit: order, reservation, audit
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(minutes=15)

        with atomic_transaction(self.session):
            order = Order(
                order_id=local_order_id,
                merchant_id=resolved_merchant_id,
                paypal_order_id=paypal_order.paypal_order_id,
                sku=str(request.sku),
                product_id=int(catalog_product.id),
                unit_price=Decimal(str(catalog_product.price)),
                currency=target_currency,
                quantity=int(request.quantity),
                total_amount=total_amount,
                order_status=OrderStatus.CREATED.value,
                payment_status=PaymentStatus.PENDING.value,
                preflight_scan_id=int(preflight.scan_id) if preflight.scan_id is not None else None,
                preflight_passed=True,
                idempotency_key=str(request.idempotency_key) if request.idempotency_key else None,
                correlation_id=correlation_id,
            )
            self.order_repo.create(order)

            # Local demo inventory reservation
            reservation = DemoInventoryReservation(
                merchant_id=resolved_merchant_id,
                order_id=int(order.id),
                sku=str(request.sku),
                quantity=int(request.quantity),
                status=ReservationStatus.RESERVED.value,
                expires_at=expires_at,
            )
            self.reservation_repo.create(reservation)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=resolved_merchant_id,
                    action="ORDER_CREATED",
                    entity_type="Order",
                    entity_id=local_order_id,
                    approval_id=None,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    before_state=None,
                    after_state=json.dumps({
                        "order_id": local_order_id,
                        "paypal_order_id": paypal_order.paypal_order_id,
                        "sku": str(request.sku),
                        "amount": str(total_amount),
                        "currency": target_currency,
                        "status": OrderStatus.CREATED.value,
                    }),
                    details=f"Created order with PayPal Orders v2 ({paypal_order.paypal_order_id})",
                ),
            )

        response = OrderResponse.model_validate(order)
        response.approve_url = paypal_order.approve_url
        return response
