from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from jose import jwt

from ..config import settings
from .sheets_adapter import SheetsAdapter

logger = logging.getLogger(__name__)

GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
APPLE_PROFILE_SCOPES = {
    "APPLE_OVERNIGHT",
    "APPLE_DAYTIME",
    "APPLE_DAYTIME_P1",  # legacy alias
    "APPLE_OT",
    "APPLE_TOTAL_LATE",
}


def _parse_date_like(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if "T" in text:
            normalized = text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).date()
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _iter_months_inclusive(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        return []
    cursor = _month_start(start_date)
    end_cursor = _month_start(end_date)
    output: list[date] = []
    while cursor <= end_cursor:
        output.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return output


class GoogleSheetsMonthlyTabManager:
    def __init__(self, *, service_account_json: str = ""):
        self.service_account_json = str(service_account_json or "").strip()
        self._creds: dict[str, Any] | None = None
        self._access_token = ""
        self._access_token_expires_at = 0.0
        self._missing_config_logged = False

    def _load_creds(self) -> dict[str, Any] | None:
        if self._creds is not None:
            return self._creds
        if not self.service_account_json:
            if not self._missing_config_logged:
                logger.warning("Google Sheets service account not configured; monthly sheet auto-create skipped")
                self._missing_config_logged = True
            return None
        try:
            parsed = json.loads(self.service_account_json)
            if not isinstance(parsed, dict):
                raise ValueError("service account json must be object")
            required = {"client_email", "private_key"}
            if any(not str(parsed.get(key) or "").strip() for key in required):
                raise ValueError("service account json missing client_email/private_key")
            self._creds = parsed
            return self._creds
        except Exception as exc:
            if not self._missing_config_logged:
                logger.warning("invalid Google service account json; monthly sheet auto-create skipped: %s", exc)
                self._missing_config_logged = True
            return None

    def _token(self) -> str:
        now = time.time()
        if self._access_token and now < (self._access_token_expires_at - 60):
            return self._access_token

        creds = self._load_creds()
        if not creds:
            raise RuntimeError("google service account credentials are not configured")

        iat = int(now)
        exp = iat + 3600
        assertion = jwt.encode(
            {
                "iss": str(creds["client_email"]),
                "scope": GOOGLE_SHEETS_SCOPE,
                "aud": GOOGLE_OAUTH_TOKEN_URL,
                "iat": iat,
                "exp": exp,
            },
            str(creds["private_key"]),
            algorithm="RS256",
        )
        body = urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        ).encode("utf-8")
        request = Request(
            url=GOOGLE_OAUTH_TOKEN_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            token = str(payload.get("access_token") or "").strip()
            if not token:
                raise RuntimeError("google oauth token response missing access_token")
            expires_in = int(payload.get("expires_in") or 3600)
            self._access_token = token
            self._access_token_expires_at = now + max(300, expires_in)
            return token

    def _request_json(self, *, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = Request(url=url, data=data, method=method, headers=headers)
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            if not raw:
                return {}
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}

    def _get_metadata(self, spreadsheet_id: str) -> dict[str, Any]:
        fields = "sheets(properties(sheetId,title)),namedRanges(namedRangeId,name,range)"
        url = f"{GOOGLE_SHEETS_API_BASE}/{quote(spreadsheet_id, safe='')}?fields={quote(fields, safe='(),=')}"
        return self._request_json(method="GET", url=url)

    def _batch_update(self, spreadsheet_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        url = f"{GOOGLE_SHEETS_API_BASE}/{quote(spreadsheet_id, safe='')}:batchUpdate"
        return self._request_json(method="POST", url=url, payload={"requests": requests})

    def _next_named_range_name(self, existing_names: set[str], base_name: str) -> str:
        candidate = base_name
        suffix = 2
        while candidate in existing_names:
            candidate = f"{base_name}_{suffix}"
            suffix += 1
        existing_names.add(candidate)
        return candidate

    def _derive_named_range_name(self, base_name: str, sheet_name: str) -> str:
        clean_base = str(base_name or "").strip() or "RANGE"
        if re.search(r"template", clean_base, flags=re.IGNORECASE):
            return re.sub(r"template", sheet_name, clean_base, flags=re.IGNORECASE)
        return f"{clean_base}_{sheet_name.replace('-', '_')}"

    def _recreate_named_ranges_for_month(
        self,
        *,
        spreadsheet_id: str,
        metadata: dict[str, Any],
        template_sheet_id: int,
        new_sheet_id: int,
        new_sheet_name: str,
    ) -> None:
        named_ranges = metadata.get("namedRanges")
        if not isinstance(named_ranges, list) or not named_ranges:
            return

        existing_names: set[str] = set()
        for item in named_ranges:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    existing_names.add(name)

        requests: list[dict[str, Any]] = []
        for item in named_ranges:
            if not isinstance(item, dict):
                continue
            base_name = str(item.get("name") or "").strip()
            source_range = item.get("range") if isinstance(item.get("range"), dict) else {}
            if int(source_range.get("sheetId") or -1) != int(template_sheet_id):
                continue
            if not base_name:
                continue

            new_name = self._next_named_range_name(
                existing_names,
                self._derive_named_range_name(base_name, new_sheet_name),
            )
            new_range = {
                "sheetId": int(new_sheet_id),
            }
            for key in ("startRowIndex", "endRowIndex", "startColumnIndex", "endColumnIndex"):
                if key in source_range and source_range.get(key) is not None:
                    new_range[key] = int(source_range[key])
            requests.append(
                {
                    "addNamedRange": {
                        "namedRange": {
                            "name": new_name,
                            "range": new_range,
                        },
                    },
                },
            )

        if requests:
            self._batch_update(spreadsheet_id, requests)

    def ensureMonthlySheetExists(self, spreadsheet_id: str, work_date: date) -> str:
        sheet_name = f"{work_date.year:04d}-{work_date.month:02d}"
        metadata = self._get_metadata(spreadsheet_id)
        sheets = metadata.get("sheets") if isinstance(metadata.get("sheets"), list) else []
        title_to_id: dict[str, int] = {}
        for item in sheets:
            if not isinstance(item, dict):
                continue
            props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            title = str(props.get("title") or "").strip()
            sheet_id = props.get("sheetId")
            if title and sheet_id is not None:
                title_to_id[title] = int(sheet_id)

        if sheet_name in title_to_id:
            return sheet_name

        template_sheet_id = title_to_id.get("TEMPLATE")
        new_sheet_id: int | None = None
        if template_sheet_id is not None:
            result = self._batch_update(
                spreadsheet_id,
                [
                    {
                        "duplicateSheet": {
                            "sourceSheetId": int(template_sheet_id),
                            "newSheetName": sheet_name,
                        },
                    },
                ],
            )
            replies = result.get("replies") if isinstance(result.get("replies"), list) else []
            if replies and isinstance(replies[0], dict):
                duplicate = replies[0].get("duplicateSheet") if isinstance(replies[0].get("duplicateSheet"), dict) else {}
                props = duplicate.get("properties") if isinstance(duplicate.get("properties"), dict) else {}
                if props.get("sheetId") is not None:
                    new_sheet_id = int(props["sheetId"])
        else:
            result = self._batch_update(
                spreadsheet_id,
                [
                    {
                        "addSheet": {
                            "properties": {
                                "title": sheet_name,
                            },
                        },
                    },
                ],
            )
            replies = result.get("replies") if isinstance(result.get("replies"), list) else []
            if replies and isinstance(replies[0], dict):
                added = replies[0].get("addSheet") if isinstance(replies[0].get("addSheet"), dict) else {}
                props = added.get("properties") if isinstance(added.get("properties"), dict) else {}
                if props.get("sheetId") is not None:
                    new_sheet_id = int(props["sheetId"])

        if new_sheet_id is None:
            refreshed = self._get_metadata(spreadsheet_id)
            refreshed_sheets = refreshed.get("sheets") if isinstance(refreshed.get("sheets"), list) else []
            for item in refreshed_sheets:
                props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                if str(props.get("title") or "").strip() == sheet_name and props.get("sheetId") is not None:
                    new_sheet_id = int(props["sheetId"])
                    break
            if new_sheet_id is None:
                raise RuntimeError(f"monthly sheet '{sheet_name}' was not created")

        if template_sheet_id is not None:
            self._recreate_named_ranges_for_month(
                spreadsheet_id=spreadsheet_id,
                metadata=metadata,
                template_sheet_id=template_sheet_id,
                new_sheet_id=new_sheet_id,
                new_sheet_name=sheet_name,
            )
        return sheet_name


class SheetsSyncOrchestrator:
    def __init__(self, *, default_webhook_url: str = ""):
        self.default_webhook_url = str(default_webhook_url or "").strip()
        self.monthly_tab_manager = GoogleSheetsMonthlyTabManager(
            service_account_json=settings.google_sheets_service_account_json,
        )

    def _profile_scope(self, profile: dict[str, Any]) -> str:
        options = profile.get("options_json") if isinstance(profile.get("options_json"), dict) else {}
        raw = str(options.get("profile_scope") or "").strip().upper()
        if raw == "APPLE_DAYTIME_P1":
            return "APPLE_DAYTIME"
        return raw

    def _is_apple_scope_profile(self, profile: dict[str, Any]) -> bool:
        return self._profile_scope(profile) in APPLE_PROFILE_SCOPES

    def _collect_target_months(
        self,
        *,
        period: dict[str, str],
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[date]:
        months: set[date] = set()
        for section_rows in rows.values():
            if not isinstance(section_rows, list):
                continue
            for row in section_rows:
                if not isinstance(row, dict):
                    continue
                for key in ("work_date", "schedule_date", "date", "request_date", "start_date", "end_date"):
                    parsed = _parse_date_like(row.get(key))
                    if parsed:
                        months.add(_month_start(parsed))
        if months:
            return sorted(months)

        start_date = _parse_date_like(period.get("start_date"))
        end_date = _parse_date_like(period.get("end_date"))
        if start_date and end_date:
            return _iter_months_inclusive(start_date, end_date)
        if start_date:
            return [_month_start(start_date)]
        if end_date:
            return [_month_start(end_date)]
        return [_month_start(datetime.now(timezone.utc).date())]

    def _ensure_monthly_tabs(
        self,
        *,
        profile: dict[str, Any],
        period: dict[str, str],
        rows: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {"ensured": [], "failed": []}
        if not self._is_apple_scope_profile(profile):
            return result
        spreadsheet_id = str(profile.get("spreadsheet_id") or "").strip()
        if not spreadsheet_id:
            logger.warning("apple profile has no spreadsheet_id; monthly sheet ensure skipped")
            return result

        months = self._collect_target_months(period=period, rows=rows)
        for month_date in months:
            try:
                ensured_name = self.monthly_tab_manager.ensureMonthlySheetExists(spreadsheet_id, month_date)
                result["ensured"].append(ensured_name)
            except Exception as exc:
                sheet_name = f"{month_date.year:04d}-{month_date.month:02d}"
                result["failed"].append(sheet_name)
                logger.warning(
                    "monthly sheet ensure failed (spreadsheet=%s, sheet=%s): %s",
                    spreadsheet_id,
                    sheet_name,
                    exc,
                )
        return result

    def _post_webhook(self, url: str, payload_json: bytes) -> dict[str, Any]:
        request = Request(
            url=url,
            data=payload_json,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "rg-arls-dev/1.0",
            },
        )
        with urlopen(request, timeout=15) as response:
            status_code = int(getattr(response, "status", 200))
            excerpt = response.read(3000).decode("utf-8", errors="ignore")
            return {"status_code": status_code, "body_excerpt": excerpt}

    def dispatch(
        self,
        *,
        profile: dict[str, Any],
        tenant_code: str,
        period: dict[str, str],
        generated_at: str,
        rows: dict[str, list[dict[str, Any]]],
        payload_json_serializer,
    ) -> dict[str, Any]:
        ensure_result = self._ensure_monthly_tabs(profile=profile, period=period, rows=rows)
        adapter = SheetsAdapter(profile)
        payload = adapter.build_payload(
            tenant_code=tenant_code,
            period=period,
            generated_at=generated_at,
            rows=rows,
        )
        if self._is_apple_scope_profile(profile):
            payload["monthly_sheet"] = ensure_result
        webhook_url = str(profile.get("webhook_url") or "").strip() or self.default_webhook_url
        if not webhook_url:
            return {
                "ok": False,
                "sent": False,
                "sync_message": "webhook_url is not configured",
                "payload": payload,
            }

        body = payload_json_serializer(payload).encode("utf-8")
        try:
            result = self._post_webhook(webhook_url, body)
            warning_suffix = ""
            if ensure_result.get("failed"):
                warning_suffix = f" (monthly tab ensure failed: {', '.join(ensure_result['failed'])})"
            return {
                "ok": True,
                "sent": True,
                "sync_message": f"webhook delivered ({result.get('status_code', 200)}){warning_suffix}",
                "payload": payload,
            }
        except HTTPError as exc:
            response_body = exc.read(3000).decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
            return {
                "ok": False,
                "sent": False,
                "sync_message": f"webhook http error {exc.code}: {response_body}",
                "payload": payload,
            }
        except URLError as exc:
            return {
                "ok": False,
                "sent": False,
                "sync_message": f"webhook url error: {exc.reason}",
                "payload": payload,
            }
        except Exception as exc:  # pragma: no cover - safety net
            return {
                "ok": False,
                "sent": False,
                "sync_message": str(exc),
                "payload": payload,
            }
