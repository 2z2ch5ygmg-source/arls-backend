# ARLS Backend Restore - Step 4A

## Files changed
- /Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py
- /Users/mark/Desktop/rg-arls-dev/tests/test_arls_support_origin_materialization.py
- /Users/mark/Desktop/rg-arls-dev/arls_backend_step4a_notes.md
- /Users/mark/Desktop/rg-arls-dev/arls_backend_step4a_manual_checklist.md
- /Users/mark/Desktop/rg-arls-dev/arls_support_origin_truth_contract.md
- /Users/mark/Desktop/rg-arls-dev/arls_support_origin_read_path_contract.md

## Inbound consumer path
- Sentrix-origin support actions continue to enter ARLS through the existing bridge action queue in `/api/v1/schedules/support-roundtrip/arls-bridge/process`.
- Step 4A hardens the existing consumer instead of introducing a second materialization path.
- The bridge consumer now rejects incomplete or ambiguous payloads earlier:
  - wrong source
  - missing ticket/site/employee/display name
  - invalid shift kind
  - non-self-staff payloads
  - UPSERT on non-approved ticket state

## Truth write path
- Canonical truth write path remains `monthly_schedules` plus `sentrix_support_schedule_materializations`.
- UPSERT:
  - resolves canonical site
  - resolves same-site active employee
  - updates same-ticket Sentrix-origin row in place if it already owns the slot
  - creates a new Sentrix-origin row only when no equivalent slot exists
  - links to an existing base/manual row instead of duplicating a visible same-shift row
- RETRACT:
  - retracts owned Sentrix-origin rows
  - preserves linked base/manual rows
  - records the retracted materialization state

## Read path corrections
- `monthly-lite`
- `monthly-board-lite`
- `_fetch_schedule_context`
- `_read_monthly_board_rows_for_export`

These now carry support-origin lineage fields so calendar/detail/export all read the same active truth with consistent source metadata:
- `source_ticket_id`
- `source_ticket_uuid`
- `source_ticket_state`
- `source_action`
- `source_self_staff`

## Coexistence logic
- Same employee/date/shift and same Sentrix ticket lineage => update, never duplicate.
- Same employee/date/shift and existing base/manual row => link materialization to the existing row, do not create a second visible row.
- Different Sentrix lineage already owning the same slot => block with explicit error.
- Day/night coexistence remains supported because materialization identity includes shift kind.

## What was intentionally not changed
- No frontend changes
- No Sentrix changes
- No workbook parsing changes
- No support ticket/status truth moved into ARLS
- No legacy SOC integration rewrite in this step
