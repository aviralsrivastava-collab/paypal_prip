"""
Staging Smoke Test Script for PRIP
Executes non-destructive health, connectivity, latency, and security verification
against the live deployed environments.
Usage:
    python scripts/smoke_test_staging.py --backend-url https://paypal-prip.onrender.com --frontend-url https://paypalprip.vercel.app
"""

import sys
import time
import argparse
import json
import urllib.request
import urllib.error

def test_endpoint(
    url: str,
    description: str,
    method: str = "GET",
    data: dict = None,
    headers: dict = None,
    expected_status: int = 200,
) -> dict:
    print(f"[*] Testing [{method}] {description}: {url}")
    start_time = time.perf_counter()
    result = {
        "url": url,
        "method": method,
        "description": description,
        "expected_status": expected_status,
        "actual_status": None,
        "latency_ms": None,
        "passed": False,
        "payload_snippet": "",
        "error": None
    }
    req_headers = {"User-Agent": "PRIP-Staging-SmokeTest/1.0"}
    if headers:
        req_headers.update(headers)
    
    encoded_data = None
    if data is not None:
        req_headers["Content-Type"] = "application/json"
        encoded_data = json.dumps(data).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            result["latency_ms"] = round(latency_ms, 2)
            result["actual_status"] = resp.status
            body = resp.read().decode("utf-8")
            if resp.status == expected_status:
                result["passed"] = True
                print(f"    [+] PASS: HTTP {resp.status} ({result['latency_ms']} ms)")
                try:
                    parsed = json.loads(body)
                    result["payload_snippet"] = json.dumps(parsed)[:250]
                except json.JSONDecodeError:
                    result["payload_snippet"] = body.strip().replace("\n", " ")[:250]
            else:
                print(f"    [-] FAIL: Expected {expected_status}, got {resp.status} ({result['latency_ms']} ms)")
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        result["latency_ms"] = round(latency_ms, 2)
        result["actual_status"] = e.code
        body = e.read().decode("utf-8")
        result["payload_snippet"] = body[:250]
        if e.code == expected_status:
            result["passed"] = True
            print(f"    [+] PASS (Expected Status): HTTP {e.code} ({result['latency_ms']} ms)")
        else:
            result["error"] = f"HTTP {e.code}: {body[:250]}"
            print(f"    [-] FAIL: HTTP Error {e.code}: {body[:150]} ({result['latency_ms']} ms)")
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        result["latency_ms"] = round(latency_ms, 2)
        result["error"] = str(e)
        print(f"    [-] ERROR: {e} ({result['latency_ms']} ms)")

    return result

def run_all_tests(backend_url: str, frontend_url: str) -> list:
    results = []

    # 1. Frontend Web App
    results.append(test_endpoint(
        url=f"{frontend_url}/",
        description="Frontend Web SPA Entrypoint",
        expected_status=200
    ))

    # 2. Frontend Proxy to Backend Health
    results.append(test_endpoint(
        url=f"{frontend_url}/api/health",
        description="Vercel Edge Proxy -> Backend Health",
        expected_status=200
    ))

    # 3. Frontend Proxy to Backend Products Catalog
    results.append(test_endpoint(
        url=f"{frontend_url}/api/products",
        description="Vercel Edge Proxy -> Products Catalog",
        expected_status=200
    ))

    # 4. Direct Backend Root
    results.append(test_endpoint(
        url=f"{backend_url}/",
        description="Direct Backend Service Root Info",
        expected_status=200
    ))

    # 5. Direct Backend Health
    results.append(test_endpoint(
        url=f"{backend_url}/api/health",
        description="Direct Backend Health & DB Dependency",
        expected_status=200
    ))

    # 6. Direct Backend Catalog
    results.append(test_endpoint(
        url=f"{backend_url}/api/products",
        description="Direct Backend Seeded Catalog (SX-001)",
        expected_status=200
    ))

    # 7. Direct Backend Checkout Preflight (Active Discrepancy Gate)
    results.append(test_endpoint(
        url=f"{backend_url}/api/checkout/preflight",
        description="Checkout Preflight Evaluation for SX-001",
        method="POST",
        data={"sku": "SX-001"},
        expected_status=200
    ))

    # 8. Direct Backend Order Creation (Expect 400 Blocked by Preflight)
    results.append(test_endpoint(
        url=f"{backend_url}/api/checkout/orders",
        description="Checkout Order Creation Blocking on Discrepancy",
        method="POST",
        data={"sku": "SX-001", "quantity": 1},
        expected_status=400
    ))

    # 9. Direct Backend Operations Overview
    results.append(test_endpoint(
        url=f"{backend_url}/api/operations/overview",
        description="Operations & Reconciliation Health Overview",
        expected_status=200
    ))

    # 10. Direct Backend Auth Guard (Invalid Token on Protected Action -> Expect 401)
    results.append(test_endpoint(
        url=f"{backend_url}/api/corrections/proposals/1/approve",
        description="Auth Security Guard with Invalid Bearer Token",
        method="POST",
        data={"notes": "Security test unauthorized approval attempt"},
        headers={"Authorization": "Bearer invalid_token_signature_test"},
        expected_status=401
    ))

    return results

def main():
    parser = argparse.ArgumentParser(description="PRIP Live Staging Smoke & Verification Test")
    parser.add_argument("--backend-url", default="https://paypal-prip.onrender.com", help="Primary backend base URL")
    parser.add_argument("--alt-backend-url", default="https://prip-backend.onrender.com", help="Alternate backend base URL to check")
    parser.add_argument("--frontend-url", default="https://paypalprip.vercel.app", help="Frontend base URL")
    args = parser.parse_args()

    backend_url = args.backend_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    alt_backend_url = args.alt_backend_url.rstrip("/")

    print("=" * 75)
    print("PRIP LIVE DEPLOYMENT SMOKE & VERIFICATION SUITE")
    print(f"Target Primary Backend:  {backend_url}")
    print(f"Target Frontend SPA:     {frontend_url}")
    print(f"Target Alternate Host:   {alt_backend_url}")
    print("=" * 75)

    # First check alternate host to document status
    print("[*] Probing Alternate Host:")
    alt_res = test_endpoint(f"{alt_backend_url}/", "Alternate Host Root Probe", expected_status=200)
    print(f"    Notice: Alternate host returned HTTP {alt_res['actual_status']} ({alt_res['error'] or 'OK'})")
    print("-" * 75)

    results = run_all_tests(backend_url, frontend_url)

    print("\n" + "=" * 75)
    print("LIVE SMOKE TEST RESULTS SUMMARY")
    print("=" * 75)
    print(f"{'STATUS':6} | {'HTTP':5} | {'LATENCY':10} | {'DESCRIPTION':45}")
    print("-" * 75)
    all_passed = True
    for r in results:
        status_str = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_passed = False
        lat = f"{r['latency_ms']} ms" if r["latency_ms"] is not None else "N/A"
        print(f"{status_str:6} | {str(r['actual_status']):5} | {lat:10} | {r['description'][:45]}")

    print("=" * 75)

    # Machine-readable output for documentation
    print("\n--- JSON_REPORT_START ---")
    print(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend_url": backend_url,
        "alt_backend_url": alt_backend_url,
        "frontend_url": frontend_url,
        "alt_host_status": alt_res["actual_status"],
        "all_passed": all_passed,
        "results": results
    }, indent=2))
    print("--- JSON_REPORT_END ---")

    if all_passed:
        print("\n[+] SUCCESS: ALL LIVE TESTS PASSED!")
        sys.exit(0)
    else:
        print("\n[-] WARNING: ONE OR MORE TESTS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()
