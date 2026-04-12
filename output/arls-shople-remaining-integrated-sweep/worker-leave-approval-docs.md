# Worker 3 — Leave / Approval / Documents Remaining Sweep Evidence

- Team: `arls-shople-remaining-sweep`
- Task: `task-3` — Leave Approval Documents evidence
- Worker: `worker-3`
- Scope: read-only product-source analysis; this artifact is the only intended file change.
- Source baseline: current tree after commit `7ff8256` per `.omx/context/arls-shople-remaining-integrated-sweep-20260412T042950Z.md`.

## Evidence read

- Integrated sweep context: `.omx/context/arls-shople-remaining-integrated-sweep-20260412T042950Z.md`
- Gap report: `docs/design/arls-shiftee-shople-ui-gap-report-20260412.md`
- Prior cluster analysis: `output/arls-all-tabs-ui-reference-comparison/leave-approval-documents.md`
- ARLS catalog: `docs/design/arls-reference-action-layout-classification-20260412.md`
  - Relevant images: `4` leave status top, `8` leave full surface, `9` leave grants, `10` leave settings, `11` leave history, `13/16/18` approval queues, `17` approval procedure editor, `7/20` documents.
- Shiftee catalog: `docs/design/shiftee-reference-action-layout-classification-20260412.md`
  - Relevant references: `14/16` leave accrual/list, `15/18/22` request history empty/list, `41` leave management modal, partial `6/12` request/leave context.
- Shople catalog: `docs/design/shople-reference-action-layout-classification-20260412.md`
  - Applicable traits: light work surface, compact top toolbars, domain-local actions, list/detail over card walls, no heavy box-in-box/decorative title icons/U-shaped tabs/oversized empty states.
- Source inspected read-only: `frontend/index.html`, `frontend/css/styles.css`, `frontend/js/app.js`.

## Current gaps

### 1) Leave status/history/grants/settings

The current Leave DOM is already separated into routeable workspace sections, but it still has visible mini-app layering risk:

- `frontend/index.html:1853` `#view-leave` keeps a page description that restates section ownership instead of letting the sheet/list controls carry the task.
- `frontend/index.html:1867-1918` `#leaveWorkspaceDesktop` / `#leaveWorkspaceTabs` gives one top-level underline section model, which is good and should be preserved.
- `frontend/index.html:1921-1964` `#leavePolicySection` still uses `#leavePolicyStatusTabs` for `활성/비활성`. That is effectively a policy state filter, so it is the clearest remaining extra-tab layer.
- `frontend/index.html:1974-2098` `#leaveRequestsToolbar` is the right compact filter/action surface, but it remains a separate module card above another module card (`#leaveWorkspaceRequestsCard`). This creates toolbar-card + list-card stacking.
- `frontend/index.html:2101-2149` `#leaveHistoryChartCard` still appears before the history list. The gap report and Shiftee request-history references favor table/list first; `사용 흐름` should be optional/secondary after the history list.
- `frontend/index.html:2157` `#leaveWorkspaceSecondaryTabsWrap` is already hidden by CSS (`frontend/css/styles.css:44465`), which is good; keep it removed/hidden rather than reactivating a second status segmentation layer.
- `frontend/index.html:2301-2361` `#leaveGrantsSection` has a valid `부여 내역 / 구성원별` mode control, but it should remain a compact toolbar control, not a section-tab sibling. Current placement inside `.leave-grants-head` is acceptable if styling stays subtle.
- `frontend/index.html:2369-2608` `#leaveUsageSection` is closest to the target: KPI strip + filter toolbar + dense grid/list. This should be the pattern for history and grants.

Source behavior hooks to preserve:

