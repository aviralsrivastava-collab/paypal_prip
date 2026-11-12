from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.policies.checkout_policy import PaymentStatus
from backend.repositories.order import OrderRepository
from backend.repositories.payment_capture import PaymentCaptureRepository
from backend.repositories.product import ProductRepository
from backend.repositories.scan import ScanRepository
from backend.repositories.storefront import StorefrontRepository


class RevenueIntelligenceService:
    """
    Revenue Intelligence Service.
    Computes revenue protection analytics, at-risk revenue leakage from uncorrected discrepancies,
    verified captured volume, and catalog integrity health metrics.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.product_repo = ProductRepository(session)
        self.storefront_repo = StorefrontRepository(session)
        self.scan_repo = ScanRepository(session)
        self.order_repo = OrderRepository(session)
        self.capture_repo = PaymentCaptureRepository(session)

    def get_revenue_metrics(self, merchant_id: Optional[str] = None) -> Dict[str, Any]:
        products = self.product_repo.get_all(merchant_id=merchant_id)
        total_products = len(products)
        discrepancies_count = 0
        total_at_risk_amount = Decimal("0.00")
        currency = "USD"

        for p in products:
            currency = p.currency
            sf = self.storefront_repo.get_by_sku(p.sku)
            if sf:
                diff = abs(sf.price - p.price)
                if diff > Decimal("0.00"):
                    discrepancies_count += 1
                    total_at_risk_amount += diff

        # Captured orders revenue
        orders = self.order_repo.get_all(merchant_id=merchant_id)
        captured_orders = [o for o in orders if o.payment_status == PaymentStatus.CAPTURED.value]
        protected_volume = sum((o.total_amount for o in captured_orders), Decimal("0.00"))

        integrity_score = 100.0
        if total_products > 0:
            clean_count = total_products - discrepancies_count
            integrity_score = round((clean_count / total_products) * 100.0, 1)

        return {
            "merchant_id": merchant_id or "all_merchants",
            "currency": currency,
            "total_products_monitored": total_products,
            "active_discrepancies": discrepancies_count,
            "integrity_score_pct": integrity_score,
            "at_risk_revenue_leakage": f"{total_at_risk_amount:.2f}",
            "verified_captured_volume": f"{protected_volume:.2f}",
            "total_orders_processed": len(orders),
            "completed_captured_orders": len(captured_orders),
            "protection_status": "OPTIMAL" if discrepancies_count == 0 else "ACTION_REQUIRED",
        }
