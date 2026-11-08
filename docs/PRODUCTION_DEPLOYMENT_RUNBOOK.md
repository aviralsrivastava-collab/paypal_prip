# PRIP Production Deployment Runbook

## 1. Prerequisites and Infrastructure Requirements

- **Runtime**: Docker Engine 24+ and Docker Compose v2.20+
- **Database**: PostgreSQL 16+ with persistent SSD storage and backup volume
- **Reverse Proxy**: Nginx with valid TLS certificates (Let's Encrypt / Cloudflare)
- **Identity Provider**: OpenID Connect compliant IdP (Auth0, Okta, Keycloak) issuing RS256/ES256 asymmetric tokens with public JWKS endpoint
- **PayPal Configuration**: Authorized PayPal Developer Sandbox app credentials (Client ID, Client Secret, Webhook ID)
- **Notice**: Real-money / PayPal Live processing is strictly prohibited in this phase.

---

## 2. Environment Configuration

Create a production environment file (`.env.production`) on the target host:

```bash
APP_ENV=production
APP_NAME=PRIP
APP_VERSION=0.1.0

# Database Configuration (PostgreSQL Target)
DATABASE_URL=postgresql://prip_user:STRONG_PASSWORD_HERE@prip-db:5432/prip_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
DATABASE_POOL_TIMEOUT=30.0
SESSION_SECRET=GENERATE_64_CHAR_RANDOM_SECRET_HERE

# Production OIDC Identity Provider (Mandatory Asymmetric RS256/ES256)
OIDC_ISSUER=https://auth.merchant.com/
OIDC_CLIENT_ID=prip-production-api
OIDC_JWKS_URL=https://auth.merchant.com/.well-known/jwks.json

# PayPal Sandbox Configuration (Live is strictly blocked)
PAYPAL_CLIENT_TYPE=sdk
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_CLIENT_ID=YOUR_SANDBOX_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_CLIENT_SECRET
PAYPAL_WEBHOOK_ID=YOUR_SANDBOX_WEBHOOK_ID

# Controlled Storefront URL Allowlist
CONTROLLED_STOREFRONT_BASE_URL=https://storefront.merchant.com

# Background Worker Settings
WORKER_POLL_INTERVAL_SECONDS=5.0
WORKER_BATCH_SIZE=10
WORKER_LEASE_SECONDS=60
MAX_REQUEST_BODY_BYTES=1048576
```

---

## 3. Deployment Procedure

### Step 1: Database Migration (Mandatory Pre-Deployment Step)
Execute schema migrations to bring the PostgreSQL database to the current revision (`011_revalidate_parent_tenant_ownership`).
In production, this must run as a standalone pre-deployment job before starting API replicas, as `create_all` is intentionally disabled on API startup to prevent race conditions and table locking (SEC-OPS-002).

```bash
docker compose -f infra/docker-compose.yml run --rm migration
```

Verify migration status:
```bash
docker compose -f infra/docker-compose.yml run --rm migration alembic current
```

### Step 2: Build and Launch Containers
```bash
docker compose -f infra/docker-compose.yml up -d --build
```

### Step 3: Verify Container Health Probes
```bash
# Check Docker container status and health
docker compose -f infra/docker-compose.yml ps

# Verify Backend liveness probe
curl -f http://localhost:8000/api/health/live

# Verify Backend readiness probe (checks database connectivity)
curl -f http://localhost:8000/api/health/ready
```

### Step 4: Verify Background Worker Heartbeat
Query the registered worker status via operations endpoint or CLI:
```bash
python -c "from backend.core.database import SessionLocal; from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository; s=SessionLocal(); print([(w.worker_id, w.status) for w in WorkerHeartbeatRepository(s).list_heartbeats()]); s.close()"
```

---

## 4. Rollback and Disaster Recovery

If health checks fail or an unrecoverable failure occurs during deployment:

1. **Stop Application Containers**:
   ```bash
   docker compose -f infra/docker-compose.yml stop backend worker frontend
   ```
2. **Revert Schema Migration (if necessary)**:
   ```bash
   docker compose -f infra/docker-compose.yml run --rm migration alembic downgrade -1
   ```
3. **Relaunch Previous Image Tag**:
   ```bash
   docker compose -f infra/docker-compose.yml up -d
   ```
