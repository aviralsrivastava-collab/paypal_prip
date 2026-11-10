# PRIP — Read-Only Deployment & Runtime Infrastructure Audit

**Audit Date:** 2026-11-10  
**Target Project:** PayPal Revenue Intelligence Platform (PRIP)  
**Public Frontend Target:** `https://paypalprip.vercel.app`  
**Audit Scope:** Purely read-only investigation of deployment state, runtime connectivity, database readiness, background worker state, and authentication posture across Vercel, local environment, and cloud infrastructure.

---

## Executive Summary

| Component | Audit Status | Runtime Reachability | Evidence Source |
| :--- | :--- | :--- | :--- |
| **1. Frontend** | **DEPLOYED AND VERIFIED** | **HTTP 200 OK** | Live HTTP probe to `https://paypalprip.vercel.app` |
| **2. FastAPI Backend** | **CONFIGURED BUT NOT DEPLOYED** | **HTTP 500 Internal Server Error** (`FUNCTION_INVOCATION_FAILED`) | Live HTTP probe to `https://paypalprip.vercel.app/api/health` |
| **3. Database** | **RUNNING LOCALLY (SQLite) / NOT PROVISIONED (PostgreSQL)** | Port 5432 closed; SQLite `prip_demo.db` local only | Local socket probe & SQLite inspection |
| **4. Background Worker** | **CONFIGURED BUT NOT DEPLOYED** | Zero worker processes running | OS process scan & Docker inspection |
| **5. Authentication Provider**| **NOT CONFIGURED** | Zero OIDC login flow; mock authority only | Frontend source scan & `.env` configuration |

### Overall Verdict: **`FRONTEND ONLY DEPLOYED`**

---

## 1. Frontend Audit

### Status: **DEPLOYED AND VERIFIED**

### Runtime Evidence:
* **Live HTTP Probe:** `GET https://paypalprip.vercel.app` returns `HTTP 200 OK`.
  * Response Body: Returns valid single-page React HTML shell referencing `/assets/index-Y0iLr5_k.js`.
* **Configured API Base URL:**
  * Direct inspection of the deployed JavaScript bundle (`https://paypalprip.vercel.app/assets/index-Y0iLr5_k.js`) reveals:
    - Baked-in base URL is relative: `"/api"`.
    - No external domain, ngrok URL, or localhost URL is embedded in production API routes.
* **Request Flow:** Browser API calls route to `https://paypalprip.vercel.app/api/*` and depend on Vercel's rewrite rule in `vercel.json` (`/api/(.*)` $\rightarrow$ backend service).

### Remaining Blockers:
* The frontend relies on relative `/api` paths routing to the Vercel backend service, which is currently failing invocation.

### Next Required Action:
* Either point the frontend to an external hosted backend via `VITE_API_URL` (requires a Vercel redeploy), or fix the Vercel serverless Python runtime environment variables and dependencies.

---

## 2. FastAPI Backend Audit

### Status: **CONFIGURED BUT NOT DEPLOYED**

### Runtime Evidence:
* **Remote Vercel Runtime Probe:**
  * `GET https://paypalprip.vercel.app/api/health` $\rightarrow$ `HTTP 500 Internal Server Error`
  * Error Body:
    ```text
    A server error has occurred
    FUNCTION_INVOCATION_FAILED
    ```
  * `GET https://paypalprip.vercel.app/api/products` $\rightarrow$ `HTTP 500 FUNCTION_INVOCATION_FAILED`
* **Local Runtime Probe:**
  * `127.0.0.1:8000` (FastAPI backend port): **CLOSED** (No process listening).
  * `127.0.0.1:8085` (Ingress Guard port): **CLOSED** (No process listening).
* **Configuration Status:**
  * `vercel.json` contains a service definition for backend (`"root": "backend", "framework": "fastapi", "entrypoint": "api/main.py:app"`).
  * Local fixes for module path aliasing and PostgreSQL drivers are in the local working tree but have not been deployed to Vercel.
  * No remote standalone hosting configurations (e.g., `render.yaml`, `railway.json`, `fly.toml`) exist in the repository.

### Remaining Blockers:
* Missing production environment variables (`DATABASE_URL`, `SESSION_SECRET`, `OIDC_ISSUER`, etc.) in Vercel project settings.
* Vercel Serverless Functions cannot host long-running background workers.

### Next Required Action:
* Deploy the verified backend entrypoint fix and configure Vercel environment variables with a live PostgreSQL 16 database, OR host the backend container on a dedicated ASGI platform (e.g. Railway or Render).

---

## 3. Database Audit