- Routing: `frontend/js/app.js:36341` `normalizeLeaveWorkspaceTabParam`, `36351` `resolveLeaveTabFromWorkspaceSection`, `36369` `getLeaveTabRoute`, `36853` `applyLeaveRouteStateFromQuery`.
- Section visibility: `frontend/js/app.js:41403` `renderLeaveWorkspaceTabs` toggles `#leavePolicySection`, `#leaveRequestsSection`, `#leaveUsageSection`, `#leaveGrantsSection`.
- Primary action: `frontend/js/app.js:41442` `renderLeaveWorkspacePrimaryAction` switches `휴가 신청` / `휴가 부여` / `정책 등록` by section and permissions.
- Policy status filter: `frontend/js/app.js:41494` `renderLeavePolicySection` + `41542` `renderLeavePolicyStatusTabs`.
- History list/filter: `frontend/js/app.js:41786` `renderLeaveWorkspaceRequestToolbar`, `41843` `createLeaveWorkspaceRequestRow`, `41857` `renderLeaveWorkspaceRequestRows`.
- History chart: `frontend/js/app.js:41988` `renderLeaveHistoryChart`.
- Grants: `frontend/js/app.js:42694` `renderLeaveGrantsSection`, `42787` `renderLeaveGrantsPolicyFilter`.

### 2) Approval queues

The requests workspace is already queue/list/detail oriented, but it still carries two segmentation concepts in markup:

- `frontend/index.html:1214` `#view-requests` is the approval/request workspace root.
- `frontend/index.html:1256-1275` `#requestsWorkspaceSegments` splits exception requests vs document approvals. This is an ownership split and should remain if document approval mode is available.
- `frontend/index.html:1279-1344` `#requestsFilterBar` includes status select `#requestsStatusFilter` plus range/employee/site filters.
- `frontend/index.html:1346` `#requestsKpiStrip` is an appropriate compact summary strip.
- `frontend/index.html:1356-1392` `#requestsPriorityQueueCard` is useful, but it should look like same-plane priority rows, not an extra dashboard card above the work list.
- `frontend/index.html:1395-1554` `#requestsMainListCard` is the primary table/list surface.
- `frontend/index.html:1413-1444` `#requestsSecondaryTabsWrap` / `#requestsSecondaryTabs` provides a second pending/in-progress/completed status strip. If `#requestsStatusFilter` remains as the status control, this secondary strip should stay hidden/unused; if the strip becomes the only status control, the dropdown should be removed from the first reading path.
- `frontend/index.html:1557-1589` `#requestsUnifiedDetailPanel` is the correct detail/review panel pattern and should not be replaced by route-launcher cards.

Source behavior hooks to preserve:

- Segment visibility: `frontend/js/app.js:33173` `renderRequestsWorkspaceSegments`.
- Filter state: `frontend/js/app.js:33216` `normalizeRequestsWorkspaceStatusFilter`, `33382` `ensureRequestsWorkspaceFilters`, `34554` `applyRequestsWorkspaceFilters`.
- Document approvals: `frontend/js/app.js:34179` `normalizeApprovalDocumentStatus`, `34296` `buildRequestsDocumentItem`, `55747` `fetchRequestsDocumentRows`, `55800` `fetchRequestsApprovalRows`.
- Queue/list/detail rendering: `frontend/js/app.js:34702` `renderRequestsWorkspaceKpis`, `34981` `renderRequestsPriorityQueue`, `34944` `renderRequestsWorkspaceListRows`, `35026` `renderRequestsWorkspaceDetailPanel`, `35464` `setRequestsListCount`.
- CSS shape: `frontend/css/styles.css:15741` `#requestsFilterBar.requests-ops-toolbar`, `15327/15756` `#requestsKpiStrip`, `15411/50400` `#requestsPriorityQueueCard`, `15588` `.requests-workspace-row`.

### 3) Documents apply / my-docs / manage

The regression-sensitive route split is present and should be protected:

