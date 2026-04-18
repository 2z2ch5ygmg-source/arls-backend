# Visual Verdict Template

## Metadata

- Date: 2026-04-16
- Status: Phase 1 Ralph execution artifact
- Governing workflow: Ralph visual task gate
- PRD: `.omx/plans/prd-arls-visual-grammar-remediation-20260416.md`
- Test spec: `.omx/plans/test-spec-arls-visual-grammar-remediation-20260416.md`
- Ledger links: VIS-001 through VIS-015
- Scope: every future visual slice in this remediation

## Purpose

This template prevents another static-pass/visual-fail cycle. A route can pass build, static guardrails, and route sweep and still be rejected by this verdict.

Use this for every implementation slice before closing a visual issue.

## Required Verdict Record

Save one verdict file per slice under:

`artifacts/global-ui-audit/phase5/evidence/<slice>/visual-verdict.json`

Use this JSON shape:

```json
{
  "slice": "",
  "date": "2026-04-16",
  "route_family": "",
  "screen_type": "Work List Type | Analytics Type | Wizard Type | Document/Form Type | Calendar Type",
  "calendar_exception": false,
  "ledger_items": [],
  "viewports": ["desktop", "768", "375"],
  "references": [],
  "before_screenshots": [],
  "after_screenshots": [],
  "checks": {
    "topbar": {
      "score": 0,
      "max": 15,
      "pass": false,
      "failures": []
    },
    "filter_row": {
      "score": 0,
      "max": 15,
      "pass": false,
      "failures": []
    },
    "table_list_axis": {
      "score": 0,
      "max": 15,
      "pass": false,
      "failures": []
    },
    "work_plane": {
      "score": 0,
      "max": 15,
      "pass": false,
      "failures": []
    },
    "divider_title_empty_state": {
      "score": 0,
      "max": 15,
      "pass": false,
      "failures": []
    },
    "action_row_and_hook_preservation": {
      "score": 0,
      "max": 10,
      "pass": false,
      "failures": []
    },
    "accessibility_and_text_integrity": {
      "score": 0,
      "max": 10,
      "pass": false,
      "failures": []
    },
    "cross_tab_consistency": {
      "score": 0,
      "max": 5,
      "pass": false,
      "failures": []
    }
  },
  "total_score": 0,
  "verdict": "REJECT",
  "category_match": false,
  "differences": [],
  "suggestions": [],
  "reasoning": "",
  "evidence": {
    "static_guardrail": "",
    "route_sweep_manifest": "",
    "action_state_manifest": "",
    "deployed_smoke_manifest": ""
  },
  "open_risks": []
}
```

## Scoring Rules

| Area | Max | Automatic reject if |
| --- | ---: | --- |
| Topbar | 15 | Any visible topbar item lacks icon or text; title/topbar/body order is broken. |
| Filter row | 15 | Default filter area wraps into two visual rows; sync/download/default sort remains in the default row. |
| Table/list axis | 15 | Header/body track centers do not align; mobile converts operational rows to cards. |
| Work plane | 15 | Touched sibling tabs mix `PRIMARY_WHITE_PLANE` and `TRANSPARENT_CANVAS` without approved exception. |
| Divider/title/empty state | 15 | Duplicate same-direction lines appear within 24px; page title repeats as section title. |
| Action row and hook preservation | 10 | A moved action loses its `data-action` hook or expected business result. |
| Accessibility/text integrity | 10 | Text clips, overlaps, active state collides with label, or focus target becomes ambiguous. |
| Cross-tab consistency | 5 | Sibling tabs in the same family use different grammar for the same component type. |

Pass threshold:

- `total_score >= 90`
- no automatic reject condition
- all ledger-specific required checks present

Any automatic reject sets `verdict` to `REJECT`, even if the numeric score is 90 or above.

## Schedule Board Auto-Reject Addendum

For schedule board/calendar redesign slices, also reject if any item is true:

- simple mode is not a toggle,
- detailed mode is not the default,
- simple monthly mode is not employee-by-date,
- simple monthly cells flatten vertically instead of preserving square/square-like rhythm or horizontal scroll,
- empty/no-work simple-mode cells use dark navy or another high-emphasis semantic fill instead of neutral gray,
- site/shift/employee filters sit inside an extra inner wrapper box within the main toolbar while each control also has its own border,
- month previous/next arrows are boxed controls visually detached from the month title row,
- week/day arrows move the month instead of the week/day context,
- default schedule legend is visible without an explicit active legend task,
- default legend includes off/holiday when the active task is not non-work explanation,
- legend color does not match the visible schedule rail/cell mark color,
- legend row is not vertically centered.
- empty-state text is not centered in the available blank area.

