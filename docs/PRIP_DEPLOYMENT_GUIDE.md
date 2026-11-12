# PRIP — Staging Environment Setup & Deployment Guide

**Document Version:** 1.0.0  
**Target Architecture:** Multi-Tenant SaaS (Render Backend + Vercel Frontend + Supabase PostgreSQL)  
**Security Classification:** Operational Engineering Guide  
**Date:** 2026-11-12  

---

## 1. Overview and Architecture Targets

This guide details the complete procedure for deploying and validating the **PayPal Revenue Intelligence Platform (PRIP)** into the staging cloud environment.

### Target Infrastructure Components
- **Backend API:** Render Web Service (`https://paypal-prip.onrender.com`)
  - Runtime: Python 3.11 / FastAPI / Uvicorn
- **Frontend SPA:** Vercel Hosting (`https://paypalprip.vercel.app`)
  - Runtime: Vite 5 / React 18 / TypeScript
  - Proxy: Vercel edge rewrite (`/api/:path*` -> `https://paypal-prip.onrender.com/api/:path*`)
- **Database:** Supabase PostgreSQL (Managed Relational Database)
  - Engine: PostgreSQL 15+
  - Security: Row-Level Security (RLS) policies + Alembic schema migrations
- **Payment Gateway:** PayPal Sandbox API (`api-m.sandbox.paypal.com`)
- **AI Intelligence Provider:** Google Gemini API (Gemini 2.5 Flash / Pro)

---

## 2. Environment Variables Configuration

All secrets must be configured via host environment dashboards. **Never hardcode secrets into source code or commit them to source control.**

### 2.1 Backend Environment Variables (Render Dashboard)

| Variable Name | Required | Default / Staging Format | Description |
|---|:---:|---|---|
| `DATABASE_URL` | **Yes** | `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres` | Supabase / Neon PostgreSQL connection URI. Use Transaction Pooler (port 6543) or direct connection. |
| `ENV` | **Yes** | `staging` | Environment mode (`development`, `staging`, `production`). |
| `AUTH_SECRET_KEY` | **Yes** | *[64-character hex string]* | Cryptographic secret for signing session JWTs. |
| `AUTH_TOKEN_EXPIRE_MINUTES` | No | `1440` (24 hours) | Local session token TTL. |
| `PAYPAL_ENV` | **Yes** | `sandbox` | PayPal API environment (`sandbox` or `live`). Staging must always be `sandbox`. |
| `PAYPAL_CLIENT_ID` | **Yes** | *[PayPal Sandbox App Client ID]* | Platform Sandbox App client identifier. |
| `PAYPAL_CLIENT_SECRET` | **Yes** | *[PayPal Sandbox App Client Secret]* | Platform Sandbox App client secret. |
| `PAYPAL_WEBHOOK_ID` | **Yes** | *[PayPal Webhook ID]* | ID of the registered webhook endpoint in PayPal Developer Dashboard. |
| `PAYPAL_ENABLE_PAYEE_ROUTING` | No | `false` | Guardrail feature flag. Must remain `false` until PayPal Partner marketplace onboarding is approved. |
| `GEMINI_API_KEY` | No | *[Google AI Studio API Key]* | API key for Gemini LLM diagnosis. If unset, the hermetic fallback provider runs automatically. |
| `CORS_ORIGINS` | **Yes** | `https://paypalprip.vercel.app,http://localhost:5173` | Comma-separated list of allowed frontend origins. |
| `LOG_LEVEL` | No | `INFO` | Application log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

### 2.2 Frontend Environment Variables (Vercel Dashboard)

| Variable Name | Required | Default / Staging Format | Description |
|---|:---:|---|---|
| `VITE_API_BASE_URL` | No | `/api` | Base path for REST API calls. Due to `vercel.json` rewrite, `/api` proxies directly to Render. |
| `VITE_GOOGLE_CLIENT_ID` | No | *[Google Cloud OAuth Client ID]* | Google OIDC Client ID for browser Google Sign-In button. |

---

## 3. Database Setup & Migration Procedure

### Step 3.1: Execute Alembic Migrations
Ensure network access to the remote Supabase database (either via temporary IP whitelist or direct SSL connection).

From the repository root with the active `.venv`:
```bash
# Set target database URL in terminal session
export DATABASE_URL="postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

# Execute all migrations up to revision 013 (multi_tenant_foundation)
alembic upgrade head
```

