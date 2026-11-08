# PRIP Operations Runbook

## 1. Routine Observability & Monitoring

### 1.1 Health Probes
- **Liveness Probe**: `GET /api/health/live` (HTTP 200 `{"status": "alive"}`)
- **Readiness Probe**: `GET /api/health/ready` (HTTP 200 `{"status": "ready", "database": ...}`)

### 1.2 Metrics Endpoint
- **Telemetry Metrics**: `GET /api/operations/metrics`
  Returns structured counters and gauges:
  - `webhook_events.processed`: Cumulative successful event executions.
  - `webhook_events.retryable_failure`: Retried event counter.
  - `webhook_events.dead_letter`: Exhausted retry count.

### 1.3 Operations Dashboard Overview & Tenant Scoping (SEC-TENANT-004)
- `GET /api/operations/overview`
  Consolidated summary of:
  - Webhook queue depth by status (`PENDING`, `PROCESSING`, `RETRYABLE_FAILURE`, `DEAD_LETTER`).
  - Active worker heartbeats and lease states.
  - Pending payment reconciliations.
  - **Tenancy Boundary**: Merchant operators (`merchant_admin`, `demo_operator`) see strictly their own tenant's webhook counts and reconciliations. Platform superadmins (`superadmin`, `system_admin`) retain global multi-tenant visibility.

---

## 2. Webhook Queue & Failure Management

### 2.1 Investigating Stuck Webhooks
Query all events in non-terminal error states (scoped to caller's merchant tenant):
```bash
curl -s http://localhost:8000/api/operations/webhooks/stuck \
  -H "Authorization: Bearer <MERCHANT_ADMIN_TOKEN>"
```

### 2.2 Replaying Dead-Letter Events
When a bug or network outage is resolved, dead-lettered events can be safely replayed.
Tenancy authorization (`require_merchant_access`) is strictly enforced: merchant admins can only replay their own events (cross-tenant replay returns HTTP 403 Forbidden). Superadmins can replay events globally.
```bash
# Replay specific event
curl -X POST http://localhost:8000/api/operations/webhooks/12/replay \
  -H "Authorization: Bearer <MERCHANT_ADMIN_TOKEN>"

# Reprocess all failed events for tenant
curl -X POST http://localhost:8000/api/operations/webhooks/reprocess-failed \
  -H "Authorization: Bearer <MERCHANT_ADMIN_TOKEN>"
```
Replay resets event status to `PENDING`, zeroes attempt counts, and logs an append-only audit record stamped with the tenant's `merchant_id`.

---

## 3. Secret & Key Rotation Procedures

### 3.1 Session Secret Rotation
1. Generate new 64-character entropy string.
2. Update `SESSION_SECRET` in `.env.production`.
3. Restart backend service: `docker compose restart backend`.

### 3.2 Enterprise OIDC Asymmetric Key Rotation (Zero-Downtime)
1. Identity Provider (IdP) introduces a new RSA/EC key pair and updates its public JWKS endpoint (`OIDC_JWKS_URL`) with the new `kid`.
2. PRIP's `JWKSManager` automatically fetches and caches the new signing key on token presentation with the corresponding `kid`.
3. Existing valid tokens signed with previous keys continue to verify until expiration.
4. No backend container restart or configuration modification is required for key rotation.

### 3.3 PayPal Sandbox Credentials Rotation
1. Generate new Sandbox REST app credentials in PayPal Developer Portal.
2. Update `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`.
3. Restart backend and worker containers:
   `docker compose restart backend worker`