- `frontend/index.html:2616` `#view-hr` root.
- `frontend/index.html:2655-2680` `#hrWorkspaceSegments` has `apply`, `my-docs`, `manage` segments.
- `frontend/index.html:2682-2733` `#hrDocumentHomeCard` / `#hrDocCardGrid` is a document catalog. It is compact compared with older card walls, but still includes repeated “승인 후 출력 가능 · 앱에서 상태 확인” helper copy per type.
- `frontend/index.html:2736-2878` `#hrEmploymentEmployeeCard` is the selected request form and should be the dominant apply work area.
- `frontend/index.html:2882-2907` `#hrEmploymentMyRequestsCard` is correctly table-first for personal history.
- `frontend/index.html:2910-3066` `#hrTemplateAdminCard` is the approval procedure/admin workspace. `#hrManageApprovalRulesPanel` currently leads with authoring + preview, which is correct; `#hrManageTemplatesPanel` is already hidden, which aligns with demoting template library/version history.
- CSS route separation exists at `frontend/css/styles.css:13939-13941` for `data-hr-layout="my-docs"` and `data-hr-layout="manage"`.

Source behavior hooks to preserve:

- Segment routing/access: `frontend/js/app.js:57753` `normalizeHrWorkspaceSegment`, `57762` `resolveDefaultHrWorkspaceSegment`, `57767` `resolveAccessibleHrWorkspaceSegment`, `57780` `setHrWorkspaceSegment`, `57788` `renderHrWorkspaceSegments`, `60134` `renderHrScopeAndPanels`, `36830` `applyHrRouteStateFromQuery`.
- Catalog: `frontend/js/app.js:58129` `renderHrDocCardSelection`, `58004` `getHrCertificateTypeSubtitle`, `58019` `getHrCertificateTypeStateLabel`.
- Request form/history: `frontend/js/app.js:58262` `renderHrEmployeeRequestCard`, `58696` `renderHrMyRequestRows`, `60593` `submitHrEmploymentRequest`, `60804` `downloadHrEmploymentRequestPdf`.
- Approval editor/templates: `frontend/js/app.js:59325` `renderHrApprovalRulesEditor`, `59300` `renderHrApprovalProcedurePreview`, `59808` `loadHrDocumentApprovalRules`, `59905` `saveHrDocumentApprovalRules`, `60466` `loadHrDocumentTemplates`, `60881` `uploadHrDocumentTemplate`.
- CSS catalog: `frontend/css/styles.css:11354` `.hr-doc-card-grid`, `11381` `.hr-doc-card`, `11394` `.hr-doc-card-copy`.

## Recommended small patch plan

1. **Guard routes first, especially HR documents.**
   - Add/extend a DOM smoke that visits `#/hr?segment=apply`, `#/hr?segment=my-docs`, and `#/hr?segment=manage` and asserts the expected visible cards:
     - apply: `#hrDocumentHomeCard` + `#hrEmploymentEmployeeCard`; not `#hrEmploymentMyRequestsCard` / `#hrTemplateAdminCard`.
     - my-docs: `#hrEmploymentMyRequestsCard`; not apply catalog/form.
     - manage: `#hrTemplateAdminCard`; not apply/my-docs cards.
   - Do the same for `#/leave`, `#/leave?tab=history`, `#/leave?tab=grants`, `#/leave?tab=settings` by asserting the matching leave section visibility.

2. **Leave history list-first polish.**
   - Move `#leaveHistoryChartCard` below `#leaveWorkspaceRequestsCard` in `frontend/index.html`, or keep DOM order and use CSS/order only if that is safer for focus order. DOM reorder is preferable for accessibility.
   - Keep `renderLeaveHistoryChart()` behavior unchanged.
   - Keep `#leaveWorkspaceSecondaryTabsWrap` hidden; do not revive queue tabs while `#leaveWorkspaceStatusFilter` exists.

3. **Leave policy status filter simplification.**
   - Convert `#leavePolicyStatusTabs` from tab-like visual treatment to a compact filter chip/select in the policy header/toolbar.
   - Minimal implementation option: retain `data-action="leave-policy-status-tab"` buttons and JS state, but style them as a small same-row filter cluster and rename wrapper class to communicate filter semantics. Avoid changing `renderLeavePolicySection()` logic unless tests cover it.

4. **Approval queue same-plane compression.**
   - Keep `#requestsKpiStrip` and `#requestsPriorityQueueList`, but reduce `#requestsPriorityQueueCard` card chrome so it reads as a summary row block directly attached to the main list plane.
   - Choose one status segmentation model. Least risky option: keep `#requestsStatusFilter` as the single status control and keep `#requestsSecondaryTabsWrap` hidden/unused for the unified workspace.
   - Preserve `#requestsUnifiedDetailPanel` and current row detail actions.

