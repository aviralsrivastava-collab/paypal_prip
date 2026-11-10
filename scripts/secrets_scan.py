#!/usr/bin/env python3
import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import List, NamedTuple, Set

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Patterns based on common secret detection heuristics.
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
        r"""(?:postgres|postgresql|mysql|mongodb)://(?!(?:prip|user):(?:prip_secure_password_replace_in_prod|password|STRONG_PASSWORD_HERE|STRONG_RANDOM_PASSWORD|GENERATE_STRONG_RANDOM_PASSWORD|GENERATE_64_CHAR_RANDOM_SECRET_HERE|GENERATE_64_CHAR_HEX_STRING))[^/\s:@]+(?::[^@/\s]+)?@""",
        re.IGNORECASE,
    )),
]

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
    "strong-prod-secret-1234567890",
    "super-secret-password-123",
    "pass",
    "user:pass@localhost",
    "user:pass@nonexistent",
    "-----BEGIN PRIVATE KEY-----",
    "changeme",
    "change-me",
    "example",
    "sample",
    "dummy",
    "placeholder",
    "mock_secret",
    "your_token_here",
    "replace_me",
    "test-secret",
    "fake-secret",
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

SKIP_FILE_EXTENSIONS = {
    ".sqlite",
    ".db",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar.gz",
    ".gz",
}

class Finding(NamedTuple):
    rule: str
    file_path: str
    line_no: int
    redacted_secret: str


def redact(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "****"
    if len(value) <= 8:
        return value[:2] + "*" * max(2, len(value) - 4) + value[-2:]
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def is_safe_value(match_str: str) -> bool:
    candidate = match_str.strip().lower()
    if not candidate:
        return True

    # Direct placeholder checks.
    for placeholder in SAFE_PLACEHOLDERS:
        if placeholder.lower() in candidate:
            return True

    # Common docs/test/example markers.
    for marker in ("example", "sample", "dummy", "mock", "placeholder", "replace_me", "replace-me", "changeme", "test"):
        if marker in candidate:
            return True

    return False


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
        return True

    if path.suffix in SKIP_FILE_EXTENSIONS or name.endswith(tuple(SKIP_FILE_EXTENSIONS)):
        return True

    return False


def extract_secret(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 1:
        candidate = match.group(1)
        if candidate:
            return str(candidate)
    return str(match.group(0))


def scan_file(file_path: Path, root_dir: Path) -> List[Finding]:
    findings: List[Finding] = []

    try:
        with file_path.open("r", encoding="utf-8", errors="surrogateescape") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.strip()

                # Skip comment-only example/template lines.
                if stripped.startswith("#") and file_path.name.endswith(".example"):
                    continue

                for rule_name, pattern in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if not match:
                        continue

                    candidate = extract_secret(match)
                    if is_safe_value(candidate):
                        continue

                    rel_path = file_path.relative_to(root_dir) if file_path.is_relative_to(root_dir) else file_path
                    findings.append(Finding(rule_name, str(rel_path), line_no, redact(candidate)))
    except OSError as exc:
        logging.error("Error reading %s: %s", file_path, exc)
    except Exception as exc:
        logging.error("Unexpected error scanning %s: %s", file_path, exc)

    return findings


def scan_directory(root_dir: Path, as_json: bool = False) -> int:
    root_dir = root_dir.resolve()
    total_findings = 0
    scanned_count = 0
    seen: Set[tuple] = set()

    logging.info("Starting security secrets scan in: %s", root_dir)

    for current_root, dirs, files in os.walk(root_dir):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".tmp"))

        for filename in sorted(files):
            file_path = Path(current_root) / filename

            if should_skip_file(file_path):
                continue

            findings = scan_file(file_path, root_dir)
            scanned_count += 1

            for finding in findings:
                dedupe_key = (finding.rule, finding.file_path, finding.line_no, finding.redacted_secret)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                total_findings += 1
                if as_json:
                    print(json.dumps({
                        "rule": finding.rule,
                        "file": finding.file_path,
                        "line": finding.line_no,
                        "secret": finding.redacted_secret,
                    }))
                else:
                    print(f"[ALERT] {finding.rule} detected at {finding.file_path}:{finding.line_no} -> {finding.redacted_secret}")

    logging.info("")
    logging.info("Scan completed: %s files scanned across repository.", scanned_count)
    if total_findings == 0:
        logging.info("[SUCCESS] Zero real secrets or unredacted credentials detected.")
    else:
        logging.warning("[FAILURE] %s potential secret(s) found!", total_findings)

    return total_findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan a repository for likely hardcoded secrets.")
    parser.add_argument("root", nargs="?", default=".", help="Root directory to scan (default: current directory).")
    parser.add_argument("--json", action="store_true", help="Emit finding records as JSON lines.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root_dir = Path(args.root).resolve()
    exit_code = scan_directory(root_dir, as_json=args.json)
    raise SystemExit(1 if exit_code else 0)
# Patterns based on standard Gitleaks, TruffleHog, and OWASP secret detection rules
