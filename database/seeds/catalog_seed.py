"""
PRIP Catalog & Storefront Seeding Script
========================================
Seeds the standard PRIP demo scenario:
- Product: StrideX Runner
- SKU: SX-001
- Merchant-authorized catalog price: USD 100.00
- Controlled storefront price: USD 120.00
- Established price discrepancy: USD 20.00

Idempotency:
- If records already exist, running without --reset is a safe no-op.
- Running with --reset restores the initial baseline.
"""

import argparse
from pathlib import Path
import sys
from typing import Any, Dict

# Ensure project root is in sys.path when script is executed directly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.database import SessionLocal
from backend.services.catalog import CatalogService


def run_seed(reset: bool = False) -> Dict[str, Any]:
    """Execute catalog and storefront seeding."""
    db = SessionLocal()
    try:
        service = CatalogService(db)
        result = service.seed_initial_catalog(reset=reset)
        print(f"Catalog seeding completed: {result}")
        return result
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed PRIP catalog and storefront demo data")
    parser.add_argument("--reset", action="store_true", help="Reset catalog and storefront to baseline")
    args = parser.parse_args()

    try:
        run_seed(reset=args.reset)
        sys.exit(0)
    except Exception as ex:
        print(f"Error during seeding: {ex}", file=sys.stderr)
        sys.exit(1)