5. **Documents catalog copy reduction.**
   - In `renderHrDocCardSelection()`, shorten `getHrCertificateTypeSubtitle()` output for requestable rows or hide repeated subtitles through CSS at desktop widths. Prefer JS text change if it remains understandable for screen readers.
   - Keep `hr-doc-card-state` as the visible status signal (`승인형`, `신청 불가`, etc.).
   - Do not change `renderHrWorkspaceSegments()` or `renderHrScopeAndPanels()` unless route tests fail.

6. **Approval procedure editor guardrails.**
   - Keep `#hrManageTemplatesPanel` hidden by default and only expose template library as advanced/admin when explicitly selected.
   - Do not let template upload/version table move above `#hrApprovalProcedureEditor` and `#hrApprovalProcedurePreview`.

7. **Empty-state normalization.**
   - Ensure lists created by `renderCompactListEmpty()` and requests/leave/HR table empty rows remain same-plane, neutral, and compact. Avoid orange/tinted boxed cards.

## Verification routes / checks

Run locally at 1366 and 1920 widths where feasible:

- Leave:
  - `#/leave` — `#leaveUsageSection` visible; KPI strip + list/table primary; `#leaveWorkspacePrimaryAction` present when allowed.
  - `#/leave?tab=history` — `#leaveRequestsSection` visible; history list precedes/anchors the chart; filters and `#leaveWorkspaceStatusFilter` work.
  - `#/leave?tab=grants` — manager-permission gate respected; `#leaveGrantsSection` visible only for eligible roles.
  - `#/leave?tab=settings` — manager-permission gate respected; policy list visible; active/inactive state filter still changes `#leavePolicyList`.
- Approval / requests:
  - `#/requests` — workspace enters without console errors; `#requestsFilterBar`, `#requestsKpiStrip`, `#requestsWorkspaceList`, and `#requestsUnifiedDetailPanel` render.
  - Toggle requests/document segment if `canUseRequestsDocumentApprovalMode()` allows it; document approval rows still load from `fetchRequestsDocumentRows()` / `fetchRequestsApprovalRows()`.
  - Status filter and detail drawer actions still preserve pending/in-progress/completed/rejected semantics.
- Documents:
  - `#/hr?segment=apply` — catalog + form visible; submit validation and disabled/eligibility reasons remain explicit.
  - `#/hr?segment=my-docs` — personal history table visible; download/view action remains available when row state permits.
  - `#/hr?segment=manage` — approval procedure editor + preview visible for authorized roles; template library remains secondary/hidden unless intentionally opened.
- Global:
  - Console errors: 0.
  - HTTP API errors: 0 except known benign SSE route interruptions if reproduced.
  - Horizontal overflow: false at 1366 and 1920.
  - `npm`/project verification: typecheck, focused frontend test/smoke, and lint on touched source files once leader applies the patch.

## Risks / implementation notes

- **Route regression risk is highest in Documents.** Prior audit found `apply` and `my-docs` collapsing into admin view; current `renderHrWorkspaceSegments()` + `renderHrScopeAndPanels()` separation is a win and should be locked before visual changes.
- **Status segmentation can regress Approval.** Do not expose both `#requestsStatusFilter` and `#requestsSecondaryTabsWrap` as equivalent workflow controls.
- **Leave policy filter can be simplified visually without changing state names.** Reusing `policyStatusTab` internally is lower risk than renaming state and event actions.
- **History chart demotion should preserve data rendering.** Move visual position only; avoid modifying `renderLeaveHistoryChart()` aggregation unless there is a separate bug.
- **Permissions matter.** Grants/settings/manage are manager/admin gated. Smoke tests need both employee and manager-capable states or must explicitly note unavailable surfaces.
- **No product source edits were made by this worker.** This report is intended as leader handoff evidence for a later integrated patch.
