# Filter / Topbar / Table / Divider Law

## Metadata

- Date: 2026-04-16
- Status: Draft law for immediate use
- Parent: `visual-grammar-constitution-amendment-20260416.md`
- Scope: all non-calendar ARLS frontend surfaces

## 1. Topbar Component Contract

### Required DOM/Visual Structure

Every topbar is a row with:

- item icon,
- item text,
- active state,
- optional count/badge only when it changes the current user decision.

### Fixed Measurements

- topbar height: 40px
- page title to topbar gap: 16px
- topbar to body gap: 16px
- icon size: 16px
- icon/text gap: 6-8px
- active underline thickness: 2px if underline style is used
- active underline to text minimum vertical gap: 8px

### Pass Criteria

- All topbar items include icons.
- Topbar row is vertically centered.
- Topbar does not touch title or body separator.
- Active indicator does not overlap text.
- Only one topbar row exists unless a secondary submode is required.

### Fail Criteria

- text-only topbar item,
- icon-only topbar item,
- topbar within 8px of title text,
- topbar within 8px of body/filter line,
- active color line touching text,
- repeated page/section title near topbar,
- two same-level topbars.
- a sibling screen's topbar remains visible on a route where it does not control the body, such as `월간 근무표 / 목록` on a schedule upload wizard.

### Two Topbar Rule

When two topbars are consecutive:

1. First topbar: icon + text topbar.
2. Second topbar: bracket-shaped secondary topbar.
3. Second topbar is only allowed for a true submode, not for another status filter that duplicates a select.

## 2. Filter Row Component Contract

### Required Structure

One filter row contains only essential controls.

Allowed default controls:

- period/date,
- status,
- employee,
- site,
- bounded search.

Optional controls:

- one primary work action only when it is the current task.

Disallowed default controls:

- sync,
- download,
- default/basic sort,
- low-frequency export,
- debug/admin-only action.

### One-Row Law

- A filter area must fit in one row.
- Two filter rows fail.
- If controls cannot fit, move lower-priority controls to advanced filter or actions menu.
- Do not create a second visual row for overflow.

### Control Sizing

All controls in the same filter row must share:

- height,
- border radius,
- border weight,
- vertical center,
- label placement.

Search width:

- max width is bounded by expected input length.
- search must not stretch to fill unused horizontal space by default.

### Pass Criteria

- all controls have equal height,
- controls sit in the row center,
- labels align,
- controls read as one block,
- no control touches top or bottom divider,
- no sync button in the default row.

### Fail Criteria

- controls split into two visual rows,
- one control taller than others,
- search field significantly wider than its job,
- sync/download/default sort in primary row,
- filter row attached to a divider,
- top row and bottom row read as separate filter groups,
- an inner filter-cluster box wraps already boxed inputs/selects/buttons inside the main toolbar plane,
- a low-frequency display preference creates a second boxed control group.

### Schedule Board Filter Addendum

For schedule board screens:

- `상세` is the default mode.
- `간단 표기` is a single toggle placed at the end of the one-row filter/control row.
- `간단 표기` must replace lower-priority display toggles such as `휴가 표시`; do not show both in the primary row.
- The month title and previous/next arrows are one inline navigation group. Previous/next arrows must not be boxed square buttons detached from the month title.
- Site, shift, and employee filters must sit inside the main toolbar/control plane. Keep the main outer toolbar boundary when it defines the row, but do not wrap those filters in a second bordered inner container.
- Week/day board navigation must change the week/day context, not the calendar month.

## 3. Table/List Axis Contract

### Column Axis Rule

Header and body use one shared column definition.

For every column:

- header label center point and body content block center point align on the same x-axis.
- body text can internally align left only inside its own centered content block.
- no row cell starts at a different x-axis than the header track.

### Narrow Width Rule

- Use horizontal scroll.
- Do not convert operational rows to cards by default.
- Do not stack column values vertically under unrelated headers.

### Empty State Rule

If a table/list has no data:

- keep header visible when it helps users understand structure,
- show one empty state on the same plane,
- do not create a separate card with additional borders when the table already has a boundary.

### Pass Criteria

- header/body share track widths,
- checkbox/status/date/numeric tracks stay stable,
- selected/hover applies across full row,
- empty state does not break column structure.

### Fail Criteria

- header centered but body left-flushed,
- body starts under wrong column,
- status pill shifts later columns,
- empty-state block plus table border plus row separator all visible,
- mobile card conversion.

## 4. Divider Contract

### Allowed Uses

Dividers may appear only as:

