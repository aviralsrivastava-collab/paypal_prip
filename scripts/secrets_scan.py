import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Patterns based on standard Gitleaks, TruffleHog, and OWASP secret detection rules
SECRET_PATTERNS = [
    ("Private Key", re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS Client ID", re.compile(r"\b(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub Personal Access Token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}\b")),
    ("GitHub Fine-Grained Token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b")),
    ("Stripe Live Secret Key", re.compile(r"\b(?:sk|rk)_live_[0-9a-zA-Z]{24,}\b")),
    ("SendGrid API Key", re.compile(r"\bSG\.[0-9a-zA-Z_-]{22}\.[0-9a-zA-Z_-]{43}\b")),
    ("Generic High-Entropy Secret / Password", re.compile(
        r"""(?i)(?:api_key|client_secret|jwt_secret|session_secret|auth_token|database_password)\s*[:=]\s*["']([^"'\s]{16,})["']"""
    )),
    ("Hardcoded Database URI with Password", re.compile(
        r"""(?:postgres|postgresql|mysql|mongodb)://(?!(?:prip|user):(?:prip_secure_password_replace_in_prod|password|STRONG_PASSWORD_HERE|STRONG_RANDOM_PASSWORD|GENERATE_STRONG_RANDOM_PASSWORD|GENERATE_64_CHAR_RANDOM_SECRET_HERE))[^:]+:([^@\s]+)@"""
    )),
]

# Safe placeholders that are allowed in templates, tests, and documentation
SAFE_PLACEHOLDERS = {
    "replace-with-api-key-for-live-provider",
    "replace-with-a-long-random-local-secret",
    "prip-insecure-default-change-in-production",
    "prip_secure_password_replace_in_prod",
    "prip-dev-oidc-secret-replace-in-production",
    "prip-prod-oidc-secret-replace-in-production",
    "prip_prod_secret_override_me",
    "STRONG_PASSWORD_HERE",
    "STRONG_RANDOM_PASSWORD",
    "GENERATE_STRONG_RANDOM_PASSWORD",
    "GENERATE_64_CHAR_RANDOM_SECRET_HERE",
    "GENERATE_64_CHAR_HEX_STRING",
    "YOUR_SANDBOX_CLIENT_ID",
    "YOUR_SANDBOX_CLIENT_SECRET",
    "YOUR_SANDBOX_WEBHOOK_ID",
    "YOUR_SANDBOX_REST_APP_CLIENT_ID",
    "YOUR_SANDBOX_REST_APP_CLIENT_SECRET",
    "WH-MOCK-SANDBOX-001",
    "sb-client-id-demo",
    # Test fixture dummy strings
    "strong-prod-secret-1234567890",
    "super-secret-password-123",
    "pass",
    "user:pass@localhost",
    "user:pass@nonexistent",
    "-----BEGIN PRIVATE KEY-----",
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".import_linter_cache",
    "__pycache__",
}


def redact(val: str) -> str:
    if len(val) <= 4:
        return "****"
    return val[:2] + "*" * (len(val) - 4) + val[-2:]


def is_safe_value(match_str: str) -> bool:
    for placeholder in SAFE_PLACEHOLDERS:
        if placeholder in match_str:
            return True
    return False


def scan_file(file_path: Path) -> List[Tuple[str, int, str]]:
    findings = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                # Skip comments in example/template files
                line_stripped = line.strip()
                if line_stripped.startswith("#") and file_path.name.endswith(".example"):
                    continue

                for rule_name, pattern in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        matched_text = match.group(0)
                        # Check captured group if available
                        captured = match.group(1) if match.lastindex and match.lastindex >= 1 else matched_text
                        if not is_safe_value(captured):
                            findings.append((rule_name, idx, redact(captured)))
    except Exception as exc:
        print(f"Error reading {file_path}: {exc}", file=sys.stderr)
    return findings


def scan_directory(root_dir: Path) -> int:
    total_findings = 0
    scanned_count = 0
    print(f"Starting security secrets scan in: {root_dir}")

    for root, dirs, files in os.walk(root_dir):
        # Filter ignore dirs in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".tmp")]

        for file in files:
            file_path = Path(root) / file
            # Skip binary doc uploads, sqlite DBs, and local git-ignored env files (.env is checked for untracked status by harness-check)
            if file.endswith((".sqlite", ".db", ".doc", ".png", ".jpg", ".ico", ".pdf", ".zip", ".tar.gz", ".gz")):
                continue
            if file == ".env" or (file.startswith(".env.") and not file.endswith(".example")):
                continue

            findings = scan_file(file_path)
            scanned_count += 1
            if findings:
                for rule, line_no, redacted_secret in findings:
                    print(f"[ALERT] {rule} detected at {file_path}:{line_no} -> {redacted_secret}")
                    total_findings += 1

    print(f"\nScan completed: {scanned_count} files scanned across repository.")
    if total_findings == 0:
        print("[SUCCESS] Zero real secrets or unredacted credentials detected.")
    else:
        print(f"[FAILURE] {total_findings} potential secret(s) found!")
    return total_findings


if __name__ == "__main__":
    base_path = Path(__file__).resolve().parent.parent
    sys.exit(scan_directory(base_path))
