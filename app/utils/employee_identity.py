from __future__ import annotations

from typing import Any


def normalize_management_no(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text


def build_canonical_employee_code(site_code: str | None, management_no: str | None) -> str:
    left = str(site_code or "").strip().upper()
    right = normalize_management_no(management_no)
    if not left or not right:
        return ""
    return f"{left}-{right}"


def normalize_employee_code(value: str | None, *, site_code: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    preferred_site_code = str(site_code or "").strip().upper()
    if preferred_site_code:
        prefix = f"{preferred_site_code}-"
        if text.upper().startswith(prefix):
            suffix = text[len(prefix):]
            return build_canonical_employee_code(preferred_site_code, suffix)

    if "-" not in text:
        return normalize_management_no(text)

    left, right = text.split("-", 1)
    return build_canonical_employee_code(left, right)


def extract_management_no_from_employee_code(value: str | None, *, site_code: str | None = None) -> str:
    normalized = normalize_employee_code(value, site_code=site_code)
    if not normalized:
        return ""

    preferred_site_code = str(site_code or "").strip().upper()
    if preferred_site_code:
        prefix = f"{preferred_site_code}-"
        if normalized.startswith(prefix):
            return normalized[len(prefix):]

    if "-" not in normalized:
        return normalized
    return normalized.split("-", 1)[1]


def build_employee_directory_identity_key(row: dict[str, Any]) -> str:
    tenant_id = str(row.get("tenant_id") or "").strip()
    site_code = str(row.get("site_code") or "").strip().upper()
    management_no = normalize_management_no(
        row.get("management_no_str")
        or row.get("management_no")
        or extract_management_no_from_employee_code(row.get("employee_code"), site_code=site_code)
    )
    if site_code and management_no:
        return f"{tenant_id}|{site_code}|{management_no}"

    normalized_code = normalize_employee_code(row.get("employee_code"), site_code=site_code)
    if normalized_code:
        return f"{tenant_id}|code|{normalized_code}"

    employee_id = str(row.get("id") or "").strip()
    return f"{tenant_id}|id|{employee_id}"
