from __future__ import annotations

from typing import Any

SOC_INTEGRATION_ENABLED = "soc_integration_enabled"
SHEETS_SYNC_ENABLED = "sheets_sync_enabled"
APPLE_REPORT_OVERNIGHT_ENABLED = "apple_report_overnight_enabled"
APPLE_REPORT_DAYTIME_ENABLED = "apple_report_daytime_enabled"
APPLE_REPORT_OT_ENABLED = "apple_report_ot_enabled"
APPLE_REPORT_TOTAL_LATE_ENABLED = "apple_report_total_late_enabled"
PAYROLL_SHEET_ENABLED = "payroll_sheet_enabled"

# Operational flags currently used by P0 handlers.
SOC_LEAVE_OVERRIDE_ENABLED = "soc_leave_override_enabled"
SOC_OVERTIME_ENABLED = "soc_overtime_enabled"
SOC_CLOSING_OT_ENABLED = "soc_closing_ot_enabled"

FLAG_KEY_ALIASES = {
    SOC_INTEGRATION_ENABLED: SOC_INTEGRATION_ENABLED,
    "soc_ingest_enabled": SOC_INTEGRATION_ENABLED,
    SHEETS_SYNC_ENABLED: SHEETS_SYNC_ENABLED,
    "google_sheets_sync_enabled": SHEETS_SYNC_ENABLED,
    APPLE_REPORT_OVERNIGHT_ENABLED: APPLE_REPORT_OVERNIGHT_ENABLED,
    "soc_overnight_enabled": APPLE_REPORT_OVERNIGHT_ENABLED,
    APPLE_REPORT_DAYTIME_ENABLED: APPLE_REPORT_DAYTIME_ENABLED,
    APPLE_REPORT_OT_ENABLED: APPLE_REPORT_OT_ENABLED,
    APPLE_REPORT_TOTAL_LATE_ENABLED: APPLE_REPORT_TOTAL_LATE_ENABLED,
    PAYROLL_SHEET_ENABLED: PAYROLL_SHEET_ENABLED,
    SOC_LEAVE_OVERRIDE_ENABLED: SOC_LEAVE_OVERRIDE_ENABLED,
    SOC_OVERTIME_ENABLED: SOC_OVERTIME_ENABLED,
    SOC_CLOSING_OT_ENABLED: SOC_CLOSING_OT_ENABLED,
}

CANONICAL_TO_ALIASES = {
    SOC_INTEGRATION_ENABLED: {SOC_INTEGRATION_ENABLED, "soc_ingest_enabled"},
    SHEETS_SYNC_ENABLED: {SHEETS_SYNC_ENABLED, "google_sheets_sync_enabled"},
    APPLE_REPORT_OVERNIGHT_ENABLED: {APPLE_REPORT_OVERNIGHT_ENABLED, "soc_overnight_enabled"},
    APPLE_REPORT_DAYTIME_ENABLED: {APPLE_REPORT_DAYTIME_ENABLED},
    APPLE_REPORT_OT_ENABLED: {APPLE_REPORT_OT_ENABLED},
    APPLE_REPORT_TOTAL_LATE_ENABLED: {APPLE_REPORT_TOTAL_LATE_ENABLED},
    PAYROLL_SHEET_ENABLED: {PAYROLL_SHEET_ENABLED},
    SOC_LEAVE_OVERRIDE_ENABLED: {SOC_LEAVE_OVERRIDE_ENABLED},
    SOC_OVERTIME_ENABLED: {SOC_OVERTIME_ENABLED},
    SOC_CLOSING_OT_ENABLED: {SOC_CLOSING_OT_ENABLED},
}


def normalize_flag_key(flag_key: str | None) -> str:
    normalized = str(flag_key or "").strip().lower()
    if not normalized:
        return ""
    return FLAG_KEY_ALIASES.get(normalized, normalized)


def build_feature_flag_defaults(settings: Any) -> dict[str, bool]:
    soc_enabled = bool(getattr(settings, "soc_integration_enabled", False))
    sheets_enabled = bool(getattr(settings, "sheets_sync_enabled", False))
    overnight_enabled = bool(getattr(settings, "apple_report_overnight_enabled", False))
    daytime_enabled = bool(getattr(settings, "apple_report_daytime_enabled", False))
    ot_enabled = bool(getattr(settings, "apple_report_ot_enabled", False))
    total_late_enabled = bool(getattr(settings, "apple_report_total_late_enabled", False))
    return {
        SOC_INTEGRATION_ENABLED: soc_enabled,
        "soc_ingest_enabled": soc_enabled,  # backward compatibility
        SHEETS_SYNC_ENABLED: sheets_enabled,
        "google_sheets_sync_enabled": sheets_enabled,  # backward compatibility
        APPLE_REPORT_OVERNIGHT_ENABLED: overnight_enabled,
        "soc_overnight_enabled": overnight_enabled,  # backward compatibility
        APPLE_REPORT_DAYTIME_ENABLED: daytime_enabled,
        APPLE_REPORT_OT_ENABLED: ot_enabled,
        APPLE_REPORT_TOTAL_LATE_ENABLED: total_late_enabled,
        PAYROLL_SHEET_ENABLED: bool(getattr(settings, "payroll_sheet_enabled", False)),
        SOC_LEAVE_OVERRIDE_ENABLED: bool(getattr(settings, "soc_leave_override_enabled", False)),
        SOC_OVERTIME_ENABLED: bool(getattr(settings, "soc_overtime_enabled", False)),
        SOC_CLOSING_OT_ENABLED: bool(getattr(settings, "soc_closing_ot_enabled", False)),
    }


class FeatureFlagService:
    def __init__(self, conn, defaults: dict[str, bool]):
        self.conn = conn
        self.defaults = {normalize_flag_key(key): bool(value) for key, value in (defaults or {}).items()}

    def _aliases(self, flag_key: str) -> list[str]:
        canonical = normalize_flag_key(flag_key)
        aliases = CANONICAL_TO_ALIASES.get(canonical, {canonical})
        return sorted(aliases)

    def get_override(self, tenant_id, flag_key: str) -> bool | None:
        aliases = self._aliases(flag_key)
        if not aliases:
            return None

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT enabled
                FROM integration_feature_flags
                WHERE tenant_id = %s
                  AND flag_key = ANY(%s::text[])
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (tenant_id, aliases),
            )
            row = cur.fetchone()
        if not row:
            return None
        return bool(row["enabled"])

    def is_enabled(self, tenant_id, flag_key: str) -> bool:
        canonical = normalize_flag_key(flag_key)
        override = self.get_override(tenant_id, canonical)
        if override is not None:
            return override
        return bool(self.defaults.get(canonical, False))

    def set_flag(self, tenant_id, flag_key: str, enabled: bool, updated_by=None) -> str:
        canonical = normalize_flag_key(flag_key)
        aliases = self._aliases(canonical)
        with self.conn.cursor() as cur:
            for alias in aliases:
                cur.execute(
                    """
                    INSERT INTO integration_feature_flags (tenant_id, flag_key, enabled, updated_by, updated_at)
                    VALUES (%s, %s, %s, %s, timezone('utc', now()))
                    ON CONFLICT (tenant_id, flag_key)
                    DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = timezone('utc', now())
                    """,
                    (tenant_id, alias, bool(enabled), updated_by),
                )
        return canonical

    def list_effective(self, tenant_id) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key, default_enabled in sorted(self.defaults.items()):
            override = self.get_override(tenant_id, key)
            result.append(
                {
                    "flag_key": key,
                    "enabled": bool(default_enabled if override is None else override),
                },
            )
        return result
