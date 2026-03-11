from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, parse, request


def monday_of(value: date) -> date:
    return value - timedelta(days=value.weekday())


def recent_mondays(count: int, *, end_date: date | None = None) -> list[date]:
    anchor = monday_of(end_date or date.today())
    return [anchor - timedelta(days=7 * offset) for offset in range(count)]


def http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 120) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def login(base_url: str, *, tenant_code: str, username: str, password: str) -> str:
    body = http_json(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        payload={"tenant_code": tenant_code, "username": username, "password": password},
        timeout=120,
    )
    return body["data"]["access_token"]


def fetch_truth(base_url: str, token: str, *, apple_tenant_code: str, week_start: date, site_code: str | None = None) -> dict[str, Any]:
    params = {"tenant_code": apple_tenant_code, "week_start": week_start.isoformat()}
    if site_code:
        params["site_code"] = site_code
    url = f"{base_url}/api/v1/apple-weekly/truth/debug?{parse.urlencode(params)}"
    return http_json(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)


def _domain_state(rows: list[dict[str, Any]], field: str) -> str:
    sections = [row.get(field) for row in rows if isinstance(row.get(field), dict)]
    states = {(section or {}).get("section_state") for section in sections}
    states.discard(None)
    if "conflicted" in states:
        return "conflicted"
    if "supported_missing" in states:
        return "supported_missing"
    if sections and not any((section or {}).get("has_data") for section in sections):
        return "supported_zero"
    if states:
        return sorted(states)[0]
    return "unsupported_or_absent"


def summarize_contract(contract: dict[str, Any]) -> dict[str, Any]:
    employee_rows = contract.get("employee_day_rows", [])
    site_days = contract.get("site_day_summaries", [])
    scenario_coverage = {
        "leave": any((row.get("leave_summary") or {}).get("has_leave") for row in employee_rows),
        "late": any((row.get("late_tardy_summary") or {}).get("is_late") for row in employee_rows),
        "overtime": any((row.get("overtime_summary") or {}).get("has_overtime") for row in employee_rows),
        "overnight": any((row.get("overnight_summary") or {}).get("has_overnight") for row in employee_rows) or any((row.get("overnight_summary") or {}).get("has_overnight") for row in site_days),
        "support_assignment": any((row.get("support_assignment_summary") or {}).get("has_support_assignment") for row in employee_rows) or any((row.get("support_assignment_summary") or {}).get("has_support_assignment") for row in site_days),
        "event_additional": any((row.get("event_additional_note_summary") or {}).get("count") for row in site_days),
        "attendance_without_schedule": any("schedule_missing_for_attendance" in (row.get("missing_data_flags") or []) for row in employee_rows),
        "scheduled_without_attendance": any("attendance_missing_for_scheduled_shift" in (row.get("missing_data_flags") or []) for row in employee_rows),
    }
    discrepancy_codes: dict[str, int] = {}
    for row in employee_rows + site_days:
        for item in row.get("discrepancies", []):
            code = str(item.get("code") or "")
            if not code:
                continue
            discrepancy_codes[code] = discrepancy_codes.get(code, 0) + 1
    return {
        "contract_version": contract.get("contract_version"),
        "contract_state": contract.get("contract_state"),
        "service_state": contract.get("service_state"),
        "site_count": contract.get("scope", {}).get("site_count"),
        "site_codes": sorted({(row.get("site") or {}).get("site_code") for row in site_days if (row.get("site") or {}).get("site_code")}),
        "employee_day_rows": len(employee_rows),
        "site_day_summaries": len(site_days),
        "discrepancy_summary": contract.get("discrepancy_summary", {}),
        "top_discrepancy_codes": sorted(discrepancy_codes.items(), key=lambda item: (-item[1], item[0]))[:10],
        "domain_confidence": {
            "leave": _domain_state(employee_rows, "leave_summary"),
            "late": _domain_state(employee_rows, "late_tardy_summary"),
            "overtime": _domain_state(employee_rows, "overtime_summary"),
            "overnight": _domain_state(site_days, "overnight_summary"),
            "support_assignment": _domain_state(site_days, "support_assignment_summary"),
            "event_additional": _domain_state(site_days, "event_additional_note_summary"),
        },
        "rollout": contract.get("rollout", {}),
        "observability": contract.get("observability", {}),
        "scenario_coverage": scenario_coverage,
        "debug": contract.get("debug", {}),
    }


