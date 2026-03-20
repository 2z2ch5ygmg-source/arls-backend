## ARLS Supervisor Schedule Runtime Gap Addendum (2026-03-20)

Authenticated `Supervisor` runtime was re-captured on `2026-03-20` to close the remaining non-destructive schedule workspace gaps. This addendum updates ARLS runtime evidence only. It does not reopen the frozen Sentrix Phase 2A or Phase 2B baselines.

### Finance workspace shell opening

- A direct hash route to `#/schedules/reports` was **not sufficient by itself** in the fresh captured session. The hash changed to `#/schedules/reports`, but the Finance workspace shell did not open and no Finance status request fired from that direct-route attempt.
- A visible menu click on `Finance용 스케쥴 제출` from the authenticated shell **did** open the Finance workspace shell:
  - final hash: `#/schedules/reports`
  - `#scheduleReportsPanel` visible
  - `#scheduleFinanceSubmissionPanel` visible
  - default Finance tab: download
  - no site selected yet, so buttons stayed disabled and no Finance status request fired in that specific capture
- A visible schedule-toolbar path also **did** open the Finance workspace shell:
  - starting point: calendar shell
  - action: `다운로드` button (`data-action="schedule-open-download-monthly-excel"`)
  - final hash: `#/schedules/reports`
  - Finance shell opened with `reportsSiteValue=R738`
  - immediate UI state was still `조회 중` in the retained snapshot
- A visible schedule tab click on `Finance용 스케쥴 제출` also **did** open the Finance workspace shell and reached the backend read/status path:
  - final hash: `#/schedules/reports`
  - Finance shell opened
  - request fired: `GET /api/v1/schedules/finance-submission/status?month=2026-03&site_code=R738&tenant_code=srs_korea` -> `200`
  - state pill: `1차 확인 대기`
  - status text: `R738 · 2026-03`

### Finance non-destructive action surface

- In the opened Finance download shell:
  - `1차 스케쥴 다운로드` button was visible
  - `2차 최종 스케쥴 다운로드` button was visible
- With no site selected yet, both download buttons were disabled.
- In the Finance shell reached through the visible `reports` tab path with `R738` selected:
  - `1차 스케쥴 다운로드` was visible and enabled
  - `2차 최종 스케쥴 다운로드` was visible but disabled
  - no blocked reasons were rendered in the captured state
- These controls were **not executed** in this pass:
  - `1차 스케쥴 다운로드` was not clicked because the backend path mutates submission state/history
  - `2차 최종 스케쥴 다운로드` was not clicked because this pass remained evidence-only and mutation-adjacent actions were intentionally avoided
- Direct backend Finance read/status remained reachable:
  - `GET /api/v1/schedules/finance-submission/status?month=2026-03&site_code=R738&tenant_code=srs_korea` -> `200`
  - response envelope returned `success=true` and Finance state/readiness fields including `state`, `review_download_ready`, `final_download_enabled`, `final_upload_stale`, and `blocked_reasons`

### Finance upload subtab

- A Finance upload-subtab probe was attempted from the Finance shell without executing preview/apply.
- The retained capture was **inconclusive**:
  - the click target for the `upload` subtab was present and returned `clickedUploadTab=true`
  - the post-click retained snapshot collapsed back to the profile shell with no Finance panel visible
  - only background/profile/schedule refresh requests were observed
- This capture is not strong enough to claim that the Finance upload subtab is either fully usable or fully blocked for Supervisor.

### Upload workspace / preview boundary

- Fresh `Supervisor` sessions currently hit a password-change gate before unrestricted schedule workspace use:
  - the authenticated shell displayed `초기 비밀번호 변경이 필요합니다.`
  - direct hash navigation to `#/schedules/upload` resolved back to `#/profile`
  - the visible `근무표 업로드·자동등록` shortcut from the same shell also remained on `#/profile`
- Even in that gated state, backend upload read-side initialization still occurred:
  - `GET /api/v1/schedules/import-mapping-profile?tenant_code=srs_korea` -> `200`
  - the retained shell state included populated upload context values such as `siteValue=R738`, `monthValue=2026-03`, and a non-empty `mappingProfileValue`
- Because the upload shell itself did not open in the fresh gated session, the following remain unproven in this pass:
  - upload file-stage shell opening
  - preview button usability in a fresh gated session
  - non-destructive upload preview execution
- This means the earlier retained statement “Supervisor upload shell opening is confirmed” is now too broad unless it is explicitly scoped to a non-gated runtime context.

### Scope statement

- This addendum is ARLS runtime correction evidence only.
- This addendum does not reopen the frozen Sentrix Phase 2A baseline.
- This addendum does not reopen the frozen Sentrix Phase 2B baseline.
- This addendum must not be read as full schedule workspace support or a universal ARLS permission matrix.