Verify that revision `013_multi_tenant_foundation` is stamped in the `alembic_version` table:
```bash
alembic current
```

### Step 3.2: Apply Supabase Row-Level Security (RLS) Policies
1. Open the **Supabase Dashboard** for the staging project.
2. Navigate to the **SQL Editor**.
3. Open `database/rls_policies.sql` from this repository.
4. Execute the SQL script.
5. Confirm that RLS is enabled on:
   - `merchants`
   - `users`
   - `products`
   - `storefronts`
   - `orders`
   - `discrepancies`
   - `corrections`
   - `audit_events`

---

## 4. Backend Deployment on Render

### Step 4.1: Service Configuration
The repository includes `render.yaml` for declarative configuration. If deploying via the Render web UI:
1. Create a new **Web Service** connected to the repository.
2. Configure settings:
   - **Name:** `paypal-prip`
   - **Region:** Ohio (US East) or Frankfurt (EU Central)
   - **Branch:** `main`
   - **Root Directory:** *(leave blank for repository root)*
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/api/health`

### Step 4.2: Inject Environment Variables
In the **Environment** tab on Render, add all keys listed in Section 2.1 above.

### Step 4.3: Trigger Deploy
Click **Manual Deploy > Deploy latest commit**. Monitor logs to confirm startup:
```text
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
```

---

## 5. Frontend Deployment on Vercel

### Step 5.1: Project Setup
1. Import the repository into the **Vercel Dashboard**.
2. Configure project settings:
   - **Framework Preset:** Vite
   - **Root Directory:** `frontend`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
   - **Install Command:** `npm install`

### Step 5.2: Verify API Proxy Rewrite
Confirm that `vercel.json` (or `frontend/vercel.json`) contains:
```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://paypal-prip.onrender.com/api/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

### Step 5.3: Deploy and Validate
Deploy the branch. Navigate to `https://paypalprip.vercel.app` and confirm that the application loads without console errors.

---

## 6. PayPal Developer Sandbox Configuration

### Step 6.1: Webhook Endpoint Registration
1. Log in to [PayPal Developer Dashboard](https://developer.paypal.com/).
2. Select your Sandbox REST API App.
3. Click **Add Webhook**.
4. Set Webhook URL:
   ```text
   https://paypal-prip.onrender.com/api/webhooks/paypal
   ```
5. Subscribe to the following event types:
   - `CHECKOUT.ORDER.APPROVED`
   - `CHECKOUT.ORDER.COMPLETED`
   - `PAYMENT.CAPTURE.COMPLETED`
   - `PAYMENT.CAPTURE.DENIED`
   - `PAYMENT.CAPTURE.REFUNDED`
6. Copy the generated **Webhook ID** and set it as `PAYPAL_WEBHOOK_ID` on Render.

---

## 7. Post-Deployment Verification & Smoke Testing

Run the automated smoke test script against the staging deployment:
```bash
python scripts/smoke_test_staging.py --base-url https://paypal-prip.onrender.com
```

### Expected Output
```text
============================================================
Starting PRIP Staging Smoke Test against: https://paypal-prip.onrender.com
============================================================
[*] Testing Backend Health Check: https://paypal-prip.onrender.com/api/health
    [+] PASS: HTTP 200
    [+] Payload: {
      "status": "healthy",
      "environment": "staging",
      "version": "1.0.0"
    }
[*] Testing Public Product Catalog: https://paypal-prip.onrender.com/api/products
    [+] PASS: HTTP 200
[*] Testing Unauthorized Access Guard: https://paypal-prip.onrender.com/api/merchants/me
    [+] PASS (Expected Error): HTTP 401
============================================================
[+] ALL STAGING SMOKE TESTS PASSED SUCCESSFULLY!
```

---

## 8. Rollback and Disaster Recovery Procedures

### 8.1 Database Rollback
If a schema issue occurs after running migration 013:
```bash
# Downgrade schema one revision
alembic downgrade -1
```

### 8.2 Backend Rollback on Render
1. Go to **Render Dashboard > paypal-prip > Deploys**.
2. Select the previous stable deployment.
3. Click **Rollback to this deploy**.

### 8.3 Frontend Rollback on Vercel
1. Go to **Vercel Dashboard > paypalprip > Deployments**.
2. Locate the previous production deployment.
3. Click the `...` menu and select **Instant Rollback**.
