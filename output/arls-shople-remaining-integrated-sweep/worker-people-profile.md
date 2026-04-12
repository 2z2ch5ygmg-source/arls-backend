# Worker 2 — People / Workplace / Profile evidence

Date: 2026-04-12  
Team: `arls-shople-remaining-sweep`  
Task: `People Workplace Profile evidence`  
Scope: analysis/report only. Product source was inspected but not modified.

## Sources inspected

- Integrated context: `.omx/context/arls-shople-remaining-integrated-sweep-20260412T042950Z.md`
- Gap report: `docs/design/arls-shiftee-shople-ui-gap-report-20260412.md`
- Prior comparison: `output/arls-all-tabs-ui-reference-comparison/people-workplace-profile-notices-calendar.md`
- Current product source touchpoints: `frontend/index.html`, `frontend/css/styles.css`, `frontend/js/app.js`
- Current/reference captures named by the prior comparison: `output/playwright/phase12-employee-management-hq-1366.png`, `output/playwright/phase12-site-management-1366.png`, `output/playwright/phase13-company-workspace-desktop-1920.png`, `output/playwright/batch2-profile-1366.png`, `output/playwright/settings-operations-after-prune-live.png`, `output/shople-people-direct.png`, `output/shople-workplace-direct.png`, `output/shople-workplace-mgmt-direct.png`, `output/shople-company-settings-direct.png`.

## Current gaps

### P0 — Profile / Settings: admin tools still default ahead of personal account settings

**Evidence**

- `frontend/index.html:6155-6285` still presents `#/profile` as one settings workspace with top tabs `기본 설정`, `작업 로그`, `모드 변경`, then a manager-only subsection tab row ordered `운영`, `연동`, `고급`, `개인`.
- `frontend/index.html:6205-6213` headline copy says `내 계정과 운영 설정`, so personal identity and operations tooling still share the first-read identity.
- `frontend/index.html:6676-6683` keeps the manager operations shell (`#integrationFlagsCard`, `data-profile-settings-section="operations"`) in the same visual family as personal settings.
- `frontend/index.html:7512-7540` has a right state rail mixing employee-only personal facts (`알림 권한`, `최근 동기화`) with manager-only ops facts (`플래그`, `활성 프로파일`, `그룹웨어`).
- `frontend/js/app.js:49045-49063` makes managers default to `operations` via `getDefaultProfileSettingsSection()`, while non-managers default to `account`.

**Gap vs Shople/Shiftee direction**

Shiftee account/profile references are direct account/security forms; Shople company settings uses grouped admin sections. ARLS should make `내 설정` / account identity/security the default, with operations/integration as explicit admin subsections. The current manager default still teaches admins that `운영 플래그` is the profile landing page.

### P0 — Employee directory: closer, but still filter/admin-heavy before row work

**Evidence**

- `frontend/index.html:9362-9410` has the right macro shape (`직원 목록과 상세 패널`) and a `#employeeDirectorySummaryStrip` before the toolbar.
- `frontend/index.html:9412-9435` keeps a top action bar with disabled destructive action `#employeeBulkDeleteSiteBtn` (`선택 현장 전체 삭제`) above the work list.
- `frontend/index.html:9437-9525` default visible toolbar still includes `회사`, `현장`, `역할`, `재직 상태`, plus inactive/deleted toggles. The desired default is only search + site + employment status; company/role/deleted should be advanced/admin.
- `frontend/index.html:10002-10218` table/detail shell is already in place, but table columns still spend first-view width on `회사`, `현장`, `직원`, `직원번호`, `역할`, `재직`, `계정`, `작업`.
- `frontend/js/app.js:69061-69138` renders three summary cards (`표시 인원`, `재직중`, `운영 현장`) above the directory; this is better than the old KPI wall but still a card strip before list-first work.
- `frontend/js/app.js:69176-69220` only uses the employee detail as an inline rail for desktop route + `(min-width: 1760px)`. At common 1366/1440 desktop widths the detail behaves as a drawer, so it is not yet the persistent two-pane pattern requested by the gap report.
- `frontend/js/app.js:70442-70540` already has compact empty/detail rendering; reuse this instead of inventing another detail component.
- `frontend/js/app.js:71960-72024` is the main render entry for filtered rows and detail synchronization.

