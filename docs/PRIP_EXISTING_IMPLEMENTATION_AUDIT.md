# PRIP Existing Implementation & Architecture Audit (Phase 0)

> **Document:** Comprehensive Technical Audit, Functionality Inventory & Gap Analysis  
> **Status:** Completed Baseline Verification (323 Passed, 1 Skipped, 0 Failed)  
> **Target System:** PRIP (PayPal Revenue Intelligence Platform) — Multi-Merchant SaaS + AI Intelligence Engine + PayPal Payment Infrastructure

---

## 1. Existing Project Architecture

The PRIP repository is structured as a modular monolith adhering to clean architectural boundaries:

```
├── .agents/                    # Agent instructions & specialized skill definitions
├── backend/
│   ├── api/                    # FastAPI routers (checkout, corrections, diagnoses, health, operations, products, scans, storefront, webhooks)
│   ├── core/                   # Configuration (pydantic-settings), database session manager, security (OIDC/JWKS/RBAC)
│   ├── integrations/
│   │   ├── ai/                 # AI diagnostic provider interface, prompt context, mock provider
│   │   ├── paypal/             # PayPal Sandbox client, Orders v2 adapter, webhook signature verifier, mock client
│   │   └── storefront/         # Controlled demo storefront extractor
│   ├── migrations/             # Alembic migration scripts (001 to 012)
│   ├── models/                 # SQLAlchemy ORM declarative models (14 models)
│   ├── policies/               # Deterministic rule engines (checkout preflight, discrepancy classification, correction bounds)
│   ├── repositories/           # Isolated data persistence layers per domain entity
│   ├── schemas/                # Strict Pydantic v2 validation and serialization schemas
│   ├── services/               # Core business services orchestrating domain logic outside open DB transactions
│   └── tests/                  # Pytest test suite (324 tests across unit, integration, and security boundaries)
├── frontend/                   # React 18 + TypeScript + Vite + Tailwind CSS dashboard and demo storefront
└── docs/                       # Product specifications, architecture blueprints, decision records, reports
```

---

## 2. Functionality Inventory & Status

Every major capability of PRIP has been inspected and classified according to the required taxonomy:

