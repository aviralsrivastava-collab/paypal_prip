import datetime
import json
import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.core.security import AuthenticatedActor, require_merchant_access
from backend.integrations.paypal import (
    PayPalApiError,
    PayPalClientInterface,
    PayPalTimeoutError,
    get_paypal_client,
)
from backend.integrations.paypal.mock_client import MockPayPalClient
from backend.models.payment_capture import PaymentCapture
from backend.models.reconciliation import PaymentReconciliation
from backend.policies.checkout_policy import (
    CaptureStatus,
    OrderStatus,
    PaymentStatus,
    ReconciliationStatus,
    ReservationStatus,
    validate_payment_transition,
)
from backend.repositories.order import OrderRepository
from backend.repositories.payment_capture import PaymentCaptureRepository
from backend.repositories.reconciliation import PaymentReconciliationRepository
from backend.repositories.reservation import ReservationRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.payment import (
    CapturePaymentRequest,
    CapturePaymentResponse,
    ReconcilePaymentResponse,
)
from backend.services.audit import AuditService

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Payment business service.
    Orchestrates PayPal Orders v2 server-side capture, ambiguous timeout handling,
    authoritative reconciliation, and atomic audit logging.
    Guarantees that external PayPal network calls occur OUTSIDE open database transactions.
    """

    def __init__(
        self,
        session: Session,
        paypal_client: Optional[PayPalClientInterface] = None,
    ) -> None:
        self.session = session
        self.paypal_client = paypal_client or get_paypal_client()
        self.order_repo = OrderRepository(session)
        self.capture_repo = PaymentCaptureRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.reconciliation_repo = PaymentReconciliationRepository(session)

    def capture_payment(
        self,
        request: CapturePaymentRequest,
        actor_id: str = "MERCHANT",
        actor_type: str = "MERCHANT",
        trusted_actor: Optional[AuthenticatedActor] = None,
    ) -> CapturePaymentResponse:
        """
        Executes server-side capture for an approved PayPal order.
        If capture times out or errors ambiguously, transitions state to UNKNOWN
        and requires reconciliation before any retry.
        """
        # 1. Resolve order
        order = self.order_repo.get_by_order_id(request.order_id)
        if not order:
            order = self.order_repo.get_by_paypal_order_id(request.order_id)
        if not order:
            raise ValueError(f"Order '{request.order_id}' not found.")

        # Tenancy authorization check
        if trusted_actor:
            require_merchant_access(trusted_actor, order.merchant_id)

        # 2. Check for idempotent already-captured state
        if order.payment_status == PaymentStatus.CAPTURED.value:
            existing_capture = self.capture_repo.get_by_order_id(order.id)
            if existing_capture:
                return CapturePaymentResponse(
                    capture_id=existing_capture.paypal_capture_id,
                    order_id=order.order_id,
                    paypal_order_id=order.paypal_order_id,
                    status=existing_capture.status,
                    amount=existing_capture.amount,
                    currency=existing_capture.currency,
                    fee_amount=existing_capture.fee_amount,
                    net_amount=existing_capture.net_amount,
                    reconciliation_status=existing_capture.reconciliation_status,
                    error_message=existing_capture.error_message,
                    created_at=existing_capture.created_at,
                )

        # 3. Guard against retrying ambiguous UNKNOWN state without reconciliation
        if order.payment_status == PaymentStatus.UNKNOWN.value:
            raise ValueError(
                f"Order '{order.order_id}' has an ambiguous capture outcome (UNKNOWN). "
                "Authoritative reconciliation is required before any capture action."
            )

        # Validate allowed transition
        if not validate_payment_transition(
            PaymentStatus(order.payment_status),
            PaymentStatus.CAPTURED,
        ):
            raise ValueError(f"Cannot capture order from current payment state '{order.payment_status}'.")

        if not order.paypal_order_id:
            raise ValueError(f"Order '{order.order_id}' has no associated PayPal Order ID.")

        correlation_id = f"cap_corr_{uuid.uuid4().hex[:12]}"

        # 4. Configure test simulation flags on Mock client if requested
        if isinstance(self.paypal_client, MockPayPalClient):
            if request.simulate_timeout:
                self.paypal_client.simulate_timeout = True
            if request.simulate_decline:
                self.paypal_client.simulate_decline = True

        # 5. External PayPal capture OUTSIDE database transaction
        # Stable PayPal-Request-Id ensures repeated/retried capture attempts are idempotent
        paypal_request_id = request.idempotency_key or f"cap_{order.order_id}"
        try:
            paypal_capture = self.paypal_client.capture_order(
                order.paypal_order_id,
                paypal_request_id=paypal_request_id,
            )
        except PayPalTimeoutError as exc:
            # Ambiguous outcome! Must persist UNKNOWN state transactionally.
            logger.warning(f"PayPal capture timed out for order {order.order_id}: {exc}")
            now = datetime.datetime.now(datetime.timezone.utc)
            with atomic_transaction(self.session):
                order.payment_status = PaymentStatus.UNKNOWN.value
                capture = PaymentCapture(
                    merchant_id=order.merchant_id,
                    order_id=order.id,
                    paypal_capture_id=None,
                    status=CaptureStatus.UNKNOWN.value,
                    amount=order.total_amount,
                    currency=order.currency,
                    error_message=str(exc),
                    reconciliation_status=ReconciliationStatus.RECONCILIATION_REQUIRED.value,
                )
                self.capture_repo.create(capture)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=order.merchant_id,
                        action="PAYMENT_CAPTURE_TIMEOUT",
                        entity_type="Order",
                        entity_id=order.order_id,
                        approval_id=None,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        before_state=PaymentStatus.PENDING.value,
                        after_state=PaymentStatus.UNKNOWN.value,
                        details="PayPal capture timed out. Status set to UNKNOWN, reconciliation required.",
                    ),
                )

            return CapturePaymentResponse(
                capture_id=None,
                order_id=order.order_id,
                paypal_order_id=order.paypal_order_id,
                status=CaptureStatus.UNKNOWN.value,
                amount=order.total_amount,
                currency=order.currency,
                fee_amount=None,
                net_amount=None,
                reconciliation_status=ReconciliationStatus.RECONCILIATION_REQUIRED.value,
                error_message="Capture timed out. Ambiguous outcome persisted as UNKNOWN.",
                created_at=now,
            )
        except (PayPalApiError, Exception) as exc:
            logger.error(f"PayPal capture error for order {order.order_id}: {exc}")
            now = datetime.datetime.now(datetime.timezone.utc)
            with atomic_transaction(self.session):
                order.payment_status = PaymentStatus.FAILED.value
                order.order_status = OrderStatus.FAILED.value
                capture = PaymentCapture(
                    merchant_id=order.merchant_id,
                    order_id=order.id,
                    paypal_capture_id=None,
                    status=CaptureStatus.FAILED.value,
                    amount=order.total_amount,
                    currency=order.currency,
                    error_message=str(exc),
                    reconciliation_status=ReconciliationStatus.NOT_NEEDED.value,
                )
                self.capture_repo.create(capture)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=order.merchant_id,
                        action="PAYMENT_CAPTURE_FAILED",
                        entity_type="Order",
                        entity_id=order.order_id,
                        approval_id=None,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        before_state=PaymentStatus.PENDING.value,
                        after_state=PaymentStatus.FAILED.value,
                        details=f"PayPal capture failed: {exc}",
                    ),
                )

            return CapturePaymentResponse(
                capture_id=None,
                order_id=order.order_id,
                paypal_order_id=order.paypal_order_id,
                status=CaptureStatus.FAILED.value,
                amount=order.total_amount,
                currency=order.currency,
                fee_amount=None,
                net_amount=None,
                reconciliation_status=ReconciliationStatus.NOT_NEEDED.value,
                error_message=str(exc),
                created_at=now,
            )

        # 6. Process successful or declined capture response in atomic transaction
        is_completed = (paypal_capture.status == "COMPLETED")
        now = datetime.datetime.now(datetime.timezone.utc)

        with atomic_transaction(self.session):
            if is_completed:
                order.payment_status = PaymentStatus.CAPTURED.value
                order.order_status = OrderStatus.COMPLETED.value

                # Commit inventory reservation
                reservation = self.reservation_repo.get_by_order_id(order.id)
                if reservation:
                    reservation.status = ReservationStatus.COMMITTED.value

                capture = PaymentCapture(
                    merchant_id=order.merchant_id,
                    order_id=order.id,
                    paypal_capture_id=paypal_capture.paypal_capture_id,
                    status=CaptureStatus.COMPLETED.value,
                    amount=paypal_capture.amount,
                    currency=paypal_capture.currency,
                    fee_amount=paypal_capture.fee_amount,
                    net_amount=paypal_capture.net_amount,
                    reconciliation_status=ReconciliationStatus.NOT_NEEDED.value,
                )
                self.capture_repo.create(capture)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=order.merchant_id,
                        action="PAYMENT_CAPTURED",
                        entity_type="Order",
                        entity_id=order.order_id,
                        approval_id=None,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        before_state=PaymentStatus.PENDING.value,
                        after_state=PaymentStatus.CAPTURED.value,
                        details=json.dumps({
                            "paypal_capture_id": paypal_capture.paypal_capture_id,
                            "amount": str(paypal_capture.amount),
                            "currency": paypal_capture.currency,
                            "fee": str(paypal_capture.fee_amount) if paypal_capture.fee_amount else None,
                            "net": str(paypal_capture.net_amount) if paypal_capture.net_amount else None,
                        }),
                    ),
                )
            else:
                order.payment_status = PaymentStatus.FAILED.value
                order.order_status = OrderStatus.FAILED.value

                capture = PaymentCapture(
                    merchant_id=order.merchant_id,
                    order_id=order.id,
                    paypal_capture_id=paypal_capture.paypal_capture_id,
                    status=paypal_capture.status,
                    amount=paypal_capture.amount,
                    currency=paypal_capture.currency,
                    error_message=f"Capture returned non-completed status: {paypal_capture.status}",
                    reconciliation_status=ReconciliationStatus.NOT_NEEDED.value,
                )
                self.capture_repo.create(capture)

                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=order.merchant_id,
                        action="PAYMENT_CAPTURE_DECLINED",
                        entity_type="Order",
                        entity_id=order.order_id,
                        approval_id=None,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        before_state=PaymentStatus.PENDING.value,
                        after_state=PaymentStatus.FAILED.value,
                        details=f"Payment capture returned status: {paypal_capture.status}",
                    ),
                )

        return CapturePaymentResponse(
            capture_id=capture.paypal_capture_id,
            order_id=order.order_id,
            paypal_order_id=order.paypal_order_id,
            status=capture.status,
            amount=capture.amount,
            currency=capture.currency,
            fee_amount=capture.fee_amount,
            net_amount=capture.net_amount,
            reconciliation_status=capture.reconciliation_status,
            error_message=capture.error_message,
            created_at=capture.created_at,
        )

    def reconcile_payment(
        self,
        order_id: str,
        actor_id: str = "MERCHANT",
        actor_type: str = "MERCHANT",
        trusted_actor: Optional[AuthenticatedActor] = None,
    ) -> ReconcilePaymentResponse:
        """
        Reconciles ambiguous (UNKNOWN) or unconfirmed order status using authoritative PayPal API.
        External PayPal call is made OUTSIDE database transaction.
        Persists PaymentReconciliation outcome and audit log.
        Safe to repeat: if already reconciled or states match, records NO_DISCREPANCY.
        """
        order = self.order_repo.get_by_order_id(order_id)
        if not order:
            order = self.order_repo.get_by_paypal_order_id(order_id)
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        # Tenancy authorization check
        if trusted_actor:
            require_merchant_access(trusted_actor, order.merchant_id)

        if not order.paypal_order_id:
            raise ValueError(f"Order '{order.order_id}' has no PayPal Order ID to reconcile.")

        correlation_id = f"rec_corr_{uuid.uuid4().hex[:12]}"

        # External PayPal status inquiry OUTSIDE database transaction
        paypal_details = self.paypal_client.get_order_details(order.paypal_order_id)

        now = datetime.datetime.now(datetime.timezone.utc)
        message: str
        prev_payment_status = order.payment_status

        with atomic_transaction(self.session):
            capture = self.capture_repo.get_by_order_id(order.id)
            reservation = self.reservation_repo.get_by_order_id(order.id)

            if prev_payment_status == PaymentStatus.UNKNOWN.value:
                if paypal_details.status == "COMPLETED":
                    order.payment_status = PaymentStatus.CAPTURED.value
                    order.order_status = OrderStatus.COMPLETED.value
                    if capture:
                        capture.status = CaptureStatus.COMPLETED.value
                        capture.reconciliation_status = ReconciliationStatus.RECONCILED.value
                        capture.reconciled_at = now
                    if reservation:
                        reservation.status = ReservationStatus.COMMITTED.value
                    outcome = "RESOLVED_CAPTURED"
                    message = "Reconciliation resolved status to CAPTURED based on PayPal records."
                    action_name = "PAYMENT_RECONCILED_SUCCESS"
                else:
                    order.payment_status = PaymentStatus.FAILED.value
                    order.order_status = OrderStatus.FAILED.value
                    if capture:
                        capture.status = CaptureStatus.FAILED.value
                        capture.reconciliation_status = ReconciliationStatus.RECONCILED.value
                        capture.reconciled_at = now
                    if reservation:
                        reservation.status = ReservationStatus.RELEASED.value
                    outcome = "RESOLVED_FAILED"
                    message = f"Reconciliation resolved status to FAILED (PayPal status: {paypal_details.status})."
                    action_name = "PAYMENT_RECONCILED_FAILED"

            elif prev_payment_status == PaymentStatus.CAPTURED.value:
                if paypal_details.status == "COMPLETED":
                    outcome = "NO_DISCREPANCY"
                    message = "Order already CAPTURED and confirmed by PayPal; no discrepancy detected."
                    action_name = "PAYMENT_RECONCILED_NO_CHANGE"
                else:
                    outcome = "DISCREPANCY_DETECTED"
                    message = f"Local order is CAPTURED but PayPal reports status '{paypal_details.status}'."
                    action_name = "PAYMENT_RECONCILED_DISCREPANCY"

            elif prev_payment_status == PaymentStatus.FAILED.value:
                if paypal_details.status != "COMPLETED":
                    outcome = "NO_DISCREPANCY"
                    message = f"Order already marked FAILED; provider confirms non-completed status ({paypal_details.status})."
                    action_name = "PAYMENT_RECONCILED_NO_CHANGE"
                else:
                    outcome = "DISCREPANCY_DETECTED"
                    message = "Local order is FAILED but PayPal reports status COMPLETED."
                    action_name = "PAYMENT_RECONCILED_DISCREPANCY"
            else:
                # Pending or created
                if paypal_details.status == "COMPLETED":
                    order.payment_status = PaymentStatus.CAPTURED.value
                    order.order_status = OrderStatus.COMPLETED.value
                    if reservation:
                        reservation.status = ReservationStatus.COMMITTED.value
                    outcome = "RESOLVED_CAPTURED"
                    message = "Reconciliation identified missing capture webhook and transitioned order to CAPTURED."
                    action_name = "PAYMENT_RECONCILED_SUCCESS"
                else:
                    outcome = "NO_DISCREPANCY"
                    message = f"Order is {prev_payment_status}; provider status is {paypal_details.status}."
                    action_name = "PAYMENT_RECONCILED_NO_CHANGE"

            # Persist PaymentReconciliation entry
            recon_entry = PaymentReconciliation(
                merchant_id=order.merchant_id,
                order_id=order.id,
                paypal_order_id=order.paypal_order_id,
                paypal_capture_id=capture.paypal_capture_id if capture else None,
                outcome=outcome,
                previous_payment_status=prev_payment_status,
                new_payment_status=order.payment_status,
                provider_status=paypal_details.status,
                details=message,
                actor_type=actor_type,
                actor_id=actor_id,
                correlation_id=correlation_id,
                reconciled_at=now,
            )
            self.reconciliation_repo.create(recon_entry)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=order.merchant_id,
                    action=action_name,
                    entity_type="Order",
                    entity_id=order.order_id,
                    approval_id=None,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    before_state=prev_payment_status,
                    after_state=order.payment_status,
                    details=message,
                ),
            )

        return ReconcilePaymentResponse(
            order_id=order.order_id,
            paypal_order_id=order.paypal_order_id,
            order_status=order.order_status,
            payment_status=order.payment_status,
            reconciliation_status=ReconciliationStatus.RECONCILED.value,
            message=message,
        )

    def reconcile_all_pending(
        self,
        actor_id: str = "MERCHANT",
        actor_type: str = "MERCHANT",
        merchant_id: Optional[str] = None,
        trusted_actor: Optional[AuthenticatedActor] = None,
    ) -> list[ReconcilePaymentResponse]:
        """
        Finds all orders currently in UNKNOWN payment status and reconciles each one safely.
        Enforces tenant isolation when merchant_id or trusted_actor is provided.
        """
        effective_merchant = merchant_id or (
            trusted_actor.merchant_id
            if trusted_actor and trusted_actor.role not in {"superadmin", "system_admin"}
            else None
        )
        pending_orders = self.reconciliation_repo.list_orders_requiring_reconciliation(
            merchant_id=effective_merchant
        )
        results: list[ReconcilePaymentResponse] = []
        for ord_item in pending_orders:
            res = self.reconcile_payment(
                order_id=ord_item.order_id,
                actor_id=actor_id,
                actor_type=actor_type,
                trusted_actor=trusted_actor,
            )
            results.append(res)
        return results