**Gap vs Shople/Shiftee direction**

The surface has moved toward a list/detail workspace, but the default read path still has summary strip + broad filters + disabled destructive action before employee selection. Shiftee is narrower/table-first; Shople uses summary modules only when they have strong identity and do not push the table out of the operating path.

### P1 — Workplace / Site: summary is mostly demoted, but rows still expose infrastructure fields too early

**Evidence**

- `frontend/index.html:10343-10592` provides a site list + right detail panel (`#siteDirectoryDetailPanel`) and a direct `지점 등록` CTA.
- `frontend/css/styles.css:10217-10225` currently hides the organization tabs, `#orgScopeHint`, `#siteDirectorySummaryStrip`, `#siteTableHint`, and the master summary strip, so the previous KPI-strip problem is partly solved in CSS.
- `frontend/index.html:10390-10448` default site toolbar still exposes `회사`, `상태`, inactive/deleted toggles, `새로고침`, and `지점 등록` in one row; acceptable for admin but a bit less Shiftee-like than compact filter chips.
- `frontend/index.html:10471-10532` default table columns include `주소` and `출퇴근 기준`, so address/radius/readiness remain first-view browse data instead of detail-pane sections.
- `frontend/js/app.js:54449-54612` detail panel already groups facts and readiness; it includes address/coordinates in `현장 개요` and readiness in `출퇴근 준비`. This is the right place to move low-level infrastructure fields.
- `frontend/js/app.js:54614-54735` still builds a full `renderSiteDirectorySummaryStrip`, although CSS hides it. If kept hidden, avoid adding more logic here; if revived, make it compact chips only.

**Gap vs Shople/Shiftee direction**

The page is closer than Employees: summary is hidden and a detail pane exists. Remaining mismatch is row density/content priority: Shiftee/Shople-like browsing should show site name/code, company, employee count, active/readiness badge; address, geofence radius, coordinates, Wi-Fi and criteria should live in detail.

### P2 — Company / admin context: better than old audit, but default copy still exposes placeholder/admin noise

**Evidence**

- `frontend/css/styles.css:10217-10225` hides `#masterTenantSummaryStrip`, so the old placeholder-heavy KPI strip is not currently first-read.
- `frontend/js/app.js:46349-46438` still builds master count text; `frontend/js/app.js:46439-46538` still computes hidden summary content with disabled/deleted/recent/footprint states.
- `frontend/js/app.js:46539-46680` starts the company detail panel and badges; detail body uses fact cards and status/seal/profile completion badges. The detail is usable, but it still risks showing incomplete internal states (`미입력`, `도장 미등록`, cached counts) as primary governance facts.
- `frontend/css/styles.css:4517-4565` and `4804-4960` define the master toolbar/detail cards; changes here can tune density without touching business logic.

**Gap vs Shople/Shiftee direction**

Keep company/admin as a distinct MASTER context, but do not revive the hidden summary strip as a card wall. If touched, move toward a single compact status strip and detail checklist instead of first-view placeholder values.

## Exact selectors/functions likely touched for a small integrated patch

### Profile / Settings

- `frontend/index.html`
  - `#profileViewTitle`, `#profileViewSubtitle`, `.profile-identity-copy h3`, `.profile-identity-copy p` at `6155-6213`
  - `#profileSettingsSectionTabs` and `[data-action="profile-settings-section"]` buttons at `6248-6285`
  - `#integrationFlagsCard` / `[data-profile-settings-section="operations"]` at `6676-6683`
  - `#profileSettingsStateRail`, `.profile-settings-rail-item`, `#profileRail*Value` area around `7512-7549`
