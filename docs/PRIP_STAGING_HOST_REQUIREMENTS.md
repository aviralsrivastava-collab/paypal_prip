# PRIP — Staging Host Infrastructure Requirements

**Document Version:** 1.0.0  
**Phase:** 9D — Staging Handoff & Environment Prerequisites  
**Target Audience:** DevOps Engineers, Platform Administrators, Security Auditors  

---

## 1. Overview and Purpose

This document specifies the technical, infrastructural, architectural, and security prerequisites for provisioning a dedicated staging environment capable of executing the runtime validations defined in Phase 9C for the PayPal Revenue Intelligence Platform (PRIP).

---

## 2. Supported Operating Systems

The PRIP container stack is standardized on OCI-compliant Linux containers:

| Platform | Supported Versions | Notes |
| :--- | :--- | :--- |
| **Ubuntu Linux (Recommended)** | 22.04 LTS (Jammy Jellyfish), 24.04 LTS | Primary validated reference OS |
| **Debian Linux** | Debian 12 (Bookworm) | Fully supported |
| **Red Hat Enterprise Linux / Rocky** | RHEL 9.x / Rocky Linux 9.x | Requires Rootless or Standard Docker / Podman |
| **macOS (Developer Staging)** | macOS 14+ (Sonoma) on Apple Silicon / Intel | Via Docker Desktop or OrbStack |
| **Windows Server / Pro (Staging)** | Windows 11 / Server 2022 via WSL2 | Requires WSL2 with Ubuntu distro and Docker Engine |

---

## 3. Container Runtime and Database Requirements

### 3.1 Docker Engine & Compose
- **Docker Engine:** Version 24.0.0 or higher.
- **Docker Compose:** Version 2.20.0 or higher (v2 plugin format: `docker compose`).
- **Container Architecture:** `linux/amd64` or `linux/arm64`. Multi-arch base images (`python:3.11-slim`, `node:20-alpine`, `nginx:alpine`, `postgres:16-alpine`) support both x86_64 and ARM64.

### 3.2 Database Engine (PostgreSQL 16)
- **Target Version:** PostgreSQL 16.0 or higher (16.2+ recommended).
- **Deployment Mode:**
  - *Option A (Default):* Managed container via `infra/docker-compose.yml` (`image: postgres:16-alpine`).
  - *Option B (External Managed Database):* AWS RDS PostgreSQL 16, Google Cloud SQL for PostgreSQL 16, or Azure Database for PostgreSQL 16.
- **PostgreSQL Configuration Settings:**
  - `max_connections`: >= 100
  - `shared_buffers`: >= 256MB
  - `client_encoding`: `UTF8`

---

## 4. Hardware Sizing Recommendations

> [!NOTE]
> The following resource allocations are engineering recommendations based on containerized component profiles, not hard operational limits.

| Sizing Tier | vCPU Cores | RAM | Storage | Workload Suitability |
| :--- | :--- | :--- | :--- | :--- |
| **Minimum Disposable Staging** | 2 Cores | 4 GB | 20 GB SSD | Basic integration, single-replica backend, migration tests |
| **Standard Multi-Worker Staging** | 4 Cores | 8 GB | 40 GB SSD | Multi-worker concurrency, Nginx rate-limiting, load testing |
| **High-Throughput Benchmark** | 8 Cores | 16 GB | 80 GB NVMe | 50+ concurrent merchant simulated load, crash recovery stress |

---

## 5. Network, DNS, and Firewall Requirements

### 5.1 Internal Container Networking
- **Bridge Network `prip-internal` (`internal: true`):**
  - Isolates PostgreSQL (`prip-db`), Alembic migration runner (`prip-migration`), and Background Worker (`prip-worker`).
  - No inbound traffic from external or host interfaces permitted on port 5432.
- **Bridge Network `prip-public`:**
  - Routes external ingress to Nginx (`prip-frontend`) on port 80 and optionally API direct port 8000 for integration debugging.

### 5.2 Outbound Egress Connectivity
The staging host must have outbound HTTPS (TCP port 443) connectivity to the following endpoints:

| Destination | Purpose | Necessity |
| :--- | :--- | :--- |
| `https://api-m.sandbox.paypal.com` | PayPal Developer Sandbox Orders v2 and Webhook verification | Mandatory for live PayPal tests; optional in mock mode |
| `https://www.sandbox.paypal.com` | PayPal Buyer Approval checkout redirect flow | Mandatory for end-to-end checkout demonstration |
| `https://<oidc-issuer>/.well-known/jwks.json` | Public JWKS endpoint for dynamic RS256/ES256 key retrieval | Mandatory for live OIDC testing; optional in hermetic mode |
| Docker Registry (`docker.io`, `ghcr.io`) | Base image downloads (`postgres:16`, `python:3.11`, `node:20`) | Initial host provisioning |

### 5.3 Inbound Ports & Reverse Proxy
- **Port 80 (HTTP):** Ingress to Nginx (`prip-frontend`).
- **Port 443 (HTTPS - Optional for Staging):** Terminated via host reverse proxy or Cloudflare tunnel.
- **Port 8000 (HTTP - Optional):** Direct API access for debugging. Blocked from public internet via firewall in staging.

---

## 6. Environment Variables Categorization

### 6.1 Mandatory Staging Baseline (Runs with Mock Integrations)
These variables must be populated in `.env.staging` on the host:

```bash
APP_ENV=staging
POSTGRES_USER=prip
POSTGRES_PASSWORD=GENERATE_STRONG_RANDOM_PASSWORD
POSTGRES_DB=prip_db
DATABASE_URL=postgresql://prip:GENERATE_STRONG_RANDOM_PASSWORD@db:5432/prip_db
SESSION_SECRET=GENERATE_64_CHAR_HEX_STRING
PAYPAL_CLIENT_TYPE=mock
PAYPAL_ENVIRONMENT=sandbox
```

### 6.2 Mandatory for Live OIDC Identity Provider Testing
Required only when validating Workstream 6 live identity verification:

```bash
OIDC_ISSUER=https://<your-tenant>.auth0.com/
OIDC_CLIENT_ID=prip-staging-api
OIDC_JWKS_URL=https://<your-tenant>.auth0.com/.well-known/jwks.json
```

### 6.3 Mandatory for Live PayPal Developer Sandbox Testing
Required only when validating Workstream 6 live payment capture:

```bash
PAYPAL_CLIENT_TYPE=sdk
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_CLIENT_ID=YOUR_SANDBOX_REST_APP_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_REST_APP_CLIENT_SECRET
PAYPAL_WEBHOOK_ID=YOUR_SANDBOX_WEBHOOK_ID
PAYPAL_CLIENT_ID_PUBLIC=YOUR_SANDBOX_REST_APP_CLIENT_ID
```

---

## 7. Security and Safety Rules

1. **Sandbox Exclusivity:** `PAYPAL_ENVIRONMENT` must always be `sandbox`. `backend/core/config.py` strictly raises `ValueError` if configured to `live`.
2. **Secret Non-Exposure:** Never commit `.env.staging`, `.env.production`, or private key files into version control.
3. **Quarantine Isolation:** The reserved tenant identity `QUARANTINED_ORPHAN` must remain blocked from merchant queries.
4. **Append-Only Auditing:** Audit logs must retain database-level trigger immutability.
