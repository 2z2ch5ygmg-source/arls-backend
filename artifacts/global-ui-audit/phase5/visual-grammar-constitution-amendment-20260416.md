# ARLS Visual Grammar Constitution Amendment

## Metadata

- Date: 2026-04-16
- Status: Draft amendment for ARLS Global UI Constitution v2
- Source interview: guardrail revision deep-interview, final ambiguity 1%
- Parent constitution: `docs/design/arls-global-ui-constitution-v2.md`
- Evidence audit: `artifacts/global-ui-audit/phase5/phase5-full-modified-elements-audit-20260416.md`
- Scope: all non-calendar ARLS frontend surfaces
- Calendar: regression-only exception remains unchanged

## Purpose

This amendment clarifies rules that were too abstract in the prior constitution. The goal is not for every tab to copy one exact layout. The goal is that every tab reads through the same limited visual grammar.

The top-level product rule is:

> All non-calendar tabs must read as one product, using a fixed set of screen types and fixed subcomponent laws.

## Authority

Apply this amendment in this order:

1. Active user instruction.
2. Shople reference, only when it does not conflict with the global visual grammar confirmed here.
3. This amendment.
4. `docs/design/arls-global-ui-constitution-v2.md`.
5. Local component precedent.

If a Shople reference exists but uses a pattern that would reintroduce ARLS inconsistency, use Shople as hierarchy/density reference only. The ARLS visual grammar remains binding.

## Screen Type Taxonomy

Only five screen types are allowed.

### 1. Work List Type

Use for:

- requests,
- approvals,
- leave history,
- finance submit/download,
- people,
- sites,
- document lists,
- operational queues.

Required sequence:

1. Page title
2. Icon topbar
3. One-row filter/command row
4. Table/list work area
5. Detail drawer, side panel, or bottom actions when needed

### 2. Analytics Type

Use for:

- attendance statistics,
- usage flow,
- dashboard-style summaries.

Required sequence:

1. Page title
2. Icon topbar
3. One-row filter/command row
4. Graph or metric frame
5. Drill-down table/list

### 3. Wizard Type

Use for:

- schedule upload,
- support-worker upload,
- finance submission flow.

Required sequence:

1. Page title
2. Stepper
3. Active canvas
4. Footer action row
5. Page-number pagination when row/site selection exceeds one page

### Wizard Type Addendum: Schedule Upload Failure Patterns

The following patterns are explicitly banned for Wizard Type screens, especially schedule upload and support-worker upload.

1. A sibling route topbar leaking into a wizard route fails. Example: `월간 근무표 / 목록` belongs to the monthly schedule surface and must not appear as a topbar above `스케쥴 업로드`.
2. If a wizard truly needs two navigation rows, the first row must be a valid icon topbar and the second row must be a bracket subbar. A stray calendar/list topbar above wizard mode controls is not a valid two-row topbar.
3. Wizard step markers and labels must read as one centered stepper system. A line that passes through label text or visually cuts through the marker/label group fails.
4. Step connector lines must connect only the space between adjacent step markers. A connector that extends beyond the next marker, crosses the next label, or appears as one long line through all step labels fails.
5. If step labels are visible, they sit centered below the marker by default. Label text placed beside the marker is allowed only when the entire stepper is designed as a compact segmented control and the connector line does not collide with the text.
6. A full-width footer bar is not allowed just to hold one primary button. Wizard actions must sit in the active form canvas or in a compact action row that shares the canvas width and visual grammar.
7. Stepper width and active form canvas width must align. A stepper that spans the route while the active form card is much narrower fails unless the stepper is intentionally centered to the same max-width container.
8. Native-looking file inputs, oversized blank template areas, and duplicate upload/analyze controls fail when they make the step feel like a legacy browser form instead of a business wizard.
9. Review steps must expose blocker reasons. A blocked/count summary without visible cause, row-level reason, or grouped issue explanation fails.
10. Analysis/review steps may not show duplicate primary actions in both the active canvas and a footer. One user action has one visible control.
11. Short UI labels that are words or compact phrases, such as `행 미리보기`, `기본 보기`, and `전체 보기`, must not wrap into multiple lines. If they cannot fit, the component width or layout must change.
12. Preview rows must identify the exact source cell or range, such as `F10` or `A3:A6`, when a workbook value causes an issue. Row-only references are insufficient when column context exists.
13. Related workbook issues caused by one cell or range must be grouped together. Splitting one source-cell problem into multiple unrelated rows/cards fails.
14. Upload preview tables use the minimum task columns by default: `위치`, `작성내용`, `영역/블록`, `유형`, `사유`. Extra technical columns are allowed only in an expanded technical view.
15. Result cells must not include low-value gray subtitles under the primary result chip/text. A result like `반영 예정` must not be followed by repeated secondary metadata unless it changes the user's next action.
16. Workbook value `0` in support worker slots or no-demand support cells is a normal empty/no-demand signal unless another meaningful payload makes it ambiguous.
17. Completed step checkmarks must be visually stronger than ordinary numeric markers. A tiny faint checkmark fails.
18. `차단` means a wizard-blocking reason that prevents applying/advancing. Every blocked count must have visible row-level or grouped blocker evidence in the review step. `검토 필요` is non-blocking and must not disable the next/apply action by itself.
19. Upload review result chips use only `반영 가능` and `반영 불가능`. `반영 불가능` is reserved for true blocker rows and must use red visual treatment; all non-blocking review/protected/reference rows use `반영 가능`.

