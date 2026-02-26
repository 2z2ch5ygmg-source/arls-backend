from __future__ import annotations

import re
from typing import Optional

_AUTH_IDENTIFIER_SEPARATORS = re.compile(r"[\s-]+")


def normalize_auth_identifier(value: Optional[str]) -> str:
    """Normalize login identifiers by removing hyphens and whitespace."""
    text = str(value or "").strip()
    if not text:
        return ""
    return _AUTH_IDENTIFIER_SEPARATORS.sub("", text)
