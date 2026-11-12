import base64
import logging
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, cast
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from pydantic import BaseModel

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

RESERVED_SYSTEM_TENANTS = {"QUARANTINED_ORPHAN", "platform_system", "platform"}


def is_allowed_origin(origin: Optional[str], allowed_origins: Sequence[str]) -> bool:
    """
    Cryptographically safe, strict URL/origin validation.
    Replaces unsafe substring or suffix matching to prevent:
    - Hostname suffix attacks: e.g. https://paypalprip.vercel.app.attacker.com
    - Subdomain prefix attacks: e.g. https://attackerpaypalprip.vercel.app
    - Embedded trusted domains: e.g. https://attacker.com/paypalprip.vercel.app or ?url=...
    - Scheme downgrade attacks: e.g. http://paypalprip.vercel.app when https is required
    - Userinfo / port spoofing / path injection
    """
    if not origin or not isinstance(origin, str):
        return False

    raw_origin = origin.strip()
    if not raw_origin:
        return False

    try:
        parsed = urlparse(raw_origin)
    except Exception:
        return False

    # Origin must specify an allowed scheme (http for local dev, https for production)
    if parsed.scheme not in ("http", "https"):
        return False

    # Origin must have a valid hostname and netloc
    if not parsed.hostname or not parsed.netloc:
        return False

    # An Origin header must not contain a path (except empty or '/'), query, or fragment
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False

    # Origin must not contain userinfo (username:password@)
    if parsed.username or parsed.password:
        return False

    incoming_scheme = parsed.scheme.lower()
    incoming_hostname = parsed.hostname.lower()
    incoming_port = parsed.port or (443 if incoming_scheme == "https" else 80)

    for candidate in allowed_origins:
        if not candidate or not isinstance(candidate, str):
            continue
        cand_trimmed = candidate.strip()
        if not cand_trimmed:
            continue

        try:
            cand_parsed = urlparse(cand_trimmed)
        except Exception:
            continue

        cand_scheme = cand_parsed.scheme.lower() if cand_parsed.scheme else ""
        cand_hostname = cand_parsed.hostname.lower() if cand_parsed.hostname else ""
        cand_port = cand_parsed.port or (443 if cand_scheme == "https" else 80)

        # Exact matching of scheme, exact hostname, and exact port
        if (
            incoming_scheme == cand_scheme
            and incoming_hostname == cand_hostname
            and incoming_port == cand_port
        ):
            return True

    return False


class AuthenticatedActor(BaseModel):
    """
    Server-side authenticated actor context.
    Identifies the authenticated principal, role, and merchant tenancy.
    """

    actor_id: str
    actor_type: str = "merchant"  # "merchant", "demo_operator", "system"
    role: str = "merchant_operator"  # "OWNER", "ADMIN", "MANAGER", "VIEWER", "merchant_admin", "demo_operator", "ordinary_user", "superadmin"
    merchant_id: str = "merchant_default"
    user_id: Optional[str] = None
    email: Optional[str] = None
    is_authenticated: bool = True


class JWKSManager:
    """
    Manages JWKS public key retrieval, caching, and key rotation for asymmetric OIDC tokens.
    Supports offline/test key registration for hermetic testing.
    """

    def __init__(self) -> None:
        self._test_keys: Dict[str, Any] = {}
        self._clients: Dict[str, PyJWKClient] = {}

    def register_test_key(self, kid: str, public_key_pem: str) -> None:
        """Registers a PEM-encoded public key for deterministic test verification."""
        self._test_keys[kid] = public_key_pem

    def clear_test_keys(self) -> None:
        """Clears registered test keys."""
        self._test_keys.clear()

    def get_signing_key(self, token: str, jwks_url: str, kid: Optional[str]) -> Any:
        """
        Resolves the signing key matching the token's kid header.
        Prioritizes registered test keys, then queries cached JWKS endpoint.
        """
        if kid and kid in self._test_keys:
            return self._test_keys[kid]

        if not jwks_url:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWKS URL not configured for OIDC asymmetric token verification.",
            )

        if jwks_url not in self._clients:
            self._clients[jwks_url] = PyJWKClient(
                jwks_url,
                cache_keys=True,
                max_cached_keys=16,
                cache_jwk_set=True,
                lifespan=3600,
                timeout=5.0,
                cooldown_duration=10.0,
            )

        client = self._clients[jwks_url]
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            return signing_key.key
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unable to obtain signing key from JWKS endpoint: {exc}",
            )


# Global JWKS manager singleton
jwks_manager = JWKSManager()


