# Calendar / Reports / Notices remaining sweep evidence

Date: 2026-04-12
Worker: worker-4
Task: `Calendar Reports Notices verification evidence`
Scope: read-only product-source analysis; output artifact only.

## Inputs inspected

- `.omx/context/arls-shople-remaining-integrated-sweep-20260412T042950Z.md`
- `docs/design/arls-shiftee-shople-ui-gap-report-20260412.md`
- `output/arls-all-tabs-ui-reference-comparison/people-workplace-profile-notices-calendar.md`
- Current source touchpoints, inspected only:
  - `frontend/index.html`
  - `frontend/css/styles.css`
  - `frontend/js/app.js`

## Current gaps

### Calendar (`#/calendar`, `#/calendar/month`, `#/calendar/week`, `#/calendar/day`)

- The current calendar is already clean and same-plane: `#view-calendar` mounts a header, toolbar, and `#calendarWorkspaceRoot`, while JS renders an Outlook-like shell with a left mini-month rail and a main month/week/day grid.
- Remaining Shiftee/Shople gap is **interpretation**, not decoration. The standalone calendar still has only grid + mini-month in the default shell; selected-day meaning is weak unless a user opens/selects an event.
- `renderCalendarDetailDrawer()` already exists and would provide detail/editor/empty-state semantics, but `renderCalendarWorkspace()` currently renders only left rail + center surface. It does not mount the drawer in the default layout.
- The toolbar has today/prev/next/filter/day-week-month/fullscreen, but lacks a compact legend/count strip for meaningful event types (`일정`, `외부`, `휴가`, `근무`) or container/source state.
- Month cells show up to 3 event pills and a `+N` overflow marker, but empty selected dates have no same-plane interpretation. Avoid adding KPI cards above the grid; use a slim detail rail/bottom panel instead.

### Reports / statistics

- `#view-reports` currently presents Finance-owned tabs (`Finance 제출`, hidden `Finance 다운로드`) and intentionally hides generic report wording when Finance tabs are active. That is good for the P0 Finance ownership constraint, but it means a broad “reports/statistics” patch should avoid reintroducing a generic report-center shell.
- The remaining reports/statistics gap is mostly **wide-table context and scroll affordance**:
  - Finance download table has site/status/upload/file/download columns and a `table-wrap`, but no explicit sticky/context treatment beyond the generic table styling.
  - Attendance statistics uses a separate `#attendanceStatsPanel` with chart/table CSS. It is not under `#view-reports`; if the leader touches “statistics,” route ownership must be explicit to avoid mixing Attendance stats and Finance reports.
- The `renderReportsScopeHint()` implementation has a minor unreachable/contradictory branch: it returns for both `finance` and `finance-download`, then checks `currentTab === "finance-download"` afterward. Not harmful visually because both Finance modes hide the hint, but it is a cleanup candidate if reports source is touched.
- Any next patch should preserve the second-pass Finance IA: `Finance` title for Finance tabs, no Apple weekly/report-center competition in the first reading path, and no new summary-card wall.

### Notices (`#/feature/notices`, `#/feature/notices?mode=new`, detail routes)

- Notices are already the closest to the Shople-like reference: header + category tabs + search, single list plane, detail panel, and a compose document surface are in place.
- Remaining list gap: empty list still uses `renderCompactListEmpty()` and appends `첫 공지 작성`; depending on the shared empty renderer, this can still feel like a framed mini-card. Target is a same-plane empty note: icon/title/one CTA, no large bordered module unless grouping real pinned/detail content.
- Remaining detail gap: detail is a route-level replacement panel, not an inline list/detail split when data exists. A lightweight two-pane list/detail only for desktop and populated rows would better match the recommendation, but it should be a later/small patch because the current route separation is stable.
- Remaining compose gap: metadata (`카테고리`, `상단고정`, `발행`) is currently a top settings strip and insert tools are a horizontal toolbar above the document body. This is acceptable, but the next polish could group metadata into a compact publish panel or command block while keeping title/body dominant and preserving all rich tools.
- Do not restart Notices from scratch; avoid card-wall regressions or hiding required image/table/poll/link capabilities.

## Exact selectors / functions likely touched

### Calendar

