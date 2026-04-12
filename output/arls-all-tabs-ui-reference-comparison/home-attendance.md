# ARLS Home + Attendance Reference UI Comparison

Date: 2026-04-12
Worker: worker-1
Scope: read-only design analysis for `홈` and `출퇴근` surfaces. No product source was edited.

## Source evidence used

### ARLS evidence
- `docs/design/arls-reference-action-layout-classification-20260412.md`
  - Home: image 1 = top dashboard cards, image 2 = lower dashboard cards.
  - Attendance: image 5 = daily filter bar, image 37 = daily upper/middle, image 39 = daily lower records, image 33 = period list, image 35 = period calendar, image 12/14/19/42 = statistics.
- `output/playwright/arls-home-visual-pass-current.png`
- `output/playwright/arls-attendance-visual-pass-current.png`
- `output/playwright/current-home-audit.png`
- `output/playwright/current-attendance-daily-audit.png`
- `.omx/audits/task-1-home-attendance-audit.md`
- `.omx/context/arls-home-attendance-visual-language-gap-20260410T080000Z.md`
- `docs/design/arls-global-design-law.md`

### Reference evidence
- `docs/design/shople-reference-action-layout-classification-20260412.md`
  - `output/shople-home-reference.png` and `output/shople-home-direct.png` = Shople home dashboard reference.
  - Reference traits: light work surface, compact top toolbars, domain-local actions, list/detail or active-section patterns, avoid card walls and oversized empty states.
- `docs/design/shiftee-reference-action-layout-classification-20260412.md`
  - Home: Shiftee image 54 (`/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.14.18.png`) and image 56 (`... 오전 5.14.20.png`).
  - Attendance: image 20 (`... 오전 5.15.24.png`) monthly grid/table, image 32 (`... 오전 5.15.28.png`) detailed attendance list, image 35 (`... 오전 5.18.26.png`) my attendance records, plus report/statistics images 24/25/27/28/36/37/38/39/42/44/46/47.
  - Reference notes: Shiftee is table-first and workflow-first; use it for dense operational views, reports, schedule grids, approvals, management lists, and setting forms.
- `ui-redesign-guardrails` skill: one primary job per screen, action-led home surfaces, list/table over card walls for scanning/triage, compact aligned filters, remove duplicate helper copy and redundant navigation CTAs, preserve permission/business behavior.

## Priority summary

| Priority | Surface | Issue | Recommended direction |
| --- | --- | --- | --- |
| P0 | Home | Still reads as a passive dashboard/card wall rather than a Shople-like work launcher. | Convert first fold into a compact operations inbox: context strip + ranked work queue + small KPI/status chips. |
| P0 | Home + Attendance | Shople visual-language layer is under-specified in ARLS: weak icon semantics, little blue/neutral border rhythm, and muted module headers. | Add a controlled visual-language contract: semantic icon chips, Shople-like blue/gray emphasis rhythm, and stronger module headers while preserving ARLS brand/action semantics. |
| P0 | Attendance daily | Primary operational table is visually secondary to summary blocks and empty states. | Make filters + exception queue + employee attendance records the first working plane; summary becomes a compact strip. |
| P1 | Attendance period/list/calendar/stats | Analysis modes and no-data states occupy too much primary canvas. | Keep list-first attendance triage; move calendar/statistics to secondary modes with compact interpretation rails and drill-down links. |
| P1 | Home + Attendance | Navigation/action ownership is duplicated across sidebar, card CTAs, and local buttons. | Sidebar owns navigation; content owns contextual work actions through rows, chevrons, drawers, and explicit attendance exception actions. |
| P2 | Home + Attendance | Empty states and zero metrics over-render as large surfaces. | Collapse zero-data modules to one-line confirmations and compact placeholders; do not render dash rows or giant empty cards. |

## Detailed findings

### P0 — Home is not yet an operational inbox

**ARLS evidence**
- The current ARLS home screenshot shows large white modules for `출퇴근`, `오늘 스케줄`, `구성원`, and `근무지`, with repeated right-chevron module entries and zero/low-count blocks.
- `.omx/audits/task-1-home-attendance-audit.md` records four large cards (`오늘 운영 안정`, `요청·승인`, `오늘 스케줄`, `공지·조직`) that mostly show zeros and duplicate sidebar destinations.
- The ARLS catalog maps image 1 and 2 to home dashboard top/lower cards, not to an action queue or list/detail work surface.

