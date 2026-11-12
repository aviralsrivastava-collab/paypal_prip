import datetime
import json
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.database import atomic_transaction
from backend.models.product import Product
from backend.models.storefront import StorefrontProduct
from backend.repositories.product import ProductRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.audit import AuditEventCreate
from backend.schemas.product import ProductComparisonResponse, ProductResponse
from backend.services.audit import AuditService

DEFAULT_SEEDED_SKU = "SX-001"
DEFAULT_PRODUCT_TITLE = "StrideX Runner"
DEFAULT_PRODUCT_DESCRIPTION = (
    "High-performance lightweight running shoe with responsive cushioning and breathable mesh."
)
DEFAULT_CATALOG_PRICE = Decimal("100.00")
DEFAULT_STOREFRONT_PRICE = Decimal("120.00")
DEFAULT_CURRENCY = "USD"


class CatalogService:
    """
    Business service coordinating merchant catalog products and comparisons with storefront state.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.product_repo = ProductRepository(session)
        self.storefront_repo = StorefrontRepository(session)

    def list_products(self, merchant_id: Optional[str] = None) -> List[ProductComparisonResponse]:
        """
        Lists all catalog products alongside their current storefront prices and discrepancy status.
        """
        products = self.product_repo.get_all(merchant_id=merchant_id)
        results: List[ProductComparisonResponse] = []

        for p in products:
            storefront = self.storefront_repo.get_by_sku(p.sku)
            if storefront:
                if p.currency != storefront.currency:
                    is_comparable = False
                    comparability_reason = (
                        f"CURRENCY_MISMATCH: Catalog currency '{p.currency}' != Storefront currency '{storefront.currency}'"
                    )
                    price_discrepancy = None
                    has_discrepancy = True
                else:
                    is_comparable = True
                    comparability_reason = None
                    discrepancy = storefront.price - p.price
                    price_discrepancy = f"{discrepancy:+.2f}"
                    has_discrepancy = discrepancy != Decimal("0.00")

                results.append(
                    ProductComparisonResponse(
                        id=p.id,
                        merchant_id=p.merchant_id,
                        sku=p.sku,
                        title=p.title,
                        description=p.description,
                        merchant_price=f"{p.price:.2f}",
                        merchant_currency=p.currency,
                        storefront_price=f"{storefront.price:.2f}",
                        storefront_currency=storefront.currency,
                        price_discrepancy=price_discrepancy,
                        has_discrepancy=has_discrepancy,
                        is_comparable=is_comparable,
                        comparability_reason=comparability_reason,
                        availability=p.availability,
                        source_version=p.source_version,
                        storefront_version=storefront.version,
                        updated_at=p.updated_at,
                    )
                )
            else:
                results.append(
                    ProductComparisonResponse(
                        id=p.id,
                        merchant_id=p.merchant_id,
                        sku=p.sku,
                        title=p.title,
                        description=p.description,
                        merchant_price=f"{p.price:.2f}",
                        merchant_currency=p.currency,
                        storefront_price=None,
                        storefront_currency=None,
                        price_discrepancy=None,
                        has_discrepancy=False,
                        is_comparable=True,
                        comparability_reason=None,
                        availability=p.availability,
                        source_version=p.source_version,
                        storefront_version=None,
                        updated_at=p.updated_at,
                    )
                )
        return results

    def get_product_by_id(self, product_id: int) -> Optional[ProductResponse]:
        """Fetch isolated catalog product by ID."""
        product = self.product_repo.get_by_id(product_id)
        if not product:
            return None
        return ProductResponse.from_orm_model(product)

    def get_product_by_sku(self, sku: str, merchant_id: Optional[str] = None) -> Optional[ProductComparisonResponse]:
        """Fetch catalog product by SKU with storefront comparison."""
        product = self.product_repo.get_by_sku(sku, merchant_id=merchant_id)
        if not product:
            return None

        storefront = self.storefront_repo.get_by_sku(sku)
        if storefront:
            if product.currency != storefront.currency:
                is_comparable = False
                comparability_reason = (
                    f"CURRENCY_MISMATCH: Catalog currency '{product.currency}' != Storefront currency '{storefront.currency}'"
                )
                price_discrepancy = None
                has_discrepancy = True
            else:
                is_comparable = True
                comparability_reason = None
                discrepancy = storefront.price - product.price
                price_discrepancy = f"{discrepancy:+.2f}"
                has_discrepancy = discrepancy != Decimal("0.00")

            return ProductComparisonResponse(
                id=product.id,
                sku=product.sku,
                title=product.title,
                description=product.description,
                merchant_price=f"{product.price:.2f}",
                merchant_currency=product.currency,
                storefront_price=f"{storefront.price:.2f}",
                storefront_currency=storefront.currency,
                price_discrepancy=price_discrepancy,
                has_discrepancy=has_discrepancy,
                is_comparable=is_comparable,
                comparability_reason=comparability_reason,
                availability=product.availability,
                source_version=product.source_version,
                storefront_version=storefront.version,
                updated_at=product.updated_at,
            )

        return ProductComparisonResponse(
            id=product.id,
            sku=product.sku,
            title=product.title,
            description=product.description,
            merchant_price=f"{product.price:.2f}",
            merchant_currency=product.currency,
            storefront_price=None,
            storefront_currency=None,
            price_discrepancy=None,
            has_discrepancy=False,
            is_comparable=True,
            comparability_reason=None,
            availability=product.availability,
            source_version=product.source_version,
            storefront_version=None,
            updated_at=product.updated_at,
        )

    def seed_initial_catalog(self, reset: bool = False, actor_id: str = "system") -> Dict[str, Any]:
        """
        Idempotent seeding of the PRIP demo scenario:
        - Catalog product: StrideX Runner (SX-001) at USD 100.00
        - Storefront product: StrideX Runner (SX-001) at USD 120.00
        - Established discrepancy: USD 20.00
        """
        correlation_id = f"seed-{uuid.uuid4()}"
        with atomic_transaction(self.session):
            catalog_product = self.product_repo.get_by_sku(DEFAULT_SEEDED_SKU)
            storefront_product = self.storefront_repo.get_by_sku(DEFAULT_SEEDED_SKU)

            catalog_created = False
            storefront_created = False

            if not catalog_product:
                catalog_product = Product(
                    sku=DEFAULT_SEEDED_SKU,
                    title=DEFAULT_PRODUCT_TITLE,
                    description=DEFAULT_PRODUCT_DESCRIPTION,
                    price=DEFAULT_CATALOG_PRICE,
                    currency=DEFAULT_CURRENCY,
                    availability="IN_STOCK",
                    source_version=1,
                )
                self.product_repo.create(catalog_product)
                catalog_created = True
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=catalog_product.merchant_id,
                        actor_type="system",
                        actor_id=actor_id,
                        action="CATALOG_SEEDED",
                        entity_type="product",
                        entity_id=DEFAULT_SEEDED_SKU,
                        approval_id=None,
                        correlation_id=correlation_id,
                        details=json.dumps({"price": str(DEFAULT_CATALOG_PRICE), "currency": DEFAULT_CURRENCY}),
                    ),
                )
            elif reset:
                catalog_product.price = DEFAULT_CATALOG_PRICE
                catalog_product.currency = DEFAULT_CURRENCY
                catalog_product.title = DEFAULT_PRODUCT_TITLE
                catalog_product.source_version = 1
                self.product_repo.update(catalog_product)
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=catalog_product.merchant_id,
                        actor_type="system",
                        actor_id=actor_id,
                        action="CATALOG_RESET",
                        entity_type="product",
                        entity_id=DEFAULT_SEEDED_SKU,
                        approval_id=None,
                        correlation_id=correlation_id,
                        details=json.dumps({"price": str(DEFAULT_CATALOG_PRICE), "currency": DEFAULT_CURRENCY}),
                    ),
                )

            if not storefront_product:
                storefront_product = StorefrontProduct(
                    sku=DEFAULT_SEEDED_SKU,
                    title=DEFAULT_PRODUCT_TITLE,
                    price=DEFAULT_STOREFRONT_PRICE,
                    currency=DEFAULT_CURRENCY,
                    availability="IN_STOCK",
                    url_path="/products/stridex-runner",
                    version=1,
                )
                self.storefront_repo.create(storefront_product)
                storefront_created = True
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=storefront_product.merchant_id,
                        actor_type="system",
                        actor_id=actor_id,
                        action="STOREFRONT_SEEDED",
                        entity_type="storefront_product",
                        entity_id=DEFAULT_SEEDED_SKU,
                        approval_id=None,
                        correlation_id=correlation_id,
                        details=json.dumps({"price": str(DEFAULT_STOREFRONT_PRICE), "currency": DEFAULT_CURRENCY}),
                    ),
                )
            elif reset:
                storefront_product.price = DEFAULT_STOREFRONT_PRICE
                storefront_product.currency = DEFAULT_CURRENCY
                storefront_product.version = 1
                self.storefront_repo.create(storefront_product)  # updates dirty attributes
                AuditService.log_event(
                    self.session,
                    AuditEventCreate(
                        merchant_id=storefront_product.merchant_id,
                        actor_type="system",
                        actor_id=actor_id,
                        action="STOREFRONT_RESET",
                        entity_type="storefront_product",
                        entity_id=DEFAULT_SEEDED_SKU,
                        approval_id=None,
                        correlation_id=correlation_id,
                        details=json.dumps({"price": str(DEFAULT_STOREFRONT_PRICE), "currency": DEFAULT_CURRENCY}),
                    ),
                )

        return {
            "status": "success",
            "sku": DEFAULT_SEEDED_SKU,
            "catalog_price": f"{catalog_product.price:.2f}",
            "storefront_price": f"{storefront_product.price:.2f}",
            "discrepancy": f"{(storefront_product.price - catalog_product.price):+.2f}",
            "catalog_created": catalog_created,
            "storefront_created": storefront_created,
            "reset_applied": reset,
        }

    def create_product(
        self,
        merchant_id: str,
        sku: str,
        title: str,
        price: Decimal,
        currency: str = "USD",
        description: Optional[str] = None,
        availability: str = "IN_STOCK",
        storefront_price: Optional[Decimal] = None,
        actor_id: str = "merchant",
    ) -> ProductResponse:
        existing = self.product_repo.get_by_sku(sku, merchant_id=merchant_id)
        if existing:
            raise ValueError(f"Product with SKU '{sku}' already exists in catalog.")

        correlation_id = f"prod-create-{uuid.uuid4()}"
        with atomic_transaction(self.session):
            product = Product(
                merchant_id=merchant_id,
                sku=sku,
                title=title,
                description=description,
                price=price,
                currency=currency,
                availability=availability,
                source_version=1,
            )
            self.product_repo.create(product)

            sf = self.storefront_repo.get_by_sku(sku)
            if not sf:
                sf = StorefrontProduct(
                    merchant_id=merchant_id,
                    sku=sku,
                    title=title,
                    price=storefront_price if storefront_price is not None else price,
                    currency=currency,
                    availability=availability,
                    url_path=f"/products/{sku.lower()}",
                    version=1,
                )
                self.storefront_repo.create(sf)

            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=merchant_id,
                    actor_type="merchant",
                    actor_id=actor_id,
                    action="CATALOG_PRODUCT_CREATED",
                    entity_type="product",
                    entity_id=sku,
                    correlation_id=correlation_id,
                    details=json.dumps({"price": str(price), "currency": currency, "title": title}),
                ),
            )

        return ProductResponse.from_orm_model(product)

    def update_product(
        self,
        product_id: int,
        merchant_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[Decimal] = None,
        currency: Optional[str] = None,
        availability: Optional[str] = None,
        actor_id: str = "merchant",
    ) -> ProductResponse:
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise KeyError(f"Product with ID {product_id} not found.")
        if product.merchant_id != merchant_id:
            raise PermissionError(f"Actor from merchant '{merchant_id}' cannot mutate product belonging to '{product.merchant_id}'.")

        changes = {}
        with atomic_transaction(self.session):
            if title is not None:
                changes["title"] = {"old": str(product.title), "new": str(title)}
                product.title = title
            if description is not None:
                changes["description"] = {"old": str(product.description or ""), "new": str(description)}
                product.description = description
            if price is not None:
                changes["price"] = {"old": str(product.price), "new": str(price)}
                product.price = price
            if currency is not None:
                changes["currency"] = {"old": str(product.currency), "new": str(currency)}
                product.currency = currency
            if availability is not None:
                changes["availability"] = {"old": str(product.availability), "new": str(availability)}
                product.availability = availability

            product.source_version += 1
            product.updated_at = datetime.datetime.now(datetime.timezone.utc)
            self.product_repo.update(product)

            correlation_id = f"prod-upd-{uuid.uuid4()}"
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=merchant_id,
                    actor_type="merchant",
                    actor_id=actor_id,
                    action="CATALOG_PRODUCT_UPDATED",
                    entity_type="product",
                    entity_id=product.sku,
                    correlation_id=correlation_id,
                    details=json.dumps(changes),
                ),
            )

        return ProductResponse.from_orm_model(product)

    def delete_product(
        self,
        product_id: int,
        merchant_id: str,
        actor_id: str = "merchant",
    ) -> None:
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise KeyError(f"Product with ID {product_id} not found.")
        if product.merchant_id != merchant_id:
            raise PermissionError(f"Actor from merchant '{merchant_id}' cannot mutate product belonging to '{product.merchant_id}'.")

        sku = product.sku
        with atomic_transaction(self.session):
            self.product_repo.delete(product)

            correlation_id = f"prod-del-{uuid.uuid4()}"
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=merchant_id,
                    actor_type="merchant",
                    actor_id=actor_id,
                    action="CATALOG_PRODUCT_DELETED",
                    entity_type="product",
                    entity_id=sku,
                    correlation_id=correlation_id,
                    details=json.dumps({"sku": sku, "product_id": product_id}),
                ),
            )

    def set_storefront_price(
        self,
        sku: str,
        merchant_id: str,
        new_price: Decimal,
        currency: str = "USD",
        actor_id: str = "merchant",
    ) -> ProductComparisonResponse:
        sf = self.storefront_repo.get_by_sku(sku)
        if not sf:
            raise KeyError(f"Storefront product with SKU '{sku}' not found.")
        if sf.merchant_id != merchant_id:
            raise PermissionError(f"Actor from merchant '{merchant_id}' cannot mutate storefront product for '{sf.merchant_id}'.")

        old_price = str(sf.price)
        with atomic_transaction(self.session):
            sf.price = new_price
            sf.currency = currency
            sf.version += 1
            sf.updated_at = datetime.datetime.now(datetime.timezone.utc)
            self.storefront_repo.create(sf)

            correlation_id = f"sf-price-{uuid.uuid4()}"
            AuditService.log_event(
                self.session,
                AuditEventCreate(
                    merchant_id=merchant_id,
                    actor_type="merchant",
                    actor_id=actor_id,
                    action="STOREFRONT_PRICE_MODIFIED",
                    entity_type="storefront_product",
                    entity_id=sku,
                    correlation_id=correlation_id,
                    details=json.dumps({"old_price": old_price, "new_price": str(new_price), "currency": currency}),
                ),
            )

        res = self.get_product_by_sku(sku, merchant_id=merchant_id)
        if not res:
            raise KeyError(f"Product with SKU '{sku}' not found.")
        return res
