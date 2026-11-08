from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_current_actor,
    require_merchant_access,
)
from backend.schemas.storefront import StorefrontProductResponse, StorefrontUpdatePriceRequest
from backend.services.storefront import StorefrontService

router = APIRouter(prefix="/api/storefront/products", tags=["Controlled Storefront"])


@router.get("/{sku}", response_model=StorefrontProductResponse, summary="Get storefront product by SKU")
def get_storefront_product(
    sku: str,
    db: Session = Depends(get_db),
) -> StorefrontProductResponse:
    """
    Returns the current customer-facing controlled demo storefront product facts.
    """
    service = StorefrontService(db)
    product = service.get_product(sku)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storefront product with SKU '{sku}' not found.",
        )
    return product


@router.put("/{sku}/price", response_model=StorefrontProductResponse, summary="Update storefront price")
def update_storefront_price(
    sku: str,
    request: StorefrontUpdatePriceRequest,
    current_actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> StorefrontProductResponse:
    """
    Updates the customer-facing storefront price for the given SKU.
    Guarantees isolation: merchant-authorized catalog records are untouched.
    Enforces that actor identity is derived strictly from server authentication context.
    """
    service = StorefrontService(db)
    current_product = service.repository.get_by_sku(sku)
    if not current_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storefront product with SKU '{sku}' not found.")
    require_merchant_access(current_actor, current_product.merchant_id)
    try:
        return service.update_price(sku=sku, request=request, trusted_actor=current_actor)
    except ValueError as ex:
        err_msg = str(ex)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        if "concurrency conflict" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