### Status: **RUNNING LOCALLY (SQLite) / NOT PROVISIONED (PostgreSQL)**

### Runtime Evidence:
* **Local Database Engine:** Confirmed **SQLite** (`prip_demo.db` in workspace root).
* **Current Local Alembic Revision:**
  * Querying `alembic_version` from `prip_demo.db` returns:
    $$\texttt{011\_revalidate\_parent\_tenant\_ownership}$$
  * All 11 migrations (`001` through `011`) in `backend/migrations/versions/` are represented in the local database.
* **PostgreSQL Engine Status:**
  * Local port `5432`: **CLOSED**.
  * Docker Engine: **Not running**.
  * Production PostgreSQL database (e.g., Supabase, Neon, AWS RDS, Railway): **Not provisioned or connected** in `.env` or Vercel.
* **Fail-Closed Protection:**
  * `backend/core/database.py` strictly prevents SQLite when `APP_ENV=production`. If `DATABASE_URL` is omitted or starts with `sqlite`, the engine throws an immediate `RuntimeError`.

### Remaining Blockers:
* No remote PostgreSQL 16 database has been provisioned.

### Next Required Action:
* Provision a managed PostgreSQL 16 database instance and apply migrations:
  ```bash
  alembic upgrade head
  ```

---

## 4. Background Worker Audit

### Status: **CONFIGURED BUT NOT DEPLOYED**

### Runtime Evidence:
* **Source Implementation:**
  * Worker entrypoint exists in `backend/worker.py`.
  * Service logic implemented in `backend/services/webhook_worker.py`.
* **Local Process Evidence:**
  * Process table check confirms zero `python`, `uvicorn`, or worker processes currently running.
* **Container / Cloud Deployment Evidence:**
  * `infra/Dockerfile.worker` and `infra/docker-compose.yml` define a `prip-worker` container.
  * Docker daemon is not active locally.
  * No standalone background worker service is deployed to any cloud provider.
* **Vercel Incompatibility:**
  * The background worker is an infinite polling daemon (`while not self.shutdown_requested`). Vercel Serverless functions have execution timeouts (15–60s) and cannot host daemon worker loops.

### Remaining Blockers:
* Requires a persistent container host or external scheduler (e.g., Render Background Worker, Railway, AWS ECS, or Vercel Cron).

### Next Required Action:
* Deploy `infra/Dockerfile.worker` to an independent container runtime connected to the PostgreSQL database.

---

## 5. Authentication Provider Audit

### Status: **NOT CONFIGURED**

### Runtime Evidence:
* **Environment Configuration (`.env`):**
  * `APP_ENV`: `development`
  * `OIDC_ISSUER`: `https://auth.prip.local` *(mock local domain)*
  * `OIDC_CLIENT_ID`: Present *(placeholder)*
  * `OIDC_JWKS_URL`: **Empty / Not Configured**
* **Frontend Authentication Capabilities:**
  * Inspection of `frontend/src/` confirms **zero** OIDC PKCE login components, authentication providers, or session storage.
  * `ApiClient` in `frontend/src/services/api.ts` makes unauthenticated fetch requests without `Authorization: Bearer <token>` headers.
* **Backend Authentication Enforcement:**
  * In `development`: Backend defaults unauthenticated requests to `demo-operator-1` on `merchant_default`, permitting header-based tenant simulation (`X-Merchant-ID`).
  * In `production`: Backend strictly fails closed with `401 Unauthorized` on missing or unverified Bearer tokens.

### Remaining Blockers:
* No public JWKS OIDC authority configured.
* Frontend cannot authenticate users.

### Next Required Action:
* Configure an OIDC provider (Auth0, Okta, Google Cloud, or Keycloak) with a public JWKS URL and integrate an OIDC client into the React frontend before enforcing `APP_ENV=production`.

---

## Summary of Findings & Next Steps

```
[User Browser]
       │
       ▼
[https://paypalprip.vercel.app]  ──▶  HTTP 200 OK (Static SPA Shell Loaded)
       │
       ▼ (fetch relative /api/health)
[Vercel Serverless Backend]      ──▶  HTTP 500 FUNCTION_INVOCATION_FAILED
       │
       ├──▶ PostgreSQL 16        ──▶  NOT PROVISIONED (No remote DB)
       ├──▶ Background Worker    ──▶  NOT DEPLOYED (Vercel serverless cannot run daemons)
       └──▶ OIDC Identity IdP    ──▶  NOT CONFIGURED (Empty JWKS URL, no frontend login)
```

### Final Overall Verdict
# **`FRONTEND ONLY DEPLOYED`**
