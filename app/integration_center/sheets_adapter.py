from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

SYNC_MODE_KEY_ROW = "key_row"
SYNC_MODE_NAMED_RANGE = "named_range"
SYNC_MODE_CUSTOM_JSON = "custom_json"
ALLOWED_SYNC_MODES = {SYNC_MODE_KEY_ROW, SYNC_MODE_NAMED_RANGE, SYNC_MODE_CUSTOM_JSON}


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


class SheetsAdapter:
    def __init__(self, profile: dict[str, Any]):
        self.profile = profile or {}
        options = self.profile.get("options_json") if isinstance(self.profile.get("options_json"), dict) else {}
        raw_mode = str(options.get("sync_mode") or self.profile.get("auth_mode") or SYNC_MODE_CUSTOM_JSON).strip().lower()
        self.sync_mode = raw_mode if raw_mode in ALLOWED_SYNC_MODES else SYNC_MODE_CUSTOM_JSON

    def _base_meta(self, *, tenant_code: str, period: dict[str, str], generated_at: str) -> dict[str, Any]:
        return {
            "tenant_code": tenant_code,
            "period": period,
            "generated_at": generated_at,
            "profile": {
                "id": str(self.profile.get("id") or ""),
                "profile_name": self.profile.get("profile_name"),
                "spreadsheet_id": self.profile.get("spreadsheet_id"),
                "worksheet_schedule": self.profile.get("worksheet_schedule"),
                "worksheet_overtime": self.profile.get("worksheet_overtime"),
                "worksheet_overnight": self.profile.get("worksheet_overnight"),
            },
            "sync_mode": self.sync_mode.upper(),
        }

    def _build_key_row_payload(self, rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        key_rows: list[dict[str, Any]] = []
        for section, row_list in rows.items():
            for row in row_list:
                employee_code = str(row.get("employee_code") or "-")
                day = str(row.get("schedule_date") or row.get("work_date") or "-")
                row_key = f"{section}:{employee_code}:{day}"
                key_rows.append(
                    {
                        "row_key": row_key,
                        "section": section,
                        "columns": _serialize(row),
                    },
                )
        return {"key_rows": key_rows}

    def _build_named_range_payload(self, rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        return {
            "named_ranges": {
                "SCHEDULE_RANGE": _serialize(rows.get("schedule", [])),
                "OVERTIME_RANGE": _serialize(rows.get("overtime", [])),
                "OVERNIGHT_RANGE": _serialize(rows.get("overnight", [])),
            },
        }

    def _build_custom_json_payload(self, rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        return {
            "rows": {
                "schedule": _serialize(rows.get("schedule", [])),
                "overtime": _serialize(rows.get("overtime", [])),
                "overnight": _serialize(rows.get("overnight", [])),
            },
        }

    def build_payload(
        self,
        *,
        tenant_code: str,
        period: dict[str, str],
        generated_at: str,
        rows: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        payload = self._base_meta(tenant_code=tenant_code, period=period, generated_at=generated_at)
        if self.sync_mode == SYNC_MODE_KEY_ROW:
            payload.update(self._build_key_row_payload(rows))
        elif self.sync_mode == SYNC_MODE_NAMED_RANGE:
            payload.update(self._build_named_range_payload(rows))
        else:
            payload.update(self._build_custom_json_payload(rows))
        return payload
