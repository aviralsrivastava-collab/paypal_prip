# PRIP Security and Threat Model

## Scope and trust boundaries

Assets: merchant catalog data, storefront correction capability, PayPal credentials/tokens, payment/order/capture references, webhook integrity, audit history, and merchant sessions.

Trust boundaries: browser ↔ backend; backend ↔ database; backend ↔ controlled storefront adapter; backend ↔ LLM provider; backend ↔ PayPal APIs; PayPal ↔ webhook endpoint; untrusted storefront content ↔ model prompt.

## Threats and required controls

| Threat | Required control | Verification evidence |
|---|---|---|
| Prompt injection in storefront text | Treat page content as untrusted data; no privileged tools; normalize/delimit facts | Adversarial fixture test shows no unauthorized action |
| Hallucinated evidence or values | Evidence-ID allowlist; strict schema; reject unsupported claims | Invalid evidence/schema tests |
| AI bypasses merchant approval | AI has no mutation/payment tools; backend policy gate | Integration test confirms model output cannot mutate |
| Unauthorized correction | Authenticated actor + authorization check at apply time | Unauthorized request causes no mutation |
| Stale approval | Bind approval to proposal/source versions; recheck at apply | Stale-version conflict test |
| Out-of-bounds correction | Field allowlist, type/currency/range validation | Boundary tests |
| SSRF via storefront URL | Restrict fetches to configured controlled hosts; validate redirects/DNS/IP policy as appropriate | Host allowlist and redirect tests |
| Secret leakage | Env/secret manager; `.env` ignored; secret scanning; redact logs | Repository scan and frontend bundle inspection |
| Fake payment success from browser | Server-side PayPal verification and capture | Forged callback test |
| Duplicate/out-of-order webhook | Signature verification, event ID uniqueness, monotonic state transition policy | Duplicate/order tests |
| Webhook forgery/replay | Verify transmission signature, environment, event identity; replay/dedupe controls | Invalid signature and replay tests |
| Duplicate capture after timeout | `UNKNOWN` + reconciliation; no blind retry | Simulated timeout/reconciliation test |
| Stale checkout amount | Server-side preflight rereads current product state | Price/currency/availability change test |
| Audit tampering/leakage | Append-only application semantics; restrict access; redact secrets | Authorization and audit-integrity tests |

## Minimum controls

- Secrets never committed or exposed to browser.
- `.env` ignored; `.env.example` contains placeholders only.
- PayPal Sandbox and Live configurations isolated; MVP defaults to Sandbox.
- No card number/CVV collection or storage.
- Authenticated merchant identity for correction decisions.
- Strict request/model schema validation and allowlisted actions.
- Parameterized database access and transaction boundaries.
- HTTPS in deployed environments; secure cookies/CSRF controls if cookie sessions are used.
- CORS allowlist, rate limits, request size limits, safe error responses, security headers.
- Webhook signature verification before trusting event payload.
- Idempotency and replay protection for payment/webhook operations.
- Safe logging: no tokens, secrets, card data, or unnecessary personal data.

## PayPal verification note

Before implementing, consult current official PayPal documentation for OAuth, Orders v2, idempotency, webhook registration, event types, and signature verification. Do not assume request fields, idempotency guarantees, or event ordering from examples or memory. Sandbox webhook simulator events are useful for event-handler testing but must not be represented as proof of a real Sandbox capture or equivalent signature flow.

## Residual risks / MVP limitations

The controlled storefront adapter is not a production merchant integration. Local reservations do not lock external inventory. Authentication may be simplified for a single-user demo but must not be represented as enterprise multi-tenant security. A hackathon security checklist does not constitute a penetration test or production readiness certification.

---

## Transaction Boundaries and Payment Safety Architecture

### 1. Database Connection Management During External API Calls
Holding a relational database transaction open while awaiting an external HTTP response (e.g. calling PayPal Orders v2 or LLM providers) is strictly forbidden. 
- **Threat:** Network latency or third-party downtime exhausts connection pool, deadlocking local database operations.
- **Architectural Pattern:** State is persisted before the external call, the database transaction is closed, the external request is executed, and subsequent state transitions are committed in a fresh, isolated transaction.

### 2. Uncertain Payment Outcomes and Reconciliation
- On network timeout or ambiguous capture response, payment attempt status must transition to `UNKNOWN`.
- System must **never** blindly retry a capture without reconciling provider state via `GET /v2/checkout/orders/{id}` or `GET /v2/payments/captures/{id}`.
- Transitions must be strictly monotonic: terminal states (`CAPTURED`, `DECLINED`, `CANCELLED`) cannot be regressed by out-of-order webhook deliveries.

### 3. Cryptographic Webhook Verification
- Webhook endpoints must retain raw, unparsed request bytes to perform PayPal transmission signature verification (`PAYPAL-TRANSMISSION-SIG`, `PAYPAL-TRANSMISSION-TIME`, `PAYPAL-TRANSMISSION-ID`, `PAYPAL-CERT-URL`).
- Event IDs are recorded in an inbox table with unique constraints to ensure exactly-once state processing.

---

## Required GitHub Branch Protection Settings

To ensure CI quality gates and security boundaries are enforced on the repository:

1. **Branch Protection Rule on `master` / `main`:**
   - **Require a pull request before merging:** Minimum 1 approving review.
   - **Require status checks to pass before merging:**
     - `Harness & Secret Integrity Check`
     - `Backend Lint, Types, Architecture & Tests`
     - `Frontend Lint, Types, Architecture, Tests & Build`
   - **Require branches to be up to date before merging.**
   - **Do not allow bypassing the above settings:** Enforce for administrators.
   - **Restrict force pushes:** Enabled (prevent history rewriting).
   - **Restrict branch deletions:** Enabled.

