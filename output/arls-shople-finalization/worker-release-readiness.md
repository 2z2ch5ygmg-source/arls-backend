# Worker 4 — Non-destructive actions and release readiness

## Verdict

PASS with scoped caveats. Live non-destructive click-throughs passed for employee detail, site detail, notices compose-open, calendar new-event modal-open, and Finance tab switch. Notice detail click-through was not executed because the live notices list exposed zero detail rows in the tested context. No source files were modified by this worker.

## Live click-through evidence

- Capture JSON: `output/arls-shople-finalization/worker4-live-nondestructive/capture.json`
- Generated at: `2026-04-12T13:01:53.801Z`
- Viewport: `1366x900`
- Browser errors: consoleErrors=0, failedRequests=0, httpApiErrors=0

| Check | Result | Screenshot |
| --- | --- | --- |
| `employee-row-detail` | 85 rows; clicked=True; panelVisible=True; overflowX=False; sample=현재 상태출퇴근 예외0연차 잔여15요청 대기0기본 정보직원번호R0022-220소속 지점Codex_증명서_다종_0022 (R0022)연락처01003280023입사일 | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/employee-row-detail.png` |
| `site-row-detail` | 50 rows; clicked=True; panelVisible=True; overflowX=False; sample=SRS Korea Codex_증명서_다종_0022 운영중1명준비 완료 ✕ 현장 개요운영 상태활성출퇴근 기준준비 완료직원 수1명반경120mWi-Fi미등록회사SRS  | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/site-row-detail.png` |
| `notice-detail-row` | 0 rows; clicked=False; skipped because no notice detail rows existed; overflowX=False | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/notice-detail-row.png` |
| `notice-compose-open` | 2 open buttons; clicked=True; composeVisible=True; hash=#/feature/notices?mode=new; overflowX=False | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/notice-compose-open.png` |
| `calendar-new-event-modal-open` | 2 buttons; clicked=True; sheetOpen=True; sheetTitle=새 일정; overflowX=False | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/calendar-new-event-modal-open.png` |
| `finance-download-tab-switch` | 1 tab; clicked=True; hash=#/reports/finance-download; labels=제출, 다운로드; overflowX=False | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/worker4-live-nondestructive/finance-download-tab-switch.png` |

## Release readiness

- Git working tree was clean before this report artifact was added; branch is ahead of `backend-origin/main` and should be pushed only by the leader after final integration review.
- Latest tracked integration commit observed: `36fa37e Accept SOC site names from integration hints` (backend dirty lane now committed by another lane).
- Live backend health returned `{'status':'ok'}` and live frontend HEAD returned `HTTP/1.1 200 OK`.
- Push/PR can proceed from this worker's scope after the leader accepts residual caveats below and includes/omits output artifacts intentionally. I did not push.

### Git evidence

```text
## main...backend-origin/main [ahead 10]

36fa37e (HEAD -> main) Accept SOC site names from integration hints
6ca2a6d Give Calendar a selected-day interpretation rail
a50fac4 Let Finance tabs read as local modes

app/routers/v1/integrations.py                     |  68 ++-
 frontend/css/styles.css                            | 532 +++++++++++++++++++++
 frontend/index.html                                |  25 +-
 frontend/js/app.js                                 |  75 ++-
 .../worker-backend-dirty-lane.md                   | 122 +++++
 .../worker-calendar-reports-notices.md             | 134 ++++++
 .../worker-finance-schedule.md                     | 260 ++++++++++
 .../worker-leave-approval-docs.md                  | 153 ++++++
 .../worker-people-profile.md                       | 197 ++++++++
 tests/test_soc_site_context_resolution.py          | 135 ++++++
 10 files changed, 1679 insertions(+), 22 deletions(-)
```

## Verification commands

```text
PASS node --check output/arls-shople-finalization/worker4_nondestructive_qa.js -> exit 0
PASS INIT_SUPER_ADMIN_* env node output/arls-shople-finalization/worker4_nondestructive_qa.js -> checkCount=6, consoleErrors=0, failedRequests=0, httpApiErrors=0
PASS .venv/bin/python -m pytest -q tests/test_employee_drawer_summary_contract.py tests/test_notice_permissions.py tests/test_calendar_workspace_contract.py tests/test_schedule_finance_download_workspace.py -> 29 passed, 3 warnings in 0.64s
PASS curl -fsS https://rg-arls-backend.azurewebsites.net/health -> {"status":"ok"}
PASS curl -fsSI https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net -> HTTP/1.1 200 OK
```

## Remaining risks / blockers

- Notice detail row coverage is blocked by data absence in the tested live context (`count=0`). Compose-open was validated without publishing.
- Employee/site detail screens expose edit/delete controls to the tested privileged account; this worker did not click any mutating controls.
- Full repository pytest suite and mobile/dark coverage are outside this worker slice; rely on the other team lanes plus leader final verification before push.
- The generated Playwright evidence used the live MASTER/SRS_KOREA context only.

## Files written by worker-4

- `output/arls-shople-finalization/worker-release-readiness.md`
- `output/arls-shople-finalization/worker4-live-nondestructive/capture.json`
- `output/arls-shople-finalization/worker4-live-nondestructive/*.png`
- `output/arls-shople-finalization/worker4_nondestructive_qa.js` (ignored helper script, committed only if force-added by the leader/worker)
