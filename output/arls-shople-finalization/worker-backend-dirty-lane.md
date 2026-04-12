# Worker 1 Backend Dirty Lane Verification

## Verdict

PASS for the owned backend/test dirty lane. The dirty SOC site-context change is safe to commit with the noted repository-level full-suite blockers below.

## Scope reviewed

- `app/routers/v1/integrations.py`
  - Removed the direct import/use of `schedules._resolve_site_context_by_code` for SOC endpoints.
  - Added `_resolve_soc_site_context_by_hint` to resolve SOC site hints by exact code, id, case-insensitive code, or site name.
  - Preserves deterministic priority: exact `site_code` -> site id -> normalized `site_code` -> site name.
  - Rejects ambiguous site-name-only matches with HTTP 409.
  - Routes `/soc/backfill-employees` and `/soc/work-templates` through the new hint resolver.
  - Small owned-file lint/syntax fix: escaped the existing regex SQL literal in `_resolve_employee_by_site_full_name` from `\s+` source spelling that emitted a Python invalid-escape warning to `\\s+`; runtime SQL pattern remains `\s+`.
- `tests/test_soc_site_context_resolution.py`
  - Adds focused unit coverage for site-name hints, code-over-name precedence, and ambiguous name rejection.
- No frontend files touched.

## Commands run

### Focused SOC site resolver test

Command:

```bash
.venv/bin/python -m pytest tests/test_soc_site_context_resolution.py -q
```

Result: PASS

```text
3 passed, 3 warnings in 1.20s
```

### Focused owned lane + directly related SOC integration tests

Command:

```bash
.venv/bin/python -m pytest tests/test_soc_site_context_resolution.py tests/test_soc_employee_sync_scope_resolution.py tests/test_soc_support_assignment_bridge.py -q
```

Result: PASS

```text
32 passed, 3 warnings in 0.66s
```

### Full repository pytest suite

Command:

```bash
.venv/bin/python -m pytest tests -q
```

Result: FAIL, but failures are outside the owned backend dirty lane.

```text
9 failed, 376 passed, 14 warnings in 58.94s
```

Observed failures:

- `tests/test_auth_tenant_phone_flows.py::test_tc2_register_delete_reregister_same_tenant_login` — external SOC employee delete sync returned 502 / `SOC_EMPLOYEE_DELETE_SYNC_FAILED`.
- `tests/test_employee_active_user_repair.py::test_employee_list_repairs_missing_row_from_active_arls_user` — live DB schema mismatch: `sites.is_deleted` column missing, then cleanup transaction aborted.
- Four `tests/test_schedule_monthly_export_template.py` tests — hard-coded template path missing: `/Users/seoseong-won/Documents/rg-arls-dev/backend/app/templates/monthly_schedule_template.xlsx`.
- Three `tests/test_schedule_monthly_import_canonical.py` tests — expected-string / affected-site-day expectation mismatches in schedule canonical import behavior.

These failures do not exercise `_resolve_soc_site_context_by_hint`, `/soc/backfill-employees`, or `/soc/work-templates` directly.

### Diagnostics / typecheck

Command via OMX code-intel:

```text
npx tsc --noEmit --pretty false
```

Result: PASS

```text
lsp_diagnostics app/routers/v1/integrations.py: diagnosticCount=0
lsp_diagnostics tests/test_soc_site_context_resolution.py: diagnosticCount=0
lsp_diagnostics_directory /Users/mark/Desktop/rg-arls-dev: totalErrors=0, totalWarnings=0
```

### Python compile / lint-adjacent syntax check

Command:

```bash
PYTHONWARNINGS=error .venv/bin/python -m py_compile app/routers/v1/integrations.py tests/test_soc_site_context_resolution.py
```

Result: PASS, no output after the owned-file invalid escape fix.

### Diff whitespace check

Command:

```bash
git diff --check -- app/routers/v1/integrations.py tests/test_soc_site_context_resolution.py
```

Result: PASS, no output.

## Safe to commit?

Yes for this lane. The focused SOC/backend verification passes, diagnostics are clean, py_compile with warnings-as-errors passes, and the diff is isolated to the owned backend/test files plus this report. Full-suite failures remain repository/environment/other-feature blockers and should not block committing the verified SOC site hint lane, but they should be reported as release-readiness blockers outside this worker's owned scope.

## Blockers

No blocker for committing the owned backend dirty lane.

Repository-level blockers observed by full pytest:

1. External SOC delete sync 502 in phone-flow test.
2. Live DB schema mismatch for `sites.is_deleted` in employee active user repair test.
3. Missing hard-coded monthly schedule template path under `/Users/seoseong-won/...`.
4. Existing canonical import test expectation mismatches unrelated to SOC site hint resolution.
