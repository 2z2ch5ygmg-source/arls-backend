# ARLS Targeted UI Cleanup Verifier Report

Generated: 2026-04-13T09:30Z UTC
Worker: worker-5
Scope: final verifier pass, verification artifacts only; no frontend source edits.
Integrated checkout verified: `/Users/mark/Desktop/rg-arls-dev`

## Verdict

**FAIL — final acceptance is blocked by a confirmed responsive overflow in the Playwright sweep.**

Lifecycle recommendation: transition task 5 to `failed` with this report as evidence; verification work is complete, but product acceptance is not.

Tasks 1-4 are complete and their artifacts/commits are present in the leader checkout:

| Lane | Evidence |
|---|---|
| Worker 1 selector audit | `artifacts/ui-sweep/latest-arls-ui-cleanup/selector-audit.md`, commit `d0f4771` |
| Worker 2 CSS consolidation | `frontend/css/styles.css`, commit `47995cc` |
| Worker 3 renderer hooks | `frontend/js/app.js`, `frontend/index.html`, commit `af93d61` |
| Worker 4 sweep harness/artifacts | `scripts/qa/arls-ui-route-sweep.mjs`, `artifacts/ui-sweep/20260413-1816-arls-ui-cleanup/`, commit `1e97e15` |

The integrated syntax, whitespace, business-regression, manifest, console, and network checks pass. The fail condition is visual/responsive: `/ops/support-workers` overflows horizontally at `375` and `768` viewports (`scrollWidth: 979`). The 375px screenshot visibly contains a wide desktop panel extending into blank right-side canvas.

## Verification Commands

| Check | Result | Evidence |
|---|---:|---|
| `npx --yes --package typescript tsc --allowJs --checkJs false --noEmit --skipLibCheck --lib DOM,ES2022 --target ES2022 frontend/js/app.js` | PASS | exit 0, `PASS tsc js noEmit` |
| `node --check frontend/js/app.js` | PASS | exit 0, no output |
| `node --check scripts/qa/arls-ui-route-sweep.mjs` | PASS | exit 0, no output |
| `git diff --check` in leader checkout | PASS | exit 0, no output |
| `/Users/mark/Desktop/rg-arls-dev/.venv/bin/python -m pytest tests/test_schedule_support_roundtrip_status.py tests/test_schedule_support_roundtrip.py -q` | PASS | `54 passed, 3 warnings in 2.43s` |
| Playwright artifact manifest parse | PASS | `ok: true`, `expectedPairCount: 60`, `actualPairCount: 60`, `missingPairs: []`, `entries: 60` |
| Screenshot path completeness | PASS | `screenshotMissing: 0` across 60 manifest entries |
| Console errors | PASS | `consoleErrors: 0` across 456 captured console entries |
| Failed network requests | PASS | `networkFailures: 0` across 560 captured network entries |
| Required route/viewport matrix | PASS | 20 routes × 3 viewports present; `requiredMissing: []` |
| `!important` budget | PARTIAL PASS | `1284 -> 1261`; unique new `!important` content: `0`; still high legacy absolute count remains |

## Playwright Sweep Artifact Review

Artifact root: `artifacts/ui-sweep/20260413-1816-arls-ui-cleanup`

| Required artifact | Result |
|---|---:|
| `manifest.json` | PASS |
| `console.json` | PASS |
| `network.json` | PASS |
| `verdict.md` | PASS, with warnings |
| `desktop/`, `375/`, `768/` screenshot folders | PASS |
| `latest-run.json` pointer | PASS — points to `artifacts/ui-sweep/20260413-1816-arls-ui-cleanup` |

`latest-run.json` reports:

```json
{
  "ok": true,
  "expectedPairCount": 60,
  "capturedPairCount": 60,
  "missingPairs": []
}
```

## Route / Component Family Verdict