def register_test_jwks_key(kid: str, public_key_pem: str) -> None:
    """Helper for unit and integration tests to register public signing keys."""
    jwks_manager.register_test_key(kid, public_key_pem)


def clear_test_jwks_keys() -> None:
    """Helper for unit and integration tests to reset registered keys."""
    jwks_manager.clear_test_keys()


def generate_test_rsa_key_pair() -> Tuple[str, str]:
    """Generates an ephemeral RSA key pair (private_pem, public_pem) for hermetic tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def create_rsa_jwt_token(
    payload: Dict[str, Any],
    private_key_pem: str,
    kid: str = "test-rsa-kid-1",
    algorithm: str = "RS256",
    headers: Optional[Dict[str, Any]] = None,
) -> str:
    """Helper generating a genuine RS256/ES256 OIDC JWT for testing."""
    jwt_headers = {"kid": kid, "alg": algorithm, "typ": "JWT"}
    if headers:
        jwt_headers.update(headers)
    return jwt.encode(payload, private_key_pem, algorithm=algorithm, headers=jwt_headers)


def b64url_decode(payload: str) -> bytes:
    """Decodes standard base64url string with padding restoration."""
    rem = len(payload) % 4
    if rem > 0:
        payload += "=" * (4 - rem)
    return base64.urlsafe_b64decode(payload)


def b64url_encode(payload: bytes) -> str:
    """Encodes bytes to unpadded base64url string."""
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def create_jwt_token(
    payload: Dict[str, Any],
    secret: Optional[str] = None,
    headers: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Helper creating an HMAC-SHA256 JWT for development and legacy testing.
    Production strictly rejects HS256 tokens.
    """
    settings = get_settings()
    signing_secret = secret if secret is not None else settings.oidc_jwt_secret

    jwt_headers = {"alg": "HS256", "typ": "JWT"}
    if headers:
        jwt_headers.update(headers)

    return jwt.encode(payload, signing_secret, algorithm="HS256", headers=jwt_headers)


def verify_oidc_token(token: str) -> Dict[str, Any]:
    """
    Strictly verifies an RFC 7519 OIDC JWT.
    - In production: mandates asymmetric RS256/ES256 with dynamic JWKS discovery, kid validation,
      and strict merchant_id claim presence. Rejects HS256 and 'none'.
    - In development/test: allows RS256/ES256 via registered test keys or HS256 test tokens.
    Fails closed on any signature mismatch, expiry, or invalid claims.
    """
    settings = get_settings()
    is_production = (settings.app_env.lower() == "production")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT token structure or unreadable header.",
        )

    alg = unverified_header.get("alg", "")
    kid = unverified_header.get("kid")

    # 1. Algorithm restrictions
    if not alg or alg.lower() == "none":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signing algorithm 'none' is prohibited.",
        )

    if is_production:
        if alg not in ("RS256", "ES256"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unsupported JWT signing algorithm in production: '{alg}'. Production strictly requires RS256 or ES256.",
            )
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required 'kid' header in production JWT token.",
            )

        # Validate JWKS URL belongs to configured trusted issuer authority
        if settings.oidc_jwks_url and settings.oidc_issuer:
            parsed_jwks = urlparse(settings.oidc_jwks_url)
            parsed_issuer = urlparse(settings.oidc_issuer)
            is_google_authority = (
                parsed_issuer.netloc.lower() in ("accounts.google.com", "google.com")
                and parsed_jwks.netloc.lower() in ("www.googleapis.com", "googleapis.com")
            )
            if not is_google_authority and parsed_jwks.netloc.lower() != parsed_issuer.netloc.lower():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Security violation: Configured JWKS URL does not belong to trusted OIDC issuer authority.",
                )

        signing_key = jwks_manager.get_signing_key(token, settings.oidc_jwks_url, kid)
        allowed_algorithms = [alg]
    else:
        # Development / Testing environment
        if alg == "HS256":
            signing_key = settings.oidc_jwt_secret
            allowed_algorithms = ["HS256"]
        elif alg in ("RS256", "ES256"):
            signing_key = jwks_manager.get_signing_key(token, settings.oidc_jwks_url, kid)
            allowed_algorithms = [alg]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unsupported JWT signing algorithm: '{alg}'.",
            )

    # 2. Cryptographic decode & claims verification
    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed JWT token payload: {exc}",
        )

    token_has_iss = "iss" in unverified_claims
    token_has_aud = "aud" in unverified_claims

    expected_issuer_cfg = settings.oidc_issuer if (is_production or token_has_iss) else None
    if expected_issuer_cfg in ("https://accounts.google.com", "accounts.google.com"):
        expected_issuer: Any = ["https://accounts.google.com", "accounts.google.com"]
    elif expected_issuer_cfg:
        expected_issuer = expected_issuer_cfg
    else:
        expected_issuer = None

    expected_audience = settings.oidc_client_id if (is_production or token_has_aud) else None

    decode_options: Dict[str, Any] = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_nbf": True,
        "verify_iss": bool(expected_issuer),
        "verify_aud": bool(expected_audience),
        "require": ["exp", "sub"],
    }
    if is_production:
        decode_options["require"] = ["exp", "sub", "iss", "aud"]

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=allowed_algorithms,
            issuer=expected_issuer,
            audience=expected_audience,
            options=cast(Any, decode_options),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token has expired.",
        )
    except jwt.ImmatureSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token is not yet valid.",
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid JWT issuer: expected '{settings.oidc_issuer}'.",
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid JWT audience: expected '{settings.oidc_client_id}'.",
        )
    except jwt.InvalidAlgorithmError as ex:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Algorithm verification failed: {ex}",
        )
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT signature.",
        )
    except jwt.PyJWTError as ex:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid JWT token: {ex}",
        )

    # 3. Explicit merchant identity resolution (Fails closed in production)
    merchant_id = (
        payload.get("merchant_id")
        or payload.get("org_id")
        or payload.get("tenant_id")
    )

    # Google OAuth / standard OIDC email-to-merchant mapping
    token_email = payload.get("email")
    if not merchant_id and token_email:
        # Require email_verified is explicitly True
        email_verified = payload.get("email_verified")
        if email_verified is not True:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security violation: Google account email is not verified.",
            )

        clean_email = str(token_email).strip().lower()
        allowed_emails = settings.allowed_google_emails_set
        if allowed_emails and clean_email not in allowed_emails:
            logger.warning("Rejected unallowlisted Google account email: %s", clean_email)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Google account '{clean_email}' is not authorized to access this PRIP merchant.",
            )

        # Map to configured demo merchant ID server-side
        merchant_id = settings.default_merchant_id
        payload["merchant_id"] = merchant_id
        if "role" not in payload:
            payload["role"] = "merchant_operator"
        if "actor_type" not in payload:
            payload["actor_type"] = "merchant"

    if is_production and not merchant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required merchant identity claim ('merchant_id') in production token.",
        )

    return cast(Dict[str, Any], payload)


