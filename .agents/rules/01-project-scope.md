---
trigger: always_on
description: PRIP product scope, claims, and MVP boundaries.
---
# PRIP product scope

- Build only the controlled-storefront vertical slice defined in `docs/PRODUCT_SPEC.md`.
- MVP includes one controlled demo storefront, a small seeded catalog, evidence-backed inspection, structured AI diagnosis, merchant approval/rejection, controlled correction, reinspection, checkout preflight, PayPal Sandbox order/approval/capture, webhook verification, audit trail, and resettable demo data.
- Do not add universal crawling, bot-challenge bypass, arbitrary-site guarantees, Shopify/WooCommerce/ERP/PIM integrations, multi-merchant tenancy, role hierarchy, autonomous listing changes, autonomous payments, multiple gateways, dispute/payout automation, or A/B testing unless the user explicitly changes scope.
- Do not claim recovered revenue, conversion lift, production payment processing, universal site coverage, or calibrated AI confidence without separate evidence.
- Keep the demo scenario reproducible: StrideX Runner, SKU `SX-001`, catalog USD 100.00, controlled storefront USD 120.00, same configured variant and market, no active promotion.
- If a task expands scope, explain the cost and ask before implementing it.
