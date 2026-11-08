"""
Evidence Integrity and Canonical Hashing Policies
=================================================

Hash Inputs & Canonicalization Rules:
-------------------------------------
1. Timestamp Normalization:
   Observation timestamps are converted to UTC and formatted as ISO 8601
   without microseconds: '%Y-%m-%dT%H:%M:%SZ'.
2. Canonical Key Ordering:
   JSON payload contains strictly defined keys in alphabetical order:
   ['details', 'evidence_type', 'expected_value', 'field_name',
    'observation_timestamp', 'observed_value', 'source_url', 'status'].
3. Strict Serialization:
   Serialized with json.dumps(..., sort_keys=True, separators=(',', ':'))
   to eliminate platform-specific whitespace variations.
4. Cryptographic Hashing:
   The UTF-8 encoded canonical JSON string is hashed using SHA-256.
   Returns a 64-character lowercase hexadecimal digest string.

Integrity Guarantees and Limitations:
-------------------------------------
- What this guarantees: Deterministic detection of data drift, application-level
  tampering, accidental corruption, or column edits without updating the hash.
- What this does NOT guarantee: Unkeyed SHA-256 is not a digital signature (HMAC
  or asymmetric signature). It does not provide non-repudiation against an attacker
  with direct database write access who can recompute hashes.
"""

import datetime
import hashlib
import hmac
import json
from typing import Any, Optional


def compute_evidence_hash(
    evidence_type: str,
    field_name: str,
    expected_value: Optional[str],
    observed_value: Optional[str],
    source_url: str,
    observation_timestamp: Optional[datetime.datetime],
    status: str,
    details: Optional[str] = None,
) -> str:
    """
    Computes a deterministic SHA-256 hash over canonical evidence fields.
    """
    formatted_ts = ""
    if observation_timestamp:
        if observation_timestamp.tzinfo is None:
            ts_utc = observation_timestamp.replace(tzinfo=datetime.timezone.utc)
        else:
            ts_utc = observation_timestamp.astimezone(datetime.timezone.utc)
        formatted_ts = ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    canonical_payload = {
        "details": details,
        "evidence_type": evidence_type,
        "expected_value": expected_value,
        "field_name": field_name,
        "observation_timestamp": formatted_ts,
        "observed_value": observed_value,
        "source_url": source_url,
        "status": status,
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_evidence_hash(item: Any) -> bool:
    """
    Verifies whether an EvidenceItem's stored content_hash matches its canonical content.
    Returns False if any field or the hash itself has been tampered with.
    """
    stored_hash = getattr(item, "content_hash", None)
    if not stored_hash or not isinstance(stored_hash, str) or len(stored_hash) != 64:
        return False

    calculated = compute_evidence_hash(
        evidence_type=getattr(item, "evidence_type", ""),
        field_name=getattr(item, "field_name", ""),
        expected_value=getattr(item, "expected_value", None),
        observed_value=getattr(item, "observed_value", None),
        source_url=getattr(item, "source_url", ""),
        observation_timestamp=getattr(item, "observation_timestamp", None),
        status=getattr(item, "status", ""),
        details=getattr(item, "details", None),
    )
    return hmac.compare_digest(stored_hash, calculated)


def compute_request_hash(sku: str, simulated_scenario: Optional[str] = None) -> str:
    """
    Computes deterministic SHA-256 request fingerprint for inspection idempotency.
    """
    payload = {
        "simulated_scenario": simulated_scenario or None,
        "sku": sku.strip().upper(),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
