# Worker 2 — Populated data discovery

## Verdict

PASS — a populated visual-QA tenant is available: **SRS Korea / `SRS_KOREA`** (`7d3997c3-346a-407e-a416-687fe0827992`). It has usable rows for schedule, leave grants, notices, employees, and sites. The currently checked Phase13 tenants are accessible but effectively empty for the target QA surfaces.

Source files were not edited. This lane only wrote evidence artifacts under `output/arls-shople-finalization/`.

## Commands / checks run

- `cat .omx/context/arls-shople-finalization-20260412T125430Z.md` — PASS; loaded team context.
- Live read-only API probe against `https://rg-arls-backend.azurewebsites.net/api/v1` — PASS; results in `output/arls-shople-finalization/worker-populated-data-api-probe.json`.
  - Used `POST /auth/login` to obtain a QA developer session, then only GET requests for discovery.
  - Tenant list: `GET /tenants?include_inactive=true&include_deleted=true` → `200`, 12 tenants.
- Live read-only browser probe against `https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net` — PASS; results in `output/arls-shople-finalization/worker-populated-data-browser-probe.json` and screenshots in `output/arls-shople-finalization/populated-captures/`.
  - No mutating clicks or submits were performed; only navigation and screenshots.

## Candidate tenants

| Tenant | Result | Evidence |
| --- | --- | --- |
| `SRS_KOREA` / SRS Korea | **Use this for populated visual QA.** | Employees `5/limit 5`, sites `5/limit 5`, schedule rows, leave grants, notice rows. |
| `phase13_09011819` / Phase13 회사 09011819 | Accessible, but empty for current target surfaces. | Employees 0, sites 0, schedules 0, leaves 0, notices 0; policies 1. |
| `phase13_09694533` / Phase13 회사 09694533 | Accessible, but empty for current target surfaces. | Employees 0, sites 0, schedules 0, leaves 0, notices 0; policies 1. |

## SRS_KOREA data findings

| Surface | API evidence | Browser route evidence |
| --- | --- | --- |
| Attendance | `GET /attendance/requests/review-queue?tenant_code=SRS_KOREA&status=pending,approved,rejected,cancelled&limit=10` → `200`, 0. Direct `attendance/records` tenant scan is limited because the endpoint uses the authenticated tenant, and the known SRS HQ credential probe returned `401 invalid credentials`. | `#/attendance?section=period&mode=list` captured, no overflow, but current date shows `총 0건` / no detailed records. Screenshot: `populated-captures/attendance-period-list.png`. |
| Schedule | `GET /schedules/monthly-lite?month=2026-04&tenant_code=SRS_KOREA` → `200`, 6 rows; sample `Apple_가로수길`, `2026-04-01`, `야간근무`. `GET /schedules/monthly-lite?month=2026-03&tenant_code=SRS_KOREA` → `200`, 186 rows. | `#/schedules/list` and `#/schedules/calendar` captured, no overflow. UI showed April 2026 rows such as `서성원`, `송원석`, `Apple_가로수길`, `22:00-08:00`; screenshots: `schedule-list.png`, `schedule-calendar.png`. |
| Leave | `GET /leaves?tenant_code=SRS_KOREA&limit=10` → `200`, 0 leave request rows. `GET /leaves/grants?tenant_code=SRS_KOREA&limit=10` → `200`, 2 grant rows. `GET /leaves/policies?tenant_code=SRS_KOREA` → `200`, 1 policy. | `#/leave?tab=grants` captured, no overflow. UI showed two grant rows (`코덱스경력0220`, `서성원`) with `15일`, `2026. 1. 1. ~ 2026. 12. 31.` Screenshot: `leave-grants.png`. |
| Notices | `GET /notices?limit=10` with `X-Tenant-Id: SRS_KOREA` → `200`, 10 items. `GET /notices/home-teaser?limit=6` with same header → `200`, 6 items. | `#/feature/notices` captured, no overflow. UI showed several notice titles including `[Phase1 검증] 공지센터 생성/상세/홈 티저 확인 2026-03-23 10:28`. Screenshot: `notices.png`. |
| Employees/sites | `GET /employees?tenant_code=SRS_KOREA&limit=5&include_inactive=true&include_deleted=true` → `200`, 5 rows; `GET /sites?...` → `200`, 5 rows. | Useful as supporting tenant context for route filters; sample site `Apple_가로수길` appears in schedule UI. |

## Screenshot artifacts

- `output/arls-shople-finalization/populated-captures/attendance-period-list.png`
- `output/arls-shople-finalization/populated-captures/schedule-list.png`
- `output/arls-shople-finalization/populated-captures/schedule-calendar.png`
- `output/arls-shople-finalization/populated-captures/leave-grants.png`
- `output/arls-shople-finalization/populated-captures/notices.png`

## Suggested follow-up capture commands

Use the live frontend with SRS tenant context and the same developer session pattern from `output/arls-shople-finalization/worker-populated-data-browser-probe.js`:

```bash
ARLS_QA_PASSWORD=<redacted> node output/arls-shople-finalization/worker-populated-data-browser-probe.js > output/arls-shople-finalization/worker-populated-data-browser-probe.json
```

For a full role/mobile/dark visual matrix, reuse SRS_KOREA and cover at least:

- `#/schedules/list`
- `#/schedules/calendar`
- `#/leave?tab=grants`
- `#/feature/notices`
- `#/attendance?section=period&mode=list` (expected empty for current date unless a tenant-scoped attendance-record auth path is supplied)

## Limits / blockers

- Attendance record discovery is only partial. The direct `/attendance/records` endpoint does not accept `tenant_code`; with the developer token it resolves to the developer/master auth tenant rather than SRS_KOREA. A known SRS HQ login probe (`SRS_KOREA` / `09903300003`) returned `401 invalid credentials`, so I did not obtain tenant-authenticated attendance records.
- Browser probe reported one benign console warning from `navigator.vibrate` being blocked without a user gesture.
- Browser `requestfailed` contained several API URLs, including `auth/me`, `attendance/records`, and schedule SSE; there were **no HTTP API errors** (`httpApiErrors: []`) and the target populated pages still rendered.
- Phase13 tenants previously referenced by earlier artifacts are accessible but current GET checks found no target-surface rows.