def to_markdown(base_url: str, weeks: list[tuple[date, str | None, dict[str, Any], dict[str, Any]]]) -> str:
    lines = [
        "# Phase 4 ARLS Replay Report",
        "",
        f"- Base URL: `{base_url}`",
        f"- Generated at: `{datetime.utcnow().isoformat()}Z`",
        f"- Replay count: `{len(weeks)}` weeks",
        "",
        "## Replay Weeks",
        "",
        "| Week Start | Contract State | Service State | Sites | Employee-Day Rows | Leave | Late | OT | Overnight | Support | Event/Additional |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for week_start, site_code, summary, _contract in weeks:
        coverage = summary["scenario_coverage"]
        lines.append(
            f"| {week_start.isoformat()}{f' [{site_code}]' if site_code else ''} | {summary['contract_state']} | {summary['service_state']} | {summary['site_count']} | {summary['employee_day_rows']} | "
            f"{'Y' if coverage['leave'] else '-'} | {'Y' if coverage['late'] else '-'} | {'Y' if coverage['overtime'] else '-'} | "
            f"{'Y' if coverage['overnight'] else '-'} | {'Y' if coverage['support_assignment'] else '-'} | {'Y' if coverage['event_additional'] else '-'} |"
        )
    lines.extend([
        "",
        "## Per-week Findings",
        "",
    ])
    for week_start, site_code, summary, contract in weeks:
        lines.extend([
            f"### {week_start.isoformat()}{f' [{site_code}]' if site_code else ''}",
            "",
            f"- Contract version: `{summary['contract_version']}`",
            f"- Contract state: `{summary['contract_state']}`",
            f"- Service state: `{summary['service_state']}`",
            f"- Site count: `{summary['site_count']}`",
            f"- Site codes: {', '.join(summary['site_codes']) or '(none)' }",
            f"- Employee-day rows: `{summary['employee_day_rows']}`",
            f"- Site-day summaries: `{summary['site_day_summaries']}`",
            f"- Discrepancies: `{json.dumps(summary['discrepancy_summary'], ensure_ascii=False)}`",
            f"- Domain confidence: `{json.dumps(summary['domain_confidence'], ensure_ascii=False)}`",
            f"- Rollout: `{json.dumps(summary['rollout'], ensure_ascii=False)}`",
            f"- Observability: `{json.dumps(summary['observability'], ensure_ascii=False)}`",
            f"- Source counts: `{json.dumps(summary.get('debug', {}).get('source_counts', {}), ensure_ascii=False)}`",
            "- Top discrepancy codes:",
        ])
        if summary["top_discrepancy_codes"]:
            for code, count in summary["top_discrepancy_codes"]:
                lines.append(f"  - `{code}` x `{count}`")
        else:
            lines.append("  - none")
        unresolved = sorted({item.get("code") for row in contract.get("site_day_summaries", []) for item in row.get("discrepancies", []) if item.get("severity") == "hard_error"})
        lines.append(f"- Unresolved hard errors: {', '.join(unresolved) if unresolved else 'none'}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://rg-arls-backend.azurewebsites.net")
    parser.add_argument("--login-tenant-code", default="MASTER")
    parser.add_argument("--apple-tenant-code", default="APPLE")
    parser.add_argument("--username", default="platform_admin")
    parser.add_argument("--password", default="Admin1234!!")
    parser.add_argument("--weeks", default="")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--site-codes", default="")
    parser.add_argument("--output", default="/Users/seoseong-won/Documents/phase3_arls_replay_report.md")
    args = parser.parse_args()

    if args.weeks.strip():
        week_starts = [monday_of(date.fromisoformat(item.strip())) for item in args.weeks.split(",") if item.strip()]
    else:
        week_starts = sorted(recent_mondays(args.count))

    site_codes = [item.strip().upper() for item in args.site_codes.split(",") if item.strip()]
    token = login(args.base_url, tenant_code=args.login_tenant_code, username=args.username, password=args.password)
    weeks: list[tuple[date, str | None, dict[str, Any], dict[str, Any]]] = []
    target_site_codes = site_codes or [None]
    for week_start in week_starts:
        for site_code in target_site_codes:
            contract = fetch_truth(args.base_url, token, apple_tenant_code=args.apple_tenant_code, week_start=week_start, site_code=site_code)
            summary = summarize_contract(contract)
            weeks.append((week_start, site_code, summary, contract))

    markdown = to_markdown(args.base_url, weeks)
    Path(args.output).write_text(markdown, encoding="utf-8")
    print(json.dumps({"output": args.output, "weeks": [week.isoformat() for week in week_starts], "site_codes": target_site_codes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
