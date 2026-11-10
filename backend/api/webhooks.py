--- a/backend/api/webhooks.py
+++ b/backend/api/webhooks.py
@@ -11,6 +11,26 @@
 
 router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
 logger = logging.getLogger(__name__)
+
+_PAYPAL_SIGNATURE_HEADERS = (
+    "paypal-transmission-id",
+    "paypal-transmission-time",
+    "paypal-cert-url",
+    "paypal-auth-algo",
+    "paypal-transmission-sig",
+)
+
+
+def _paypal_signature_header_availability(headers: Dict[str, str]) -> Dict[str, bool]:
+    """Return non-empty availability flags without exposing signature header values."""
+    normalized = {
+        name.lower(): (value or "").strip()
+        for name, value in headers.items()
+    }
+    return {
+        header: bool(normalized.get(header))
+        for header in _PAYPAL_SIGNATURE_HEADERS
+    }
 
 
 @router.post(
@@ -30,18 +50,8 @@
     raw_body = raw_bytes.decode("utf-8")
     headers = dict(request.headers)
 
-    lower_header_keys = {k.lower() for k in headers}
-    presence = {
-        h: (h in lower_header_keys)
-        for h in (
-            "paypal-transmission-id",
-            "paypal-transmission-time",
-            "paypal-cert-url",
-            "paypal-auth-algo",
-            "paypal-transmission-sig",
-        )
-    }
-    logger.info("PayPal webhook header presence: %s", presence)
+    availability = _paypal_signature_header_availability(headers)
+    logger.info("PayPal webhook signature header availability: %s", availability)
 
     service = WebhookService(db)
     try:

--- /dev/null
+++ b/backend/tests/test_webhook_header_diagnostics.py
@@ -0,0 +1,35 @@
+from backend.api.webhooks import _paypal_signature_header_availability
+
+
+def test_paypal_signature_header_availability_is_case_insensitive_and_non_empty():
+    headers = {
+        "PayPal-Transmission-Id": "transmission-id-test",
+        "PAYPAL-TRANSMISSION-TIME": "2026-11-10T10:00:00Z",
+        "paypal-cert-url": "https://example.invalid/cert",
+        "paypal-auth-algo": "SHA256withRSA",
+        "PaYpAl-TrAnSmIsSiOn-SiG": "signature-test",
+    }
+
+    assert _paypal_signature_header_availability(headers) == {
+        "paypal-transmission-id": True,
+        "paypal-transmission-time": True,
+        "paypal-cert-url": True,
+        "paypal-auth-algo": True,
+        "paypal-transmission-sig": True,
+    }
+
+
+def test_paypal_signature_header_availability_detects_missing_and_blank_values():
+    headers = {
+        "paypal-transmission-id": "",
+        "paypal-transmission-time": "   ",
+        "paypal-cert-url": "https://example.invalid/cert",
+    }
+
+    assert _paypal_signature_header_availability(headers) == {
+        "paypal-transmission-id": False,
+        "paypal-transmission-time": False,
+        "paypal-cert-url": True,
+        "paypal-auth-algo": False,
+        "paypal-transmission-sig": False,
+    }
