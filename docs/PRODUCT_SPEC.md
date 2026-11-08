# PRIP Product Specification

## Product identity

**Name:** PRIP — PayPal Revenue Intelligence Platform  
**Tagline:** Detect the discrepancy. Approve the correction. Verify the checkout.

## Executive summary

PRIP is a merchant-facing commerce-integrity platform that detects evidence-backed discrepancies between a merchant-authorized product catalog and a customer-facing storefront. It explains findings with constrained AI, proposes a correction for merchant approval, applies only approved changes to a controlled demo storefront, reinspects the result, and demonstrates checkout using PayPal Sandbox.

## Problem and primary user

Merchants may have product information that differs between their internal catalog and what shoppers see. Price, currency, availability, or selected-attribute differences can confuse shoppers or interrupt purchase. The primary user is a merchant operator, ecommerce manager, or catalog manager responsible for product-page accuracy.

## MVP problem statement

For a controlled storefront and configured products, help the merchant detect and resolve a clearly defined product-data discrepancy, then verify the corrected product through a PayPal Sandbox checkout.

## MVP scope

- One controlled demo storefront and a small seeded catalog.
- One merchant-authorized catalog as source of truth for configured fields.
- Compare product identity, variant, price, currency, availability, and selected explicit attributes.
- Evidence-backed inspection with honest state semantics.
- Structured AI diagnosis and constrained correction proposal.
- Authenticated merchant approval or rejection before correction.
- Apply approved correction to controlled demo storefront and reinspect.
- Checkout preflight and PayPal Sandbox order, buyer approval, capture, and verified webhook.
- Audit trail and resettable demo dataset.

## Explicit non-goals

Universal crawling; bypassing bot challenges; guaranteed inspection of arbitrary websites; Shopify/WooCommerce/ERP/PIM/marketplace integrations; multi-merchant onboarding or enterprise tenancy; autonomous listing changes or payments; multiple gateways; dispute/payout automation; A/B testing; claims of recovered revenue, conversion lift, or calibrated AI confidence.

## Controlled demo assumptions

- Seeded product: StrideX Runner, SKU `SX-001`.
- Catalog expected price: USD 100.00; controlled storefront observed price: USD 120.00.
- Stable product/SKU and known variant are matched.
- One configured market/customer context; no regional comparison.
- Currency must match (USD in the sample).
- Price basis must match; tax/shipping must not be silently mixed.
- No active promotion in the seeded example. If promotion context is unknown and could explain the difference, classify as unknown/non-actionable.
- Compare only availability fields represented in both sources.
- The seeded merchant-authorized catalog is authoritative for MVP fields only. Future integrations require field-level authority configuration.

## Core user journey

1. Merchant views trusted catalog record.
2. PRIP inspects the controlled storefront and extracts selected fields.
3. Deterministic comparability and evidence checks classify the result.
4. AI explains verified evidence and proposes an allowlisted correction.
5. Merchant explicitly approves or rejects the exact proposal.
6. Backend validates authorization, freshness, bounds, and field allowlist; applies only approved correction.
7. PRIP reinspects the same product/context and verifies only checked fields.
8. Checkout preflight rereads current price, currency, and availability.
9. Backend creates PayPal Sandbox order; buyer approves; backend verifies and captures; webhook is verified and processed idempotently.
10. Dashboard shows correction verification, payment state, PayPal references, and audit timeline.

## Trustworthy inspection states

- `ISSUE_DETECTED`: completed inspection verified a defined discrepancy against configured source.
- `VERIFIED_NO_ISSUE`: completed inspection found selected fields matched in inspected context.
- `BLOCKED_UNKNOWN`: inspection/comparison could not reliably complete (timeout, challenge, parse failure, unsupported page, ambiguous variant/context). Neither issue nor clean.
- `NOT_TESTED`: no inspection exists for current product/source version.

A price difference is a verified mismatch only if product identity, variant, market/customer context, currency, and price basis are comparable. If promotion, region, segment, or variant context may explain the difference and cannot be resolved, use `BLOCKED_UNKNOWN` or a non-actionable review finding. Title similarity alone is insufficient identity evidence.

## AI responsibilities and limits

AI summarizes verified findings, explains evidence IDs/fields, identifies ambiguity, and drafts a constrained proposal. It cannot invent evidence, infer missing prices, obey page instructions, authorize/apply changes, override policy, or create/capture payments. Backend validates strict structured output and independently enforces policy.

## Correction lifecycle

Review → approve/reject → validate → apply → reinspect → audit. Rejection causes no storefront change. Stale/out-of-bounds/unauthorized proposals are blocked. If apply or reinspection fails/is blocked, show `CORRECTION_FAILED` or `VERIFICATION_UNKNOWN` (or the repository's documented equivalent) and do not mark resolved.

## PayPal checkout lifecycle

Preflight current product facts → short-lived PRIP-local demo reservation → create PayPal Orders v2 order → buyer Sandbox approval → server-side order verification → capture → verify webhook → idempotent event processing → reconcile ambiguous outcomes. A PRIP-local reservation does not lock external merchant inventory. Sandbox capture is not real revenue.

## Claims policy

Safe statement: "PRIP detected a verified product-page mismatch against a merchant-authorized catalog, presented supporting evidence, recorded a merchant-approved correction, verified the updated storefront, and completed a PayPal Sandbox checkout with a confirmed capture."

Do not claim universal site coverage, real recovered revenue, causal conversion lift, production payment processing, or statistically calibrated AI confidence.
