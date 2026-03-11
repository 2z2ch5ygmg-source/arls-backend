from __future__ import annotations

import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_APP = ROOT.parent / "frontend" / "js" / "app.js"
ATTENDANCE_API = ROOT / "app" / "routers" / "v1" / "attendance.py"
SITES_API = ROOT / "app" / "routers" / "v1" / "sites.py"
EMPLOYEES_API = ROOT / "app" / "routers" / "v1" / "employees.py"
COMPANIES_API = ROOT / "app" / "routers" / "v1" / "companies.py"
SCHEDULES_API = ROOT / "app" / "routers" / "v1" / "schedules.py"


def _check(label: str, patterns: list[tuple[Path, str]]) -> dict:
    started = time.perf_counter()
    missing: list[str] = []
    for file_path, pattern in patterns:
        content = file_path.read_text(encoding="utf-8")
        if pattern not in content:
            missing.append(f"{file_path.name}:{pattern}")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "path": label,
        "ok": len(missing) == 0,
        "elapsed_ms": elapsed_ms,
        "missing": missing,
    }


def main() -> None:
    results = [
        _check(
            "/sites",
            [
                (SITES_API, '@router.get("", response_model=list[SiteOut])'),
                (SITES_API, "limit: int = Query(default=200"),
                (SITES_API, "OFFSET %s"),
            ],
        ),
        _check(
            "/attendance/today/status",
            [
                (ATTENDANCE_API, '@router.get("/today/status", response_model=AttendanceTodayStatusOut)'),
                (ATTENDANCE_API, "def get_today_status"),
            ],
        ),
        _check(
            "/attendance/records(today)",
            [
                (ATTENDANCE_API, '@router.get("/records")'),
                (ATTENDANCE_API, "AND ar.event_at >= %s"),
                (ATTENDANCE_API, "AND ar.event_at < %s"),
            ],
        ),
        _check(
            "/attendance/weekly-summary",
            [
                (ATTENDANCE_API, '@router.get("/weekly-summary")'),
                (ATTENDANCE_API, "def get_weekly_summary"),
            ],
        ),
        _check(
            "/schedules/monthly (ops summary input)",
            [
                (SCHEDULES_API, '@router.get("/monthly")'),
                (FRONTEND_APP, "loadOpsSummary"),
                (FRONTEND_APP, "loadMonthlyScheduleRowsWithCache"),
            ],
        ),
        _check(
            "/companies",
            [
                (COMPANIES_API, '@router.get("", response_model=list[CompanyOut])'),
                (FRONTEND_APP, "loadCompanies("),
            ],
        ),
        _check(
            "/employees",
            [
                (EMPLOYEES_API, '@router.get("", response_model=list[EmployeeOut])'),
                (EMPLOYEES_API, "limit: int = Query(default=200"),
                (EMPLOYEES_API, "OFFSET %s"),
                (FRONTEND_APP, "fetchPagedApiRows(employeesPath"),
            ],
        ),
        _check(
            "/employee-entry (register/edit dependencies)",
            [
                (FRONTEND_APP, "syncEmployeeFormSitesForTenant"),
                (FRONTEND_APP, "fetchPagedApiRows('/sites'"),
                (FRONTEND_APP, "loadEmployees({ preferCache: true"),
            ],
        ),
    ]

    attendance_sql = ATTENDANCE_API.read_text(encoding="utf-8")
    utc_range_ok = ("AND ar.event_at >= %s" in attendance_sql) and ("AND ar.event_at < %s" in attendance_sql)
    old_tz_date_filter = "AT TIME ZONE 'Asia/Seoul')::date = %s::date" in attendance_sql

    print(
        json.dumps(
            {
                "results": results,
                "attendance_records_utc_range": utc_range_ok,
                "attendance_records_old_tz_date_filter": old_tz_date_filter,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
