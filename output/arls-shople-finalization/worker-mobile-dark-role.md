# Worker 3 — Mobile dark role QA matrix

Latest live capture: `2026-04-12T13:07:23.146Z`
Local current-tree capture: `2026-04-12T13:06:56.168Z`

## Scope

- Read-only Playwright QA on ARLS Shople finalization surfaces.
- Latest live frontend: `https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net`
- Local current-tree frontend: `http://127.0.0.1:4174/?api=https://rg-arls-backend.azurewebsites.net`
- API: `https://rg-arls-backend.azurewebsites.net/api/v1`
- Viewport: `390x844` mobile, `isMobile=true`, `hasTouch=true`
- Theme: `dark` via `localStorage.rg-arls-ui-theme=dark` (`data-ui-theme=dark` verified on each route).
- Roles covered: `hq_admin_srs` (`srs_korea` / hq_admin) and `developer_master_scoped_srs` (MASTER developer scoped to SRS_KOREA).
- No create/save/delete/upload/submit actions were clicked; this was route navigation + screenshot/DOM inspection only.

## Commands run

```bash
command -v npx && node --version && npm --version
node -e "import('playwright').then(()=>console.log('playwright import ok'))"
node output/arls-shople-finalization/mobile_dark_role_probe.js
python3 -m http.server 4174 --directory frontend  # background server for local current-tree verification
FRONTEND_URL='http://127.0.0.1:4174/?api=https://rg-arls-backend.azurewebsites.net' OUT_DIR='output/arls-shople-finalization/mobile-dark-role-local-current' node output/arls-shople-finalization/mobile_dark_role_probe.js
node --check output/arls-shople-finalization/mobile_dark_role_probe.js
git diff --check -- output/arls-shople-finalization
```

## Artifacts

- Latest live raw JSON: `output/arls-shople-finalization/mobile-dark-role/capture.json`
- Local current-tree raw JSON: `output/arls-shople-finalization/mobile-dark-role-local-current/capture.json`
- Capture script: `output/arls-shople-finalization/mobile_dark_role_probe.js`
- Latest live screenshots: `output/arls-shople-finalization/mobile-dark-role/`
- Local current-tree screenshots: `output/arls-shople-finalization/mobile-dark-role-local-current/`

Key latest-live screenshots:

- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-calendar-month-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-profile-theme-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-notices-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-employees-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-sites-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-reports-finance-submit-390x844-dark.png`
- `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-reports-finance-download-390x844-dark.png`

## Matrix summary

### Latest live

| Role | Login role/tenant | Routes | Page errors | API >=400 | Console errors | Failed requests | Page overflow routes | Internal wide routes |
|---|---|---:|---:|---:|---:|---:|---|---|
| `hq_admin_srs` | `hq_admin` / `srs_korea` | 10 | 0 | 0 | 1 | 2 | `none` | `none` |
| `developer_master_scoped_srs` | `developer` / `master` | 10 | 0 | 0 | 1 | 2 | `none` | `none` |

### Local current tree

| Role | Routes | Page errors | API >=400 | Console errors | Failed requests | Page overflow routes | Internal wide routes |
|---|---:|---:|---:|---:|---:|---|---|
| `hq_admin_srs` | 10 | 0 | 0 | 1 | 2 | `none` | `none` |
| `developer_master_scoped_srs` | 10 | 0 | 0 | 1 | 2 | `none` | `none` |

## Per-route latest-live details

### `hq_admin_srs`

| Surface | Hash | View/title | Dark | Page overflow | Internal wide nodes | Screenshot | Notes |
|---|---|---|---:|---:|---:|---|---|
| calendar-month | `#/calendar/month` | `calendar` / `캘린더` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-calendar-month-390x844-dark.png` | selected-day rail count 1 |
| profile-settings | `#/profile` | `profile` / `설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-profile-settings-390x844-dark.png` | - |
| profile-theme | `#/profile?segment=theme` | `profile` / `설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-profile-theme-390x844-dark.png` | active segment `모드 변경` |
| leave-history | `#/leave?tab=history` | `leave` / `휴가 사용 이력` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-leave-history-390x844-dark.png` | 휴가 사용 이력 |
| leave-settings | `#/leave?tab=settings` | `leave` / `휴가 설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-leave-settings-390x844-dark.png` | 휴가 설정 |
| notices | `#/feature/notices` | `notices` / `공지사항` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-notices-390x844-dark.png` | notice rows observed 32 |
| employees | `#/branch/employees` | `employees` / `직원 관리` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-employees-390x844-dark.png` | - |
| sites | `#/branch/sites` | `org` / `지점 관리` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-sites-390x844-dark.png` | - |
| reports-finance-submit | `#/reports?tab=finance` | `reports` / `Finance` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-reports-finance-submit-390x844-dark.png` | finance rows observed 51 |
| reports-finance-download | `#/reports/finance-download` | `reports` / `Finance` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-reports-finance-download-390x844-dark.png` | finance rows observed 100 |

### `developer_master_scoped_srs`

| Surface | Hash | View/title | Dark | Page overflow | Internal wide nodes | Screenshot | Notes |
|---|---|---|---:|---:|---:|---|---|
| calendar-month | `#/calendar/month` | `calendar` / `캘린더` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-calendar-month-390x844-dark.png` | selected-day rail count 1 |
| profile-settings | `#/profile` | `profile` / `설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-profile-settings-390x844-dark.png` | - |
| profile-theme | `#/profile?segment=theme` | `profile` / `설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-profile-theme-390x844-dark.png` | active segment `모드 변경` |
| leave-history | `#/leave?tab=history` | `leave` / `휴가 사용 이력` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-leave-history-390x844-dark.png` | 휴가 사용 이력 |
| leave-settings | `#/leave?tab=settings` | `leave` / `휴가 설정` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-leave-settings-390x844-dark.png` | 휴가 설정 |
| notices | `#/feature/notices` | `notices` / `공지사항` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-notices-390x844-dark.png` | notice rows observed 32 |
| employees | `#/branch/employees` | `employees` / `직원 관리` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-employees-390x844-dark.png` | - |
| sites | `#/branch/sites` | `org` / `지점 관리` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-sites-390x844-dark.png` | - |
| reports-finance-submit | `#/reports?tab=finance` | `reports` / `Finance` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-reports-finance-submit-390x844-dark.png` | finance rows observed 51 |
| reports-finance-download | `#/reports/finance-download` | `reports` / `Finance` | `dark` | `False` | `0` | `/Users/mark/Desktop/rg-arls-dev/output/arls-shople-finalization/mobile-dark-role/developer_master_scoped_srs-reports-finance-download-390x844-dark.png` | finance rows observed 100 |