- `frontend/index.html:6124-6144` — `#view-calendar`, `#calendarWorkspaceTabs`, `#calendarWorkspaceRoot` mount points.
- `frontend/js/app.js:61734-61820` — `renderCalendarWorkspaceTabs()` toolbar; candidate for adding only data-backed legend/count chips.
- `frontend/js/app.js:62360-62418` — `renderCalendarMonthShell()` month grid and event pills.
- `frontend/js/app.js:62420-62431` — `renderCalendarDayShell()` day timeline.
- `frontend/js/app.js:63228-63345` — `renderCalendarDetailDrawer()` existing detail/empty/editor rail; likely reusable rather than inventing a new detail component.
- `frontend/js/app.js:64676-64687` — `renderCalendarLeftRail()` mini-month + `새 일정` rail.
- `frontend/js/app.js:64930-64969` — `renderCalendarWorkspace()` current shell assembly; likely insertion point for detail rail/bottom panel.
- `frontend/css/styles.css:36963-37076` — calendar toolbar and view segment styles.
- `frontend/css/styles.css:37170-37316` — `.calendar-outlook-shell`, sidebar, main, and surface layout.
- `frontend/css/styles.css:37318-37435` — month weekday/grid/cell/event pill styles.
- `frontend/css/styles.css:37692-37840` — dark-mode and responsive calendar styles.

### Reports / statistics

- `frontend/index.html:7744-7785` — `#view-reports`, `#reportsWorkspaceTitle`, `#reportsScopeHint`, and context card.
- `frontend/index.html:7787-7810` — Finance report workspace tabs and refresh action.
- `frontend/index.html:8190-8255` — Finance download header and wide table shell.
- `frontend/js/app.js:13503-13525` — `renderReportsScopeHint()` title/hint logic; small cleanup target if touched.
- `frontend/js/app.js:13730-13743` — `renderReportsContextSummary()` currently clears/hides context summary.
- `frontend/js/app.js:14616-14687` — `renderReportsWorkspacePanels()` tab/panel/context visibility.
- `frontend/css/styles.css:13016-13045` — report context grid/summary/site row.
- `frontend/css/styles.css:15117-15125` — report tabbar row spacing.
- `frontend/index.html:4180-4210` — Attendance statistics panel mount; only touch if the next patch explicitly includes Attendance stats rather than Finance reports.
- `frontend/css/styles.css:44700+`, `45504+`, `49531+`, `49881+`, `50544+` — Attendance statistics chart/table shell styles. These are high-risk to sweep casually because multiple later overrides exist.

### Notices

- `frontend/index.html:5698-5728` — notices header, create button, category tabs/search row.
- `frontend/index.html:5793-5845` — list/detail/compose panel split.
- `frontend/js/app.js:56202-56247` — `createNoticeListRow()` row density and metadata.
- `frontend/js/app.js:56934-57002` — category tabs and search controls.
- `frontend/js/app.js:57004-57047` — `renderNoticesListPanel()` empty state + first notice CTA insertion.
- `frontend/js/app.js:57049-57093` — `renderNoticesDetailPanel()` default/detail empty rendering.
- `frontend/js/app.js:57095-57143` — `renderNoticesComposePanel()` settings/toolbar/body rendering orchestration.
- `frontend/js/app.js:57145-57205` — `renderNoticesView()` mode visibility.
- `frontend/css/styles.css:26856-27165` — notices list/header/detail plane styling.
- `frontend/css/styles.css:27531-27608` — compose settings strip.
- `frontend/css/styles.css:27646-27695` — compose document/title/body sizing.
- `frontend/css/styles.css:27837-27903` — compose insert toolbar.

## Recommended small patch plan

1. **Calendar selected-day detail rail (highest value in this lane)**
   - Reuse `renderCalendarDetailDrawer()` inside `renderCalendarWorkspace()` instead of creating a new component.
   - Desktop: change shell from `sidebar + main` to `sidebar + main + detail rail` only when width allows; mobile/tablet: keep current shell and place a compact selected-day summary below the grid if necessary.
   - Empty rail copy should say selected date + event count + one `새 일정` CTA when permitted. It must not become a KPI stack.
   - If adding legend chips, derive from actual workspace containers/events/source badges; do not hardcode decorative chips.

