# PRIP Security Threat Model (STRIDE)

## 1. Overview and Trust Boundaries

The PayPal Revenue Intelligence Platform (PRIP) enforces strict trust boundaries between external storefronts, client browsers, merchant identity providers, the application backend, and PayPal Sandbox APIs.

```
+-------------------------------------------------------------------------------+
| UNTRUSTED EXTERNAL ZONE                                                       |
| Storefront HTML, Scraping Target, Buyer Browser, Inbound Webhook Payloads    |
+-------------------------------------------------------------------------------+
                                    | (HTTPS / TLS 1.3, Raw Body Signing, OIDC Bearer)
+-------------------------------------------------------------------------------+
| PERIMETER & APPLICATION GATEWAY                                               |
| Nginx Reverse Proxy, Security Headers, 1MB Body Limit, Correlation ID         |
+-------------------------------------------------------------------------------+
                                    | (FastAPI Middleware, Auth Validation, SSRF Guard)
+-------------------------------------------------------------------------------+
| TRUSTED CORE BACKEND                                                          |
| Modular Monolith, Multi-Tenant Domain Services, Append-Only Audit Engine     |
+-------------------------------------------------------------------------------+
                                    | (Isolated Internal Network, Connection Pooling)
+-------------------------------------------------------------------------------+
| ISOLATED PERSISTENCE & WORKERS                                                |
| PostgreSQL 16 (prip-internal network), Standalone Distributed Worker          |
+-------------------------------------------------------------------------------+
```

---

## 2. STRIDE Threat Analysis

### 2.1 Spoofing (Identity Forgery, Tenant Masquerading & BOLA/IDOR)
- **Threat**: Attackers forge merchant identity headers (`X-Actor-ID`, `X-Merchant-ID`), spoof merchant tenant tokens, or perform Insecure Direct Object Reference (IDOR) attacks to mutate other merchants' proposals, orders, captures, storefront prices, or view diagnoses.
- **Mitigations (Remediated: SEC-TENANT-001, SEC-TENANT-002, SEC-AUTH-001)**:
  - In production (`app_env == "production"`), all simulation headers are strictly rejected with HTTP 401. Genuine OIDC Bearer JWTs are mandatory.
  - Enterprise OIDC verification enforces asymmetric signature validation (RS256/ES256) via `pyjwt[crypto]`, using dynamic JWKS discovery with in-memory caching (1-hour TTL, cooldown throttles), key rotation support, mandatory `kid` validation, and issuer authority boundary validation.
  - Symmetric algorithm `HS256` and unsigned `none` algorithms are strictly forbidden and rejected in production.
  - Tokens in production must contain an explicit, verified `merchant_id` claim; fallback to `merchant_default` in production is removed.
  - Object-level authorization (`require_merchant_access`) is strictly enforced at every route and service boundary for proposals (approve, reject, cancel, execute), orders (capture, reconcile), storefront price updates, and diagnosis retrieval/creation.
  - Multi-tenant data attribution: `merchant_id` is durably stamped across `diagnoses`, `evidence_items`, `payment_captures`, and `demo_inventory_reservations`. Migration `010` recalculates historical ownership from parent `storefront_scans` and `orders`, strips `server_default`, and quarantines unlinked orphan rows under the reserved `QUARANTINED_ORPHAN` tenant.
  - Reserved system tenant protection: `QUARANTINED_ORPHAN` and `platform_system` are reserved identifiers in `security.py`. Ordinary merchants are blocked from claiming or querying these system tenants.

### 2.2 Tampering (Data & Integrity Corruption)
- **Threat**: Malicious actors or compromised storefronts alter price observations, modify inspection evidence, or tamper with webhook payloads.
- **Mitigations**:
  - Storefront observations are cryptographically hashed using SHA-256 (`content_hash`) upon extraction.
  - Evidence items are immutable; update and delete operations are strictly prohibited.
  - Inbound PayPal webhooks require raw body cryptographic verification using PayPal certificates and official signature headers (`paypal-transmission-id`, `paypal-transmission-sig`).
  - Worker concurrency integrity: On PostgreSQL, webhook leasing uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent double-claiming or race conditions across distributed worker replicas.