### 4. Document / Form Type

Use for:

- document issue,
- my documents,
- policy registration,
- leave grant,
- employee/site create/edit,
- form sheets.

Required sequence:

1. Page title or sheet title
2. Icon topbar or step label when the form has modes
3. Grouped input controls
4. Validation/status
5. Submit/cancel actions

### 5. Calendar Type

Use for:

- ARLS schedule calendar,
- calendar routes.

Calendar is still regression-only. Do not force structure rewrite unless user explicitly reopens calendar redesign.

### Calendar Type Addendum: Schedule Boards

When the user explicitly reopens schedule calendar redesign, the calendar exception does not permit arbitrary visual grammar. The schedule board must still read as the same ARLS product.

1. Detailed schedule mode is the default.
2. Simple schedule mode is a toggle, not a separate topbar or primary tab.
3. Simple monthly schedule mode uses an employee-by-date matrix:
   - employee names on the vertical axis,
   - dates on the horizontal axis,
   - work days show only the scheduled hour value when the cell is numeric,
   - leave, half leave, day, night, and day-night mixed states may show text.
4. Simple monthly schedule cells must be square or maintain a square-like rhythm. If square cells cannot fit the viewport, horizontal scrolling is required; compressing cell height until the matrix becomes a flat strip fails.
5. Empty/no-work cells in simple schedule mode use a neutral gray fill. Dark navy or high-emphasis semantic color for empty days fails.
6. Month navigation arrows sit in the same row as the month title and do not use boxed button chrome unless the title itself is inside the same segmented control. Boxed arrow buttons visually detached from the month title fail.
7. Week and day views must have their own previous/next navigation semantics:
   - week view arrows move one week,
   - day view arrows move one day,
   - month view arrows move one month.
   Reusing month navigation semantics in week/day view fails.
8. Schedule legends are hidden by default. Day/night/mixed meaning should be communicated by the actual cell or rail styling, not by a separate pill row, unless the active task specifically requires a legend.
9. If a schedule legend is explicitly shown, its colors must match the schedule marks exactly:
   - day: green,
   - night: red,
   - day-night mixed: orange.
10. Data-empty states must be centered in the available empty area. Empty-state text attached to the top, bottom, or left edge of a large blank region fails.

## Universal Topbar Law

This law applies to every non-calendar top-level route and every major tab family.

1. The visible order is always:
   - page title,
   - topbar,
   - body.
2. The topbar is an independent row.
3. Every topbar item has an icon and a text label.
4. Icon-only or text-only topbar items fail.
5. Page title to topbar gap: 16px.
6. Topbar height: 40px.
7. Topbar to body gap: 16px.
8. Icon size: 16px.
9. Icon-to-text gap: 6-8px.
10. Page title, topbar items, buttons, and filters are vertically centered within their own row.
11. Repeated page and section titles fail.
12. If two topbars are consecutive:
    - first row: icon + text topbar,
    - second row: bracket-shaped secondary topbar.
13. If a topbar visually touches the title, body, or divider, it fails.
14. If the active topbar color or underline collides with text, it fails.
15. A topbar from a sibling surface must not appear on a route where it does not control the visible body. Example: monthly schedule topbar controls must not appear above schedule upload.

## Universal Filter Row Law

This law applies to every Work List, Analytics, and Document/Form screen unless the screen is a Wizard step.

