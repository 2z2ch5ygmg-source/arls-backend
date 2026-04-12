# Worker 1 — Finance + Schedule remaining Shople/Shiftee sweep

Date: 2026-04-12 13:35 KST
Scope: read-only evidence and patch plan only. Product source was inspected but not edited.

## Inputs inspected

- Integrated sweep brief: `.omx/context/arls-shople-remaining-integrated-sweep-20260412T042950Z.md`
- Gap report: `docs/design/arls-shiftee-shople-ui-gap-report-20260412.md`
- Schedule/Finance comparison: `output/arls-all-tabs-ui-reference-comparison/schedule-finance.md`
- Shople/Shiftee reference classification:
  - `docs/design/shople-reference-action-layout-classification-20260412.md`
  - `docs/design/shiftee-reference-action-layout-classification-20260412.md`
- Current/reference captures:
  - `output/playwright/phase5-schedule-calendar-deployed.png`
  - `output/playwright/phase5-schedule-upload-deployed-1920.png`
  - `output/playwright/phase5-schedule-hq-upload-deployed.png`
  - `output/playwright/phase5-schedule-templates-deployed.png`
  - `output/playwright/task4-finance-submit-current.png`
  - `output/playwright/task4-finance-download-current.png`
  - `output/shople-schedule-direct.png`
  - `output/shople-schedule-child-direct.png`
  - `output/shople-schedule-settings-direct.png`
  - Shiftee schedule items called out in the catalog: 13, 29, 43, 48-50, 52-58.
- Current source read only:
  - `frontend/index.html`
  - `frontend/css/styles.css`
  - `frontend/js/app.js`

## Current gaps after commit `7ff8256`

Commit `7ff8256` added a visual baseline CSS pass in `frontend/css/styles.css`; the inspected screens are materially closer to Shople/Shiftee, but a few ownership and plane-reset gaps remain.

### P0 — Finance submit/download ownership is still report-owned in the DOM and sidebar

Evidence:

- `output/playwright/task4-finance-submit-current.png` and `output/playwright/task4-finance-download-current.png` still show Finance under the global `리포트/보고` owner even though the workflow is described as `스케줄 > Finance` in the gap docs.
- `frontend/index.html:7744-8253` mounts Finance inside `#view-reports`, with `#reportsWorkspaceTitle`, `#reportsWorkspaceTabs`, `#scheduleFinanceSubmissionPanel`, and `#financeDownloadPanel`.
- `frontend/js/app.js:462-472` defines both report and schedule routes; Finance submit/download are active report routes (`ROUTE_REPORTS`, `ROUTE_REPORTS_FINANCE_DOWNLOAD`), while the schedule-family report route also exists (`ROUTE_SCHEDULE_REPORTS`).
- The Finance tabs are now only same-job modes (`Finance 제출`, `Finance 다운로드`), which is good. The remaining mismatch is the visible/semantic owner: the left nav and page title still read as reports, not a Finance-owned workflow.

Recommended direction:

- Keep business behavior in the reports module for a small patch, but relabel the active Finance route as a Finance-owned operational surface rather than a generic report center.
- Do **not** reintroduce Apple weekly or other unrelated report modes into the local Finance tab row.
- Keep only `제출` and `다운로드` as local modes.

Likely touched selectors/functions:

- `frontend/index.html:7744-8253`
  - `#view-reports`
  - `#reportsWorkspaceTitle`
  - `#reportsScopeHint`
  - `#reportsCenterContextCard`
  - `#reportsWorkspaceTabs [data-action="reports-view-tab"]`
  - `#scheduleFinanceSubmissionPanel`
  - `#scheduleFinanceOverviewView`
  - `#scheduleFinanceOverviewStartBtn`
  - `#financeDownloadPanel`
  - `#financeDownloadHeaderContextMount`
  - `#financeDownloadPrimaryBtn`