### 2.3 Repudiation (Action Disavowal)
- **Threat**: An operator or merchant disputes authorizing a storefront price change or executing a payment capture.
- **Mitigations (Remediated: SEC-TENANT-003, SEC-AUDIT-001)**:
  - Universal, append-only audit logging (`audit_events` table) records every state mutation, actor ID, actor type, before/after states, timestamp, and correlation ID.
  - Strict audit attribution: Silent fallbacks to `merchant_default` are eliminated across repositories and services. `AuditRepository.append` and `AuditService.log_event` fail closed with `ValueError` on omitted, empty, or conflicting merchant IDs.
  - Infrastructure events (e.g. unassociated webhooks, dead-letter entries) are explicitly scoped to `platform_system`, while business events require explicit merchant tenancy derived from authenticated actor context or trusted entity lineage.
  - Audit records enforce strict tenant attribution (`merchant_id`). Query APIs isolate audit logs by merchant tenant, preventing cross-tenant information exposure. Reserved system tenants (`QUARANTINED_ORPHAN`, `platform_system`) are excluded from tenant queries unless explicitly privileged.
  - Human approval binds cryptographically to the exact proposal ID, catalog source version, and storefront version. AI is restricted to advisory diagnoses and can never authorize or execute corrections.

### 2.4 Information Disclosure (Data Leakage)
- **Threat**: Sensitive credentials, access tokens, customer PII, cross-tenant operational data, or internal stack traces leak into logs, client responses, or version control.
- **Mitigations (Remediated: SEC-TENANT-004)**:
  - `StructuredJsonFormatter` automatically scrubs secrets, client secrets, passwords, Bearer tokens, and payment card patterns from all log records.
  - Cardholder data (PAN, CVV) is never collected or stored; PayPal handles payment capture interfaces.
  - Operational endpoints (`/api/operations/*`) enforce tenant scoping: merchant operators can only inspect their own tenant's stuck webhooks, queue metrics, and pending reconciliations. Platform superadmins maintain separate, explicitly audited global visibility.
  - Generic client error responses mask internal database structures and stack traces.

### 2.5 Denial of Service (Resource Exhaustion)
- **Threat**: Excessive payload uploads, unbounded database connections, or runaway worker retries cause service exhaustion.
- **Mitigations (Remediated: SEC-OPS-001, SEC-OPS-002)**:
  - Database connectivity in production fails closed: if engine initialization fails, a `RuntimeError` halts startup immediately; silent fallback to SQLite in production is eliminated.
  - Production database schema migrations are decoupled from application startup: `Base.metadata.create_all` is disabled on API startup in production, eliminating startup race conditions and table locking across auto-scaling replicas.
  - Max request body size middleware enforces a hard 1MB (`1,048,576 bytes`) limit, returning HTTP 413.
  - PostgreSQL connection pooling (`pool_size=10`, `max_overflow=20`, `pool_timeout=30s`, `pool_pre_ping=True`) prevents connection pool starvation.
  - Webhook processing implements bounded exponential backoff with jitter and dead-letter queue isolation after 5 failed attempts.

### 2.6 Elevation of Privilege (Unauthorized Actions)
- **Threat**: An ordinary user approves catalog price synchronizations or triggers database resets.
- **Mitigations**:
  - Role-based authorization (`require_demo_operator`, `require_operator_role`) restricts reset, approval, and replay actions to verified `demo_operator` or `merchant_admin` roles.
  - Reset and destructive seed endpoints fail closed (HTTP 403) whenever `app_env == "production"`.

---

## 3. SSRF (Server-Side Request Forgery) Defense Matrix

Storefront inspection URLs are subject to strict URL parsing and network validation:
1. **Scheme Validation**: Strictly limited to `http` and `https`.
2. **Cloud Metadata Defense**: Rejects `169.254.169.254`, `metadata.google.internal`, and cloud metadata hostnames.
3. **Private IP Filtering**: Rejects RFC1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`), and link-local ranges (`169.254.0.0/16`, `fe80::/10`).
4. **Host Allowlist**: Production mode strictly restricts external HTTP extraction to the configured `controlled_storefront_base_url`.
