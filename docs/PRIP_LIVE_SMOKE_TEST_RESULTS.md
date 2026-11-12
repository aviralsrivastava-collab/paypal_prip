# PRIP — Live Staging Smoke Test Results & Verification

**Execution Date:** 2026-11-12  
**Target Architecture:** Multi-Tenant SaaS (Render Web Service + Vercel Frontend SPA + Supabase Managed PostgreSQL)  
**Executed Script:** `scripts/smoke_test_staging.py`  
**Overall Verdict:** **100% PASS** on Active Staging Infrastructure (10/10 Verified)  

---

## 1. Target Host Verification & Domain Resolution

During probe execution, both candidate backend URLs were tested:

| Host Description | Target URL | HTTP Response | Operational Finding |
|---|---|:---:|---|
| **Active Live Backend** | `https://paypal-prip.onrender.com/` | **HTTP 200** | **ACTIVE & ONLINE**. This is the production/staging backend service running the PRIP API, connected to Supabase and PayPal Sandbox. |
| **Alternate Backend Host** | `https://prip-backend.onrender.com/` | **HTTP 404** | **INACTIVE / UNBOUND**. Render returns 404 (service not registered or inactive on this hostname). |
| **Active Frontend Host** | `https://paypalprip.vercel.app/` | **HTTP 200** | **ACTIVE & ONLINE**. Vercel edge CDN serves React SPA and proxies `/api/*` to `https://paypal-prip.onrender.com/api/*`. |

---

## 2. Live Smoke Test Execution Table

All ten live verification checks were executed sequentially against the deployed infrastructure:

| Check # | Target URL | HTTP Method | Expected Status | Actual Status | Latency | Result | Verification Focus |
|:---:|---|:---:|:---:|:---:|:---:|:---:|---|
| **1** | `https://paypalprip.vercel.app/` | `GET` | 200 | **200** | 147.67 ms | **PASS** | Frontend Web SPA entrypoint (HTML5 bundle delivered) |
| **2** | `https://paypalprip.vercel.app/api/health` | `GET` | 200 | **200** | 1407.25 ms | **PASS** | Vercel Edge Proxy rewrite to Render backend health |
| **3** | `https://paypalprip.vercel.app/api/products` | `GET` | 200 | **200** | 1590.57 ms | **PASS** | Vercel Edge Proxy rewrite to Render backend catalog |
| **4** | `https://paypal-prip.onrender.com/` | `GET` | 200 | **200** | 343.33 ms | **PASS** | Direct Render root service metadata & route discovery |
| **5** | `https://paypal-prip.onrender.com/api/health` | `GET` | 200 | **200** | 1340.09 ms | **PASS** | Direct Backend health check, DB connection & PayPal config |
| **6** | `https://paypal-prip.onrender.com/api/products` | `GET` | 200 | **200** | 926.44 ms | **PASS** | Direct Backend catalog fetch (SX-001 StrideX Runner) |
| **7** | `https://paypal-prip.onrender.com/api/checkout/preflight` | `POST` | 200 | **200** | 1327.75 ms | **PASS** | Preflight price gate evaluation (detected price mismatch) |
| **8** | `https://paypal-prip.onrender.com/api/checkout/orders` | `POST` | 400 | **400** | 1196.68 ms | **PASS** | Preflight order blocking (HTTP 400 returned, no funds moved) |
| **9** | `https://paypal-prip.onrender.com/api/operations/overview` | `GET` | 200 | **200** | 1507.48 ms | **PASS** | Operations monitoring (system HEALTHY, 0 stuck webhooks) |
| **10** | `https://paypal-prip.onrender.com/api/corrections/proposals/1/approve` | `POST` | 401 | **401** | 355.09 ms | **PASS** | Auth security guard (malformed token rejected with 401) |

---

## 3. Detailed Response Payloads