- `frontend/js/app.js`
  - Route constants and aliases: `ROUTE_REPORTS`, `ROUTE_REPORTS_FINANCE_DOWNLOAD`, `ROUTE_SCHEDULE_REPORTS` around `frontend/js/app.js:462-472` and route aliases around `689-705`.
  - Reports tab/title helpers around `getDefaultReportsViewTab`, `renderReportsWorkspaceChrome`, and Finance helpers around `frontend/js/app.js:13450-13838`.
  - Download renderer: `renderReportsFinanceDownloadWorkspace()` at `frontend/js/app.js:13838`.
  - Finance submit/status render path: `renderScheduleFinancePreviewTable()`, `renderScheduleFinanceApplyDetails()`, `setScheduleFinanceUI()`, `renderScheduleFinanceSubmissionStatus()`, `loadReportsFinanceOverviewWorkspace()`, `loadScheduleFinanceSubmissionStatus()`, `loadReportsFinanceDownloadWorkspace()` around `frontend/js/app.js:24591-25343`.
- `frontend/css/styles.css`
  - Finance density overrides around `frontend/css/styles.css:48712-48820` (and later duplicated responsive/override blocks matching `#view-reports #financeDownloadPanel` if retained by the build/style structure).

Small patch plan:

1. Copy-only first pass: on Finance tab routes, change `#reportsWorkspaceTitle` / hint text to Finance-owned wording, e.g. `Finance` / `지점별 제출과 다운로드 상태를 같은 흐름에서 관리합니다.` while leaving non-Finance report routes unchanged.
2. Keep `#reportsWorkspaceTabs` two-mode only for Finance: local labels can become `제출`, `다운로드` when the owner title already says Finance.
3. Add a compact owner/status strip above the Finance submit table: target month, eligible/blocked/selected, and next action. Reuse existing `#scheduleFinanceOverviewSummary`, `#scheduleFinanceOverviewSelectionHint`, `#scheduleFinanceOverviewStatusSummary` rather than adding new state.
4. For `#financeDownloadPanel`, keep the table-led structure, but convert the loading/empty row into a compact actionable status row/strip so the large blank loading region does not dominate the page.
5. Verify routes continue to preserve selection, generated file download, first-confirmation download, final upload, per-site status, and role scoping.

Risks:

- Route ownership is partly IA/product wording and partly implementation. Moving Finance physically out of `#view-reports` is higher risk; prefer a copy/chrome patch unless the leader explicitly wants a route migration.
- `#reportsCenterContextCard` is mounted into the Finance download header via `mountReportsCenterContext("#financeDownloadHeaderContextMount")`; changing this component could affect non-Finance report screens if not scoped.
- Finance state spans hidden in `#scheduleFinanceSubmissionPanel .reports-finance-state-cache` are likely used by render code; remove none of them without checking references.

### P0 — Schedule upload/HQ upload wizard plane is improved but still narrates too much state above the active action

Evidence:

- `output/playwright/phase5-schedule-upload-deployed-1920.png` shows the desired single left step rail + canvas baseline after `7ff8256`, but there is still a prominent top status/narration block plus a context strip before the active step.
- `output/playwright/phase5-schedule-hq-upload-deployed.png` is closer than the earlier box-in-box implementation, but HQ upload still has two stacked context card bands and a file input band before the actual review/inspect action.
- Current source confirms the one-rail structure already exists in `frontend/index.html:4652-5643` via `#scheduleUploadPanel`, `.schedule-upload-wizard-layout`, `#scheduleBaseWizardProgress`, `#scheduleHqWizardProgress`, and `#scheduleUploadMainCanvas`.
- CSS confirms the intended architecture at `frontend/css/styles.css:6044-6072` (`.schedule-upload-workspace`, `.schedule-upload-wizard-layout`, `.schedule-upload-step-rail`, `.schedule-upload-main-canvas`) and `6257-6360` (`.schedule-wizard-progress`, `.schedule-wizard-step`).

Recommended direction:

- Keep the current one-rail / one-canvas architecture.
- Reduce repeated summary cards inside each active canvas; make the guide panel and context strip compact, not another dashboard.
- In HQ mode, surface the active step’s call-to-action sooner and collapse secondary diagnostics into `<details>` / lower-priority blocks.

Likely touched selectors/functions:

- `frontend/index.html:4652-5643`
  - `#scheduleUploadPanel`
  - `#scheduleBaseWizardProgress`
  - `#scheduleHqWizardProgress`
  - `#scheduleUploadMainCanvas`
  - `#scheduleExcelWorkflowMappingSection`
  - `#scheduleExcelWorkflowBaseSection`
  - `#scheduleExcelWorkflowExportSection`
  - `#scheduleExcelWorkflowHandoffSection`
  - `#scheduleSupportHqDownloadSection`
  - `#scheduleSupportHqUploadFile`
  - `#scheduleSupportHqInspectInlineBtn`
  - `#scheduleSupportHqProgress`
  - `#scheduleSupportHqReviewSummary`
  - `#scheduleSupportHqIssueGroups`
  - `#scheduleSupportHqReviewTableWrap`
- `frontend/js/app.js`
  - Wizard context/guide: `renderScheduleUploadWorkflowContext()`, `setScheduleUploadGuidePanel()`, `renderScheduleUploadGuidePanel()` around `frontend/js/app.js:20306-20566`.
  - Wizard visibility/state: `renderScheduleUploadModeTabs()`, `renderScheduleWizardProgress()`, `renderScheduleBaseWizardPages()`, `renderScheduleHqWizardPages()`, `renderScheduleUploadWorkflowSections()`, `setScheduleUploadWorkspaceMode()`, `setScheduleBaseWizardStep()`, `setScheduleHqWizardStep()`, `renderScheduleUploadWorkspace()` around `frontend/js/app.js:20870-21160`.
  - HQ review: `renderScheduleSupportHqSiteSelectionTable()`, `renderScheduleSupportHqReviewSummary()`, `renderScheduleSupportHqIssueGroups()`, `renderScheduleSupportHqReviewTable()`, `renderScheduleSupportHqWorkspace()` around `frontend/js/app.js:21943-22683`.
- `frontend/css/styles.css`
  - `.schedule-upload-guide-panel`, `.schedule-excel-context-strip`, `.schedule-excel-context-card`, `.schedule-upload-stage-shell`, `.schedule-upload-policy-strip`, `.schedule-upload-context-grid`, `.schedule-hq-context-grid`, `.schedule-support-status-grid`, `.schedule-support-actions-grid` around `frontend/css/styles.css:6087-6227`, `6416-6499`, `6806-7298`.

Small patch plan:

1. Keep `#scheduleBaseWizardProgress` and `#scheduleHqWizardProgress`; do not add another horizontal stepper.
2. Compress `.schedule-excel-context-strip` and `.schedule-hq-context-grid` to one line of decisive fields. Hide non-critical technical fields behind existing `details`/diagnostic sections.
3. In HQ upload, move or visually elevate the `#scheduleSupportHqUploadFile` + `#scheduleSupportHqInspectInlineBtn` action group so it is the first active element after the guide/context copy.
4. Trim duplicate phase words in step labels and headings: the rail already says the phase; active panel headings should describe the user action.
5. Preserve workflow order: mapping profile → target selection → file preparation → review → apply; HQ source status/check → extraction/download → workbook upload → preview/review → complete.

Risks:

- `renderScheduleUploadWorkflowSections()` physically moves section nodes into `#scheduleUploadMainCanvas`; styling changes should avoid relying on DOM order that changes across base/HQ modes.
- Wizard step buttons are intentionally disabled unless current/completed (`renderScheduleWizardProgress()`); making rail steps look like tabs may imply random access that the code does not allow.
- HQ resume persistence (`SCHEDULE_HQ_WIZARD_RESUME_KEY`) means hidden sections can reappear depending on stored state; test with fresh and resumed sessions.

### P1 — Monthly calendar/list need final toolbar and list-table polish, not a rebuild

Evidence:

- `output/playwright/phase5-schedule-calendar-deployed.png` shows the monthly calendar is the correct hero. The toolbar is already consolidated (`#scheduleOpsToolbar`, `#scheduleCalendarFilterRow`, `#scheduleActionMenuRow`), but the screenshot still shows pale shift blocks and a drawer overlay that can reduce contrast.
- Shiftee monthly references (catalog items 13, 29, 52) are denser and higher-contrast; Shople schedule references favor clear active/selected rhythm.
- List view is rendered as a list-sheet component (`renderScheduleListView()` and `createScheduleListSheetRow()`), not a true admin table. That is serviceable, but it remains visually secondary compared with Shiftee’s table-first schedule list reference (catalog item 50).

