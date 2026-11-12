from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from backend.api.chat import ChatMessage, ChatRequest, chat_with_assistant, get_catalog_intelligence, get_revenue_intelligence
from backend.core.security import AuthenticatedActor
from backend.integrations.ai.context import DiagnosisPromptContext
from backend.integrations.ai.gemini_provider import GeminiAIProvider
from backend.models.merchant import Merchant, MerchantStatus
from backend.models.product import Product
from backend.models.storefront import StorefrontProduct
from backend.services.catalog_intelligence import CatalogIntelligenceService
from backend.services.revenue_intelligence import RevenueIntelligenceService


@pytest.fixture
def ai_fixture(db_session: Session):
    m = Merchant(
        id="merch_ai_test",
        slug="ai-store",
        name="AI Athletics Store",
        status=MerchantStatus.ACTIVE.value,
        currency="USD",
    )
    p1 = Product(
        merchant_id="merch_ai_test",
        sku="AI-SKU-001",
        title="Nike Air Pegasus Running Shoes",
        description="Premium responsive running shoe with breathable engineered mesh.",
        price=Decimal("120.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    p2 = Product(
        merchant_id="merch_ai_test",
        sku="AI-SKU-002",
        title="Cap",
        description="A cap",
        price=Decimal("25.00"),
        currency="USD",
        availability="IN_STOCK",
        source_version=1,
    )
    sf1 = StorefrontProduct(
        merchant_id="merch_ai_test",
        sku="AI-SKU-001",
        title="Nike Air Pegasus Running Shoes",
        price=Decimal("140.00"),  # $20 discrepancy
        currency="USD",
        availability="IN_STOCK",
        url_path="/products/pegasus",
        version=1,
    )
    sf2 = StorefrontProduct(
        merchant_id="merch_ai_test",
        sku="AI-SKU-002",
        title="Cap",
        price=Decimal("25.00"),  # 0 discrepancy
        currency="USD",
        availability="IN_STOCK",
        url_path="/products/cap",
        version=1,
    )
    db_session.add_all([m, p1, p2, sf1, sf2])
    db_session.commit()
    return m, p1, p2


def test_gemini_provider_fallback_diagnosis():
    provider = GeminiAIProvider()
    context = DiagnosisPromptContext(
        scan_id=1,
        sku="SX-001",
        inspection_state="ISSUE_DETECTED",
        is_comparable=True,
        failure_reason=None,
        catalog_price=Decimal("100.00"),
        observed_price=Decimal("120.00"),
        currency="USD",
        discrepancy_amount=Decimal("20.00"),
        evidence_records=[{"evidence_id": 1, "field": "price", "value": "120.00"}],
        allowed_evidence_ids=[1],
    )
    diagnosis = provider.generate_diagnosis(context)
    assert diagnosis.status.value == "COMPLETED"
    assert "PRICE_MISMATCH" in diagnosis.likely_causes
    assert len(diagnosis.summary) > 10
    assert 1 in diagnosis.supporting_evidence_ids
    assert len(diagnosis.confidence_explanation) > 10


def test_catalog_intelligence_service(db_session: Session, ai_fixture):
    service = CatalogIntelligenceService(db_session)
    result = service.analyze_catalog(merchant_id="merch_ai_test")

    assert result["total_products"] == 2
    assert result["health_index"] > 50.0
    assert len(result["products_analysis"]) == 2

    # High quality product
    p1_analysis = next(item for item in result["products_analysis"] if item["sku"] == "AI-SKU-001")
    assert p1_analysis["quality_score"] == 100
    assert p1_analysis["is_complete"] is True
    assert p1_analysis["suggested_category"] == "Footwear & Athletic Apparel"

    # Low quality product
    p2_analysis = next(item for item in result["products_analysis"] if item["sku"] == "AI-SKU-002")
    assert p2_analysis["quality_score"] < 100
    assert len(p2_analysis["recommendations"]) > 0


def test_revenue_intelligence_service(db_session: Session, ai_fixture):
    service = RevenueIntelligenceService(db_session)
    metrics = service.get_revenue_metrics(merchant_id="merch_ai_test")

    assert metrics["total_products_monitored"] == 2
    assert metrics["active_discrepancies"] == 1
    assert metrics["at_risk_revenue_leakage"] == "20.00"
    assert metrics["integrity_score_pct"] == 50.0
    assert metrics["protection_status"] == "ACTION_REQUIRED"


def test_chat_assistant_endpoint(db_session: Session, ai_fixture):
    actor = AuthenticatedActor(
        actor_id="user_ai",
        role="OWNER",
        merchant_id="merch_ai_test",
    )
    req = ChatRequest(
        messages=[
            ChatMessage(role="user", content="What is the current discrepancy status for my store?")
        ]
    )
    res = chat_with_assistant(request=req, actor=actor, db=db_session)
    assert res.reply is not None
    assert len(res.reply) > 20
    assert len(res.suggested_actions) >= 1

    # Endpoints
    cat_intel = get_catalog_intelligence(actor=actor, db=db_session)
    assert cat_intel["total_products"] == 2

    rev_intel = get_revenue_intelligence(actor=actor, db=db_session)
    assert rev_intel["at_risk_revenue_leakage"] == "20.00"
