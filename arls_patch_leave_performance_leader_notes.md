ARLS Schedule Upload + Schedule Detail Patch - Pass 1

Files changed
- /Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py
- /Users/mark/Desktop/rg-arls-dev/app/schemas.py
- /Users/mark/Desktop/rg-arls-dev/frontend/js/app.js
- /Users/mark/Desktop/rg-arls-dev/tests/test_schedule_monthly_import_canonical.py

What was wrong
- Imported `연차` rows were stored as non-working rows but the monthly schedule response/calendar/detail UI flattened them back to generic `휴무`.
- The schedule edit modal exposed the schedule-type control as `직무`, which was misleading because the values were schedule semantics, not employee duty.
- Leader candidate display flattened account roles into `GUARD`, so HQ Admin / Supervisor / Vice Supervisor were not distinguishable.
- Monthly upload preview persistence inserted preview rows one-by-one, which was a likely major contributor to slow 2-3 minute analysis on real workbooks.
- Upload analysis already had partial lock/stale infrastructure, but mapping/template actions were still left editable during analysis.

Patch summary
- Added stable schedule display semantics on the backend response path:
  - `schedule_display_type`
  - `schedule_display_label`
  - `schedule_display_time`
- Preserved annual leave semantics through existing truth:
  - `shift_type='off'`
  - `schedule_note='연차'` or `schedule_note='반차'`
- Applied the display semantics to:
  - `/schedules/monthly`
  - `/schedules/monthly-lite`
  - `/schedules/monthly-board-lite`
- Updated the schedule edit modal to use `근무유형` instead of `직무`.
- Added modal options for:
  - 주간근무
  - 초과근무
  - 야간근무
  - 휴무
  - 연차
  - 반차
  - 공휴일
- Modal save now sends explicit `schedule_note` for annual/half leave instead of flattening everything into generic off.
- Leader candidates now expose business-facing role labels instead of collapsing everything to GUARD.
- Preview batch persistence now inserts `schedule_import_rows` with `executemany` instead of per-row `execute`.
- Analysis lock UI now also disables blank-template and mapping-profile edit actions while analysis is active.

Annual leave handling
- Imported `연차` remains a non-working schedule row, but it is no longer displayed as generic `휴무`.
- Imported `반차` is also preserved as a separate display subtype.
- Generic `휴무` remains distinct from `연차`.
- `공휴일` remains distinct from both.

Leader role fix
- Leader selector display now uses canonical account-role meaning first.
- Display labels now distinguish:
  - HQ Admin
  - Supervisor
  - Vice Supervisor
  - GUARD
- Internal recommendation sorting now uses explicit role priority instead of GUARD/VICE-only flattening.

Performance patch
- The targeted bottleneck addressed in this pass is preview row persistence.
- The preview batch path now:
  - builds insert payloads once
  - batch inserts preview rows
  - avoids per-row sorted JSON serialization
- Existing timing instrumentation remains available in `analysis_timings_ms`, including:
  - workbook load
  - section parse
  - employee preload
  - template mapping preload
  - row normalization
  - preview build
  - preview persist

Analysis-state locking
- During active analysis, the workspace now disables:
  - file selector
  - site selector
  - month selector
  - latest-base download
  - blank-template download
  - mapping-profile edit action
- Stale analysis handling continues to rely on:
  - `analysis_run_id`
  - `analysis_context_key`
  - `analysis_locked_fields`
  - `stale_context_fields`

What was intentionally not changed
- No redesign of unrelated schedule tabs
- No mobile redesign
- No HQ support submission workflow move
- No broad database schema migration
- No change to imported non-working truth model beyond stable subtype/display handling through `schedule_note`