**Reference evidence**
- Shople home (`output/shople-home-direct.png`) uses a compact neutral shell with a prominent first module, icon-led section identity, blue selected/accent treatments, thin gray/blue border rhythm, and a denser sequence of actionable modules.
- Shiftee home image 54/56 is also operationally dense: top status modules, leave/support/report tables, and compact links such as “전체 보기”, not a broad decorative card wall.
- UI guardrails explicitly prefer home/landing pages that are action-led rather than text-led and warn against repeated summary cards and dashboard layouts that stack sections vertically.

**Recommended direction**
1. Replace the current home card grid with a two-zone work plane:
   - Top strip: tenant/date/user/data-scope + unresolved counts.
   - Main left: ranked operations inbox combining attendance exceptions, approval waits, leave conflicts, unread notices, and schedule risks.
   - Main right: compact secondary summaries, not duplicate route launchers.
2. Render each inbox row as a work entry with exact destination/action, owner, count, and age/urgency.
3. Demote `출근 완료`, `승인 대기`, `미확인 알림`, etc. into compact chips or a KPI strip.
4. Remove generic `보기/열기` CTAs when the sidebar already owns that destination; use row/module chevrons only when the module itself owns a work item.

### P0 — Home/Attendance visual-language layer is weaker than Shople

**ARLS evidence**
- `.omx/context/arls-home-attendance-visual-language-gap-20260410T080000Z.md` records the explicit user concern: ARLS matched plane/entry ownership but still misses Shople recognizability because Shople has icons, blue key color, blue/gray border rhythm, and stronger module-header emphasis while ARLS remains text-heavy and flat.
- `output/playwright/arls-home-visual-pass-current.png` and `output/playwright/arls-attendance-visual-pass-current.png` show mostly plain text labels, low-contrast border divisions, sparse semantic icon usage, and orange concentrated mainly in selected navigation/CTA states.

**Reference evidence**
- Shople reference home uses a recognizable blue accent layer for selection/progress/state and soft gray boundaries around modules.
- Shiftee also uses stronger information-color semantics in dashboard numbers and table statuses without turning the page into decorative cards.
- ARLS global design law bans decorative title-left icons by default, but allows icons when they carry category/state meaning and recommends hierarchy through spacing, divider rhythm, type scale, alignment, and one-time accent use.

**Recommended direction**
1. Treat this as a **visual-language overlay**, not a new layout restart.
2. Borrow Shople’s blue/gray grammar more directly for structural state and module identity, while keeping ARLS orange for brand/primary CTA semantics:
   - Blue: selected/active work-state, progress, neutral-positive operational status, module header accent.
   - Gray: secondary borders/dividers and inactive module boundaries.
   - Orange: ARLS brand anchor and high-priority primary action only.
3. Add semantic icons/chips only for stable categories (`출퇴근`, `승인`, `스케줄`, `공지`, `예외`, `지연`) and align them consistently.
4. Avoid returning to decorative title icons, random icon boxes, gradients, or box-in-box surfaces. The icon must explain category/state; if it does not, omit it.

### P0 — Attendance daily buries the work table below dashboard content

**ARLS evidence**
- `output/playwright/arls-attendance-visual-pass-current.png` shows `출퇴근 날짜별` with date/filter controls in a large sheet, a broad `오늘 출퇴근` metric grid, then `우선 확인 예외`, then `직원별 출퇴근 기록`.
- The daily view’s operational table is present, but it is visually below summary blocks. In empty/low-data states, the primary canvas is dominated by cards and blank panels.
- The audit records that the `요청·승인` CTA routes to generic `#/requests?section=pending` / `문서 승인` rather than a focused attendance-exception queue.

**Reference evidence**
- Shiftee attendance record list image 32 is table-first: a compact date range/filter row, high-density column filters, aggregate work-time totals, and a dense records table.
- Shiftee monthly grid image 20 prioritizes the record grid itself and uses small controls above it rather than a large dashboard band.
- UI guardrails say scanning/triage/comparison jobs should use lists or tables and compact aligned filter bars, not card walls.

**Recommended direction**
1. Put date/site/employee/status filters and exception actions in one compact top command row.
2. Replace the large `오늘 출퇴근` grid with a single horizontal summary strip: `출근 대상`, `출근`, `미출근`, `정정 대기`, `지각`, `조퇴`, `휴가`.
3. Move `우선 확인 예외` directly under the filter/summary strip and render it as a compact exception queue.
4. Keep `직원별 출퇴근 기록` immediately below as the primary plane.
5. Replace generic `요청·승인` with local attendance actions: `정정 대기`, `미출근`, `미퇴근`, `예외 처리`, opening a focused drawer/detail panel rather than a generic approval route.

