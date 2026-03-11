# ARLS Monthly Upload Analysis Patch - Phase 2 Fix Pass

## Files changed
- `app/routers/v1/schedules.py`
- `app/schemas.py`
- `tests/test_schedule_monthly_import_canonical.py`

## Exact parser bugs fixed
- Base schedule placeholder employee groups with employee name cell `0`, `"0"`, blank, or whitespace are now treated as empty slots and skipped.
- Night support block label detection now accepts `야간 추가 근무자` variants in addition to existing support-label aliases.
- Summary/support section detection now normalizes newline and spacing before matching.
- Support required-count parsing now extracts the first integer from mixed text such as `섭외 2인 요청`.
- Blank support required-count cells are no longer always treated as blocking.
- Missing tenant import mapping profiles no longer silently fall back to guessed templates.
- Empty unchanged workbook cells are no longer fully normalized, resolved, and persisted row-by-row.

## Placeholder `0` row handling
- `_is_placeholder_employee_name(...)` now classifies the following as empty employee slots:
  - `None`
  - `""`
  - whitespace-only text
  - numeric `0`
  - string `"0"`
  - existing legacy placeholder `"-"`
- Placeholder row groups are skipped before employee matching and do not emit false `EMPLOYEE_MATCH_FAILED` issues.

## Newline / space label normalization
- Label matching now uses whitespace-collapsed matching helpers.
- Internal newlines are converted to single spaces before semantic matching.
- Equality-style checks were patched to use normalized alias matching instead of brittle raw-string equality.
- This covers real variants such as:
  - `주간\n추가 근무자`
  - `야간\n추가 근무자`
  - `외부인원 \n투입 수`
  - `작업 목적`
  - `작업 내용`

## Required-count blank vs no-demand classification
- Support required-count parsing now uses a dedicated parser.
- If the required-count cell is blank and the support block has no meaningful payload:
  - classification becomes `no_demand`
  - `required_count_numeric` becomes `0`
  - no blocking issue is emitted
- If the required-count cell is blank but worker/vendor/purpose data indicates a real demand context:
  - classification becomes `invalid_blank`
  - blocking issue `SUPPORT_BLOCK_REQUIRED_COUNT_INVALID` is emitted
- Mixed text like `섭외 3인 요청` is parsed to `3`.

## Mapping profile loading and mapping behavior
- Mapping profile and mapping lookup are still loaded once per analysis.
- Template rows are now pre-indexed by `template_id` in memory.
- When `mapping_lookup` is supplied, empty lookups no longer trigger guessed-template fallback.
- Entirely missing mapping profiles now surface:
  - one strong workspace-level blocking issue
  - row-level blocking results for impacted numeric rows
  - without additional template-guessing behavior
- Missing specific `(row_type, hours)` keys still emit row-level blocking failures.

## Analysis-state locking implementation
- Preview metadata now includes:
  - `analysis_run_id`
  - `analysis_context_key`
  - `analysis_file_sha256`
  - `analysis_locked_fields`
  - `stale_context_fields`
  - `analysis_stage`
  - `analysis_timings_ms`
- The deterministic context key is derived from tenant/site/month/current revision/file hash.
- This makes stale-result invalidation deterministic for the existing UI contract:
  - file change
  - site change
  - month change
  - mapping-profile/context change

## Performance changes
- Empty unchanged body/support rows are skipped early instead of fully resolving and persisting them.
- Employee matching is skipped for blank/no-op rows.
- Template lookup is now O(1) by template id instead of repeated list scans.
- Analysis timings are logged and returned in preview metadata.

## What was intentionally not changed
- Final ARLS write/apply workflow was not redesigned.
- Sentrix apply logic was not expanded or redesigned in this pass.
- HQ support roster parsing was not broadened.
- Existing Phase 1/2 workspace structure was preserved.
- No tracked frontend source existed in this workspace, so the lock/stale behavior was added at the backend preview metadata contract layer rather than a UI redesign.
