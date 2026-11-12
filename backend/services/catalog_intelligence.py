from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.integrations.ai.gemini_provider import GeminiAIProvider
from backend.repositories.product import ProductRepository


class CatalogIntelligenceService:
    """
    Catalog Intelligence Service.
    Computes catalog health metrics, attribute completeness, title normalization,
    and quality scoring without modifying ground-truth catalog persistence.
    """

    def __init__(self, session: Session, ai_provider: Optional[GeminiAIProvider] = None) -> None:
        self.session = session
        self.product_repo = ProductRepository(session)
        self.ai_provider = ai_provider or GeminiAIProvider()

    def analyze_catalog(self, merchant_id: Optional[str] = None) -> Dict[str, Any]:
        products = self.product_repo.get_all(merchant_id=merchant_id)
        if not products:
            return {
                "total_products": 0,
                "health_index": 100.0,
                "items_complete": 0,
                "items_needing_improvement": 0,
                "products_analysis": [],
            }

        analyzed_items: List[Dict[str, Any]] = []
        total_score = 0
        complete_count = 0

        for p in products:
            item_analysis = self.ai_provider.analyze_catalog_item(
                sku=p.sku,
                title=p.title,
                description=p.description,
                price=p.price,
                currency=p.currency,
            )
            item_analysis["product_id"] = p.id
            item_analysis["current_price"] = f"{p.price:.2f}"
            item_analysis["currency"] = p.currency
            analyzed_items.append(item_analysis)
            total_score += item_analysis["quality_score"]
            if item_analysis["is_complete"]:
                complete_count += 1

        avg_score = round(total_score / len(products), 1)

        return {
            "total_products": len(products),
            "health_index": avg_score,
            "items_complete": complete_count,
            "items_needing_improvement": len(products) - complete_count,
            "products_analysis": analyzed_items,
        }

    def analyze_single_product(self, sku: str, merchant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        product = self.product_repo.get_by_sku(sku, merchant_id=merchant_id)
        if not product:
            return None
        analysis = self.ai_provider.analyze_catalog_item(
            sku=product.sku,
            title=product.title,
            description=product.description,
            price=product.price,
            currency=product.currency,
        )
        analysis["product_id"] = product.id
        analysis["current_price"] = f"{product.price:.2f}"
        analysis["currency"] = product.currency
        return analysis
