# PRIP — Free-Tier Production Deployment Guide

**Target Architecture:**
* **Frontend:** Vercel Static Hosting (`https://paypalprip.vercel.app`)
* **Backend:** Render Free Web Service (`https://<your-service>.onrender.com`)
* **Database:** Neon Serverless PostgreSQL 16 (Free Tier)
* **Identity:** Google Cloud OAuth 2.0 / OIDC (Free Tier)
* **Payments:** PayPal Developer Sandbox

---

## 1. Neon PostgreSQL Database Provisioning

Neon provides a fully managed, serverless PostgreSQL 16 database on a zero-cost free tier (0.5 GiB storage, auto-suspend compute).

### Step 1: Create Neon Project
1. Navigate to [https://neon.tech](https://neon.tech) and sign up with GitHub or Google.
2. Click **Create Project**:
   * **Project Name:** `prip-db`
   * **Postgres Version:** `16`
   * **Region:** Select the region closest to your Render service (e.g., `AWS US East (Ohio)` or `AWS US West (Oregon)`).
3. Click **Create Project**.

### Step 2: Retrieve Connection Strings
From the Neon Project Dashboard, navigate to the **Connection Details** card:
1. **Direct Connection String (For Alembic Migrations):**
   Select **Direct** in the connection dropdown. It has the format:
   ```text
   postgresql+psycopg://<user>:<password>@ep-<project-id>.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
2. **Pooled Connection String (For FastAPI Web Service):**
   Select **Pooled connection** (uses PgBouncer). It has `-pooler` in the host:
   ```text
   postgresql+psycopg://<user>:<password>@ep-<project-id>-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

### Step 3: Run Alembic Migrations
From your local terminal with database access, apply all 11 revisions:
```bash
cd backend
$env:DATABASE_URL="<your-neon-direct-connection-string>"
.venv\Scripts\alembic.exe upgrade head
```
*Expected Result:* Migrations `001` through `011_revalidate_parent_tenant_ownership` apply successfully.

---

## 2. Google Cloud OIDC Authentication Setup

Google Cloud provides free OAuth 2.0 authentication for up to thousands of daily active users.

### Step 1: Configure OAuth Consent Screen
1. Open [Google Cloud Console](https://console.cloud.google.com).
2. Create a new project named `PRIP-Commerce-Integrity`.
3. Go to **APIs & Services** $\rightarrow$ **OAuth consent screen**:
   * **User Type:** `External`
   * **App Name:** `PRIP Commerce Integrity`
   * **User Support Email:** Your email address
   * **Developer Contact Info:** Your email address
   * Click **Save and Continue**.

### Step 2: Create OAuth 2.0 Client ID
1. Navigate to **APIs & Services** $\rightarrow$ **Credentials** $\rightarrow$ **Create Credentials** $\rightarrow$ **OAuth client ID**.
2. **Application Type:** `Web application`.
3. **Name:** `PRIP Web Client`.
4. **Authorized JavaScript Origins:**
   * `https://paypalprip.vercel.app`
   * `http://localhost:3000` (for local development)
5. **Authorized Redirect URIs:**
   * `https://paypalprip.vercel.app`
   * `http://localhost:3000`
6. Click **Create**.
7. Copy the generated **Client ID** (e.g. `123456789-abcdefg.apps.googleusercontent.com`).

---

## 3. Render Free Web Service Deployment

Render provides free hosting for containerized or Python web applications with automatic TLS (`https://`).

### Step 1: Create Web Service from GitHub
1. Open [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select your repository: `aviralsrivastava-collab/paypal_prip`.
4. Configure service parameters:
   * **Name:** `prip-backend`
   * **Region:** Match your Neon region (`Oregon` or `Ohio`)
   * **Branch:** `main`
   * **Root Directory:** *(leave blank for repository root)*
   * **Runtime:** `Python 3`
   * **Build Command:**
     ```bash
     pip install -r backend/requirements.txt && alembic upgrade head
     ```
   * **Start Command:**
     ```bash
     uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
     ```
   * **Instance Type:** `Free`
   * **Health Check Path:** `/api/health`

### Step 2: Configure Render Environment Variables
Add the following variables in the **Environment** tab:

| Variable Name | Example / Expected Value | Purpose |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.11.9` | Pins Python runtime version. |
| `APP_ENV` | `production` | Enforces production security and rejects SQLite. |
| `DATABASE_URL` | `postgresql+psycopg://user:pass@ep-xyz-pooler...` | Neon pooled connection string. |
| `SESSION_SECRET` | *(Click "Generate" or use 64-char hex)* | Session cookie encryption. |
| `CORS_ALLOWED_ORIGINS` | `https://paypalprip.vercel.app` | Restricts browser cross-origin requests. |
| `CONTROLLED_STOREFRONT_BASE_URL` | `https://paypalprip.vercel.app` | SSRF security allowlist. |
| `PAYPAL_MODE` | `sandbox` | **Strictly Sandbox** (never `live`). |
| `PAYPAL_ENVIRONMENT` | `sandbox` | PayPal API environment flag. |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | PayPal Sandbox API base URL. |
| `PAYPAL_CLIENT_ID` | `<your-sandbox-client-id>` | PayPal Developer Sandbox client ID. |
| `PAYPAL_CLIENT_SECRET` | `<your-sandbox-client-secret>` | PayPal Developer Sandbox client secret. |
| `PAYPAL_WEBHOOK_ID` | `<your-registered-webhook-id>` | Registered Sandbox webhook ID. |
| `OIDC_ISSUER` | `https://accounts.google.com` | Google OIDC token issuer. |
| `OIDC_CLIENT_ID` | `<your-google-client-id>` | Google OAuth 2.0 Web Client ID. |
| `OIDC_JWKS_URL` | `https://www.googleapis.com/oauth2/v3/certs` | Google public JWKS certificate endpoint. |

Click **Save Changes** and deploy the web service. Note the deployed URL (e.g. `https://prip-backend.onrender.com`).

---

## 4. Vercel Frontend Configuration

### Step 1: Add Environment Variables in Vercel
1. Open your Vercel Dashboard $\rightarrow$ Select project `paypalprip`.
2. Go to **Settings** $\rightarrow$ **Environment Variables**.
3. Add the following variables:

| Variable Name | Value | Purpose |
| :--- | :--- | :--- |
| `VITE_API_URL` | `https://prip-backend.onrender.com/api` | Points frontend calls to Render backend. |
| `VITE_GOOGLE_CLIENT_ID` | `<your-google-client-id>` | Google OAuth 2.0 Client ID for PKCE. |

### Step 2: Trigger Frontend Redeployment
In Vite SPAs, `VITE_*` environment variables are baked into static JavaScript during the build step.
1. In Vercel, navigate to **Deployments**.
2. Click the three dots on the latest deployment $\rightarrow$ **Redeploy**.
3. Confirm the build finishes successfully.

---

## 5. Free-Tier Background Worker Strategy

In production, PRIP uses a background worker (`backend/worker.py`) to process incoming PayPal webhooks and lease renewals.
To operate entirely on Render's free tier without paying for a second background service:
1. **In-Process Worker Loop:** Run a lightweight asynchronous polling task directly inside the ASGI application lifespan in `backend/api/main.py`. This task calls `WebhookWorkerService(SessionLocal()).tick()` periodically.
2. **FastAPI BackgroundTasks:** On incoming webhook delivery at `POST /api/webhooks/paypal`, enqueue an immediate `worker.tick()` via FastAPI's built-in `BackgroundTasks` queue.
*Result: Instant webhook processing and reconciliation with zero additional infrastructure costs.*

---

## 6. Verification and Smoke Test Runbook

Once all components are deployed:

### 1. Test Backend Health Endpoint
```bash
curl -i https://prip-backend.onrender.com/api/health
```
*Expected Response:*
```json
{
  "status": "healthy",
  "environment": "production",
  "database": "connected",
  "version": "0.1.0"
}
```

### 2. Verify CORS Headers
```bash
curl -i -X OPTIONS https://prip-backend.onrender.com/api/products \
  -H "Origin: https://paypalprip.vercel.app" \
  -H "Access-Control-Request-Method: GET"
```
*Expected Response:*
`HTTP/1.1 200 OK`  
`access-control-allow-origin: https://paypalprip.vercel.app`  
`access-control-allow-credentials: true`

### 3. Verify Frontend Dashboard
1. Open `https://paypalprip.vercel.app` in your browser.
2. Verify the status banner displays:
   **Backend Status: Online (healthy)** with a green badge.
3. Test Google Login $\rightarrow$ verify your authenticated operator name and tenant badge appear in the header.

---

## 7. Rollback Runbook

If any component encounters unexpected failures during deployment:
1. **Backend Rollback:**
   In Render Dashboard $\rightarrow$ **Deploys** $\rightarrow$ select previous working deploy $\rightarrow$ click **Rollback**.
2. **Database Rollback:**
   Revert the specific Alembic revision using the direct connection string:
   ```bash
   alembic downgrade -1
   ```
3. **Frontend Rollback:**
   In Vercel Dashboard $\rightarrow$ **Deployments** $\rightarrow$ click previous deployment $\rightarrow$ **Promote to Production**.
