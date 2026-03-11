from __future__ import annotations

import re
from typing import Optional

_AUTH_IDENTIFIER_SEPARATORS = re.compile(r"[\s-]+")
_NON_DIGIT_PATTERN = re.compile(r"\D+")


def normalize_auth_identifier(value: Optional[str]) -> str:
    """Normalize login identifiers by removing hyphens and whitespace."""
    text = str(value or "").strip()
    if not text:
        return ""
    return _AUTH_IDENTIFIER_SEPARATORS.sub("", text)


def normalize_phone_identifier(value: Optional[str]) -> str:
    """Normalize phone-based identifiers by keeping digits only."""
    text = str(value or "").strip()
    if not text:
        return ""
    return _NON_DIGIT_PATTERN.sub("", text)


def build_auth_identifier_candidates(value: Optional[str]) -> tuple[str, ...]:
    """
    Build normalized identifier candidates for login lookups.

    - generic credential normalization (whitespace/hyphen removed)
    - phone normalization (digits only)
    """
    generic = normalize_auth_identifier(value).lower()
    phone = normalize_phone_identifier(value).lower()
    values: list[str] = []
    for candidate in (generic, phone):
        if candidate and candidate not in values:
            values.append(candidate)
    return tuple(values)
