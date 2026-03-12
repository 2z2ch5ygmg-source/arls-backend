ARLS Backend Restore - Step 3A

Files changed
- /Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py
- /Users/mark/Desktop/rg-arls-dev/app/schemas.py
- /Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py

What was restored
- ARLS now acts as the backend ingress for HQ-filled support roster workbooks.
- Inspect/review/apply no longer depend on an ARLS-side preloaded Sentrix ticket map.
- Preview and apply are driven by ARLS support-demand artifact scopes generated earlier from base upload.

Ingest path
- HQ workbook upload enters ARLS inspect flow.
- ARLS resolves sheet -> site by exact sheet name first.
- If sheet name fails, ARLS falls back to BC34 workbook text.
- ARLS parses dynamic worker rows and builds normalized worker entries with provenance.
- ARLS produces aggregated scope review rows and persists preview batch lineage for retry/apply.

Inspect/review/apply flow
- Inspect:
  - validates workbook metadata/family/month
  - resolves selected sites
  - excludes stale/unselected/unresolved sheets without silently applying them
  - binds each scope to canonical requested_count from ARLS artifact scope
  - returns aggregated review rows per site/date/shift
- Apply:
  - uses persisted scope_summary rows from the preview batch
  - excludes stale scopes instead of forcing full failure
  - sends normalized support roster snapshot to Sentrix
  - returns success / partial success / failure based on actual handoff result

Stale handling implementation
- Stale is detected per site using source revision / source batch availability.
- Sites without current artifact source or with revision mismatch are excluded.
- Valid sites can continue; stale sites are reported separately.
- Apply result now includes processed_site_codes, excluded_site_codes, and stale_site_codes.

Site resolution logic
- Primary resolver: exact sheet name match
- Fallback resolver: workbook BC34 text
- If both fail:
  - site is marked blocking
  - sheet is excluded from apply
  - no silent remap occurs

What was intentionally not changed
- Sentrix support ticket truth still lives in Sentrix.
- ARLS still does not finalize approval/pending logic locally.
- ARLS still does not materialize support-origin rows into schedule truth here.
- No frontend wizard/layout work was changed in this step.