## Findings

### PASS

- Latest live and local current-tree runs both completed 20 role × route captures with expected views and dark theme applied.
- No page-level horizontal overflow was detected in either run on calendar, profile, leave history/settings, notices, employees, sites, Finance submit, or Finance download for both tested roles.
- No internal wide Finance routes remain in the latest live or local current-tree captures.
- No `pageerror` events and no API HTTP >=400 responses were recorded.
- Calendar month mobile dark rendered the selected-day rail; profile theme rendered `모드 변경`; leave history/settings, notices, employees, sites, and Finance rendered under the mobile bottom navigation without global overflow.

### WARN / recommended blockers

- `hq_admin_srs` calendar console warning: `Error: 요청 실패: API_BASE=https://rg-arls-backend.azurewebsites.net/api/v1, path=/calendar/workspace?view=month&date=2026-04-12, origin=https://rgarlsfront50018.z12.web.core.windows.net. 백엔드가 실행 중인지 확인하세요. (Failed to fetch) 브라우저 네트워크/CORS 또는 DNS 제한일 가능성이 있습니다.`
- `developer_master_scoped_srs` calendar console warning: `Error: 요청 실패: API_BASE=https://rg-arls-backend.azurewebsites.net/api/v1, path=/calendar/workspace?view=month&date=2026-04-12&tenant_code=SRS_KOREA, origin=https://rgarlsfront50018.z12.web.core.windows.net. 백엔드가 실행 중인지 확인하세요. (Failed to fetch) 브라우저 네트워크/CORS 또는 DNS 제한일 가능성이 있습니다.`
- Calendar still records `Failed to fetch` / `net::ERR_ABORTED` for `/api/v1/calendar/workspace?view=month&date=2026-04-12` in both latest live and local current-tree runs. The calendar UI still renders and there are no HTTP >=400 responses, so this may be navigation/abort noise, but it should be re-run or investigated if console cleanliness is a release gate.
- Finance download dark visual polish remains imperfect: the latest-live screenshot `output/arls-shople-finalization/mobile-dark-role/hq_admin_srs-reports-finance-download-390x844-dark.png` shows the Finance download workspace/table as light card content within the dark app shell. This is no longer an overflow blocker, but it is still a dark-mode parity decision.

## Verification

- Playwright smoke: `node output/arls-shople-finalization/mobile_dark_role_probe.js` → PASS (latest live: 20 routes, 0 route errors, 0 page errors, 0 API >=400, 0 page/internal overflow routes; 1 calendar console/abort warning per role).
- Local current tree smoke: `FRONTEND_URL=... OUT_DIR=... node output/arls-shople-finalization/mobile_dark_role_probe.js` → PASS with the same calendar warning profile and 0 overflow routes.
- Script syntax: `node --check output/arls-shople-finalization/mobile_dark_role_probe.js` → PASS.
- Artifact whitespace: `git diff --check -- output/arls-shople-finalization` → PASS.
- Typecheck/test/lint note: no source files were edited by worker-3; repo `package.json` exposes only the placeholder `test` script and no lint/typecheck scripts, so source typecheck/lint were not applicable for this read-only QA artifact task.

## Completion verdict

PASS with warnings: the requested read-only mobile/dark role matrix was executed live and against the local current tree. Remaining release decision: calendar fetch-abort console warning and whether Finance download must be fully dark-styled before push/PR.