- topbar/body separator,
- filter/table separator,
- table header/body separator,
- table row separator,
- sheet header/body/action separator.

### Quantitative Rules

- same-direction horizontal dividers less than 24px apart fail.
- row separator must be at least 12px from a sheet edge.
- one UI group may have only one boundary type.
- table header bottom line and first row top line cannot both be visible.

### Title Rules

- page title duplicated as section title fails.
- same-meaning title repeated immediately below topbar fails.
- title must sit vertically centered in its row.
- title cannot be attached to a divider with uneven top/bottom spacing.

### Empty State Rules

Empty state can be:

1. text on same plane,
2. one independent empty block.

It cannot be:

- empty block with section border and row separator,
- empty mini-card inside another bordered area,
- a framed block touching table lines.

## 4.5 Wizard Stepper Line Contract

This contract exists because a wizard can pass static checks while the stepper still reads as broken.

### Required Structure

- Step markers are centered on one horizontal axis.
- Visible labels, when present, are centered under each marker.
- Connector lines exist only between adjacent marker centers.
- Connector lines stop before the next marker and never run through label text.
- Completed connector color applies only to the completed segment between completed/current markers.

### Fail Criteria

- connector line passes through the step label text,
- connector line passes above or below the marker center enough to read as detached,
- connector line extends past the next marker or into a future label,
- marker labels sit beside the marker while the line uses below-label stepper geometry,
- active/completed line color continues beyond the current step,
- marker, label, and connector are not centered as one stepper system.
- current/completed connector color extends beyond the current marker center,
- step marker is clipped by the top or side of the stepper container,
- completed checkmark is smaller or visually weaker than the numeric marker it replaces.

## 5. Action Row Contract

### Vertical Center Rule

All action rows sit vertically centered in the space between adjacent boundaries.

Fail if:

- button row is visually attached to top divider,
- button row is visually attached to bottom divider,
- action row top/bottom spacing differs by more than 4px.
- a full-width footer/action band is introduced solely to contain one button,
- the footer/action band is wider than the active wizard canvas without a structural reason,
- the same primary action appears both inside the canvas and in the footer.

### Upload Preview Row Contract

For upload/review preview tables:

- Default visible columns are `위치`, `작성내용`, `영역/블록`, `유형`, `사유`.
- `위치` must use workbook coordinates when available, for example `F10` or `A3:A6`.
- `사유` should include the problematic coordinate in parentheses when it names a missing or invalid value.
- Related errors from the same workbook cell/range are grouped together.
- Short labels and toggle labels never wrap.
- Default/All view controls use a toggle or segmented control shape, not two loose buttons.
- Result chips do not include redundant gray subtitles below them.
- Blocker rows are the only rows that may show `반영 불가능`, and their reason text must be visually red.
- A non-zero blocker summary with no visible blocker rows in the default review preview fails.
- `검토 필요` rows are not blockers and must remain able to proceed unless a separate true blocker exists.

### Default Action Visibility

Default visible actions:

- primary current task,
- cancel/back when inside modal/sheet,
- confirm/apply when inside modal/sheet.

Default hidden/moved actions:

- sync,
- download,
- default sort,
- low-frequency export.

## 6. Calendar Legend Contract

This contract applies when a calendar or schedule board uses a legend.

### Required Rules

- Legend row is vertically centered within its available row.
- Legend colors match the actual marks used in the calendar/list cells.
- Only visible decision-relevant schedule states appear in the default legend.
- Schedule board default legend is hidden unless the active task specifically requires a legend.

### Fixed Schedule Colors

- Day: green.
- Day-night mixed: orange.
- Night: red.
- Off/holiday: hidden by default.

### Fail Criteria

- Legend pill color differs from the visible schedule rail/mark color.
- Off/holiday appears in the default schedule legend when non-work states are not the active task.
- Legend is visually attached to the upper or lower divider instead of sitting in the row center.
- Legend uses a different naming system than the schedule cells.

## 7. Empty State Contract

When a work area has no rows, cards, or events:

- Empty text or empty illustration sits in the visual center of the available blank area.
- Same-plane empty states may use one boundary, but the message itself must be centered.
- Large blank calendar/timeline/list areas with empty text attached to the top edge fail.

## 8. Automatic Fix Priority

When a screen fails these laws, fix in this order:

1. remove duplicated title,
2. normalize topbar,
3. reduce filter row to one row,
4. normalize control sizes,
5. remove duplicate dividers,
6. establish work plane,
7. align table/list axes,
8. verify actions still work.
