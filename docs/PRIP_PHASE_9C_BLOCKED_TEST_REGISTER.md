# PRIP — Phase 9C Blocked Test Register & Execution Protocol

**Document Version:** 1.0.0  
**Phase:** 9D — Staging Handoff & Test Protocol  
**Purpose:** Formal register of tests that were blocked or not tested in Phase 9C, detailing exact execution commands, required infrastructure, expected evidence, and pass/fail criteria.

---

## 1. Register Overview

The following register contains the 10 core runtime validation gates required to transition PRIP from Phase 9C staging verification to complete operational validation.

---

## 2. Blocked & Untested Test Register

### TEST-01: Docker Compose Service Health & Startup Order
- **Acceptance Criterion:** All 5 services (`prip-db`, `prip-migration`, `prip-backend`, `prip-worker`, `prip-frontend`) build and launch; healthchecks transition to `healthy`; `prip-migration` exits 0 before backend launches.
- **Required Infrastructure:** Docker Engine 24+, Compose v2.20+.
- **Execution Command:**
  ```bash
  docker compose --env-file .env.staging -f infra/docker-compose.yml up -d
  docker compose --env-file .env.staging -f infra/docker-compose.yml ps
  ```
- **Expected Evidence:** Exit code 0; all containers report `healthy` or `exited (0)` for migration.
- **Pass/Fail Criteria:** PASS if all services healthy within 60s; FAIL if any container crashes or healthcheck fails.
- **Current Status:** `READY TO EXECUTE` (Blocked on host lacking Docker).

---

### TEST-02: PostgreSQL 16 Fresh Migrations (001–011)
- **Acceptance Criterion:** Migration job applies revisions 001 through 011 in linear sequence against fresh PostgreSQL 16. Current head matches `011_revalidate_parent_tenant_ownership`.
- **Required Infrastructure:** PostgreSQL 16 container or managed service.
- **Execution Command:**
  ```bash
  docker compose --env-file .env.staging -f infra/docker-compose.yml run --rm migration
  docker compose --env-file .env.staging -f infra/docker-compose.yml run --rm migration alembic current
  ```
- **Expected Evidence:** Output displays `011_revalidate_parent_tenant_ownership (head)`.
- **Pass/Fail Criteria:** PASS if exit code is 0 and head is exactly revision 011; FAIL on any DDL syntax error.
- **Current Status:** `READY TO EXECUTE` (Blocked on host lacking Docker/PostgreSQL).

---

### TEST-03: PostgreSQL Tenant Isolation, Quarantine & Audit Constraints
- **Acceptance Criterion:** Database foreign keys, unique constraints, and append-only audit triggers operate correctly under PostgreSQL 16. Blank/orphan records are quarantined under `QUARANTINED_ORPHAN`.
- **Required Infrastructure:** Running PostgreSQL 16 database.
- **Execution Command:**
  ```bash
  docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend pytest backend/tests/test_migration_009_multi_tenant_backfill.py -v
  ```
- **Expected Evidence:** 3 passed tests; quarantine tables populated without altering valid tenants.
- **Pass/Fail Criteria:** PASS if 3 tests pass on PostgreSQL; FAIL if tenant reassignment or SQL syntax error occurs.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-04: Multi-Process Worker SKIP LOCKED Concurrency
- **Acceptance Criterion:** Launching 2 or more worker processes against PostgreSQL yields zero duplicate claims for pending webhook events. Workers skip locked rows cleanly.
- **Required Infrastructure:** Running PostgreSQL 16; 2 concurrent worker processes.
- **Execution Command:**
  ```bash
  # Scale worker to 2 replicas in compose
  docker compose --env-file .env.staging -f infra/docker-compose.yml up -d --scale worker=2
  # Run dedicated concurrency test
  docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend pytest backend/tests/test_operational_resilience.py -k "test_05_concurrent_workers" -v
  ```
- **Expected Evidence:** Output confirms one worker claims event, second worker skips row without blocking.
- **Pass/Fail Criteria:** PASS if no deadlocks and exactly 1 worker processes each event; FAIL if duplicate processing detected.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-05: Worker Lease Expiry and Crash Recovery
- **Acceptance Criterion:** When a worker crashes while processing an event, the expired lease (`processing_lease_expires_at < now`) is safely reclaimed by another worker after lease timeout.
- **Required Infrastructure:** Running PostgreSQL 16; worker process kill simulation.
- **Execution Command:**
  ```bash
  docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend pytest backend/tests/test_operational_resilience.py -k "test_03_worker_crash or test_04_expired_processing_lease" -v
  ```
- **Expected Evidence:** Expired lease reclaimed, attempt_count incremented, event completed successfully.
- **Pass/Fail Criteria:** PASS if event transitions from PROCESSING to COMPLETED; FAIL if event remains permanently stranded.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-06: Nginx Edge Shared Rate-Limit Zones
- **Acceptance Criterion:** Nginx limits requests to 20 r/s (burst 40) on general routes and 5 r/s (burst 10) on sensitive routes, returning HTTP 429 when burst is exceeded.
- **Required Infrastructure:** Nginx container running on port 80 proxying to Backend.
- **Execution Command:**
  ```bash
  # Send 45 rapid requests to general API
  for i in {1..45}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/products; done
  # Send 15 rapid requests to sensitive checkout route
  for i in {1..15}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/checkout/preflight; done
  ```