- `frontend/js/app.js`
  - `getDefaultProfileSettingsSection()` at `49045-49047`
  - `normalizeProfileSettingsSection()` at `49049-49063`
  - `renderProfileSettingsSectionTabs()` at `49064-49094`
  - `renderProfileSettingsSections()` at `49095-49119`
  - `renderProfileWorkspaceSegments()` at `49221-49265`
- `frontend/css/styles.css`
  - `#profileSettingsPanel.profile-segment-panel` around `4181-4183`
  - profile/control/rail styles around the existing `.profile-*` blocks; keep changes scoped, do not introduce new component families.

### Employee directory

- `frontend/index.html`
  - `#employeeDirectorySummaryStrip` at `9406-9410`
  - `#employeeTopActionBar`, `#employeeBulkDeleteSiteBtn` at `9412-9435`
  - `#employeeToolbar`, `#employeeTenantFilterField`, `#employeeRoleFilter`, `#employeeAdvancedFilterToggles` at `9437-9525`
  - `#employeeDesktopTableCard`, `#employeeDesktopTableBody`, `#employeeDirectoryDetailPanel` at `10002-10218`
- `frontend/js/app.js`
  - `renderEmployeeDirectorySummaryStrip()` at `69061-69138`
  - `isEmployeeDirectoryInlinePanelRoute()` / `isEmployeeDirectoryInlineRailViewport()` at `69176-69187`
  - `setEmployeeDirectoryDrawerOpen()` at `69190-69220`
  - `renderEmployeeDirectoryDrawer()` at `70442-70470`
  - `renderEmployeesFromCache()` at `71960-72024`
  - `syncEmployeeTenantFilterOptions()` at `72026-72110` if company filter visibility changes
- `frontend/css/styles.css`
  - `#view-employees .employee-directory-summary-strip` and `.organization-summary-strip` around `9597-9713`, `10086-10148`, `10462-10464`
  - `#view-employees .employee-console-toolbar` around `9959-10007` and `10364-10425`
  - employee table/detail styles around `10434-10580`

### Workplace / Site

- `frontend/index.html`
  - `#siteDirectorySummaryStrip` at `10390-10394`
  - `#siteFilterGrid`, `#siteSearchInput`, `#siteTenantFilter`, `#siteActiveFilter`, `#siteIncludeInactive`, `#siteIncludeDeleted`, `#siteCreateBtn` at `10395-10448`
  - `#siteDesktopTableBody`, site table headers at `10455-10538`
  - `#siteDirectoryDetailPanel`, `#siteDirectoryDetailBody`, `#siteDirectoryDetailActions` at `10542-10592`
- `frontend/js/app.js`
  - `renderSiteDirectoryDetail()` at `54449-54612`
  - `renderSiteDirectorySummaryStrip()` at `54614-54735` (prefer leave hidden or reduce to chips only)
  - site row building functions around the existing `site-directory-row` generation near `54774+`
- `frontend/css/styles.css`
  - `#view-org .site-console-toolbar` at `10148-10209`
  - `#view-org #siteDirectorySummaryStrip` hide rule at `10217-10225`
  - site table row/column rules at `10245-10325`

### Company / Admin

- `frontend/js/app.js`
  - `renderMasterTenantSummaryStrip()` at `46439-46538` (if summary is revived)
  - `renderMasterTenantDetailPanel()` at `46539+`
- `frontend/css/styles.css`
  - `.master-company-toolbar-card`, `.master-company-toolbar*` at `4517-4565`
  - `.master-company-detail-panel`, `.master-company-fact-grid`, `.master-company-empty`, `.master-company-detail-actions` at `4808-4960`

## Recommended small patch plan

