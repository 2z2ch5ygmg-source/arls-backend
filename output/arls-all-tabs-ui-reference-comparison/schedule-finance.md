# Schedule + Finance UI Reference Comparison

Date: 2026-04-12 KST
Worker: worker-2
Scope: ARLS Schedule screens (monthly calendar, list, upload wizard, templates), Finance submit/download screens
Mode: read-only analysis; no product source edits

## Evidence used

### Catalogs and rules
- `docs/design/arls-reference-action-layout-classification-20260412.md`
  - Relevant ARLS items: 3, 26-32, 34, 36, 38, 40-41, 43.
- `docs/design/shiftee-reference-action-layout-classification-20260412.md`
  - Relevant Shiftee items: 13, 29, 43, 48-50, 52-58 plus schedule/list/template references.
- `docs/design/shople-reference-action-layout-classification-20260412.md`
  - Relevant Shople captures: `output/shople-schedule-direct.png`, `output/shople-schedule-child-direct.png`, `output/shople-schedule-settings-direct.png`, `output/playwright/task4-shople-schedule-ref.png`.
- `docs/design/arls-global-design-law.md` and `/Users/mark/.codex/skills/ui-redesign-guardrails/SKILL.md`.
- Prior context: `.omx/context/arls-home-attendance-visual-language-gap-20260410T080000Z.md`, `.omx/audits/task-1-home-attendance-audit.md`, `.omx/audits/task-3-schedule-family-audit.md`, `.omx/context/arls-schedule-family-feedback-20260409T072613Z.md`.

### Visual captures sampled for this comparison
- ARLS current-ish evidence:
  - `output/playwright/phase5-schedule-calendar-deployed.png`
  - `output/playwright/phase5-schedule-upload-deployed-1920.png`
  - `output/playwright/phase5-schedule-hq-upload-deployed.png`
  - `output/playwright/phase5-schedule-templates-deployed.png`
  - `output/playwright/task4-finance-submit-current.png`
  - `output/playwright/task4-finance-download-current.png`
