# ARLS x Shiftee x Shople UI Gap Report

## Purpose

This report compares the current ARLS screen set against the user-provided Shiftee captures, the available Shople captures, `shople-arls`, `ui-redesign-guardrails`, and the ARLS Global Design Law. It is an analysis artifact only: no implementation is performed here.

## Inputs

- ARLS screenshot catalog: [arls-reference-action-layout-classification-20260412.md](/Users/mark/Desktop/rg-arls-dev/docs/design/arls-reference-action-layout-classification-20260412.md)
- Shiftee screenshot catalog: [shiftee-reference-action-layout-classification-20260412.md](/Users/mark/Desktop/rg-arls-dev/docs/design/shiftee-reference-action-layout-classification-20260412.md)
- Shople reference catalog: [shople-reference-action-layout-classification-20260412.md](/Users/mark/Desktop/rg-arls-dev/docs/design/shople-reference-action-layout-classification-20260412.md)
- Binding ARLS design law: [arls-global-design-law.md](/Users/mark/Desktop/rg-arls-dev/docs/design/arls-global-design-law.md)
- Team analysis artifacts:
  - [home-attendance.md](/Users/mark/Desktop/rg-arls-dev/output/arls-all-tabs-ui-reference-comparison/home-attendance.md)
  - [schedule-finance.md](/Users/mark/Desktop/rg-arls-dev/output/arls-all-tabs-ui-reference-comparison/schedule-finance.md)
  - [leave-approval-documents.md](/Users/mark/Desktop/rg-arls-dev/output/arls-all-tabs-ui-reference-comparison/leave-approval-documents.md)
  - [people-workplace-profile-notices-calendar.md](/Users/mark/Desktop/rg-arls-dev/output/arls-all-tabs-ui-reference-comparison/people-workplace-profile-notices-calendar.md)

## Non-negotiable Constraints

- Preserve ARLS routes, role permissions, tenant/site scoping, approval states, import/export behavior, Finance outcomes, and existing business actions.
- Use Shiftee and Shople as UI/interaction references only. Do not copy unsupported features.
- Follow the ARLS Global Design Law: one outer background plane, one white primary sheet, same-plane subdivision, divider rhythm by default.
- Do not reintroduce box-in-box, U-shaped tabs, decorative title icons, orange/tinted empty-state cards, or repeated launcher cards.
- Prefer tables/lists for operational comparison and triage; use detail panels/drawers for secondary metadata and actions.

## Executive Summary

ARLS already has most of the required product functionality. The main UI gap is consistency and hierarchy: Shiftee is table/workflow-first, Shople is visually light and compact, while ARLS still mixes dashboard cards, toolbar cards, nested panels, duplicated navigation CTAs, and large zero/empty states across many sibling tabs.

The highest-value next pass should not start by repainting colors. It should first normalize screen ownership:

1. Home becomes an operations inbox, not a passive dashboard.
2. Schedule and Attendance become list/calendar workspaces with compact toolbars.
3. Leave, Approval, and Documents become queue/list/editor surfaces with one status segmentation model.
4. People and Workplace become directory/list + right detail panel surfaces.
5. Reports remain table-heavy but gain cleaner toolbar and horizontal-scroll handling.
6. Settings/Profile split personal settings from admin/ops controls.

## Priority Map

| Priority | Surface Family | Improvement Needed | Reference Direction |
| --- | --- | --- | --- |
| P0 | Home | Convert from dashboard card wall to action-led operations inbox. | Shiftee home status modules + Shople compact dashboard; ARLS should show ranked work queue + small KPI strip. |
| P0 | Attendance daily | Move operational table/exception queue above decorative summary cards. | Shiftee date/record management; UKG-style exceptions. |
| P0 | Finance | Resolve ownership confusion: Finance is not a generic reports center. | Keep `제출/다운로드` as one Finance workflow; remove unrelated report/Apple-weekly competition. |
| P0 | Schedule upload / HQ upload | Wizard has too much repeated phase and box-in-box structure. | One step rail + one active canvas + footer actions. |
| P0 | Profile/Settings | Split personal account settings from admin/ops tooling. | Shiftee profile/account settings; Shople company settings. |
| P0 | Employee management | Replace dashboard-first composition with directory/list + detail panel. | Shiftee employee management + Shople people directory. |
| P1 | Monthly schedule | Calendar is correct hero but controls and state rhythm need tightening. | Shiftee schedule calendar + Shople schedule shell. |
| P1 | Schedule list | Treat as dense operational table, not secondary afterthought. | Shiftee schedule list. |
| P1 | Work templates | Convert to direct CRUD management table rhythm. | Shiftee template management. |
| P1 | Leave status/history/grants/settings | Remove mini-app layering; make lists/tables primary. | Shiftee leave accrual/history; Global Design Law. |
| P1 | Approval queues | Use one status segmentation model and compact queue summary. | Shiftee request history; ServiceNow-style queue/detail. |
| P1 | Documents | Preserve `apply`, `my-docs`, `manage` separation and reduce catalog/card heaviness. | Shiftee request create/history patterns. |
| P1 | Workplace/Site | Shift from infrastructure dump to readiness browser + detail panel. | Shiftee workplace management + Shople workplace reference. |
| P1 | Notices | Keep recent Shople-like shell; polish list/detail/compose separation. | Existing Shople-like notices reference captures. |
| P1 | Calendar | Keep calendar-first; add selected-day interpretation and compact legend/detail. | Shiftee schedule calendar + Shople calendar/schedule reference. |
| P1 | Reports/statistics | Keep table-first; improve horizontal scroll, sticky context, and tooltip clarity. | Shiftee real-time report. |
| P2 | Empty states | Collapse zero/no-data modules to same-plane empty states. | Global Design Law + Shiftee empty-state restraint. |
| P2 | Visual language | Add controlled blue/neutral selected-state grammar without repainting ARLS. | Shople blue/gray rhythm + ARLS orange only for primary CTA/brand. |