2. **Reports/statistics table-context micro polish**
   - Keep `#view-reports` Finance-owned. Do not add a generic Reports dashboard.
   - If touching reports CSS, add minimal affordances for the Finance download wide table: sticky first site column if safe, a subtle horizontal-scroll hint, and tighter header context.
   - If touching Attendance stats, treat it as `#/attendance?section=stats`, not `#/reports`. Limit work to table legibility/empty overlay; avoid chart redesign unless backed by screenshot evidence.
   - Optionally clean `renderReportsScopeHint()` so the `finance-download` branch is not unreachable, but only if reports source is already in the patch.

3. **Notices finishing pass**
   - In `renderNoticesListPanel()`, replace the manager empty state with a same-plane empty note + one CTA if the shared renderer creates a framed block.
   - Keep current category tabs/search/list header. Do not re-layout the whole screen.
   - Compose: if time permits, add a compact label/heading for publish settings or move metadata into a subtle command block; keep image/table/poll/link buttons visible and stable.
   - Defer desktop list/detail split unless a populated-data screenshot proves it is worth the complexity.

4. **Integrated verification pass**
   - After source patch, run deterministic route smoke at 1366 and 1920 for Calendar month/week/day, Notices list/compose/detail, and Reports Finance submit/download (when permissions allow).
   - Include console error, HTTP API error, and horizontal overflow checks.

## Verification routes / matrix for next patch

| Surface | Route / state | Viewports | Evidence to capture | Pass criteria |
| --- | --- | --- | --- | --- |
| Calendar month | `#/calendar` and `#/calendar/month` | 1366, 1920 | screenshot + DOM state | toolbar visible; grid first; no dashboard cards; selected-day rail/summary visible if patched; no horizontal overflow. |
| Calendar week | `#/calendar/week` | 1366, 1920 | screenshot + console/network | timeline columns render; current-time line does not overlap controls; selecting a date/event keeps detail rail coherent. |
| Calendar day | `#/calendar/day` | 1366, 1920 | screenshot + interaction | `새 일정` opens existing event editor; read-only external event behavior remains read-only. |
| Notices list empty/populated | `#/feature/notices` | 1366, 1920 | screenshot + route reload | category tabs/search/header CTA preserved; empty state same-plane; populated rows stay compact. |
| Notices compose | `#/feature/notices?mode=new` | 1366, 1920 | screenshot + DOM | title/body dominant; category/pin/publish visible; image/table/poll/link controls still available. |
| Notices detail | detail route or row click from list | 1366, 1920 | click-through smoke | detail title/body/actions render; edit/delete gated by permission; back/list action preserves category/search. |
| Reports Finance submit | `#/reports?tab=finance` | 1366, 1920 | screenshot + API smoke | title is `Finance`; no generic report-center card wall; submit overview/table still loads; `제출 시작` gating unchanged. |
| Reports Finance download | `#/reports?tab=finance-download` / role-gated equivalent | 1366, 1920 | screenshot + table scroll check | download table keeps site/status/file/download columns; horizontal scroll has context; downloads remain gated to eligible rows. |
| Attendance statistics (only if touched) | `#/attendance?section=stats` or existing stats route | 1366, 1920 | screenshot + export-button smoke | charts/tables remain readable; export buttons remain wired; empty/no-data state is restrained. |

## Risks / cautions

- Calendar already has an existing modal/editor path; adding a second detail model could break event editing. Prefer mounting/reusing `renderCalendarDetailDrawer()`.
- Calendar source includes fullscreen and dark-mode branches; any new rail CSS needs responsive and dark-theme coverage.
- Reports and Finance are intentionally separated from Apple/generic reporting in the current pass. A broad reports polish can accidentally undo the P0 Finance ownership win.
- Attendance statistics has many accumulated CSS overrides; avoid broad selector edits unless the leader explicitly includes that route in the implementation patch.
- Notices compose has rich block editing, autosave, drag/drop, table picker, poll modal, and image upload logic. Keep any visual patch CSS/markup-adjacent; do not rewrite compose flow behavior.
- The current working tree has unrelated backend/test changes (`app/routers/v1/integrations.py`, `tests/test_soc_site_context_resolution.py`); do not stage or alter them for this lane.
