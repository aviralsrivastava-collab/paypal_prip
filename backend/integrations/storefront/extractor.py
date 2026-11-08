import datetime
import hashlib
import ipaddress
import json
from decimal import Decimal
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from backend.core.config import get_settings
from backend.repositories.storefront import StorefrontRepository


def is_safe_storefront_url(url: str, allowed_base: Optional[str] = None) -> bool:
    """
    Validates that a storefront URL does not target internal infrastructure,
    cloud metadata endpoints, or unauthorized external destinations (SSRF defense).
    Relative paths on the controlled storefront are considered safe.
    """
    if not url or not isinstance(url, str):
        return False

    # Relative paths on the controlled storefront are safe
    if url.startswith("/") and not url.startswith("//"):
        return True

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Block cloud metadata endpoints
        if hostname in ("169.254.169.254", "metadata.google.internal", "metadata"):
            return False

        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                # Allow loopback ONLY if allowed_base explicitly matches host and port
                if allowed_base:
                    base_parsed = urlparse(allowed_base)
                    base_port = base_parsed.port or (443 if base_parsed.scheme == "https" else 80)
                    if (base_parsed.hostname in ("localhost", "127.0.0.1") and hostname in ("localhost", "127.0.0.1")) and target_port == base_port:
                        return True
                return False
        except ValueError:
            # Hostname is a domain name
            if hostname == "localhost":
                if allowed_base:
                    base_parsed = urlparse(allowed_base)
                    base_port = base_parsed.port or (443 if base_parsed.scheme == "https" else 80)
                    return base_parsed.hostname in ("localhost", "127.0.0.1") and target_port == base_port
                return False

        # For production/domain targets, restrict to allowed base if configured
        if allowed_base:
            base_parsed = urlparse(allowed_base)
            if parsed.netloc.lower() != base_parsed.netloc.lower():
                return False

        return True
    except Exception:
        return False



class ExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    MISSING_PRODUCT = "MISSING_PRODUCT"
    TIMEOUT = "TIMEOUT"
    BLOCKED_ACCESS = "BLOCKED_ACCESS"
    UNSUPPORTED_CONTENT = "UNSUPPORTED_CONTENT"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"


class StorefrontObservation:
    """
    Structured, typed representation of a storefront extraction attempt.
    """

    def __init__(
        self,
        status: ExtractionStatus,
        source_url: str,
        observed_sku: Optional[str] = None,
        observed_title: Optional[str] = None,
        observed_price: Optional[Decimal] = None,
        observed_currency: Optional[str] = None,
        observed_availability: Optional[str] = None,
        observed_variant: Optional[str] = None,
        observed_promotion: Optional[str] = None,
        raw_content_snippet: Optional[str] = None,
        content_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        observation_timestamp: Optional[datetime.datetime] = None,
    ) -> None:
        self.status = status
        self.source_url = source_url
        self.observed_sku = observed_sku
        self.observed_title = observed_title
        self.observed_price = observed_price
        self.observed_currency = observed_currency
        self.observed_availability = observed_availability
        self.observed_variant = observed_variant
        self.observed_promotion = observed_promotion
        self.raw_content_snippet = raw_content_snippet
        self.error_message = error_message
        self.observation_timestamp = observation_timestamp or datetime.datetime.now(datetime.timezone.utc)

        # Generate cryptographic integrity hash from normalized observation payload
        if content_hash:
            self.content_hash = content_hash
        else:
            payload = json.dumps(
                {
                    "sku": observed_sku,
                    "title": observed_title,
                    "price": str(observed_price) if observed_price is not None else None,
                    "currency": observed_currency,
                    "status": status.value,
                },
                sort_keys=True,
            )
            self.content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StorefrontExtractor:
    """
    Controlled demo storefront extraction adapter.
    Extracts storefront product observations without arbitrary crawling or bypass hazards.
    """

    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory

    def extract_from_storefront(
        self,
        sku: str,
        source_url: str,
        timeout_seconds: float = 5.0,
        simulated_scenario: Optional[str] = None,
    ) -> StorefrontObservation:
        """
        Extracts observed product facts for a given SKU.
        Supports simulation triggers for deterministic fault testing (timeout, missing, blocked).
        """
        # Fault injection hooks for deterministic testing
        if simulated_scenario == "timeout":
            return StorefrontObservation(
                status=ExtractionStatus.TIMEOUT,
                source_url=source_url,
                error_message=f"Storefront extraction timed out after {timeout_seconds}s",
            )

        if simulated_scenario == "blocked":
            return StorefrontObservation(
                status=ExtractionStatus.BLOCKED_ACCESS,
                source_url=source_url,
                error_message="Storefront access blocked: 403 Forbidden or bot-detection challenge",
            )

        if simulated_scenario == "unsupported":
            return StorefrontObservation(
                status=ExtractionStatus.UNSUPPORTED_CONTENT,
                source_url=source_url,
                error_message="Storefront returned unsupported or malformed schema format",
            )

        if simulated_scenario == "missing":
            return StorefrontObservation(
                status=ExtractionStatus.MISSING_PRODUCT,
                source_url=source_url,
                error_message=f"Product with SKU '{sku}' not found on storefront (404)",
            )

        # SSRF validation guard
        settings = get_settings()
        if not is_safe_storefront_url(source_url, settings.controlled_storefront_base_url):
            return StorefrontObservation(
                status=ExtractionStatus.BLOCKED_ACCESS,
                source_url=source_url,
                error_message=f"SSRF blocked: URL '{source_url}' targets unauthorized or internal network address.",
            )

        # Normal extraction via controlled demo storefront data store
        if not self.session_factory:
            from backend.core.database import SessionLocal
            session = SessionLocal()
            close_session = True
        else:
            session = self.session_factory()
            close_session = True

        try:
            repo = StorefrontRepository(session)
            storefront_product = repo.get_by_sku(sku)

            if not storefront_product:
                return StorefrontObservation(
                    status=ExtractionStatus.MISSING_PRODUCT,
                    source_url=source_url,
                    error_message=f"Product '{sku}' was not found on the storefront.",
                )

            snippet = (
                f'<div class="product"><span class="sku">{storefront_product.sku}</span>'
                f'<span class="price">{storefront_product.price} {storefront_product.currency}</span></div>'
            )

            return StorefrontObservation(
                status=ExtractionStatus.SUCCESS,
                source_url=source_url,
                observed_sku=storefront_product.sku,
                observed_title=storefront_product.title,
                observed_price=storefront_product.price,
                observed_currency=storefront_product.currency,
                observed_availability=storefront_product.availability,
                raw_content_snippet=snippet,
            )
        finally:
            if close_session:
                session.close()