def get_current_actor(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_actor_id: Optional[str] = Header(default=None, alias="X-Actor-ID"),
    x_actor_role: Optional[str] = Header(default=None, alias="X-Actor-Role"),
    x_merchant_id: Optional[str] = Header(default=None, alias="X-Merchant-ID"),
) -> AuthenticatedActor:
    """
    Resolves the server-side authenticated identity and tenancy.
    In production environments, Bearer OIDC JWT is strictly mandatory; demo headers are rejected.
    In local/demo environments, defaults to an authorized demo operator context unless
    specified via demo boundary headers or Bearer JWT.
    """
    settings = get_settings()

    auth_str = authorization if isinstance(authorization, str) else None
    actor_id_str = x_actor_id if isinstance(x_actor_id, str) else None
    actor_role_str = x_actor_role if isinstance(x_actor_role, str) else None
    merchant_id_str = x_merchant_id if isinstance(x_merchant_id, str) else None

    # 1. Bearer Token Authentication (Always accepted & validated if provided)
    if auth_str:
        parts = auth_str.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            claims = verify_oidc_token(parts[1])
            merchant_id_claim = (
                claims.get("merchant_id")
                or claims.get("org_id")
                or claims.get("tenant_id")
            )
            resolved_merchant_id = str(merchant_id_claim or merchant_id_str or "merchant_default")
            role = str(claims.get("role", "merchant_operator"))
            email = claims.get("email")

            if resolved_merchant_id in RESERVED_SYSTEM_TENANTS and role not in {"system_admin", "superadmin", "system"}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Tenant '{resolved_merchant_id}' is a reserved non-merchant identity and cannot be claimed.",
                )

            return AuthenticatedActor(
                actor_id=str(claims.get("sub")),
                actor_type=str(claims.get("actor_type", "merchant")),
                role=role,
                merchant_id=resolved_merchant_id,
                user_id=str(claims.get("user_id")) if claims.get("user_id") else None,
                email=str(email) if email else None,
                is_authenticated=True,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header scheme. Expected 'Bearer <token>'.",
            )

    # 2. Production Environment Check (Fails closed without valid Bearer token)
    if settings.app_env.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Production authentication token required. Header simulation is prohibited.",
        )

    # 3. Development / Demo Environments: Header-based actor or trusted default
    if actor_id_str:
        role = actor_role_str or "merchant_operator"
        actor_type = "merchant" if role != "system" else "system"
        merchant_id = merchant_id_str or "merchant_default"
        if merchant_id in RESERVED_SYSTEM_TENANTS and role not in {"system_admin", "superadmin", "system"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Tenant '{merchant_id}' is a reserved non-merchant identity and cannot be claimed.",
            )
        return AuthenticatedActor(
            actor_id=actor_id_str,
            actor_type=actor_type,
            role=role,
            merchant_id=merchant_id,
            is_authenticated=True,
        )

    # Default trusted server-side demo identity
    default_merchant = merchant_id_str or "merchant_default"
    if default_merchant in RESERVED_SYSTEM_TENANTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Tenant '{default_merchant}' is a reserved non-merchant identity and cannot be claimed.",
        )
    return AuthenticatedActor(
        actor_id="demo-operator-1",
        actor_type="merchant",
        role="demo_operator",
        merchant_id=default_merchant,
        is_authenticated=True,
    )


