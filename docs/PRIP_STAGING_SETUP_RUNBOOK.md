# PRIP — Staging Environment Setup Runbook

**Document Version:** 1.0.0  
**Target Environment:** Dedicated Staging Host (Linux / macOS / WSL2)  
**Target Alembic Head:** `011_revalidate_parent_tenant_ownership`  

---

## 1. Overview

This runbook provides step-by-step operational instructions to provision, launch, verify, and dismantle the PRIP staging environment using Docker Compose and PostgreSQL 16.

---

## 2. Step-by-Step Staging Setup Procedure

### Step 1: Repository Checkout & Integrity Verification
On the provisioned staging host, clone or extract the repository:

```bash
git clone <repository_url> prip-staging
cd prip-staging

# Verify expected branch and clean status
git status

# Verify files are present
ls -la infra/ backend/ frontend/ docs/
```

### Step 2: Safe Environment Configuration
Create `.env.staging` from the template. Never commit this file.

```bash
cp .env.example .env.staging
chmod 600 .env.staging
```

Generate cryptographically secure secrets:
```bash
# Generate database password and session secret
DB_PASS=$(openssl rand -hex 24)
SESS_SECRET=$(openssl rand -hex 32)

# Populate into .env.staging
sed -i "s/prip_secure_password_replace_in_prod/${DB_PASS}/g" .env.staging
sed -i "s/prip-insecure-default-change-in-production/${SESS_SECRET}/g" .env.staging
sed -i "s/APP_ENV=development/APP_ENV=staging/g" .env.staging
```

If validating live PayPal Sandbox or OIDC, configure those values now:
```bash
# For live PayPal Sandbox testing (optional):
# PAYPAL_CLIENT_TYPE=sdk
# PAYPAL_CLIENT_ID=your_sandbox_client_id
# PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
# PAYPAL_WEBHOOK_ID=your_sandbox_webhook_id
```

### Step 3: Build Container Images
Build the backend, worker, and frontend images:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml build
```

### Step 4: Start Database & Verify PostgreSQL Readiness
Start the PostgreSQL 16 service first and observe health status:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml up -d db

# Wait for database healthcheck to report healthy
docker compose --env-file .env.staging -f infra/docker-compose.yml ps db
```

Verify database connectivity directly using `pg_isready`:
```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml exec db pg_isready -U prip -d prip_db
# Expected output: prip_db - accepting connections
```

### Step 5: Execute Alembic Migrations to Revision 011
Run the dedicated migration job container:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml run --rm migration
```

Verify migration status and exact head:
```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml run --rm migration alembic current
# Expected output: 011_revalidate_parent_tenant_ownership (head)
```

### Step 6: Start Full Application Stack
Start all remaining services (backend, worker, frontend):

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml up -d

# Verify all containers are running and healthy
docker compose --env-file .env.staging -f infra/docker-compose.yml ps
```

### Step 7: Verify Service Health & Liveness Probes
Execute probe validations:

```bash
# 1. API Liveness Probe (verifies process is running)
curl -f http://localhost:8000/api/health/live
# Expected: {"status": "alive"}

# 2. API Readiness Probe (verifies PostgreSQL connection)
curl -f http://localhost:8000/api/health/ready
# Expected: {"status": "ready", "database": "connected"}

# 3. Nginx Reverse Proxy Health Probe
curl -f http://localhost/nginx-health
# Expected: healthy
```

### Step 8: Verify Background Worker Heartbeat
Check that the background worker has registered its heartbeat in PostgreSQL:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml exec backend python -c "
from backend.core.database import SessionLocal
from backend.repositories.worker_heartbeat import WorkerHeartbeatRepository
s = SessionLocal()
heartbeats = WorkerHeartbeatRepository(s).list_heartbeats()
for h in heartbeats:
    print(f'Worker: {h.worker_id} | Status: {h.status} | Last Heartbeat: {h.last_heartbeat_at}')
s.close()
"
```

### Step 9: Verify Nginx Routing & Rate Limiting
Test standard request routing through Nginx:

```bash
# Verify product list routed through Nginx on port 80
curl -f http://localhost/api/products

# Verify rate limiting returns HTTP 429 when bursting over limit
for i in {1..45}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/products
done
# Expected: First 40 return 200, subsequent return 429
```

---

## 3. Safe Shutdown, Restart, and Cleanup

### Graceful Shutdown (Preserving Data)
To stop the staging environment while keeping PostgreSQL data volume intact:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml stop
```

### Safe Restart
```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml start
```

### Disposable Data Tear-down (Complete Reset)
To destroy all containers and remove the database volume for a fresh test cycle:

```bash
docker compose --env-file .env.staging -f infra/docker-compose.yml down -v --remove-orphans
```
