from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import (
    AuthenticatedActor,
    get_optional_actor,
    require_demo_operator,
    require_merchant_access,
    require_role,
)
from backend.schemas.product import (
    ProductComparisonResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    StorefrontPriceUpdate,
)
from backend.services.catalog import CatalogService

router = APIRouter(prefix="/api/products", tags=["Catalog Products"])


@router.get("", response_model=List[ProductComparisonResponse], summary="List catalog products")
def list_products(
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_optional_actor),
) -> List[ProductComparisonResponse]:
    """
    Returns merchant-authorized catalog products alongside their current storefront prices
    and discrepancy metrics for the authenticated merchant tenant.
    """
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else None
    merchant_id = actor.merchant_id if actor else None
    service = CatalogService(db)
    return service.list_products(merchant_id=merchant_id)


@router.get("/{product_id}", response_model=ProductResponse, summary="Get catalog product detail")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_optional_actor),
) -> ProductResponse:
    """
    Fetches isolated merchant-authorized catalog product facts by product ID.
    Enforces multi-merchant tenant boundary.
    """
    service = CatalogService(db)
    product = service.get_product_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found.",
        )
    if isinstance(current_actor, AuthenticatedActor):
        require_merchant_access(current_actor, product.merchant_id)
    return product


@router.get("/sku/{sku}", response_model=ProductComparisonResponse, summary="Get catalog product by SKU")
def get_product_by_sku(
    sku: str,
    db: Session = Depends(get_db),
    current_actor: Optional[AuthenticatedActor] = Depends(get_optional_actor),
) -> ProductComparisonResponse:
    """
    Fetches catalog product by SKU with storefront discrepancy comparison.
    """
    actor = current_actor if isinstance(current_actor, AuthenticatedActor) else None
    merchant_id = actor.merchant_id if actor else None
    service = CatalogService(db)
    product = service.get_product_by_sku(sku, merchant_id=merchant_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with SKU '{sku}' not found.",
        )
    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, summary="Create catalog product")
def create_product(
    request: ProductCreate,
    actor: AuthenticatedActor = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """
    Creates a new merchant-authorized product in the tenant's catalog and initializes
    a matching storefront product for controlled comparison.
    Requires at least MANAGER role.
    """
    service = CatalogService(db)
    try:
        return service.create_product(
            merchant_id=actor.merchant_id,
            sku=request.sku,
            title=request.title,
            price=request.price,
            currency=request.currency,
            description=request.description,
            availability=request.availability,
            storefront_price=request.storefront_price,
            actor_id=actor.actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put("/{product_id}", response_model=ProductResponse, summary="Update catalog product")
def update_product(
    product_id: int,
    request: ProductUpdate,
    actor: AuthenticatedActor = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """
    Updates catalog product details (title, description, price, currency, availability)
    and increments the source version.
    Requires at least MANAGER role.
    """
    service = CatalogService(db)
    try:
        return service.update_product(
            product_id=product_id,
            merchant_id=actor.merchant_id,
            title=request.title,
            description=request.description,
            price=request.price,
            currency=request.currency,
            availability=request.availability,
            actor_id=actor.actor_id,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete catalog product")
def delete_product(
    product_id: int,
    actor: AuthenticatedActor = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> None:
    """
    Deletes a catalog product from the tenant catalog.
    Requires at least ADMIN role.
    """
    service = CatalogService(db)
    try:
        service.delete_product(
            product_id=product_id,
            merchant_id=actor.merchant_id,
            actor_id=actor.actor_id,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/sku/{sku}/storefront-price", response_model=ProductComparisonResponse, summary="Simulate/update storefront price")
def update_storefront_price(
    sku: str,
    request: StorefrontPriceUpdate,
    actor: AuthenticatedActor = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
) -> ProductComparisonResponse:
    """
    Updates the controlled storefront price for a given SKU to simulate or test price discrepancies.
    Requires at least MANAGER role.
    """
    service = CatalogService(db)
    try:
        return service.set_storefront_price(
            sku=sku,
            merchant_id=actor.merchant_id,
            new_price=request.price,
            currency=request.currency,
            actor_id=actor.actor_id,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storefront product with SKU '{sku}' not found.")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/seed", response_model=Dict[str, Any], summary="Seed demo catalog and storefront")
def seed_catalog(
    reset: bool = Query(default=False, description="Reset to default seed values if already present"),
    actor: AuthenticatedActor = Depends(require_demo_operator),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Seeds the standard StrideX Runner demo scenario:
    - Merchant catalog price: USD 100.00
    - Storefront price: USD 120.00
    - Discrepancy: USD 20.00

    Guarded: Requires demo_operator permissions and is disabled in production.
    """
    service = CatalogService(db)
    return service.seed_initial_catalog(reset=reset, actor_id=actor.actor_id)
