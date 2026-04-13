# Photo-Based Unfulfilled UI Checklist

Generated: 2026-04-13
Basis:
- User-provided screenshot set from 2026-04-13 17:09-17:10
- Deep interview spec: `.omx/specs/deep-interview-arls-targeted-ui-cleanup.md`
- RALPLAN PRD/test spec: `.omx/plans/prd-arls-targeted-ui-cleanup-20260413T0850Z.md`, `.omx/plans/test-spec-arls-targeted-ui-cleanup-20260413T0850Z.md`
- Current sweep artifact: `artifacts/ui-sweep/20260413-1830-arls-ui-cleanup/`
- `ui-ux-pro-max` basis: layout consistency, touch target sizing, color contrast, no horizontal scroll, semantic color tokens, visible labels, navigation active-state clarity.

## Executive Verdict

The prior execution did **not** complete the user's requested image-by-image compare -> fix -> verify loop.

What was completed:
- A global route sweep exists with 60 route/viewport pairs.
- A selector audit exists.
- Some global tab/filter/stepper/detail rail CSS and renderer hooks were implemented.
- `/ops/support-workers` responsive overflow was found and fixed.
- Static checks and schedule support regression tests passed.

What remains unfulfilled:
- No strict 1:1 comparison from each supplied screenshot to a current matching deployed screenshot.
- Many component-family sweep checks remain `WARN missing`, so they cannot prove that each requested pattern is fixed.
- Several screenshot-specific complaints remain unverified or likely unresolved.

## UI Pro Max Rules Used For Judgement

- Layout & Responsive: no horizontal scroll, consistent container widths, adaptive gutters, spacing scale.
- Touch & Interaction: minimum 44px/44pt targets where practical, visible selected/pressed states.
- Typography & Color: semantic color tokens, high contrast, no gray-on-gray/pastel-dominant status language.
- Navigation Patterns: clear active state, no weak/bottom-border-only current-location treatment.
- Forms & Feedback: visible labels, field grouping, aligned filter bars.

## Photo-by-Photo Unfulfilled Checklist

| Image | Title | User issue | Current evidence | Status |
|---|---|---|---|---|
| 1 | Employee Management List + Detail Rail | Filter row/table/detail balance, pastel status fields, right rail visual clutter | Sweep only captured `/branch/employees`; verifier has `detailPanels WARN missing`; no 1:1 visual comparison against image 1 | Not proven / likely incomplete |
| 2 | Site Management List + Detail Rail | Same as employee: site list/detail rail balance, status color softness | Sweep only captured `/branch/sites`; verifier has `detailPanels WARN missing`; no direct comparison against image 2 | Not proven / likely incomplete |
| 3 | Segmented Filter Closeup | Top filter segmented controls oversized/detached | Global filterbar CSS changed, but no closeup comparison for this exact control | Not proven |
| 4 | Document Approval Tabs | Bottom-border-only active tab should be globally banned | Selector audit identified this family; CSS changed, but sweep still has many tab `WARN missing`; no proof all bottom-border-only instances are gone | Incomplete proof |
| 5 | Leave Usage History Filters | Crowded/misaligned filters; unnecessary icon-box controls | Sweep `/leave?tab=history` has filters `WARN missing` at 375/768 and PASS only on desktop; no direct comparison against image 5 | Not proven / likely incomplete |
| 6 | Leave Settings Table | Header/tab spacing and table rhythm inconsistency | Sweep `/leave?tab=settings` still shows filters/KPI warnings; no direct comparison against image 6 | Not proven |
| 7 | Leave Status KPI + Filters | Top KPI/filter row should use unified design | Sweep `/leave?tab=status` shows KPI/filter `WARN missing`; no visual judgement of KPI parity | Not done |
| 8 | Attendance Exception Tabs | Bottom-border-only tab closeup | General tab CSS changed, but no focused comparison for exception/document tabs | Incomplete proof |
| 9 | Approval Stage Flow | Current approval stage should become business-app structure diagram | JS hooks added around HR approval flow; no direct visual comparison to prove structure quality | Partially implemented, not visually proven |
| 10 | Leave Status Tabs Closeup | Tab typography/spacing inconsistency | No closeup comparison; leave tabs still flagged by harness in some states | Not proven |
| 11 | Attendance Period View | Period KPI strip differs from daily KPI strip | Sweep `/attendance?section=period&mode=list` still has tabs/filter/KPI `WARN missing`; terminology/design parity not proven | Not done |
| 12 | Document Approval Queue Column | Queue labels and values left-crowded, vertical column alignment off | Sweep `/requests?section=documents` has filters/KPI/detail warnings; no direct comparison | Not done |
| 13 | Attendance Daily View | Preferred top KPI design to reuse | Sweep `/attendance` has tabs/filter/KPI `WARN missing`; no proof daily grammar was used as canonical across period/stats | Not done |
| 14 | Schedule Upload Wizard Stepper | Line pierces circles, labels detached | Renderer hooks + CSS changes exist; sweep detects desktop stepper but 375/768 stepper `WARN missing`; no direct screenshot comparison | Partially implemented, not proven |
| 15 | Support Worker Upload Wizard | Stepper/content left-heavy, not one-screen balanced | Sweep `/schedules/hq-upload` has stepper/filter warnings; no direct comparison | Not proven / likely incomplete |
| 16 | Attendance Stats | Two top bars, secondary ㄷ tabs misaligned, bottom-line tab style should be banned | Sweep `/attendance?section=stats&scope=attendance` still has tab/filter/KPI warnings; no direct comparison against image 16 or Shople image 19 | Not done |
| 17 | Schedule Wizard Step 2 Closeup | Completed/current marker becomes line only | Renderer hook added; no direct step-2 capture comparison | Not proven |
| 18 | Metadata Inline Row | Text between dividers should be vertically centered | No targeted check for divider-bounded metadata row vertical centering | Not done |
| 19 | Shople Tab Reference | Match separated top/secondary tab structure, avoid bottom-line tab | Used as conceptual reference in PRD, but no visual compare loop against current ARLS | Not done |

## Global Deep-Interview Requirements Still Not Fully Proven

- Major-route sweep exists, but it does not prove every visible tab/filter/stepper/detail panel uses the new grammar because many checks are `WARN missing`.
- No bottom-border-only active tab remains: not proven; selector audit still lists several families requiring neutralization, and final verifier treats warnings as non-blocking.
- Top filter bars aligned and balanced: not proven; multiple route filters still `WARN missing`.
- Employee/site/request detail rails clean and color-consistent: not proven; detail panels frequently `WARN missing`.
- Attendance date/period/stat unified KPI/filter/tab grammar: not done/proven.
- Terminology (`출근대상` vs `근무대상`) unified where same concept: explicitly not changed because equivalence was not proven.
- Approval stage as clean structure diagram: hook added but no visual proof.
- Photo-by-photo visual comparison: not done.

## Required Next Loop

1. Capture current deployed matching screenshots for each user screenshot target.
2. For each photo row above, attach:
   - reference screenshot path
   - current deployed screenshot path
   - verdict (`pass`, `revise`, `fail`)
   - concrete visual deltas
   - selector/file owner
3. Fix one component family at a time:
   - tabs and bottom-line active states
   - filter bars
   - steppers
   - attendance KPI strips and terminology
   - leave filters/status/history
   - requests/document queue alignment
   - approval flow
   - employee/site detail rails
4. Re-capture the matching screen and update this checklist after every fix.

