from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import AuthenticatedActor, get_current_actor, require_merchant_access
from backend.schemas.checkout import (
    CreateOrderRequest,
    OrderResponse,
    PreflightCheckRequest,
    PreflightCheckResponse,
)
from backend.schemas.payment import (
    CapturePaymentRequest,
    CapturePaymentResponse,
    ReconcilePaymentResponse,
)
from backend.services.checkout import CheckoutService
from backend.services.payment import PaymentService

router = APIRouter(prefix="/api/checkout", tags=["Checkout & PayPal"])


@router.post(
    "/preflight",
    response_model=PreflightCheckResponse,
    summary="Validate checkout preflight discrepancy gate",
)
def preflight_check(
    request: PreflightCheckRequest,
    db: Session = Depends(get_db),
) -> PreflightCheckResponse:
    """
    Evaluates whether a product is eligible for checkout.
    Blocks checkout if ground-truth catalog and controlled storefront price differ,
    or if inspection scan indicates an unresolved discrepancy.
    """
    service = CheckoutService(db)
    return service.preflight_check(request.sku)


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create order with PayPal Orders v2",
)
def create_order(
    request: CreateOrderRequest,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> OrderResponse:
    """
    Creates an order after verifying preflight conditions.
    Initializes PayPal Sandbox order and reserves demo inventory.
    """
    service = CheckoutService(db)
    try:
        return service.create_order(
            request=request,
            actor_id=current_actor.actor_id,
            actor_type=current_actor.actor_type,
            merchant_id=current_actor.merchant_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "Checkout blocked" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/orders/{order_id}/capture",
    response_model=CapturePaymentResponse,
    summary="Server-side capture of approved PayPal order",
)
def capture_order(
    order_id: str,
    request: Optional[CapturePaymentRequest] = None,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CapturePaymentResponse:
    """
    Executes authoritative server-side capture against PayPal.
    On network timeout, transitions order to UNKNOWN state with reconciliation required.
    """
    service = PaymentService(db)
    order = service.order_repo.get_by_order_id(order_id)
    if not order:
        order = service.order_repo.get_by_paypal_order_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order '{order_id}' not found.")
    require_merchant_access(current_actor, order.merchant_id)

    req = request or CapturePaymentRequest(order_id=order_id)
    req.order_id = order_id
    try:
        return service.capture_payment(
            request=req,
            actor_id=current_actor.actor_id,
            actor_type=current_actor.actor_type,
            trusted_actor=current_actor,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        if "UNKNOWN" in msg or "reconciliation" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/orders/{order_id}/reconcile",
    response_model=ReconcilePaymentResponse,
    summary="Reconcile ambiguous order state with PayPal",
)
def reconcile_order(
    order_id: str,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ReconcilePaymentResponse:
    """
    Queries authoritative PayPal status for an ambiguous order to resolve payment outcome.
    """
    service = PaymentService(db)
    order = service.order_repo.get_by_order_id(order_id)
    if not order:
        order = service.order_repo.get_by_paypal_order_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order '{order_id}' not found.")
    require_merchant_access(current_actor, order.merchant_id)

    try:
        return service.reconcile_payment(
            order_id=order_id,
            actor_id=current_actor.actor_id,
            actor_type=current_actor.actor_type,
            trusted_actor=current_actor,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get(
    "/orders",
    response_model=List[OrderResponse],
    summary="List recent checkout orders",
)
def list_orders(
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_current_actor),
) -> List[OrderResponse]:
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else None
    merchant_id = actor.merchant_id if actor else None
    service = CheckoutService(db)
    orders = service.order_repo.list_orders(limit=50, merchant_id=merchant_id)
    return [OrderResponse.model_validate(o) for o in orders]


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get single order details",
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_current_actor),
) -> OrderResponse:
    service = CheckoutService(db)
    order = service.order_repo.get_by_order_id(order_id)
    if not order:
        order = service.order_repo.get_by_paypal_order_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order '{order_id}' not found.")
    if isinstance(current_actor, AuthenticatedActor):
        require_merchant_access(current_actor, order.merchant_id)
    return OrderResponse.model_validate(order)
