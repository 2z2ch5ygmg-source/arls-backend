from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_bool_any(names: list[str], default: str = "false") -> bool:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    return str(default).strip().lower() in {"1", "true", "yes", "on"}


def _load_service_account_json() -> str:
    direct = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")).strip()
    if direct:
        return direct

    b64_value = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64", "").strip()
    if b64_value:
        try:
            decoded = base64.b64decode(b64_value).decode("utf-8")
            if decoded.strip():
                return decoded.strip()
        except Exception:
            pass

    file_path = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")).strip()
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


class Settings:
    app_name = os.getenv("APP_NAME", "RG ARLS")
    environment = os.getenv("ENVIRONMENT", "development")
    port = int(os.getenv("PORT", "8080"))
    jwt_secret = os.getenv("JWT_SECRET", "change-me")
    jwt_expires_minutes = int(os.getenv("JWT_EXPIRES_MINUTES", "480"))
    jwt_refresh_expires_minutes = int(os.getenv("JWT_REFRESH_EXPIRES_MINUTES", "43200"))
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    database_url = os.getenv("DATABASE_URL", "")
    cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
    cors_origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip()
    rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))
    idempotency_ttl_minutes = int(os.getenv("API_IDEMPOTENCY_TTL_MINUTES", "120"))
    init_admin_username = os.getenv("INIT_SUPER_ADMIN_USERNAME", "platform_admin")
    init_admin_password = os.getenv("INIT_SUPER_ADMIN_PASSWORD", "")
    init_admin_tenant_code = os.getenv("INIT_SUPER_ADMIN_TENANT_CODE", "MASTER")
    allow_branch_manager_user_manage = _env_bool("ALLOW_BRANCH_MANAGER_USER_MANAGE", "false")

    # SOC -> HR integration feature flags (canonical)
    soc_integration_enabled = _env_bool_any(["SOC_INTEGRATION_ENABLED", "SOC_INGEST_ENABLED"], "true")
    sheets_sync_enabled = _env_bool_any(["SHEETS_SYNC_ENABLED", "GOOGLE_SHEETS_SYNC_ENABLED"], "false")
    apple_report_overnight_enabled = _env_bool_any(["APPLE_REPORT_OVERNIGHT_ENABLED", "SOC_OVERNIGHT_ENABLED"], "true")
    apple_report_daytime_enabled = _env_bool("APPLE_REPORT_DAYTIME_ENABLED", "false")
    apple_report_ot_enabled = _env_bool("APPLE_REPORT_OT_ENABLED", "false")
    apple_report_total_late_enabled = _env_bool("APPLE_REPORT_TOTAL_LATE_ENABLED", "false")
    payroll_sheet_enabled = _env_bool("PAYROLL_SHEET_ENABLED", "true")

    # SOC -> HR integration operational flags (P0)
    soc_ingest_enabled = soc_integration_enabled
    soc_ingest_require_hmac = _env_bool("SOC_INGEST_REQUIRE_HMAC", "true")
    soc_ingest_hmac_secret = os.getenv("SOC_INGEST_HMAC_SECRET", os.getenv("HR_WEBHOOK_SECRET", "")).strip()
    soc_ingest_require_token = _env_bool("SOC_INGEST_REQUIRE_TOKEN", "false")
    soc_ingest_token = os.getenv("SOC_INGEST_TOKEN", "").strip()
    soc_leave_override_enabled = _env_bool("SOC_LEAVE_OVERRIDE_ENABLED", "true")
    soc_overnight_enabled = apple_report_overnight_enabled
    soc_overtime_enabled = _env_bool("SOC_OVERTIME_ENABLED", "true")
    soc_closing_ot_enabled = _env_bool("SOC_CLOSING_OT_ENABLED", "true")
    soc_base_url = os.getenv(
        "SOC_BASE_URL",
        "https://security-ops-center-prod-001-ftgcbkdwggf5hhh9.koreacentral-01.azurewebsites.net",
    ).strip().rstrip("/")
    _soc_employee_sync_url_raw = os.getenv("SOC_EMPLOYEE_SYNC_URL", "").strip()
    if _soc_employee_sync_url_raw:
        soc_employee_sync_url = _soc_employee_sync_url_raw
    else:
        soc_employee_sync_url = f"{soc_base_url}/api/integrations/hr/employee-sync"

    # Google Sheets profile-based sync (P0)
    google_sheets_sync_enabled = sheets_sync_enabled
    google_sheets_default_webhook = os.getenv("GOOGLE_SHEETS_DEFAULT_WEBHOOK", "").strip()
    google_sheets_ingest_token = os.getenv("GOOGLE_SHEETS_INGEST_TOKEN", "").strip()
    google_sheets_service_account_json = _load_service_account_json()
    google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()


settings = Settings()