## Screen-family Findings

### Home

- Current problem: Home still reads as a passive dashboard with broad cards and duplicated route CTAs.
- Desired structure: context strip, ranked operations inbox, compact KPI/status chips, secondary summaries only where useful.
- Avoid: launcher cards, repeated `보기/열기`, text-heavy empty panels, giant zero-state blocks.
- Preserve: role-specific Home content, tenant scope, quick tab entry, background refresh/caching.

### Attendance

- Current problem: daily view and statistics spend too much height on summary/analytics before the actionable table.
- Desired structure: compact filter row, KPI strip, exception queue, attendance records list, right detail/drawer for row actions.
- Period/list/calendar/statistics should be sibling modes, not all primary dashboards.
- Avoid: giant charts when all values are zero, dash-row no-data rendering, routing attendance exceptions into generic document approval unless business logic requires it.
- Preserve: daily/period/calendar/statistics routes, filters, downloads, correction/review semantics, role scope.

### Schedule

- Current problem: monthly calendar is on the right path, but toolbar/actions/legend compete and list/templates feel secondary.
- Desired structure: calendar hero with at most two toolbar rows and one legend strip; list mode as table-first sibling; template management as dense CRUD table.
- Modals should stay focused: schedule add/edit should not become a large nested dashboard.
- Avoid: excessive top controls, weak selected-day interpretation, hidden DOM/route noise.
- Preserve: monthly/list switching, add/edit modal behavior, upload/download/template linkage.

### Finance

- Current problem: Finance appears under report-like wording and competes with unrelated reporting concepts.
- Desired structure: a Finance-owned workflow with only `제출` and `다운로드` local modes.
- Submit first screen should lead with target/month/eligible/blocked/selected and then site table.
- Download screen is closer to correct but needs compact loading/eligibility state.
- Avoid: Apple weekly/report-center mixing, repeated status chips as the first reading path, nested status cards.
- Preserve: submit/download eligibility, per-site state, first-confirmation download, final upload, generated file behavior.

### Leave

- Current problem: Leave reads as a mini-app with page section tabs, toolbar card, summary cards, and repeated headings.
- Desired structure: one leave workspace sheet, header + primary `휴가 신청`, compact KPI strip, aligned filters, dense table/list.
- Usage history should default to list/table; charts such as `사용 흐름` should be secondary or collapsible.
- Grants and settings should use mode controls/filters inside toolbar, not extra tab layers.
- Avoid: chart-first history, active/inactive local tabs for simple filters, boxed empty states.
- Preserve: leave request, grants, sync/download, settings/policies, manager/employee scope.

### Approval

- Current problem: Approval queues can double-segment by dropdown plus tabs and repeat state in row/status copy.
- Desired structure: one status segmentation model, compact queue summary, dense queue rows, detail/review panel.
- Row emphasis: type, requester, target date/period, elapsed time, current approver state, urgency.
- Avoid: card-like priority sections above list unless they add actionable difference.
- Preserve: approval transitions, detail drawer actions, filters, pending/in-progress/completed/rejected semantics.

### Documents

- Current problem: document issue/apply is clear but can become a card catalog; approval procedure editor may be dominated by template library.
- Desired structure: compact request catalog/list + selected form; my-docs as personal history table; approval procedure as focused rule editor.
- Preserve the recently fixed route separation: `apply`, `my-docs`, `manage`.
- Avoid: duplicating document domain between approval and document center except where approval inbox owns document approvals.
- Preserve: eligibility/quota, PDF/file generation, approval-policy editing, template upload/versioning.