1. Filters must fit in one row.
2. Two-line filter areas fail.
3. If controls do not fit in one row, remove, hide, or move lower-priority controls.
4. Required first-row filters:
   - period/date,
   - status,
   - employee/site,
   - search, only when search materially changes the list.
5. Controls banned from default filter row:
   - sync,
   - download,
   - basic/default sort,
   - low-frequency export,
   - debug/admin-only operations.
6. Sync buttons are banned from default UI. Sync must be automatic or refresh-driven.
7. Download may exist as:
   - row action,
   - toolbar action in a separate work action area,
   - more/actions menu.
8. Inputs, selects, date buttons, filter buttons, and search fields in one row must share visual height.
9. Controls in one row must share baseline and row-center alignment.
10. A search field must not expand only to fill empty width. It needs a bounded max width.
11. If one control is taller or wider than the row grammar, it fails.
12. If a filter or button touches the top or bottom divider instead of sitting in the vertical center of the row, it fails.
13. A default filter row may sit inside one outer work-plane/control-plane boundary. The failure is an additional inner wrapper box around a subset of already boxed controls, such as site/status/search being boxed together inside the outer toolbar.
14. Low-frequency boolean display preferences, such as simple/detailed schedule display, sit in the auxiliary toggle slot at the end of the filter row. They do not create a second filter group and do not replace primary data filters.

## Universal Table/List Axis Law

This law clarifies column alignment.

1. Header and body share one column grid.
2. Header and body content must occupy the same vertical column axis.
3. Long text columns may internally left-align text, but the text block itself must be centered within the column track.
4. Header centered and body left-flushed fails.
5. Body grouped separately from header fails.
6. Narrow screens use horizontal scroll.
7. Mobile card conversion is forbidden by default.
8. Empty-state rows must preserve the table/list geometry or become a separate same-plane empty state.

## Universal Divider Law

Use this instead of vague words such as "too much" or "overly".

1. Two horizontal lines in the same direction within 24px fail.
2. One UI group may use only one boundary type:
   - outer border,
   - top line,
   - bottom line.
3. Table header bottom line and first row top line cannot both exist.
4. Empty state has exactly one of:
   - same-plane text,
   - one independent empty block.
5. Empty block plus row separators above/below fails.
6. Page title and immediate section title with the same text fail.
7. Page title and section title with the same meaning fail unless the section title names a different object or state.
8. Modal/sheet visible boundaries are limited to:
   - header/body boundary,
   - body/action boundary,
   - one body internal section boundary when needed.
9. Sheet row separators must be at least 12px away from the sheet outer edge.
10. `line + empty block border + section border` around the same empty state fails.
11. Horizontal dividers are allowed only for:
   - topbar/body separation,
   - filter/table separation,
   - table header/body separation,
   - table row separation,
   - sheet header/body/action separation.
12. Any horizontal divider outside the allowed list fails.

## Universal Work Plane Law

1. Every non-calendar top-level route must have one primary white work plane unless explicitly classified as a modal/drawer/form exception.
2. Transparent canvas and white plane mixed across sibling tabs fail.
3. If one tab in a domain uses a primary white work plane, all sibling tabs in that domain use the same plane treatment.
4. Sheets and modals may be white exceptions, but their parent page must still follow its route-level plane rule.
5. Empty states sit on the current plane, not inside an extra mini-card unless the empty state is an independent module.

## Automatic Remediation Authority

The implementer may make these changes without asking again:

1. Delete repeated titles.
2. Delete duplicate dividers within 24px.
3. Move sync/download/default-sort buttons out of the default filter row.
4. Hide low-priority filters in an advanced filter or actions menu when one-row fit fails.
5. Standardize control heights and widths inside a filter row.
6. Center titles, topbars, filters, and buttons vertically in their row.
7. Convert text-only topbar items into icon + text items.
8. Add one primary work plane to route families that lack it.
9. Preserve `route`, `data-action`, backend behavior, permission gates, and business outcomes while moving or hiding controls.

## Non-Goals

These are not goals of this amendment:

- changing backend APIs,
- changing validation/business outcomes,
- changing calendar structure,
- adding new product features,
- replacing the product IA with Shople IA,
- using route sweep/static scan as the sole visual quality proof.

## Required Verification Additions

Future UI work must include:

1. static guardrail scan,
2. route sweep,
3. action-state screenshots for changed buttons/tabs/sheets,
4. visual issue ledger update,
5. explicit verdict against this amendment,
6. deployed smoke check when shipped.

Static scan passing is necessary but not sufficient.
