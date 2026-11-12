from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "PRIP"
    app_version: str = "0.1.0"

    # Database configuration (PostgreSQL target in production, SQLite in local/test)
    database_url: str = "sqlite:///./prip_demo.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: float = 30.0
    session_secret: str = "prip-insecure-default-change-in-production"

    # Production OIDC Identity Provider settings
    oidc_issuer: str = "https://auth.prip.local"
    oidc_client_id: str = "prip-api"
    oidc_client_secret: str = ""
    oidc_jwt_secret: str = "prip-dev-oidc-secret-replace-in-production"
    oidc_jwks_url: str = ""
    allowed_google_email: str = ""
    default_merchant_id: str = "merchant_default"

    @property
    def allowed_google_emails_set(self) -> set[str]:
        if not self.allowed_google_email:
            return set()
        return {e.strip().lower() for e in self.allowed_google_email.split(",") if e.strip()}

    # PayPal settings (Sandbox strictly enforced)
    paypal_client_type: str = Field(
        default="mock",
        validation_alias=AliasChoices("paypal_client_type", "paypal_adapter"),
    )
    paypal_environment: str = Field(
        default="sandbox",
        validation_alias=AliasChoices("paypal_environment", "paypal_mode"),
    )
    paypal_base_url: str = Field(
        default="https://api-m.sandbox.paypal.com",
        validation_alias=AliasChoices("paypal_base_url", "paypal_api_base_url"),
    )
    paypal_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("paypal_client_id", "paypal_sandbox_client_id"),
    )
    paypal_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("paypal_client_secret", "paypal_sandbox_client_secret"),
    )
    paypal_webhook_id: str = Field(
        default="WH-MOCK-SANDBOX-001",
        validation_alias=AliasChoices("paypal_webhook_id", "paypal_sandbox_webhook_id"),
    )
    paypal_client_id_public: str = "sb-client-id-demo"
    paypal_enable_payee_routing: bool = Field(
        default=False,
        description="Whether custom payee routing is enabled (requires PayPal Partner permissions). Defaults to False.",
    )

    # Controlled storefront URL allowlist & SSRF guards
    controlled_storefront_base_url: str = "http://localhost:3000"
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173,https://paypalprip.vercel.app"

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
        if self.controlled_storefront_base_url not in origins:
            origins.append(self.controlled_storefront_base_url)
        return origins

    def is_allowed_cors_origin(self, origin: str) -> bool:
        """Validates incoming Origin header with strict hostname, scheme, and port comparison."""
        from backend.core.security import is_allowed_origin

        return is_allowed_origin(origin, self.cors_origins_list)

    # AI Diagnostic settings (strictly advisory)
    ai_provider: str = "mock"
    ai_model: str = "prip-diagnostic-v1"
    ai_api_key: str = ""
    ai_timeout_seconds: float = 10.0
    ai_prompt_version: str = "v1.0"

    # Background worker settings
    worker_poll_interval_seconds: float = 5.0
    worker_batch_size: int = 10
    worker_lease_seconds: int = 60

    # API Security Limits
    max_request_body_bytes: int = 1_048_576  # 1MB limit

    # Rate Limiting Settings (GAP-01)
    rate_limit_enabled: bool = True
    rate_limit_default_rate: float = 20.0  # requests per second
    rate_limit_default_burst: int = 40  # burst allowance
    rate_limit_sensitive_rate: float = 5.0  # requests per second for sensitive routes
    rate_limit_sensitive_burst: int = 10  # burst allowance for sensitive routes
    trusted_proxies: str = "127.0.0.1,::1,localhost,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_production_settings(self) -> None:
        """
        Validates non-negotiable production safeguards.
        Fails closed if production is misconfigured with demo, SQLite, or Live credentials.
        """
        if self.app_env.lower() == "production":
            if self.database_url.lower().startswith("sqlite"):
                raise ValueError(
                    "Production configuration strictly rejects SQLite. "
                    "A production PostgreSQL database_url must be provided."
                )

            if self.session_secret == "prip-insecure-default-change-in-production":
                raise ValueError(
                    "Production configuration strictly rejects default insecure session_secret. "
                    "A strong secret must be configured via environment variable."
                )

            if self.paypal_environment.lower() != "sandbox":
                raise ValueError(
                    "PRIP MVP strictly rejects PayPal Live environments. "
                    "paypal_environment must be configured as 'sandbox'."
                )

            if not self.oidc_issuer or not self.oidc_client_id:
                raise ValueError(
                    "Production configuration requires OIDC authentication. "
                    "oidc_issuer and oidc_client_id must be provided."
                )

            if not self.paypal_client_id or not self.paypal_client_secret:
                raise ValueError(
                    "Production configuration requires PayPal Sandbox credentials. "
                    "paypal_client_id and paypal_client_secret must be set."
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