## Wizard Auto-Reject Addendum

For Wizard Type slices, also reject if any item is true:

- a sibling Work List/Calendar topbar is visible above the wizard route,
- the wizard mode selector is treated as a second same-level topbar when no valid primary topbar exists,
- step labels are placed beside markers while the connector line follows a marker-to-marker stepper grammar,
- a connector line crosses label text, crosses a marker visually off-center, or extends beyond the next marker,
- active/completed connector color extends into future incomplete steps,
- stepper width and active canvas width visibly mismatch without a responsive reason,
- one primary action appears twice in the same step,
- a single action is placed in a detached full-width footer band,
- file upload uses a native-looking browser file input inside an otherwise redesigned wizard,
- review/validation state shows blocked counts without visible blocker causes,
- preview table or blocked detail is hidden/cut off in the review step,
- screenshot evidence does not include every wizard step and at least one rejected/blocked review state.
- short labels such as `행 미리보기`, `기본 보기`, or `전체 보기` wrap into two lines,
- upload preview uses the old 8-column technical table instead of `위치`, `작성내용`, `영역/블록`, `유형`, `사유`,
- workbook issue rows do not show source coordinates,
- one source-cell/range problem is split into unrelated issue rows/cards,
- workbook value `0` is treated as an employee-match or support-count block when it is a no-demand/empty-slot signal,
- result chips include redundant gray subtitles,
- blocker counts are non-zero but default preview does not expose the blocker rows/reasons,
- `검토 필요` rows disable next/apply by themselves,
- `반영 불가능` is used for non-blocking review/protected rows or is not red,
- `미정` or blank support assignment fields are treated as blocking when a parseable `필요인원수` exists,
- completed step checkmarks are visually weak,
- active/completed stepper line extends beyond the current marker center,
- step marker is clipped by the stepper container.

## Manual Markdown Summary

Also save a human-readable file beside the JSON:

`artifacts/global-ui-audit/phase5/evidence/<slice>/visual-verdict.md`

Use this format:

```md
# Visual Verdict: <slice>

## Verdict

- Result: PASS | REJECT
- Score: <n>/100
- Screen type: <type>
- Ledger items: VIS-...

## Evidence

- Before:
- After:
- Static guardrail:
- Route sweep:
- Action audit:
- Deployed smoke:

## Law Checks

| Law | Result | Notes |
| --- | --- | --- |
| Topbar | PASS/FAIL | |
| Filter row | PASS/FAIL | |
| Table/list axis | PASS/FAIL | |
| Work plane | PASS/FAIL | |
| Divider/title/empty state | PASS/FAIL | |
| Action row/hooks | PASS/FAIL | |
| Text/accessibility | PASS/FAIL | |
| Cross-tab consistency | PASS/FAIL | |

## Differences

- 

## Required Fixes Before Close

- 
```

## Slice Gate

A future code slice cannot mark a visual issue closed unless this sequence is complete:

1. Classify the route by screen type.
2. Link the route to `filter-grammar-map-20260416.md`, `work-plane-consistency-map-20260416.md`, and `topbar-reference-set-20260416.md` when applicable.
3. Capture before screenshots.
4. Implement the slice without changing backend contracts or business outcomes.
5. Run static guardrail.
6. Run route sweep.
7. Run action-state audit for moved or hidden controls.
8. Capture after screenshots at desktop and 375px.
9. Fill this verdict.
10. Close the ledger item only if verdict is PASS.

## Rejection Conditions

Reject the slice if any item is true:

- static guardrail passes but screenshot still shows the failing visual pattern,
- topbar lacks icons,
- filter row becomes two rows,
- sync/download/default sort remains in the default filter row,
- title repeats,
- same-direction dividers appear within 24px,
- route family work planes remain mixed,
- table header/body axes are not shared,
- action hook or expected business result is lost,
- there is no before/after screenshot for the closed VIS item.
- a wizard-specific auto-reject condition above is present.

## Ralph State Requirement

For Ralph iterations, copy the key verdict fields into:

`.omx/state/arls-visual-grammar-remediation/ralph-progress.json`

Minimum state fields:

- current iteration,
- active phase,
- touched routes,
- changed files,
- visual verdict score,
- open failures,
- verification evidence paths,
- next required remediation.