Likely touched selectors/functions:

- `frontend/index.html:4348-4583`
  - `#view-schedule`
  - `#scheduleWorkspaceTitle`
  - `#scheduleOpsToolbar`
  - `#scheduleMonthTitle`
  - `#scheduleCalendarFilterRow`
  - `#scheduleSiteFilter`
  - `#scheduleShiftFilter`
  - `#scheduleEmployeeFilter`
  - `#scheduleLeaveManageToggle`
  - `#scheduleActionMenuRow`
  - `#scheduleToolbarMeta`
  - `#scheduleToolbarSummaryStrip`
  - `#scheduleMonthlyPanel`
  - `#scheduleCalendarGrid`
  - `#scheduleDesktopDrawer`
- `frontend/js/app.js`
  - Tab/chrome: `renderScheduleHqTabs()` around `frontend/js/app.js:85454`.
  - Toolbar: `renderScheduleMonthToolbar()` and `renderScheduleOpsToolbar()` around `frontend/js/app.js:89688-89820`.
  - List rows: `createScheduleListSheetRow()` around `frontend/js/app.js:90618`; `renderScheduleListView()` around `frontend/js/app.js:91580`.
  - Calendar: `renderScheduleCalendar()` around `frontend/js/app.js:91657`; `renderScheduleAll()` around `frontend/js/app.js:91782`.
- `frontend/css/styles.css`
  - Toolbar/calendar/list block around `frontend/css/styles.css:5289-6033`, especially `.schedule-calendar-toolbar`, `.schedule-calendar-tools`, `.schedule-view-mode-row`, `.schedule-legend-row`, `.schedule-calendar-surface`, `.schedule-shift-card`, `.schedule-list-view`, `.schedule-list-sheet`, `.schedule-list-sheet-row`, `.schedule-list-sheet-actions`.

Small patch plan:

1. Keep the current toolbar architecture; tune spacing/contrast only.
2. Increase shift-card text contrast and active/day selected state using blue/neutral selected-state grammar, while preserving ARLS orange only for primary CTAs or brand accent.
3. In list mode, make `.schedule-list-sheet` read closer to a table: persistent compact column header, tighter rows, and less card-like vertical separation. Avoid changing row identity/edit/delete behavior.
4. Do not alter monthly/list route switching, filters, download/upload/add actions, or drawer behavior.

Risks:

- Existing list rendering is virtual/chunk-aware in adjacent employee-list code; avoid heavy DOM expansion.
- Calendar populated data may be sparse in verification environments; include at least a mocked or known populated dataset capture if possible.

### P1 — Work templates are table-led but still inherit upload-wizard family weight

Evidence:

- `output/playwright/phase5-schedule-templates-deployed.png` is currently showing the upload/wizard stepper state rather than a direct template table in the visible viewport, which suggests the tab/owner transition can still feel like a wizard family surface.
- The actual template panel exists at `frontend/index.html:5646-5695` as `#scheduleTemplatePanel` with a direct `admin-table`, which is closer to the desired Shiftee/Shople admin-table rhythm.
- The remaining work is therefore mostly route/tab visibility and chrome polish, not a data/model rewrite.

Likely touched selectors/functions:

- `frontend/index.html:5646-5695`
  - `#scheduleTemplatePanel`
  - `#scheduleTemplateTemplatesSection`
  - `#scheduleTemplateStatus`
  - `#scheduleTemplateTableBody`
  - `[data-action="schedule-template-refresh"]`
  - `[data-action="schedule-template-create"]`
- `frontend/js/app.js`
  - `setScheduleTemplateOwnerTab()` around `frontend/js/app.js:85694`
  - `renderScheduleTemplateOwnerSections()` around `frontend/js/app.js:85723`
  - `renderScheduleTemplateTable()` around `frontend/js/app.js:86229`
  - `renderScheduleHqTabs()` around `frontend/js/app.js:85454` for tab/panel ownership.
