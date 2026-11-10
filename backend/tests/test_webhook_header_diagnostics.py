from backend.api.webhooks import _paypal_signature_header_availability


def test_paypal_signature_header_availability_is_case_insensitive_and_non_empty():
    headers = {
        "PayPal-Transmission-Id": "transmission-id-test",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-10T10:00:00Z",
        "paypal-cert-url": "https://example.invalid/cert",
        "paypal-auth-algo": "SHA256withRSA",
        "PaYpAl-TrAnSmIsSiOn-SiG": "signature-test",
    }

    assert _paypal_signature_header_availability(headers) == {
        "paypal-transmission-id": True,
        "paypal-transmission-time": True,
        "paypal-cert-url": True,
        "paypal-auth-algo": True,
        "paypal-transmission-sig": True,
    }


def test_paypal_signature_header_availability_detects_missing_and_blank_values():
    headers = {
        "paypal-transmission-id": "",
        "paypal-transmission-time": "   ",
        "paypal-cert-url": "https://example.invalid/cert",
    }

    assert _paypal_signature_header_availability(headers) == {
        "paypal-transmission-id": False,
        "paypal-transmission-time": False,
        "paypal-cert-url": True,
        "paypal-auth-algo": False,
        "paypal-transmission-sig": False,
    }