| Family | Verdict | Evidence / Notes |
|---|---|---|
| Tabs | WARN | Harness found tab presence on 31 expected route/viewport entries and missing on 26. Global active treatment was consolidated by CSS worker, but screenshot-level family detection still records many `WARN missing` entries. |
| Filter bars | WARN | Harness found filter presence on 11 expected route/viewport entries and missing on 40. Needs either selector expansion in harness or route-specific follow-up if those controls should be visible in mocked states. |
| Wizard steppers | WARN | Harness found steppers on 2 expected route/viewport entries and missing on 7. Desktop `/schedules/upload` passed; schedule mobile/HQ/report finance expected detections still warn. |
| KPI/status strips | WARN | Harness found KPI/status presence on 2 expected route/viewport entries and missing on 31. Some mocked states likely lack populated KPI data, but final visual acceptance should document this explicitly. |
| Detail rails/tables | WARN | Harness found detail panels on 4 expected entries and missing on 18; mocked empty states may explain some misses. |
| Approval flow | WARN | Harness found approval flow on 3 expected entries and missing on 3; `/hr?segment=manage` passed, `/hr?segment=apply` warned missing. |
| Responsive overflow | FAIL | `/ops/support-workers` has horizontal overflow at 375px and 768px (`scrollWidth: 979`, `innerWidth: 375/768`). |
| Business regression checks | PASS | Schedule support roundtrip status + roundtrip tests: `54 passed, 3 warnings`. |

## Blocking Defect

| Route | Viewport | Evidence | Impact |
|---|---:|---|---|
| `/ops/support-workers` | `375` | `pageProblems.horizontalOverflow: true`, `scrollWidth: 979`, `innerWidth: 375`, screenshot `375/ops-support-workers.jpg` | Violates mobile no-horizontal-overflow acceptance. |
| `/ops/support-workers` | `768` | `pageProblems.horizontalOverflow: true`, `scrollWidth: 979`, `innerWidth: 768`, screenshot `768/ops-support-workers.jpg` | Violates tablet no-horizontal-overflow acceptance. |

## Grep Assertion Snapshot

| Assertion | Final integrated result |
|---|---|
| `schedule-wizard-progress|schedule-wizard-step` | Multiple canonical/route-scoped blocks remain; worker-2 reduced conflict but did not reduce to a single region. |
| `workspace-tab.*active|approval-tab.*active|border-bottom|box-shadow.*inset` | Active tab candidates remain across route-specific CSS; CSS worker reports canonicalized contained orange active grammar and no unique new `!important`. |
| `ui-filterbar|leave-requests-filter-controls|requests-filter-controls|attendance-ops-toolbar` | Shared `.ui-filterbar` token group now includes request/leave/attendance controls; route-specific layout blocks remain. |
| `hr-approval-stage|hr-approval-saved-stage-stack` | Renderer hooks are present in `frontend/js/app.js` and flow CSS remains in `frontend/css/styles.css`. |
| `rg -n "!important" frontend/css/styles.css | wc -l` | `1261` final vs `1284` baseline; no unique new `!important` content found. |

## Remaining Blockers / Recommended Next Step

1. Return `/ops/support-workers` responsive overflow to the CSS owner. The likely target is the support-worker list/filter/table container width behavior under mobile/tablet.
2. Re-run `node scripts/qa/arls-ui-route-sweep.mjs --route-delay-ms 150` after the overflow fix and confirm `/ops/support-workers` no longer reports `horizontalOverflow` at `375` or `768`.
3. Decide whether the many component-family `WARN missing` entries in `verdict.md` are acceptable harness limitations for mocked empty states, or expand selectors/data seeding so the final report can mark each expected family pass or justified exception.

## Summary

The integrated ARLS UI cleanup is syntactically and regression-test clean, and the Playwright sweep covers all 60 required route/viewport pairs with zero console or network failures. Final verifier status is **failed** because the sweep still shows clear horizontal overflow on `/ops/support-workers` at 375px and 768px, plus unresolved component-family warning coverage that should be justified or fixed before release acceptance.