def get_optional_actor(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_actor_id: Optional[str] = Header(default=None, alias="X-Actor-ID"),
    x_actor_role: Optional[str] = Header(default=None, alias="X-Actor-Role"),
    x_merchant_id: Optional[str] = Header(default=None, alias="X-Merchant-ID"),
) -> Optional[AuthenticatedActor]:
    """
    Resolves authenticated actor if credentials/tokens are provided,
    or falls back to demo identity in non-production environments.
    In production, returns None if no credentials are provided (allowing public storefront and buyer checkout).
    If invalid or expired credentials are provided, fails closed with 401.
    """
    if authorization:
        return get_current_actor(
            authorization=authorization,
            x_actor_id=x_actor_id,
            x_actor_role=x_actor_role,
            x_merchant_id=x_merchant_id,
        )
    settings = get_settings()
    if settings.app_env.lower() == "production":
        return None
    return get_current_actor(
        authorization=authorization,
        x_actor_id=x_actor_id,
        x_actor_role=x_actor_role,
        x_merchant_id=x_merchant_id,
    )


def require_demo_operator(
    current_actor: AuthenticatedActor = Depends(get_current_actor),
) -> AuthenticatedActor:
    """
    Authorization dependency verifying the caller has demo operator permissions.
    Blocks any reset when app_env is production or caller lacks demo operator role.
    """
    settings = get_settings()
    if settings.app_env.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seeding and reset operations are strictly forbidden in production environments.",
        )

    if current_actor.role not in {"demo_operator", "merchant_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Actor '{current_actor.actor_id}' with role '{current_actor.role}' is not authorized to perform catalog resets.",
        )
    return current_actor


def require_merchant_access(
    current_actor: AuthenticatedActor,
    target_merchant_id: str,
) -> None:
    """
    Tenancy guard enforcing that the current actor can only access their own tenant's resources.
    Superadmin / system roles are exempt.
    Fails closed with HTTP 403 Forbidden on tenant mismatch or reserved tenant access.
    """
    if current_actor.role in {"system_admin", "superadmin", "system"}:
        return

    if target_merchant_id in RESERVED_SYSTEM_TENANTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Cannot access reserved system tenant '{target_merchant_id}' resources.",
        )

    if current_actor.merchant_id != target_merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Actor from merchant '{current_actor.merchant_id}' is not authorized to access or mutate merchant '{target_merchant_id}' resources.",
        )


ROLE_LEVELS: Dict[str, int] = {
    "VIEWER": 10,
    "MANAGER": 20,
    "ADMIN": 30,
    "OWNER": 40,
    "superadmin": 100,
    "system": 100,
    "ordinary_user": 10,
    "merchant_operator": 20,
    "demo_operator": 30,
    "merchant_admin": 40,
    "system_admin": 100,
}


def require_role(min_role: str) -> Callable[[AuthenticatedActor], AuthenticatedActor]:
    """
    Authorization dependency verifying the actor has at least the specified role level.
    Hierarchy: VIEWER (10) < MANAGER (20) < ADMIN (30) < OWNER (40) < superadmin (100).
    """
    min_level = ROLE_LEVELS.get(min_role.upper(), ROLE_LEVELS.get(min_role, 20))

    def _role_checker(actor: AuthenticatedActor = Depends(get_current_actor)) -> AuthenticatedActor:
        actor_level = ROLE_LEVELS.get(actor.role.upper(), ROLE_LEVELS.get(actor.role, 0))
        if actor_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires at least '{min_role}' role (actor possesses '{actor.role}').",
            )
        return actor

    return _role_checker