| Component / Feature Area | Implementation Status | Evidence / Code References |
| :--- | :--- | :--- |
| **Authentication (OIDC/JWKS)** | **IMPLEMENTED AND VERIFIED** | `backend/core/security.py`: RS256/ES256 asymmetric signature verification, dynamic JWKS discovery, kid validation. 323 passing tests. |
| **Merchant Identity / Tenancy** | **PARTIALLY IMPLEMENTED** | `merchant_id` column present across all models. `require_merchant_access()` enforces tenant checks. Missing: Local `users`, `merchants`, `merchant_memberships` tables. |
| **Controlled Storefront** | **IMPLEMENTED AND VERIFIED** | `backend/models/storefront.py`, `backend/api/storefront.py`: StrideX Runner SKU `SX-001` at $120.00 USD. |
| **Merchant Catalog** | **IMPLEMENTED AND VERIFIED** | `backend/models/product.py`, `backend/api/products.py`: SKU `SX-001` ground truth at $100.00 USD. Missing: Self-serve product CRUD (`POST /api/products`). |
| **Discrepancy Inspection Engine**| **IMPLEMENTED AND VERIFIED** | `backend/services/inspection.py`, `backend/policies/discrepancy_policy.py`: Honest 4-state classification (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`). |
| **AI Investigation & Diagnosis** | **PARTIALLY IMPLEMENTED** | `backend/services/diagnosis.py`, `backend/integrations/ai/`: Structured diagnosis, fault simulation, evidence grounding. Missing: Live LLM adapter (Gemini), conversational assistant, catalog intelligence. |
| **Merchant Correction & Approval**| **IMPLEMENTED AND VERIFIED** | `backend/services/correction.py`: Bounded proposals, merchant approval workflow, version checks, post-correction reinspection. |
| **Checkout Preflight Gate** | **IMPLEMENTED AND VERIFIED** | `backend/policies/checkout_policy.py`: Blocks checkout if catalog != storefront or active issue exists. Verified live in Phase 2 Option A. |
| **PayPal Orders v2 Checkout** | **IMPLEMENTED AND VERIFIED** | `backend/integrations/paypal/client.py`: Orders v2 creation, client credentials grant, Sandbox isolation, return/cancel URL handling. |
| **PayPal Payment Capture** | **IMPLEMENTED AND VERIFIED** | `backend/services/payment.py`: Server-side capture, `COMPLETED` verification, atomic inventory commitment, timeout handling (`UNKNOWN` state). |
| **PayPal Webhook Verification** | **IMPLEMENTED AND VERIFIED** | `backend/services/webhook.py`: Validates 5 transmission headers via official PayPal signature API, deduplicates on `paypal_event_id`. |
| **Append-Only Audit Trail** | **IMPLEMENTED AND VERIFIED** | `backend/models/audit.py`, `backend/services/audit.py`: Attributable event logs across all state mutations. |
| **Row-Level Security (RLS)** | **NOT IMPLEMENTED** | Supabase PostgreSQL tables lack engine-level RLS policies; currently enforced at application layer. |
| **Conversational AI Assistant** | **NOT IMPLEMENTED** | Merchant chat endpoint and retrieval-augmented generation (RAG) tools do not exist. |
| **Revenue Intelligence Analytics**| **PARTIALLY IMPLEMENTED** | Operational dashboard counts exist; advanced revenue trend analytics and leakage detection do not exist. |
| **Multi-Merchant UI / Switcher** | **NOT IMPLEMENTED** | Frontend operates as unauthenticated single-merchant demo UI without login or tenant switcher. |

---

## 3. Existing AI Implementation

- **Interface:** `AIProviderInterface` in `backend/integrations/ai/base.py` defining `generate_diagnosis(prompt_context)`.
- **Implementation:** `MockAIProvider` in `backend/integrations/ai/mock_provider.py` providing deterministic grounding, fault mode simulation (`timeout`, `rate_limit`, `outage`, `invalid_json`), and prompt injection defenses (rejects state overrides and payment execution).
- **Service:** `DiagnosisService` in `backend/services/diagnosis.py` validating that every cited evidence ID exists in `extracted_evidence` table before saving to `diagnoses` table.
- **Gaps:**
  1. Live Gemini/LLM provider adapter missing (currently mock only).
  2. Smart Catalog Intelligence (attribute extraction, description normalization, quality scoring) missing.
  3. Conversational Merchant Assistant (`/api/ai/chat`) missing.
  4. Revenue Intelligence calculations missing.

---

## 4. Existing PayPal Implementation

- **Adapter:** `PayPalSandboxClient` in `backend/integrations/paypal/client.py` strictly enforcing Sandbox base URL (`https://api-m.sandbox.paypal.com`).
- **Order Creation:** Calls `POST /v2/checkout/orders` with `intent: CAPTURE`, passes SKU and amount in `purchase_units`, omits `payee` (defaulting to REST app owner `APP-2PA34687ND667320D`).
- **Capture:** Calls `POST /v2/checkout/orders/{id}/capture` server-side, captures funds, checks `status == "COMPLETED"`.
- **Webhooks:** Listens at `POST /api/webhooks/paypal`, passes headers and raw payload to `POST /v1/notifications/verify-webhook-signature`, stores in `webhook_events`, processes in background worker.
- **Gaps:**
  1. PayPal Complete Payments (PPCP) multi-party payee routing (`purchase_units[].payee.merchant_id`) not yet configured.
  2. Explicit post-capture validation asserting `amount == expected` and `currency == expected` before setting `PaymentStatus.CAPTURED`.
  3. No seller onboarding UI/flow.

---

## 5. Existing Database Structure

14 models defined in `backend/models/`:
- `products`: catalog ground truth
- `storefront_products`: controlled storefront
- `storefront_scans`: inspection results
- `extracted_evidence`: normalized evidence facts
- `diagnosis`: AI diagnoses
- `correction_proposals`: merchant proposals
- `orders`: local orders
- `demo_inventory_reservations`: inventory reservations
- `payment_captures`: capture settlement records
- `reconciliations`: payment reconciliation records
- `webhook_events`: inbound notifications
- `worker_heartbeats`: worker resilience
- `audit_events`: universal audit log
- `demo_state`: demo reset state

---

## 6. Implementation Decision: KEEP, FIX, BUILD

### A. KEEP (Do NOT rebuild; verified working)
- Deterministic preflight discrepancy policy (`backend/policies/checkout_policy.py`).
- PayPal Sandbox client and Orders v2 capture adapter (`backend/integrations/paypal/client.py`).
- Cryptographic PayPal webhook signature verification (`backend/services/webhook.py`).
- Inspection & evidence normalization engine (`backend/services/inspection.py`).
- Bounded merchant correction & approval workflow (`backend/services/correction.py`).
- Append-only audit logging engine (`backend/services/audit.py`).
- Relational database schema for scans, proposals, orders, captures, reservations, and webhooks.

### B. FIX (Improve and repair existing modules)
- `backend/core/security.py`: Replace static Google email mapping with real multi-tenant membership lookup (`merchants`, `users`, `merchant_memberships`).
- `backend/services/payment.py`: Add explicit post-capture invariant assertions (`capture.amount == order.total_amount` and `capture.currency == order.currency`).
- `backend/services/checkout.py`: Propagate merchant-specific payee configuration into PayPal Orders v2 payload.
- `frontend/src/services/api.ts`: Attach dynamic `Authorization: Bearer <token>` and active tenant context to all API requests.

### C. BUILD (Genuinely does not exist)
- **Phase 1:** `merchants`, `users`, and `merchant_memberships` models, repositories, and authentication routes.
- **Phase 2:** Database migration creating tenant tables and Supabase PostgreSQL Row-Level Security (RLS) policies.
- **Phase 3:** Full Product Catalog CRUD endpoints (`POST /api/products`, `PUT /api/products/{id}`, `DELETE /api/products/{id}`).
- **Phase 5:** Multi-tenant webhook routing and payment verification hardening.
- **Phase 6:** Complete AI Intelligence Engine:
  - Live LLM provider adapter (`GeminiProvider` using Google GenAI SDK).
  - Catalog Intelligence Service (attribute extraction, SKU consistency).
  - Conversational Merchant Assistant (`POST /api/ai/chat`) with authorized tool calling.
  - Revenue Intelligence Service (sales trends, leakage detection).
- **Phase 7:** Frontend Multi-Merchant Experience:
  - Login/Register modal with Google OIDC integration.
  - Tenant Switcher in Navbar.
  - Catalog Management page (Add/Edit Product).
  - Conversational AI Assistant Drawer.

---
*Phase 0 Audit Complete. Proceeding autonomously with implementation.*