- **Expected Evidence:** First 40 return 200, last 5 return 429 for general; first 10 return 200, last 5 return 429 for sensitive.
- **Pass/Fail Criteria:** PASS if HTTP 429 returned after burst threshold; FAIL if unlimited requests succeed.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-07: Trusted Proxy Spoofing Resistance
- **Acceptance Criterion:** An untrusted external client sending fabricated `X-Forwarded-For` headers cannot spoof its client identity to bypass rate limiting.
- **Required Infrastructure:** Running Nginx + API container stack.
- **Execution Command:**
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-For: 8.8.8.8" http://localhost/api/products
  docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend pytest backend/tests/test_rate_limiting.py -k "test_untrusted_client_cannot_spoof_forwarded_for" -v
  ```
- **Expected Evidence:** Direct client IP is enforced; spoofed header is ignored.
- **Pass/Fail Criteria:** PASS if untrusted header is discarded; FAIL if rate limiter tracks spoofed IP.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-08: Multi-Replica Application Rate-Limiting Behavior
- **Acceptance Criterion:** Verify behavior when multiple backend API replicas run behind Nginx. Nginx enforces cluster-wide limits at the edge, while local in-memory token buckets operate per-replica.
- **Required Infrastructure:** Running stack with `--scale backend=2`.
- **Execution Command:**
  ```bash
  docker compose --env-file .env.staging -f infra/docker-compose.yml up -d --scale backend=2
  docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend pytest backend/tests/test_rate_limiting.py -k "test_multi_replica" -v
  ```
- **Expected Evidence:** Edge limits enforced globally; per-replica isolation documented.
- **Pass/Fail Criteria:** PASS if cluster is protected at edge without inter-replica cross-talk crashes.
- **Current Status:** `READY TO EXECUTE`.

---

### TEST-09: Live OIDC Dynamic JWKS Retrieval and Key Rotation
- **Acceptance Criterion:** API fetches public signing keys from external staging OIDC IdP JWKS endpoint, validates RS256 token signature, caches key for 3600s, and handles key rotation.
- **Required Infrastructure:** Dedicated staging OIDC provider (Auth0 / Keycloak staging tenant).
- **Execution Command:**
  ```bash
  # Obtain staging Bearer token from IdP
  TOKEN=$(curl -s -X POST "https://${OIDC_ISSUER}oauth/token" -d '...' | jq -r .access_token)
  # Call protected API endpoint
  curl -i -H "Authorization: Bearer ${TOKEN}" http://localhost:8000/api/products
  ```
- **Expected Evidence:** HTTP 200; claims parsed (`sub`, `iss`, `merchant_id`).
- **Pass/Fail Criteria:** PASS on valid signature and claims; FAIL if token accepted without valid signature.
- **Current Status:** `NOT TESTED` (Requires provisioned staging OIDC provider).

---

### TEST-10: PayPal Developer Sandbox Handshake and Webhook Verification
- **Acceptance Criterion:** Authenticate with `https://api-m.sandbox.paypal.com` via OAuth2, create an order, verify webhook signature from PayPal Developer Dashboard.
- **Required Infrastructure:** Authorized PayPal Developer Sandbox app credentials.
- **Execution Command:**
  ```bash
  # Trigger checkout order creation
  curl -i -X POST http://localhost:8000/api/checkout/orders -H "Content-Type: application/json" -d '{"sku":"SX-001","quantity":1}'
  ```
- **Expected Evidence:** PayPal order ID generated (`approval_url` returned from `sandbox.paypal.com`).
- **Pass/Fail Criteria:** PASS if Sandbox order created with valid PayPal ID; FAIL if live endpoint called or error returned.
- **Current Status:** `NOT TESTED` (Requires provisioned PayPal Sandbox credentials).

---

## 3. Summary of Register Status

| Test Identifier | Category | Current Status | Blocker |
| :--- | :--- | :--- | :--- |
| **TEST-01** | Docker Compose Stack Health | **READY TO EXECUTE** | Awaiting staging host with Docker Engine |
| **TEST-02** | PostgreSQL 16 Fresh Migrations | **READY TO EXECUTE** | Awaiting staging host with Docker / PostgreSQL 16 |
| **TEST-03** | PostgreSQL Tenant Constraints | **READY TO EXECUTE** | Awaiting staging host with Docker / PostgreSQL 16 |
| **TEST-04** | Multi-Process SKIP LOCKED | **READY TO EXECUTE** | Awaiting staging host with Docker / PostgreSQL 16 |
| **TEST-05** | Worker Lease Expiry Recovery | **READY TO EXECUTE** | Awaiting staging host with Docker / PostgreSQL 16 |
| **TEST-06** | Nginx Edge Rate-Limit Zones | **READY TO EXECUTE** | Awaiting staging host with Docker / Nginx |
| **TEST-07** | Proxy Spoofing Defense | **READY TO EXECUTE** | Awaiting staging host with Docker / Nginx |
| **TEST-08** | Multi-Replica Rate Limiting | **READY TO EXECUTE** | Awaiting staging host with Docker |
| **TEST-09** | Live OIDC JWKS Rotation | **NOT TESTED** | Awaiting dedicated staging IdP credentials |
| **TEST-10** | Live PayPal Sandbox Handshake | **NOT TESTED** | Awaiting dedicated Sandbox app credentials |