### People / Employees

- Current problem: employee management starts with KPI cards and broad filters before the actual directory.
- Desired structure: directory-first list/table + persistent right detail panel.
- Filters should default to search, site, active status; role/company/inactive/deleted/bulk delete should be advanced/admin.
- Avoid: disabled destructive actions high on the page, raw field dumps, dashboard-first employee management.
- Preserve: registration/import, search/filter/sort, status, account linkage, detail drawer actions, permissions.

### Workplace / Sites

- Current problem: site rows expose too much infrastructure detail in the default table, and summary cards duplicate readiness state.
- Desired structure: site list + detail pane. Default row fields: name/code, company, employee count, active state, readiness badge.
- Move address, coordinates, radius, Wi-Fi, and criteria into detail sections.
- Avoid: coordinates as primary browsing text, repeated `준비 완료`, summary cards duplicating filter chips.
- Preserve: site create/edit, geofence, Wi-Fi, active/deleted filters, employee count, attendance criteria.

### Profile / Settings

- Current problem: personal profile/account settings and admin/operations tooling share visual family.
- Desired structure: `내 설정` default page for account identity/security/notification. Operations/admin tools moved into local subroutes or sections.
- Settings should feel like compact digital control panels, not paper checklists.
- Avoid: one-control-per-paragraph settings, developer/internal labels in default path, big checkbox rows for persistent booleans.
- Preserve: password/email, notification prefs, admin-only operational settings, groupware/profile generator behavior.

### Notices

- Current state: notices list/compose already has recent Shople-like improvements and should not be restarted from scratch.
- Desired structure: keep top category tabs/header CTA, polish empty list and compose metadata separation.
- Compose should keep title/body dominant; category/pin/publish can move into compact command/publish panel.
- Avoid: reintroducing card wall, hiding rich compose tools, duplicating category controls.
- Preserve: list/detail/compose routes, CRUD, image/table/poll/link, pinning, permissions.

### Calendar

- Current problem: calendar is clean but can feel like a blank grid without interpretation.
- Desired structure: calendar-first with compact toolbar, selected-day detail rail/bottom panel, meaningful legend/filter chips.
- Avoid: dashboard KPI cards above calendar or decorative chips without data meaning.
- Preserve: month/week/day toggles, today/prev/next, filters/fullscreen, event create/edit, external calendar behavior.

### Reports / Statistics

- Current problem: reports/statistics are dense and table-first, which is appropriate, but horizontal scroll context and tooltip/column readability need stronger handling.
- Desired structure: sticky identity/context columns, compact filters, clear horizontal scroll state, concise tooltips, optional saved column presets.
- Avoid: turning reports into card dashboards, over-charting, chart text inside plot area.
- Preserve: exports/downloads, report filters, all metric columns, sorting, long-width table behavior.

## Recommended Implementation Order

1. **P0 Home + Attendance first**: convert Home to operations inbox and Attendance to list/exception-first structure. This affects perceived product quality most.
2. **P0 Schedule upload / Finance ownership**: wizard plane reset and Finance IA cleanup. This fixes high-friction operational workflows without changing outcomes.
3. **P0 People/Profile split**: directory/detail and settings split. High-frequency admin surfaces, strong Shiftee reference coverage.
4. **P1 Leave + Approval + Documents**: queue/list/editor simplification while preserving approvals and HR document routes.
5. **P1 Workplace/Site + Calendar**: lower-risk structural polishing after employee pattern is set.
6. **P1/P2 Reports/Statistics and empty-state sweep**: apply shared table/empty-state polish across remaining wide tables and charts.
7. **P2 Visual-language pass**: controlled blue/neutral selected-state grammar after structures stabilize.

## Acceptance Criteria For Next UI Pass

- Every touched screen has one primary job and one obvious first action or first reading surface.
- No new box-in-box, U-shaped tabs, decorative title icons, or oversized empty-state cards.
- Filters and command bars are aligned, compact, and consistent across sibling screens.
- Tables/lists remain scannable with long Korean labels and dense real values.
- Existing ARLS routes, permissions, and business outcomes are unchanged.
- Playwright verifies first entry, re-entry, refresh/back-navigation, changed actions, and at least one representative business flow for each touched screen family.

## Open Decisions Before Implementation

- Whether the first execution slice should start with Home/Attendance or Schedule/Finance.
- Whether ARLS should adopt Shople blue directly for selected/active states, or use a more restrained ARLS-orange + blue-neutral hybrid.
- Whether Notices should be included in the first implementation slice or kept as a small later polish because it is already close.