1. **Profile default split (highest leverage, low risk)**
   - Change manager default from `operations` to `account` in `getDefaultProfileSettingsSection()`.
   - Reorder/copy `#profileSettingsSectionTabs` to put `개인` first, then `운영`, `연동`, `고급`.
   - Change headline copy from `내 계정과 운영 설정` to `내 계정 설정`; make operations copy explicit only inside the operations section.
   - In the rail, hide manager-only ops rail rows when active section is `account`; keep employee notification/password controls intact.
   - Risk: URL query `settingsSection=operations` should still deep link for admins, so do not remove `normalizeProfileSettingsSection()` support.

2. **Employee directory filter/admin demotion (medium leverage, moderate risk)**
   - Keep summary strip but make it a thinner same-plane compact row, or hide it when all values are zero/empty.
   - Default toolbar visible controls: search, site, employment status, primary `직원 등록`, secondary `대량 등록`.
   - Move company (DEV only), role, inactive/deleted toggles, and `선택 현장 전체 삭제` behind an advanced/admin affordance or a lower guarded footer; at minimum hide the disabled destructive button until a site scope is selected.
   - Consider lowering inline detail threshold from 1760px to a safe layout breakpoint (for example 1440px) only if table columns are simplified first; otherwise keep drawer at 1366 to avoid horizontal crowding.
   - Risk: employee tenant scoping and bulk delete are permission-sensitive; do not remove controls, only demote visibility.

3. **Site table row simplification (medium leverage, lower risk)**
   - Keep `#siteDirectorySummaryStrip` hidden or replace with tiny chips, not cards.
   - Change default table columns toward: `지점명 / 코드`, `회사`, `직원 수`, `상태 / 준비도`, `작업`.
   - Move `주소`, `좌표`, radius/geofence, Wi-Fi, and attendance criteria into `renderSiteDirectoryDetail()` sections (`기본 정보`, `출퇴근 기준`, `연동/검증`). Much of this content already exists in detail and can be reused.
   - Risk: operators may currently scan addresses in the table; preserve address in detail and search matching.

4. **Company admin polish (defer unless time remains)**
   - Do not unhide the hidden `#masterTenantSummaryStrip` as cards.
   - If touched, use one compact MASTER context strip and make detail facts a checklist-style grouping. Keep create/edit/active/delete protections untouched.

## Verification routes / evidence to capture after a patch

- Local 1366 desktop:
  - `#/profile`
  - `#/profile?settingsSection=operations`
  - `#/profile?settingsSection=integration`
  - `#/branch/employees`
  - `#/branch/sites`
  - `#/master/tenants` (DEV/MASTER only)
- Local 1920 desktop:
  - `#/branch/employees` to verify inline employee detail rail if breakpoint changes
  - `#/branch/sites` to verify site detail pane width and table columns
  - `#/profile` to verify account default and admin section switching
- Mobile / narrow smoke if available:
  - `#/profile`
  - `#/branch/employees`
  - `#/branch/sites`
- Checks:
  - No console errors during route switches.
  - No horizontal overflow at 1366 and 1920.
  - Employee row selection opens detail; existing employee registration/import routes still work.
  - Site row selection opens detail; site create/edit/toggle/delete controls remain permission-gated.
  - Profile password/notification controls remain visible for employee/account section; operations/integration tabs still work for manager/admin deep links.
  - Company create/edit and destructive protections still require the existing guarded flows.

## Risks / guardrails

- Do **not** modify backend/test dirty files: `app/routers/v1/integrations.py`, `tests/test_soc_site_context_resolution.py` are pre-existing unrelated changes.
- Do **not** add new dependencies or new UI component systems.
- Do **not** delete business controls: registration/import, tenant scoping, role filtering, inactive/deleted inclusion, bulk delete, site geofence/Wi-Fi, profile generator/groupware, and MASTER tenant lifecycle actions must remain available to authorized users.
- Avoid reverting the second-pass Shople baseline: keep gray outer plane, one white primary sheet, divider rhythm, compact command bars, and semantic icons only.
- Avoid adding cards to solve hierarchy; the next pass should mostly demote/hide/reorder existing source rather than add new panels.