- `frontend/css/styles.css`
  - `.schedule-template-owner-panel`, `.schedule-template-owner-summary`, `.schedule-template-owner-summary-actions`, `.schedule-table-cell-stack`, `.schedule-template-action-note`, `.schedule-preview-table` around `frontend/css/styles.css:7425-7548`.

Small patch plan:

1. Ensure `/schedules/templates` opens directly to `#scheduleTemplatePanel`, not a remembered upload workspace state.
2. Keep a single table with top actions: refresh, create, and optionally import/export if already supported. Avoid additional cards above the table unless they are actionable filters.
3. Use Shople settings reference (`output/shople-schedule-settings-direct.png`) for a light table-management shell and Shiftee template reference items 48-49 for dense CRUD rhythm.

Risks:

- `renderScheduleHqTabs()` moves panel nodes into `#scheduleTabContent`; stale active-tab state can make screenshots misleading if not tested by direct route entry.
- Template creation/edit modals may share code with upload mapping profiles; keep template table polish separate from mapping profile manager changes.

## Recommended patch sequence

1. **Finance chrome/ownership copy** (lowest risk): scope to `#view-reports` when active tab is Finance; keep routes and APIs unchanged.
2. **Finance state strip**: reuse existing summary elements and table state to make submit/download states more actionable.
3. **Schedule wizard compaction**: CSS/HTML-light changes in upload/HQ upload only; do not change wizard order or handlers.
4. **Schedule calendar/list contrast**: tune CSS for shift cards/list rows and selected states.
5. **Templates route polish**: ensure direct table surface on `/schedules/templates` and trim inherited wizard-feel chrome.

## Verification routes / checks for the eventual patch

Run with the same user roles used by the existing captures (Developer/HQ admin and any branch manager role if available):

- Schedule monthly calendar: `/schedules/calendar`
  - Check month navigation, filters, leave toggle, download/upload/add actions, drawer open/close, and populated shift contrast.
- Schedule list: `/schedules/list`
  - Check list/table scanability, edit/delete row actions, filtering, and no horizontal overflow at 1366px and 1920px.
- Schedule base upload: `/schedules/upload`
  - Check mapping profile → target selection → file preparation → review → apply flow; verify no hidden step blocks become inaccessible.
- Schedule HQ upload: `/schedules/hq-upload`
  - Check source status, extraction/download, workbook upload, inspect/preview, mismatch review, apply/complete, and resume prompt behavior.
- Schedule templates: `/schedules/templates`
  - Check direct table load, refresh/create actions, route direct entry, and no stale upload stepper bleed-through.
- Finance submit: `/reports` with Finance submit active (or future Finance-owned route if introduced)
  - Check target month, eligible/blocked/selected counts, site selection, first confirmation download, final upload, and no Apple weekly local tab.
- Finance download: `/reports/finance-download`
  - Check month/site scope, download eligibility, select all, generated file links, loading/empty states, and per-site blocked rows.

Suggested automated smoke after source patch:

- `npm run lint` or project equivalent.
- `npm run typecheck` / `tsc --noEmit` if configured.
- Focused browser smoke for the six routes above at `1366x768` and `1920x1080`.
- Console/network regression check: zero unexpected console errors and no failed API requests beyond the known interrupted schedule SSE stream called out in the integrated brief.

## Remaining risks / open questions

- Finance IA ownership is still ambiguous in product terms: the gap report says freeze Finance as schedule child or finance child, but current code keeps it in Reports. A copy/chrome patch is safe; a full route migration needs leader/product decision.
- Schedule upload/HQ upload already received the structural one-rail pass. Further reduction should be conservative to avoid hiding required permission, tenant, revision, and blocked-reason context.
- Data in current verification screenshots is mostly empty for some routes. A populated schedule/list/template dataset is needed to judge final Shiftee density accurately.
- Existing unrelated working-tree changes are present (`app/routers/v1/integrations.py`, `tests/test_soc_site_context_resolution.py`); this worker did not inspect or modify them.
