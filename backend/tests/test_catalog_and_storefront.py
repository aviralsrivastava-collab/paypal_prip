from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.core.database import atomic_transaction
from backend.models.product import Product
from backend.repositories.audit import AuditRepository
from backend.repositories.product import ProductRepository
from backend.repositories.storefront import StorefrontRepository
from backend.schemas.product import ProductCreate
from backend.schemas.storefront import StorefrontUpdatePriceRequest
from backend.services.catalog import CatalogService
from backend.services.storefront import StorefrontService


class TestCatalogAndStorefront:

    def test_1_seed_creates_expected_scenario_and_discrepancy(self, db_session):
        service = CatalogService(db_session)
        result = service.seed_initial_catalog()

        assert result["status"] == "success"
        assert result["sku"] == "SX-001"
        assert result["catalog_price"] == "100.00"
        assert result["storefront_price"] == "120.00"
        assert result["discrepancy"] == "+20.00"

        # Verify database entities directly
        prod = ProductRepository(db_session).get_by_sku("SX-001")
        assert prod is not None
        assert prod.title == "StrideX Runner"
        assert prod.price == Decimal("100.00")
        assert prod.currency == "USD"

        storefront = StorefrontRepository(db_session).get_by_sku("SX-001")
        assert storefront is not None
        assert storefront.price == Decimal("120.00")
        assert storefront.currency == "USD"

        # Audit events should be logged
        events = AuditRepository.list_by_entity(db_session, "product", "SX-001")
        assert len(events) == 1
        assert events[0].action == "CATALOG_SEEDED"

    def test_2_seed_idempotency_repeated_execution(self, db_session):
        service = CatalogService(db_session)
        # First execution
        res1 = service.seed_initial_catalog()
        assert res1["catalog_created"] is True
        assert res1["storefront_created"] is True

        # Second execution without reset must be a safe no-op
        res2 = service.seed_initial_catalog(reset=False)
        assert res2["catalog_created"] is False
        assert res2["storefront_created"] is False

        # Verify only 1 product exists in the table
        all_products = ProductRepository(db_session).get_all()
        assert len(all_products) == 1
        assert all_products[0].sku == "SX-001"

    def test_3_sku_uniqueness_constraint(self, db_session):
        repo = ProductRepository(db_session)
        p1 = Product(
            sku="SX-UNIQUE-1",
            title="First Shoe",
            price=Decimal("99.00"),
            currency="USD",
        )
        repo.create(p1)
        db_session.commit()

        # Duplicate SKU must fail database constraint
        p2 = Product(
            sku="SX-UNIQUE-1",
            title="Second Shoe",
            price=Decimal("110.00"),
            currency="USD",
        )
        with pytest.raises(IntegrityError):
            repo.create(p2)
            db_session.commit()
        db_session.rollback()

    def test_4_price_precision_and_validation(self):
        # Valid 2 decimal places
        valid = ProductCreate(
            sku="SX-VAL-1",
            title="Valid Price",
            price=Decimal("100.00"),
            currency="USD",
        )
        assert valid.price == Decimal("100.00")

        # More than 2 decimal places must be rejected
        with pytest.raises(ValueError, match="cannot exceed 2 decimal places"):
            ProductCreate(
                sku="SX-VAL-2",
                title="Invalid Precision",
                price=Decimal("100.005"),
                currency="USD",
            )

        # Zero or negative must be rejected by Pydantic gt constraint
        with pytest.raises(ValueError, match="greater than 0"):
            ProductCreate(
                sku="SX-VAL-3",
                title="Zero Price",
                price=Decimal("0.00"),
                currency="USD",
            )

    def test_5_currency_validation(self):
        # Unsupported currency must be rejected
        with pytest.raises(ValueError, match="not supported"):
            ProductCreate(
                sku="SX-CUR-1",
                title="Invalid Currency",
                price=Decimal("50.00"),
                currency="XYZ",
            )

    def test_6_storefront_price_update_and_catalog_isolation(self, db_session):
        from backend.core.security import AuthenticatedActor

        catalog_service = CatalogService(db_session)
        catalog_service.seed_initial_catalog()

        storefront_service = StorefrontService(db_session)
        req = StorefrontUpdatePriceRequest(
            price=Decimal("105.00"),
            currency="USD",
            actor_id="merchant-admin-1",
            expected_version=1,
            reason="Corrected promotion price",
        )
        trusted = AuthenticatedActor(actor_id="merchant-admin-1", role="merchant_operator")
        updated = storefront_service.update_price("SX-001", req, trusted_actor=trusted)

        assert updated.price == "105.00"
        assert updated.version == 2

        # Verify catalog price was NOT altered (remains $100.00)
        catalog_product = ProductRepository(db_session).get_by_sku("SX-001")
        assert catalog_product.price == Decimal("100.00")

        # Verify discrepancy updated to +$5.00
        comparisons = catalog_service.list_products()
        assert len(comparisons) == 1
        assert comparisons[0].price_discrepancy == "+5.00"
        assert comparisons[0].has_discrepancy is True

        # Verify audit trail
        events = AuditRepository.list_by_entity(db_session, "storefront_product", "SX-001")
        update_events = [e for e in events if e.action == "STOREFRONT_PRICE_UPDATED"]
        assert len(update_events) == 1
        assert update_events[0].actor_id == "merchant-admin-1"

    def test_7_storefront_concurrency_conflict(self, db_session):
        catalog_service = CatalogService(db_session)
        catalog_service.seed_initial_catalog()

        storefront_service = StorefrontService(db_session)
        # Attempt update with stale version 999
        req = StorefrontUpdatePriceRequest(
            price=Decimal("100.00"),
            currency="USD",
            actor_id="merchant-admin-1",
            expected_version=999,
        )
        with pytest.raises(ValueError, match="Concurrency conflict"):
            storefront_service.update_price("SX-001", req)

    def test_8_rollback_on_storefront_failure(self, db_session):
        catalog_service = CatalogService(db_session)
        catalog_service.seed_initial_catalog()

        storefront_repo = StorefrontRepository(db_session)
        original_sf = storefront_repo.get_by_sku("SX-001")
        assert original_sf.price == Decimal("120.00")
        original_version = original_sf.version

        # Simulate exception during atomic block
        with pytest.raises(RuntimeError):
            with atomic_transaction(db_session):
                original_sf.price = Decimal("88.88")
                db_session.add(original_sf)
                db_session.flush()
                raise RuntimeError("Simulated failure")

        db_session.expire_all()
        reloaded = storefront_repo.get_by_sku("SX-001")
        assert reloaded.price == Decimal("120.00")
        assert reloaded.version == original_version

    def test_9_api_endpoints(self, db_session):
        from backend.api.products import (
            get_product,
            get_product_by_sku,
            list_products,
            seed_catalog,
        )
        from backend.api.storefront import get_storefront_product, update_storefront_price
        from backend.core.security import AuthenticatedActor

        actor = AuthenticatedActor(actor_id="operator-42", role="demo_operator")

        # 1. Seed via API endpoint
        seed_res = seed_catalog(reset=True, actor=actor, db=db_session)
        assert seed_res["catalog_price"] == "100.00"
        assert seed_res["storefront_price"] == "120.00"
        assert seed_res["discrepancy"] == "+20.00"

        # 2. List products with comparison
        items = list_products(db=db_session)
        assert len(items) >= 1
        item = items[0]
        assert item.sku == "SX-001"
        assert item.merchant_price == "100.00"
        assert item.storefront_price == "120.00"
        assert item.price_discrepancy == "+20.00"
        assert item.has_discrepancy is True

        # 3. Get isolated catalog product by ID
        prod_id = item.id
        detail = get_product(product_id=prod_id, db=db_session)
        assert detail.price == "100.00"
        assert detail.sku == "SX-001"

        # 4. Get storefront product by SKU
        sf_data = get_storefront_product(sku="SX-001", db=db_session)
        assert sf_data.price == "120.00"
        assert sf_data.version == 1

        # 5. Update storefront price via API endpoint
        update_req = StorefrontUpdatePriceRequest(
            price=Decimal("100.00"),
            currency="USD",
            actor_id="operator-42",
            expected_version=1,
            reason="Merchant approved manual alignment",
        )
        updated_sf = update_storefront_price(
            sku="SX-001", request=update_req, current_actor=actor, db=db_session
        )
        assert updated_sf.price == "100.00"
        assert updated_sf.version == 2

        # 6. Verify comparison now shows 0.00 discrepancy
        comp_data = get_product_by_sku(sku="SX-001", db=db_session)
        assert comp_data.price_discrepancy == "+0.00"
        assert comp_data.has_discrepancy is False
