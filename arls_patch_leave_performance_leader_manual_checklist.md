ARLS Schedule Upload + Schedule Detail Patch - Manual Checklist

Upload analysis
- Open `/schedules/upload` on desktop.
- Select site, month, and a real monthly workbook.
- Click `분석 시작`.
- Verify file/site/month controls become disabled immediately.
- Verify blank-template / latest-base / mapping-profile edit actions are disabled during analysis.
- Verify analysis completes without the previous frozen-feeling editable state.

Annual leave semantics
- Upload a workbook containing `연차`.
- Verify preview/apply produces a schedule row with non-working semantics preserved.
- After apply, open the monthly calendar.
- Verify the calendar card shows `연차`, not generic `휴무`.
- Open the date/detail sheet for that row.
- Verify the detail surface shows `연차`.
- Verify a plain `휴무` row still shows `휴무`.
- Verify a `공휴일` row still shows `공휴일`.
- If a `반차` row exists, verify it shows `반차`.

Schedule edit modal
- Open `근무일정 바꾸기` for a normal work row.
- Verify the field label is `근무유형`, not `직무`.
- Verify the selector includes:
  - 주간근무
  - 초과근무
  - 야간근무
  - 휴무
  - 연차
  - 반차
  - 공휴일
- Change a row to `연차` and save.
- Verify the row reloads as `연차`.
- Change the same row to `휴무` and save.
- Verify it reloads as generic `휴무`, not `연차`.
- Change the row to `공휴일` and verify it reloads as `공휴일`.

Leader selector
- Open `근무일정 바꾸기` on a date/site that has multiple role types on duty.
- Open the `리더` dropdown.
- Verify HQ Admin users display as `HQ Admin`.
- Verify Supervisor users display as `Supervisor`.
- Verify Vice Supervisor users display as `Vice Supervisor`.
- Verify only actual guard-level users display as `GUARD`.
- Verify candidates are no longer shown as all-GUARD.

Performance
- Use the same real workbook that previously took roughly 2-3 minutes.
- Start analysis and record elapsed time.
- Confirm the runtime is materially lower than before.
- Inspect backend preview metadata/logs and verify `analysis_timings_ms` includes:
  - workbook_load
  - section_parse
  - employee_match_preload
  - template_mapping_preload
  - row_normalization_pass
  - preview_build
  - preview_persist

Regression checks
- Verify generic calendar/list loading still works.
- Verify non-leave work rows still show correct time ranges.
- Verify overtime rows remain editable and displayable.
- Verify upload stale-state still requires re-analysis after changing file/site/month.
