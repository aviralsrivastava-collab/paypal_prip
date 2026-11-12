from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.products import (
    create_product,
    delete_product,
    get_product,
    get_product_by_sku,
    list_products,
    update_product,
    update_storefront_price,
)
from backend.core.security import AuthenticatedActor
from backend.models.merchant import Merchant, MerchantStatus
from backend.schemas.product import (
    ProductCreate,
    ProductUpdate,
    StorefrontPriceUpdate,
)


@pytest.fixture
def test_merchants(db_session: Session):
    m1 = Merchant(id="merch_alpha", slug="alpha", name="Alpha Store", status=MerchantStatus.ACTIVE.value)
    m2 = Merchant(id="merch_beta", slug="beta", name="Beta Store", status=MerchantStatus.ACTIVE.value)
    db_session.add_all([m1, m2])
    db_session.commit()
    return m1, m2


def test_create_product_and_storefront(db_session: Session, test_merchants):
    actor = AuthenticatedActor(
        actor_id="usr_mgr_1",
        role="MANAGER",
        merchant_id="merch_alpha",
    )
    req = ProductCreate(
        sku="TEST-SKU-001",
        title="TrailBlazer Pro Shoe",
        description="High durability hiking footwear",
        price=Decimal("150.00"),
        currency="USD",
        availability="IN_STOCK",
        storefront_price=Decimal("175.00"),
    )
    created = create_product(request=req, actor=actor, db=db_session)
    assert created.sku == "TEST-SKU-001"
    assert created.merchant_id == "merch_alpha"
    assert created.price == "150.00"
    assert created.source_version == 1

    # Verify comparison
    comp = get_product_by_sku(sku="TEST-SKU-001", db=db_session, current_actor=actor)
    assert comp.merchant_price == "150.00"
    assert comp.storefront_price == "175.00"
    assert comp.has_discrepancy is True
    assert comp.price_discrepancy == "+25.00"


def test_duplicate_sku_rejected(db_session: Session, test_merchants):
    actor = AuthenticatedActor(
        actor_id="usr_mgr_1",
        role="MANAGER",
        merchant_id="merch_alpha",
    )
    req = ProductCreate(
        sku="TEST-DUP-01",
        title="Duplicate Test Product",
        price=Decimal("50.00"),
        currency="USD",
    )
    create_product(request=req, actor=actor, db=db_session)

    with pytest.raises(HTTPException) as exc_info:
        create_product(request=req, actor=actor, db=db_session)
    assert exc_info.value.status_code == 409


def test_update_product_versioning(db_session: Session, test_merchants):
    actor = AuthenticatedActor(
        actor_id="usr_mgr_1",
        role="MANAGER",
        merchant_id="merch_alpha",
    )
    req = ProductCreate(
        sku="TEST-UPD-01",
        title="Initial Title",
        price=Decimal("80.00"),
        currency="USD",
    )
    created = create_product(request=req, actor=actor, db=db_session)
    assert created.source_version == 1

    upd_req = ProductUpdate(
        title="Updated Title V2",
        price=Decimal("95.00"),
    )
    updated = update_product(product_id=created.id, request=upd_req, actor=actor, db=db_session)
    assert updated.title == "Updated Title V2"
    assert updated.price == "95.00"
    assert updated.source_version == 2


def test_cross_tenant_update_and_delete_blocked(db_session: Session, test_merchants):
    alpha_actor = AuthenticatedActor(
        actor_id="usr_alpha",
        role="MANAGER",
        merchant_id="merch_alpha",
    )
    beta_actor = AuthenticatedActor(
        actor_id="usr_beta",
        role="MANAGER",
        merchant_id="merch_beta",
    )
    beta_admin = AuthenticatedActor(
        actor_id="admin_beta",
        role="ADMIN",
        merchant_id="merch_beta",
    )

    req = ProductCreate(
        sku="ALPHA-ONLY-01",
        title="Alpha Exclusive Product",
        price=Decimal("200.00"),
        currency="USD",
    )
    created = create_product(request=req, actor=alpha_actor, db=db_session)

    # Beta manager cannot update Alpha product
    with pytest.raises(HTTPException) as exc_info:
        update_product(
            product_id=created.id,
            request=ProductUpdate(title="Hacked"),
            actor=beta_actor,
            db=db_session,
        )
    assert exc_info.value.status_code == 403

    # Beta admin cannot delete Alpha product
    with pytest.raises(HTTPException) as exc_info:
        delete_product(
            product_id=created.id,
            actor=beta_admin,
            db=db_session,
        )
    assert exc_info.value.status_code == 403


def test_delete_product(db_session: Session, test_merchants):
    alpha_admin = AuthenticatedActor(
        actor_id="admin_alpha",
        role="ADMIN",
        merchant_id="merch_alpha",
    )
    alpha_mgr = AuthenticatedActor(
        actor_id="mgr_alpha",
        role="MANAGER",
        merchant_id="merch_alpha",
    )

    req = ProductCreate(
        sku="ALPHA-DEL-01",
        title="Product To Delete",
        price=Decimal("120.00"),
        currency="USD",
    )
    created = create_product(request=req, actor=alpha_mgr, db=db_session)

    # Delete product
    delete_product(product_id=created.id, actor=alpha_admin, db=db_session)

    # Verify 404
    with pytest.raises(HTTPException) as exc_info:
        get_product(product_id=created.id, db=db_session, current_actor=alpha_admin)
    assert exc_info.value.status_code == 404


def test_update_storefront_price_simulates_discrepancy(db_session: Session, test_merchants):
    alpha_mgr = AuthenticatedActor(
        actor_id="mgr_alpha",
        role="MANAGER",
        merchant_id="merch_alpha",
    )

    req = ProductCreate(
        sku="ALPHA-SIM-01",
        title="Discrepancy Simulation Item",
        price=Decimal("100.00"),
        currency="USD",
        storefront_price=Decimal("100.00"),
    )
    create_product(request=req, actor=alpha_mgr, db=db_session)

    # Initially matching
    comp1 = get_product_by_sku(sku="ALPHA-SIM-01", db=db_session, current_actor=alpha_mgr)
    assert comp1.has_discrepancy is False

    # Simulate rogue storefront price increase to 135.00
    comp2 = update_storefront_price(
        sku="ALPHA-SIM-01",
        request=StorefrontPriceUpdate(price=Decimal("135.00"), currency="USD"),
        actor=alpha_mgr,
        db=db_session,
    )
    assert comp2.has_discrepancy is True
    assert comp2.price_discrepancy == "+35.00"
    assert comp2.storefront_price == "135.00"
