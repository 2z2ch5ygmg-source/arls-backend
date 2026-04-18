# Visual Issue Ledger

## Metadata

- Date: 2026-04-16
- Status: Open
- Governing criteria:
  - `visual-grammar-constitution-amendment-20260416.md`
  - `filter-topbar-table-divider-law-20260416.md`
  - `docs/design/arls-global-ui-constitution-v2.md`
- Scope: all non-calendar ARLS frontend surfaces modified or touched in Phase 5

## Legend

- `OPEN`: issue still needs remediation.
- `BLOCKED`: issue needs a product decision or missing reference.
- `CLOSED`: issue has before/after evidence and verification.
- `TECH PASS / VISUAL FAIL`: route/action works, visual law fails.

## Ledger

| ID | Status | Severity | Surface | Evidence | Violated Law | Problem | Required Remediation | Verification Needed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VIS-001 | OPEN | P0 | Leave history filters | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.24.48.png` | Filter Row Law | Filter/action controls split across visual rows; sync/download/default controls are visible in default row. | Reduce to one row; remove sync; move download/default sort to actions menu or secondary action surface. | before/after screenshot, route sweep, action click for remaining controls |
| VIS-002 | OPEN | P0 | Leave request/history table | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.24.37.png` | Table/List Axis Law | Header columns are visually centered but row/empty-state treatment does not preserve a shared table plane. | Align empty state with table geometry or make same-plane empty text; remove extra empty block border if table boundary exists. | screenshot comparison, table axis check |
| VIS-003 | OPEN | P0 | Requests/leave table headers | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.24.37.png` and route captures | Table/List Axis Law | Column header/content alignment has been interpreted inconsistently; some text blocks start at left edge of column instead of centered within track. | Define centered content block per column; long text may left-align internally only inside centered block. | screenshot with header/body overlay or measured x-axis report |
| VIS-004 | OPEN | P0 | Attendance topbar exemplar vs leave topbar | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.24.58.png`, `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.25.14.png` | Topbar Component Contract | Leave topbar lacks required icon-per-item treatment and correct independent topbar row rhythm. | Convert all non-calendar topbars to icon + text items with fixed spacing and 40px height. | before/after screenshot for each topbar family |
| VIS-005 | OPEN | P0 | Leave topbar spacing | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.25.14.png` | Topbar Fixed Rhythm Law | Title/topbar/body spacing is uneven; topbar reads as text attached to title/line rather than a row. | Enforce title-to-topbar 16px, topbar height 40px, topbar-to-body 16px. | measured screenshot or CSS token check |
| VIS-006 | OPEN | P0 | Requests empty table | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.25.24.png` | Divider Contract | Duplicate horizontal separators and empty-state block boundary appear in the same local area. | Apply 24px duplicate-line rule; keep only one boundary around empty state/table group. | screenshot comparison |
| VIS-007 | OPEN | P0 | Leave grants | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.25.47.png` | Two Topbar Rule / Divider Contract | Primary topbar and secondary tab row are not using the required first-row icon topbar plus second-row bracket-shaped subbar grammar. | Implement topbar/subbar hierarchy across leave tabs. | before/after screenshot, topbar item icon check |
| VIS-008 | OPEN | P0 | HR My Documents | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.26.37.png` | Title Rule / Divider Contract | `내 문서` title appears twice; row separators and sheet/table boundaries visually merge. | Delete repeated title; retain one header; reduce row separators or strengthen single table plane. | screenshot comparison, title duplicate scan |
| VIS-009 | OPEN | P0 | Finance topbar | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.27.26.png` | Topbar Component Contract | This is the desired topbar shape: title then icon topbar. Other surfaces must match this grammar. | Use as positive reference for topbar normalization. | reference snapshot attached to topbar law |
| VIS-010 | OPEN | P0 | Finance submit spacing | `/Users/mark/Desktop/스크린샷 2026-04-16 오후 12.27.51.png` | Section Vertical Rhythm / Filter Row Law | Title top/bottom spacing differs; target-month controls sit close to upper boundary with uneven row vertical rhythm. | Center title/filter/action rows within fixed row heights; enforce equal top/bottom row padding. | measured screenshot or CSS token check |
| VIS-011 | OPEN | P0 | Global filters | full action audit captures | Filter Row Law | Filters still differ by module: leave, requests, finance, HR, attendance use different control heights and grouping. | Create shared filter row primitive and migrate domains. | cross-route screenshot matrix |
| VIS-012 | OPEN | P0 | Global work plane | full action audit captures | Work Plane Law | Some routes use visible white work plane, others float on gray background. | Create route-family work-plane map and normalize each family. | work-plane consistency map and screenshot matrix |
| VIS-013 | OPEN | P1 | Home background requests | `artifacts/global-ui-audit/phase5/evidence/full-modified-elements-route-sweep/20260416-1207-arls-ui-cleanup/network.json` | Interaction Law | Home 375 route has aborted background requests during sweep. | Determine if test teardown artifact or real entry timing issue; suppress/await/cancel background requests cleanly. | rerun route sweep with network 0 |
| VIS-014 | OPEN | P1 | CSS override accumulation | phase5 source diffs | Process Gate | Many fixes use end-of-file overrides and escaped selectors rather than shared primitives. | Replace ad hoc terminal overrides with shared primitives after grammar is finalized. | source diff review and regression sweep |
| VIS-015 | OPEN | P0 | Visual-verdict process | phase5 process history | Ralph Visual Gate | Visual changes shipped without formal visual-verdict loop. | Add visual verdict or equivalent structured screenshot verdict before future edits. | verdict JSON per edited visual slice |
| VIS-016 | OPEN | P0 | Schedule upload wizard topbars | user report 2026-04-18 and `/schedules/upload` screenshots | Topbar Reference Set / Wizard Type Addendum | `월간 근무표 / 목록` topbar appears on schedule upload even though it belongs only to monthly schedule. | Remove sibling topbar from upload routes; if upload has its own mode selector, it must be the only valid wizard mode selector or a properly bracketed subbar under a real primary topbar. | desktop/375 screenshots for base and support upload |
| VIS-017 | OPEN | P0 | Schedule upload wizard stepper | user report 2026-04-18 and `/schedules/upload` screenshots | Wizard Stepper Line Contract | Step labels sit beside markers and connector lines run through marker/text areas instead of cleanly connecting between adjacent steps. | Redesign stepper with centered markers, labels below or omitted, and connector segments only between adjacent markers. | screenshot geometry evidence for base and support steppers |
| VIS-018 | OPEN | P0 | Schedule upload action row | user report 2026-04-18 | Action Row Contract / Work Plane Law | A detached full-width footer band is used for one primary button and does not share the active form canvas grammar. | Place current action inside the active form canvas or a compact action row aligned to the active canvas; ensure one visible primary action per state. | all-step screenshots and action hook audit |
| VIS-019 | OPEN | P0 | Schedule upload file stage | user report 2026-04-18 | Wizard Type Addendum / Filter Grammar Map | File stage shows native-looking file input, oversized blank-template area, and duplicate `분석 시작` controls. | Replace with ARLS form/dropzone grammar, collapse template download into a compact action, and ensure one analysis action. | file-stage screenshot and file action audit |
| VIS-020 | OPEN | P0 | Schedule upload review stage | user report 2026-04-18 | Wizard Type Addendum / Visual Verdict Template | Review stage does not sufficiently expose blocked causes and preview content is hidden/cut off by the surrounding layout. | Make blocked causes visible through grouped issue reasons and row-level reason columns; keep preview table visible and aligned. | review screenshot with blocked fixture, page-2 preview evidence |
| VIS-021 | OPEN | P0 | Schedule upload preview semantics | user report 2026-04-18 | Upload Preview Row Contract / Wizard Auto-Reject | Preview table wraps short labels, uses too many technical columns, lacks source coordinates, splits related workbook errors, treats `0` as a false block, shows redundant gray result subtitles, and has stepper line/checkmark visual defects. | Use 5-column preview, coordinate-based reasons, grouped source-cell issues, `0` no-demand semantics, segmented preview toggle, strong checkmarks, and non-overrun connector lines. | parser baseline, preview screenshot with provided workbook, visual verdict, unit tests |
| VIS-022 | OPEN | P0 | Schedule upload blocker visibility | user report 2026-04-19 | Upload Preview Row Contract / Wizard Auto-Reject | Summary reports `차단` rows, but default row preview omits the actual blocking rows; non-blocking protected/review rows are shown instead. | Include wizard-blocking support ticket rows in preview rows; default view must expose blockers first; use `반영 불가능` only for blockers and red reason text. | actual provided workbook upload screenshot, unit test for support ticket blocker preview, deployed smoke |
| VIS-023 | OPEN | P0 | Schedule upload pending support slots | user report 2026-04-19 | Schedule Upload Business Semantics | `필요인원수` is parseable but `요청인원수`/support-worker slots are `미정` or blank; this is pending assignment, not a blocker. | Treat `미정`/blank support assignment fields as non-blocking placeholders; ignore them for upload while preserving request headcount. | provided workbook parser baseline, unit test, live upload screenshot |

## Closed Issues

None yet. Issues should be marked CLOSED only with:

- before screenshot,
- after screenshot,
- rule ID,
- action/route verification,
- static guardrail result,
- route/deep sweep result when applicable.

## Next Required Artifacts

Before implementation resumes:

1. `filter-grammar-map-20260416.md`
2. `work-plane-consistency-map-20260416.md`
3. topbar normalization reference set
4. visual-verdict template for ARLS phase work