### 3.1 Backend Health & Dependency Check (`/api/health`)
```json
{
  "status": "healthy",
  "environment": "development",
  "version": "0.1.0",
  "database_connected": true,
  "timestamp": "2026-11-12T14:17:41.370352Z",
  "dependencies": {
    "database": {
      "status": "healthy",
      "latency_ms": 424.24
    },
    "paypal_sandbox": {
      "status": "configured",
      "environment": "sandbox",
      "base_url": "https://api-m.sandbox.paypal.com",
      "webhook_configured": true
    }
  },
  "worker_health": {
    "status": "idle",
    "active_workers": 0,
    "stale_workers": 0,
    "workers": []
  },
  "operational_metrics": {
    "webhook_counts": {},
    "pending_reconciliations": 0,
    "reconciliation_counts": {},
    "metrics": {
      "counters": {},
      "gauges": {},
      "timings": {}
    }
  }
}
```

### 3.2 Public Product Catalog with Discrepancy Evidence (`/api/products`)
```json
[
  {
    "id": 1,
    "merchant_id": "merchant_default",
    "sku": "SX-001",
    "title": "StrideX Runner",
    "description": "High-performance lightweight running shoe with responsive cushioning and breathable mesh.",
    "merchant_price": "100.00",
    "merchant_currency": "USD",
    "storefront_price": "120.00",
    "storefront_currency": "USD",
    "price_discrepancy": "+20.00",
    "has_discrepancy": true,
    "is_comparable": true,
    "comparability_reason": null,
    "availability": "IN_STOCK",
    "source_version": 1,
    "storefront_version": 1,
    "updated_at": "2026-11-10T16:46:16.965418Z"
  }
]
```

### 3.3 Checkout Preflight Gating (`POST /api/checkout/preflight`)
```json
{
  "passed": false,
  "sku": "SX-001",
  "catalog_price": "100.00",
  "storefront_price": "120.00",
  "currency": "USD",
  "scan_id": 10,
  "scan_state": "ISSUE_DETECTED",
  "blocking_reasons": [
    "Price discrepancy detected: Catalog USD 100.00 vs Storefront USD 120.00. Checkout blocked until synchronized.",
    "Storefront inspection scan #10 detected an active discrepancy (state: ISSUE_DETECTED). Discrepancy must be approved and reconciled before checkout."
  ],
  "message": "Price discrepancy detected: Catalog USD 100.00 vs Storefront USD 120.00. Checkout blocked until synchronized.; Storefront inspection scan #10 detected an active discrepancy (state: ISSUE_DETECTED). Discrepancy must be approved and reconciled before checkout."
}
```

### 3.4 Preflight Order Creation Rejection (`POST /api/checkout/orders`)
```json
{
  "detail": "Checkout blocked: Price discrepancy detected: Catalog USD 100.00 vs Storefront USD 120.00. Checkout blocked until synchronized.; Storefront inspection scan #10 detected an active discrepancy (state: ISSUE_DETECTED). Discrepancy must be approved and reconciled before checkout."
}
```

### 3.5 Auth Security Guard on Mutation (`POST /api/corrections/proposals/1/approve`)
```json
{
  "detail": "Malformed JWT token structure or unreadable header."
}
```

---

## 4. Key Performance Indicators

- **Average API Latency:** 1024 ms (including cold database round-trips to Supabase managed PostgreSQL).
- **Direct Backend Root Latency:** 343.33 ms.
- **Frontend SPA CDN Load Latency:** 147.67 ms.
- **Database Query Latency:** 424.24 ms.
- **Preflight Gating Execution Time:** 1327.75 ms.
- **Error Rate on Expected Paths:** 0.0%.

---

## 5. Conclusion

The live smoke test confirms that the deployed staging infrastructure (`https://paypal-prip.onrender.com` and `https://paypalprip.vercel.app`) is operating properly. All critical gates, including database persistence, preflight discrepancy protection, Vercel proxying, and authentication rejection, are verified.