### P1 — Attendance period/calendar/statistics need clearer hierarchy

**ARLS evidence**
- The task audit records period list no-data rows as noisy dash rows before an empty-state message, calendar as a large canvas without a strong exception interpretation rail, and statistics as a detached analytics surface whose zero-value charts still consume premium space.
- ARLS catalog maps period list/calendar/statistics to separate attendance states, but the recommended lane should still be list-first.

**Reference evidence**
- Shiftee attendance/report references are dense table/report views with horizontal scroll, compact filters, and metric columns.
- Shople reference traits prefer list + detail, calendar + detail, or wizard + active-section patterns over card walls.

**Recommended direction**
1. Period list should be the default secondary attendance mode, with abnormal rows grouped first (`지각`, `조퇴`, `정정대기`, `미출근`) before full raw records.
2. Replace repeated dash rows with a single intentional empty block on the current plane.
3. Calendar should become a secondary visualization tab with a slim interpretation rail: anomaly counts, selected employee/site, and a jump to the exception list.
4. Statistics should pair every chart with a drill-down list and collapse zero-only charts into short summary rows.

### P1 — Action ownership is duplicated and weakens information scent

**ARLS evidence**
- The audit identifies repeated navigation across left accordion nav, home cards, and attendance-local CTAs.
- Current home modules repeat route-like actions instead of exposing meaningful inline work.

**Reference evidence**
- Shople reference traits explicitly say content should own the work action, not repeat the entire navigation.
- ARLS global design law says single-destination entry belongs to row/card/module/chevron, not redundant `보기/열기`.

**Recommended direction**
1. Sidebar remains the global navigation authority.
2. Home and Attendance content actions should be contextual work actions, not duplicate navigation labels.
3. Use chevrons for module drill-in only when the whole module represents a specific queue or detail list.
4. Use explicit destination labels only when a user would otherwise lose context, e.g. `정정 대기 보기` instead of generic `열기`.

### P2 — Empty/zero states should collapse, not dominate

**ARLS evidence**
- Current home and attendance screenshots show several zero-count or empty areas still taking full module height.
- The audit says zero-data states render as giant dashboards/cards/tables and feel like missing product structure.

**Reference evidence**
- ARLS global design law: default empty state sits on the current plane, uses icon + title + optional short copy only, and does not create a framed mini-card by default.
- UI guardrails: suppress placeholder summaries such as `-`, `없음`, and non-informative defaults from first-view summaries unless the missing state itself requires action.

**Recommended direction**
1. Collapse no-issue modules into a one-line confirmation with a subtle semantic icon.
2. Keep zero-state confirmations inside the existing plane; do not add framed empty cards.
3. Remove repeated dash rows from tables; prefer one empty row with action/next step only when action exists.
4. Use empty state copy only when it changes the user’s next decision.

## Must-not-break constraints

- Preserve ARLS routes, deep links, role behavior, permissions, approval states, import/export behavior, and Finance outcomes.
- Preserve `MASTER / platform_admin` data-scope clarity; if tenant context is shown, it must make the active data scope more trustworthy, not less.
- Do not reopen backend/business semantics unless a focused attendance action cannot be represented by existing data.
- Do not reintroduce box-in-box composition, U-shaped tabs, decorative title-left icons, orange/tinted empty-state cards, or giant empty cards.
- Do not use Shople as a feature-copy target; use it as a visual/hierarchy/reference system.
- If blue is adopted, use it as a controlled Shople-like operational accent layer. Do not repaint the entire ARLS product or mix random blue/orange/semantic colors.
- Keep attendance table/list comparison ability intact; dense records must remain scannable and export/download actions must remain discoverable.
- Keep content actions local: attendance exception actions should not unexpectedly route users into generic document approval unless that is still the intended business workflow and label.

## Implementation handoff checklist

- [ ] Define a Home `operations inbox` contract before editing CSS: row fields, priority order, destination/action, empty behavior.
- [ ] Define an Attendance `daily list-first` contract: compact filters, summary strip, exception queue, records table, local detail drawer/action destination.
- [ ] Define visual-language tokens: blue/gray border rhythm, semantic icon chip sizing, selected/active treatment, orange primary CTA role.
- [ ] Apply ARLS global design law during implementation: one outer plane, one primary sheet, same-plane subdivisions, divider rhythm by default.
- [ ] Validate at 1366×768 and 1920×1080 plus the primary desktop size.
- [ ] Re-test navigation, refresh/re-entry, filter changes, attendance row detail, approval/exception entry, export/download where present, and role-sensitive visibility.