- Shiftee reference evidence:
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.14.37.png` — populated monthly schedule calendar
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.15.19.png` — schedule list/table view
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.15.06.png` — schedule add modal, template basis
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.17.54.png` — schedule template management
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.18.00.png` — schedule template add modal
  - `/Users/mark/Desktop/스크린샷 2026-04-12 오전 5.15.07 1.png` and `...5.15.08.png` — job/employee-basis add modal tabs
- Shople reference evidence:
  - `output/shople-schedule-direct.png`
  - `output/shople-schedule-child-direct.png`
  - `output/shople-schedule-settings-direct.png`
  - `output/playwright/task4-shople-schedule-ref.png`

## Executive verdict

ARLS Schedule + Finance has the right functional inventory, but the UI still reads as a shared mega-surface rather than focused child workspaces. Shiftee shows a schedule domain with dense calendar/list/table operations and modalized schedule creation; Shople shows lighter workspace ownership with compact local actions and blue/neutral state rhythm. ARLS currently over-exposes parent shell tabs, metadata tiles, status narration, and nested boxes—especially in the upload and Finance flows.

The next UI pass should **not** change schedule/Finance business semantics. It should reassert ownership:

1. `스케줄 > 월간 캘린더` = calendar/list work surface.
2. `스케줄 > Excel 업로드` = one strict wizard canvas.
3. `스케줄 > 지점별 업로드 확인` = one HQ handoff wizard canvas.
4. `스케줄 > 근무 템플릿` = dense CRUD management table.
5. `스케줄 > Finance` = Finance-owned submit/download workflow only, with Apple weekly reporting removed from this local context.

## Priority issues and recommended direction

### P0 — Finance ownership is split between Schedule and Reports

**ARLS evidence**
- Catalog items 30, 32, 34, 41, 43 classify Finance as schedule/finance wizard and table surfaces.
- `task4-finance-submit-current.png` and `task4-finance-download-current.png` show Finance under a `리포트` heading with local tabs `Finance 제출` / `Finance 다운로드`.
- Prior audit notes Finance is exposed as `스케줄 > Finance` in IA but implemented visually like a reports center, with Apple weekly reporting also competing in the same family.

**Reference evidence**
- Shiftee schedule references keep schedule actions inside a schedule domain; they do not combine unrelated report families into the same local tab row.
- Shople schedule references keep child route ownership clear: schedule list/detail/settings are separate schedule-owned surfaces.

**Problem**
- Users see two owners for the same workflow: sidebar says Schedule, page says Report.
- Finance submit/download become visually equivalent to unrelated report functions.
- This breaks the guardrail that one screen should communicate one primary user job.

**Recommended direction**
- Freeze Finance as a schedule child or a finance child, but do not present it as a generic report center.
- Inside Finance, allow only same-job local modes: `제출` and `다운로드`.
- Remove `Apple 주간보고` from the ARLS Finance local tab row and from any implementation plan for this ARLS surface.
- Keep the orange brand CTA only for the primary Finance action; use neutral/blue selected-state grammar for tabs and status emphasis.

**Must not break**
- Finance submission eligibility, target month/site scope, status counts, row selection, final upload state, and download eligibility logic.
- Existing routes/deep links until a planned IA migration explicitly maps them.

---

### P0 — Upload wizards still use box-in-box and duplicate phase meaning

**ARLS evidence**
- `phase5-schedule-upload-deployed-1920.png` shows:
  - a global page tab row,
  - a large status callout,
  - a metadata tile row,
  - a horizontal five-step box row,
  - and a lower active step panel nested inside the same page.
- `phase5-schedule-hq-upload-deployed.png` repeats the same shell for the HQ upload flow, with additional dense metadata tiles and a file input inside another bordered section.
- Catalog items 3, 26, 31, 34 classify these as upload wizard states.

**Reference evidence**
- Shiftee add-schedule modal references (5.15.06 / 5.15.07 / 5.15.08) use tab-like bases for the creation mode and keep the modal canvas focused on the current scheduling action.
- Shople settings and schedule references are light: one primary canvas, restrained dividers, compact command bars.
- UI guardrails specifically warn that wizard flows should be sequence problems first, not layers of cards and repeated phase labels.

**Problem**
- The stepper, status band, `현재 단계`, `STEP 1`, helper text, and metadata tiles repeat the same stage information instead of making the next action clearer.
- The current surface violates ARLS global law’s default plane grammar: one outer background plane + one white primary sheet + same-plane subdivision.
- The first screen feels like a dashboard about the wizard, not the wizard itself.

**Recommended direction**
- Collapse each wizard to a single primary sheet with:
  1. a compact, connected step rail,
  2. one active-step header,
  3. one active-step canvas,
  4. footer actions aligned consistently (`이전`, `다음`, `적용`, etc.).
- Convert metadata tiles into a single compact context strip: tenant/site/month/file/revision only when needed for the current decision.
- Remove repeated “blocked reason / next action” cards when the disabled CTA and active step already communicate the same state.
- Attach labels such as `STEP 1` directly to their governed section or replace them with the step rail’s selected state.
- Keep explanatory copy inline and local to the field or upload control that needs it.

**Must not break**
- Excel upload sequence: mapping profile → target selection → file preparation → review → apply.
- HQ/support upload sequence: source status/check → extraction/download → workbook upload → preview/review → complete.
- File validation, row classification, mismatch/blocked reasons, review counts, and apply outcomes.

---

### P1 — Monthly calendar is the right hero surface, but ARLS hierarchy is too muted and control-heavy

**ARLS evidence**
- `phase5-schedule-calendar-deployed.png` shows the calendar as the dominant workspace, but it is preceded by a heavy header/action row and has pale event cards that lose contrast under drawer overlays.
- Catalog item 29 maps ARLS monthly schedule calendar to Shiftee schedule calendar; item 40 maps the list view.

**Reference evidence**
- Shiftee populated monthly calendar (5.14.37) is schedule-first: compact month navigation, filters, download/upload/add actions, day cells filled with legible shift blocks, and a crisp local day/week/month switch.
- Shiftee list view (5.15.19) is table-first with compact filters and dense rows.
- Shople schedule direct/child references favor compact local action bars and a clear selected surface.

**Problem**
- ARLS still feels like a canvas with many equal-priority controls rather than a calendar-first operational board.
- The month/list switch, filters, legend, download/upload/add, and detail drawer compete instead of forming one toolbar system.
- Pale green/gray shift cards and low-contrast labels make the schedule look less decisive than Shiftee’s dense gray blocks or Shople’s blue selected/active rhythm.

**Recommended direction**
- Keep the calendar as hero for monthly schedule.
- Limit top controls to two rows plus one compact legend strip at most:
  - row 1: title/month nav/view switch + primary action cluster,
  - row 2: site/work-type/leave filters,
  - legend strip: shift colors and only necessary counters.
- Use stronger event card typography and a more deliberate selected-day outline/border rhythm.
- Convert the detail drawer into the primary inspect/edit surface; avoid large dim overlays unless a modal requires exclusive focus.
- Treat list mode as a sibling mode with the same command bar grammar, not a separate dashboard.

**Must not break**
- Month navigation, list/calendar switching, site/work-type/leave filters, download/upload/add actions, and schedule edit/detail drawer behavior.

---

### P1 — Schedule list should be a dense operational table, not a secondary afterthought

**ARLS evidence**
- Catalog item 40 identifies the monthly schedule list view.
- Prior audit says ARLS monthly route mounts too many hidden sibling sections and has hundreds of hidden/main nodes, which weakens DOM order and interaction clarity.

**Reference evidence**
- Shiftee list view (5.15.19) is a dense table with column filters for employee, date, time, site, team, template, worked hours, and break time.
- UI guardrails recommend lists/tables when the job is comparison, scanning, triage, or operational management.

**Problem**
- If ARLS keeps list mode as a visual secondary toggle under a calendar-heavy shell, users who need table scanning lose the strongest Shiftee pattern.
- Hidden DOM siblings and broad parent shell controls risk stale headings and slow interactions.

**Recommended direction**
- Give list mode a table-first canvas with sticky/compact filters and column sizing that avoids vertical Korean text wrapping.
- Preserve the same route owner and toolbar, but let the list body own the remaining viewport.
- Add row-level inspect/edit affordances through a drawer, not a separate top-level modal unless existing behavior requires exclusivity.

**Must not break**
- Current list filters, date range/month scope, row identities, export/download, and detail opening semantics.

---

### P1 — Work templates need a Shiftee/Shople admin-table rhythm

**ARLS evidence**
- `phase5-schedule-templates-deployed.png` and catalog item 36 show work template management currently embedded under the broader `근무일정` top shell and tab row.

**Reference evidence**
- Shiftee template management (5.17.54) is a direct management table with side category navigation, top download/upload/add actions, search filters, compact rows, and color chips.
- Shiftee template add modal (5.18.00) keeps the add flow compact.
- Shople schedule settings (`output/shople-schedule-settings-direct.png`) uses a table/list management area plus command buttons in the schedule settings domain.

**Problem**
- ARLS template management is functionally simple but visually inherits too much family-level weight.
- The route title and top tabs make it feel like another mode in a schedule bundle rather than a CRUD admin surface.

**Recommended direction**
- Land directly on `근무 템플릿` as a dense management table.
- Keep one clear `템플릿 생성` primary CTA; put import/export as secondary utilities.
- Use color chips and compact columns for shift identity, time, site/team applicability, linked workers, and latest update.
- Prefer an edit drawer or compact modal for template add/edit; do not expand a separate card stack on the main page.

**Must not break**
- Template creation/editing/deletion, site/team applicability, color semantics, upload/download, and schedule linkage.

---

### P1 — Finance submit opens too table-heavy for a guided submission job

**ARLS evidence**
- `task4-finance-submit-current.png` shows a broad table immediately after title/status counts, with the primary `지점 선택 후 시작` CTA on the right.
- Catalog items 30 and 41 map Finance submit wizard/status and site table surfaces.

**Reference evidence**
- Shiftee schedule/work report references are table-first when the user is scanning records, but guided submissions should still communicate current state, next action, and target selection clearly.
- UI guardrails recommend validation list + result panel or step-by-step wizard for upload/submission flows.

**Problem**
- The table is useful but currently competes with the wizard start action instead of supporting it.
- Status chips (`제출 전`, `미다운로드`, `미업로드`) are legible but visually repetitive across many columns.
- The user’s first action—choose target site(s) and start—is not the dominant reading path.

**Recommended direction**
- Make the first submit screen a compact submission overview:
  - target month,
  - eligible/blocked counts,
  - selected site count,
  - primary `제출 시작하기` CTA,
  - then the site status table.
- Keep the table for operational audit and selection; compress repetitive status chips with consistent semantic badges.
- Once a site is selected, transition into a focused wizard/review panel rather than adding another nested card below the table.

**Must not break**
- Site selection, per-site status columns, submission count semantics, first/download/final upload status, and month/site filters.

---

### P2 — Finance download is closer to a table-led pattern but needs clearer status and empty/loading handling

**ARLS evidence**
- `task4-finance-download-current.png` shows a clear table shell with a target month selector and primary `Finance 자료 다운로드` CTA, but the table is in a “loading upload status” state inside a large blank region.
- Catalog item 43 maps Finance download modal/progress and item 32 maps the download step.

**Reference evidence**
- Shople and Shiftee table-first admin/report references support a compact table-led structure when selection/download is the job.
- UI guardrails warn against oversized empty/loading regions and placeholder summaries that consume primary space.

**Problem**
- The core pattern is acceptable, but blank loading rows make the screen feel unfinished.
- The target month and primary CTA alignment is clear, yet the table body lacks a compact summary of what is eligible, blocked, or missing.

**Recommended direction**
- Keep the table-led download structure.
- Add a compact status strip above the table only if it adds actionable information: eligible sites, missing upload, last generated, selected rows.
- Use skeleton rows or a short inline loading state instead of a large blank table body.
- Keep download progress in a focused modal or inline result panel; do not create another full nested card.

**Must not break**
- Download eligibility, latest upload criteria, generated file link, progress/result handling, and month/site scope.

---

### P2 — Visual-language layer needs stronger blue/neutral rhythm without violating ARLS plane law

**ARLS evidence**
- Schedule/Finance captures lean heavily on pale orange accents and text-first labels.
- Upload wizards use many bordered boxes but still lack a strong selected/active grammar.

**Reference evidence**
- Shiftee schedule references use deep blue navigation, crisp table grid lines, strong selected tabs/buttons, and high-contrast schedule blocks.
- Shople references use blue selected states, compact button emphasis, icon-led navigation, and neutral sheets with restrained borders.
- Prior home/attendance visual-language context notes the product needs icon/accent/border/module-header grammar, not only structural similarity.

**Problem**
- ARLS has many lines and boxes but not enough intentional state hierarchy.
- Orange is used for navigation/selection/CTA-like emphasis in several places; this can make all emphasis feel equally loud.

**Recommended direction**
- Adopt a system-level `blue/neutral selected-state grammar` for schedule/Finance tabs, focused controls, active steps, and table selection.
- Reserve orange for brand accents and true primary action where it improves recognition, not every selected or active state.
- Use icons only where they carry category/state meaning: upload, download, calendar, template, warning, complete.
- Use border hierarchy sparingly: one primary sheet border, dividers within it, status badges/chips for row semantics.

**Must not break**
- ARLS brand recognition, accessibility/contrast, and semantic status color distinctions.

---

## Recommended implementation order

1. **Finance ownership cleanup**: remove reports/Apple-weekly competition from the Finance surface; keep `제출/다운로드` as same-job local modes.
2. **Wizard plane reset**: schedule upload and HQ upload to one step rail + one canvas; no nested status-card stack.
3. **Monthly calendar/list toolbar consolidation**: calendar remains hero; list becomes table-first sibling with the same toolbar grammar.
4. **Template admin reset**: direct CRUD table with one primary create CTA and compact secondary import/export actions.
5. **Visual-language pass**: selected/active blue/neutral rhythm, restrained iconography, better event/status badge hierarchy.

## Must-not-break constraints for all later work

- Preserve routes, role permissions, tenant/site/month scoping, deep links, and business outcomes.
- Preserve schedule calendar/list data, event edit/add modals or drawers, and shift/template linkage.
- Preserve Excel upload and HQ upload workflow order, validation gates, row classification, blocked reasons, mismatch review, and apply/complete outcomes.
- Preserve Finance submit/download eligibility, status counts, per-site status semantics, file generation/download behavior, and persisted upload state.
- Do not reintroduce box-in-box, U-shaped tabs, decorative title icons, oversized empty-state cards, or duplicate navigation cards.
- Do not mix ARLS Finance with Sentrix-only Apple weekly reporting.
- Keep Shiftee/Shople as UI hierarchy and interaction references, not feature-copy targets.
