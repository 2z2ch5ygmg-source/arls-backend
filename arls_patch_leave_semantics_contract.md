ARLS Leave / Detail Modal / Analysis Lock Contract

Schedule truth and subtype rule
- Base storage remains compatible with existing monthly schedules:
  - working rows use `shift_type` as before
  - non-working rows still use `shift_type in ('off', 'holiday')`
- Stable subtype/display meaning is derived from:
  - `shift_type`
  - `schedule_note`
  - `source` when relevant
- Required distinctions:
  - `off` + empty note => generic `휴무`
  - `off` + `연차`/leave-like note => `연차`
  - `off` + `반차`/half-like note => `반차`
  - `holiday` => `공휴일`

Backend response rule
- Monthly schedule read paths expose:
  - `schedule_display_type`
  - `schedule_display_label`
  - `schedule_display_time`
- Expected display types:
  - `day`
  - `overtime`
  - `night`
  - `off`
  - `holiday`
  - `annual_leave`
  - `half_leave`

Calendar display rule
- Imported `연차` must render as `연차`.
- Imported `반차` must render as `반차`.
- Generic off must render as `휴무`.
- Holiday must render as `공휴일`.
- Non-working semantics must not collapse into one generic off label.

Detail modal display rule
- The schedule edit/detail modal uses `근무유형` semantics, not employee-duty semantics.
- The schedule-type selector must present meaningful schedule states, including annual leave.
- Saving `연차` must persist a non-working row with annual-leave meaning intact.
- Saving back to generic `휴무` must clear annual-leave meaning.

Leader role label rule
- Leader candidate display must use business role meaning, not a GUARD fallback.
- Required visible labels:
  - `HQ Admin`
  - `Supervisor`
  - `Vice Supervisor`
  - `GUARD`
- Recommendation priority uses explicit role priority instead of GUARD/VICE-only flattening.

Analysis-state lock rule
- While upload analysis is active, the following controls are locked:
  - file selector
  - site selector
  - month selector
  - template/mapping related mutating actions in the same workspace
- Analysis result is tied to:
  - `analysis_run_id`
  - `analysis_context_key`
- If file/site/month changes after analysis, the result becomes stale and must not be applied without re-analysis.
