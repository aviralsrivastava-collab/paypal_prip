"""
Unit tests for deployment hardening:
1. Supabase PostgreSQL URL normalization (postgres:// and postgresql:// -> postgresql+psycopg://)
2. Production SQLite fail-closed invariant
3. Google OIDC JWKS authority domain validation
4. Google email-to-merchant mapping and email_verified requirement
5. Unauthorized Google account rejection (HTTP 403)
6. Client-controlled merchant header spoofing prevention
7. Token validity (issuer, audience, expiry) enforcement
"""

import time

import pytest
from fastapi import HTTPException

from backend.core.config import get_settings
from backend.core.database import init_db_engine, normalize_database_url
from backend.core.security import (
    clear_test_jwks_keys,
    create_rsa_jwt_token,
    generate_test_rsa_key_pair,
    get_current_actor,
    register_test_jwks_key,
    verify_oidc_token,
)


class TestDatabaseUrlNormalization:
    """Verifies safe PostgreSQL URL normalization for Supabase and psycopg 3."""

    def test_postgres_legacy_prefix_normalized_to_psycopg3(self):
        raw = "postgres://postgres:mock_secret@db.projectref.supabase.co:5432/postgres?sslmode=require"
        normalized = normalize_database_url(raw)
        assert normalized == "postgresql+psycopg://postgres:mock_secret@db.projectref.supabase.co:5432/postgres?sslmode=require"

    def test_bare_postgresql_prefix_normalized_to_psycopg3(self):
        raw = "postgresql://postgres.projectref:mock_secret@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
        normalized = normalize_database_url(raw)
        assert normalized == "postgresql+psycopg://postgres.projectref:mock_secret@aws-0-us-west-1.pooler.supabase.com:5432/postgres"

    def test_explicit_psycopg3_dialect_preserved(self):
        raw = "postgresql+psycopg://user:pass@host:5432/db"
        assert normalize_database_url(raw) == raw

    def test_sqlite_url_preserved(self):
        raw = "sqlite:///./prip_demo.db"
        assert normalize_database_url(raw) == raw

    def test_empty_or_none_url_handled_safely(self):
        assert normalize_database_url("") == ""
        assert normalize_database_url("   ") == ""

    def test_production_engine_strictly_prohibits_sqlite(self, monkeypatch: pytest.MonkeyPatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "database_url", "sqlite:///./local.db")

        with pytest.raises(RuntimeError) as exc_info:
            init_db_engine()
        assert "SQLite is strictly prohibited in production" in str(exc_info.value)


class TestGoogleOidcAndTenantMapping:
    """Verifies Google OAuth/OIDC signature, JWKS authority, and email-to-merchant mapping."""

    @pytest.fixture(autouse=True)
    def setup_rsa_keys(self):
        private_pem, public_pem = generate_test_rsa_key_pair()
        self.private_pem = private_pem
        self.public_pem = public_pem
        self.kid = "test-google-kid-001"
        register_test_jwks_key(self.kid, self.public_pem)
        yield
        clear_test_jwks_keys()

    def test_google_jwks_authority_allowed(self, monkeypatch: pytest.MonkeyPatch):
        """Accounts.google.com issuer with googleapis.com JWKS URL is recognized as trusted."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "allowed_google_email", "merchant.owner@gmail.com")

        payload = {
            "sub": "google-user-7890",
            "email": "merchant.owner@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        actor = get_current_actor(authorization=f"Bearer {token}")
        assert actor.actor_id == "google-user-7890"
        assert actor.merchant_id == "merchant_default"
        assert actor.role == "merchant_operator"
        assert actor.is_authenticated is True

    def test_untrusted_jwks_authority_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Attacker pointing JWKS URL to untrusted domain is rejected with 401 Security Violation."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://attacker-domain.evil.com/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")

        payload = {
            "sub": "user-1",
            "email": "merchant.owner@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        with pytest.raises(HTTPException) as exc_info:
            verify_oidc_token(token)
        assert exc_info.value.status_code == 401
        assert "does not belong to trusted OIDC issuer authority" in exc_info.value.detail

    def test_unauthorized_google_account_rejected_with_403(self, monkeypatch: pytest.MonkeyPatch):
        """Google account not in allowed_google_email is rejected with HTTP 403 Forbidden."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "allowed_google_email", "legitimate.merchant@gmail.com")

        payload = {
            "sub": "intruder-uid-999",
            "email": "intruder@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        with pytest.raises(HTTPException) as exc_info:
            get_current_actor(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 403
        assert "not authorized to access this PRIP merchant" in exc_info.value.detail

    def test_unverified_google_email_rejected_with_401(self, monkeypatch: pytest.MonkeyPatch):
        """Google token with email_verified=False is rejected with HTTP 401 Unauthorized."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "allowed_google_email", "merchant.owner@gmail.com")

        payload = {
            "sub": "user-unverified",
            "email": "merchant.owner@gmail.com",
            "email_verified": False,
            "iss": "https://accounts.google.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        with pytest.raises(HTTPException) as exc_info:
            get_current_actor(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401
        assert "Google account email is not verified" in exc_info.value.detail

    def test_frontend_cannot_spoof_merchant_id(self, monkeypatch: pytest.MonkeyPatch):
        """Client header X-Merchant-ID is strictly ignored when authenticating via Bearer token."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "allowed_google_email", "merchant.owner@gmail.com")
        monkeypatch.setattr(settings, "default_merchant_id", "merchant_genuine")

        payload = {
            "sub": "google-user-7890",
            "email": "merchant.owner@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        actor = get_current_actor(
            authorization=f"Bearer {token}",
            x_merchant_id="merchant_spoofed_victim",
        )
        assert actor.merchant_id == "merchant_genuine"
        assert actor.merchant_id != "merchant_spoofed_victim"

    def test_invalid_audience_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Token with audience mismatch raises 401."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")

        payload = {
            "sub": "user-1",
            "email": "merchant.owner@gmail.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "wrong-client-id.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        with pytest.raises(HTTPException) as exc_info:
            verify_oidc_token(token)
        assert exc_info.value.status_code == 401
        assert "Invalid JWT audience" in exc_info.value.detail

    def test_invalid_issuer_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Token with unrecognized issuer raises 401."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "oidc_issuer", "https://accounts.google.com")
        monkeypatch.setattr(settings, "oidc_jwks_url", "https://www.googleapis.com/oauth2/v3/certs")
        monkeypatch.setattr(settings, "oidc_client_id", "google-client-id-123.apps.googleusercontent.com")

        payload = {
            "sub": "user-1",
            "email": "merchant.owner@gmail.com",
            "email_verified": True,
            "iss": "https://rogue-idp.example.com",
            "aud": "google-client-id-123.apps.googleusercontent.com",
            "exp": int(time.time()) + 3600,
        }
        token = create_rsa_jwt_token(payload, self.private_pem, kid=self.kid)

        with pytest.raises(HTTPException) as exc_info:
            verify_oidc_token(token)
        assert exc_info.value.status_code == 401
        assert "Invalid JWT issuer" in exc_info.value.detail
