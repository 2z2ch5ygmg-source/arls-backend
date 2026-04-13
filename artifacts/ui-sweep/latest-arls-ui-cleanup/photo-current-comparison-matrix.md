# Photo vs Current Capture Comparison Matrix

Generated: 2026-04-13

Purpose:
- Continue from `photo-unfulfilled-checklist.md`.
- Map each user reference screenshot to the closest current deployed/mocked route capture from `artifacts/ui-sweep/20260413-1830-arls-ui-cleanup`.
- Identify which user-requested items are still not proven or likely still unresolved before the next edit loop.

Important limitation:
- Current captures come from the Playwright route sweep with mocked auth/API. They prove route/component coverage and responsive behavior, but they are **not** the same authenticated production data state as the user's screenshots.
- Therefore, this matrix is a visual triage input for the next edit loop, not a final pass/fail visual-verdict artifact.

UI/UX Pro Max basis used:
- Layout & Responsive: no horizontal scroll, consistent container widths, aligned command/filter bars.
- Touch & Interaction: 44px-ish control targets and clear active/pressed states.
- Typography & Color: high contrast, semantic color tokens, avoid pastel-dominant low-contrast fills.
- Navigation Patterns: current location should be clearly visible; avoid weak bottom-border-only active states.
- Forms & Feedback: visible labels, grouped fields, aligned baselines, no cramped filter rows.

## Matrix

| Ref file | Interpreted title | Closest current capture(s) | Comparison verdict | Remaining work |
|---|---|---|---|---|
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.52.png` | Employee management list + right detail rail | `desktop/branch-employees.jpg`, `768/branch-employees.jpg`, `375/branch-employees.jpg` | **Revise** | Need direct visual comparison. Current sweep has route capture, but `detailPanels WARN missing`; employee detail rail cleanliness/color alignment not proven. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.58.png` | Site management list + right detail rail | `desktop/branch-sites.jpg`, `768/branch-sites.jpg`, `375/branch-sites.jpg` | **Revise** | Need direct visual comparison. Site detail rail/table balance and status color softness not proven. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.27.png` | Segmented top filter closeup | likely `desktop/attendance*.jpg` or `desktop/leave-tab-*.jpg` depending source | **Revise** | Need re-capture/crop of the exact segmented filter. Current sweep family detection is too coarse; cannot prove oversized/detached controls are fixed. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.31.png` | Document approval tab closeup | `desktop/requests-section-documents.jpg`, `375/requests-section-documents.jpg`, `768/requests-section-documents.jpg` | **Revise** | Bottom-border-only tab ban not proven. Current verdict still has tab warnings on several routes. Need visual comparison and grep/DOM proof for document tabs. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.05.png` | Leave usage history filter bar | `desktop/leave-tab-history.jpg`, `768/leave-tab-history.jpg`, `375/leave-tab-history.jpg` | **Revise** | Current sweep has filter warnings at 375/768 and only desktop filter presence. Need filterbar layout cleanup and direct comparison. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.16.png` | Leave settings table/top bar | `desktop/leave-tab-settings.jpg`, `768/leave-tab-settings.jpg`, `375/leave-tab-settings.jpg` | **Revise** | Header/tab spacing and table rhythm not directly compared. Current KPI/filter detection warnings remain. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.59.png` | Leave status KPI + filters | `desktop/leave-tab-status.jpg`, `768/leave-tab-status.jpg`, `375/leave-tab-status.jpg` | **Revise** | Current sweep shows KPI/filter warnings. Need actual KPI/filter row comparison and spacing correction. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.20.png` | Attendance exception/document tab closeup | `desktop/requests.jpg`, `desktop/requests-section-documents.jpg`, or attendance exception surface | **Revise** | Bottom-border-only closeup not proven fixed. Need locate exact route/state and compare. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.40.png` | Approval stage flow | `desktop/hr-segment-manage.jpg`, `768/hr-segment-manage.jpg`, `375/hr-segment-manage.jpg` | **Revise** | Renderer hooks exist and HR manage approval flow detection passes, but structure quality against reference screenshot not visually proven. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.54.png` | Leave status tabs closeup | `desktop/leave-tab-status.jpg`, `desktop/leave-tab-history.jpg`, `desktop/leave-tab-settings.jpg` | **Revise** | Need closeup compare; current sweep only route-level. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.44.png` | Attendance period view | `desktop/attendance-section-period-mode-list.jpg`, `768/attendance-section-period-mode-list.jpg`, `375/attendance-section-period-mode-list.jpg` | **Revise** | Current sweep has tab/filter/KPI warnings; daily-vs-period KPI grammar not proven unified. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.10.29.png` | Document approval queue column alignment | `desktop/requests-section-documents.jpg`, `768/requests-section-documents.jpg`, `375/requests-section-documents.jpg` | **Revise** | Text/value vertical alignment and left-crowding not directly checked. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.41.png` | Attendance daily view | `desktop/attendance.jpg`, `768/attendance.jpg`, `375/attendance.jpg` | **Revise** | User wanted this KPI grammar as model, but no direct comparison proves other attendance views inherited it. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.06.png` | Schedule upload wizard | `desktop/schedules-upload.jpg`, `768/schedules-upload.jpg`, `375/schedules-upload.jpg` | **Revise** | Stepper hooks/CSS exist, but 375/768 stepper detection still warns. Need direct stepper screenshot comparison. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.09.png` | Support-worker upload wizard | `desktop/schedules-hq-upload.jpg`, `768/schedules-hq-upload.jpg`, `375/schedules-hq-upload.jpg` | **Revise** | Stepper/content left-heavy issue not proven fixed. Need direct comparison; current mocked route may not expose real selected-site table state. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.50.png` | Attendance stats | `desktop/attendance-section-stats-scope-attendance.jpg`, `768/attendance-section-stats-scope-attendance.jpg`, `375/attendance-section-stats-scope-attendance.jpg` | **Revise** | Two top bars, secondary ㄷ tab alignment, and bottom-line tab ban not directly resolved/proven. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.12.31.png` | Schedule wizard step closeup | `desktop/schedules-upload.jpg`, `desktop/schedules-hq-upload.jpg` | **Revise** | Direct closeup comparison needed for completed/current marker behavior. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.13.41.png` | Metadata inline row closeup | multiple possible: schedule/report metadata rows | **Revise** | Need exact route/state identification; vertical centering between divider lines not tested. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.16.48.png` | Shople top/secondary tab reference | no ARLS equivalent, reference comparator only | **Revise** | Need compare current ARLS attendance stats/request tabs against this reference, not just conceptually cite it. |
| `/Users/mark/Desktop/스크린샷 2026-04-13 오후 5.09.02.png` | Likely schedule/top bar crop | likely `desktop/schedules-upload.jpg` or attendance/schedule route | **Revise** | Need exact route/state identification before fixing. |

## Highest-Priority Next Fix Groups

1. **Tabs / bottom-line active state**
   - Photos: document tabs, attendance exception tabs, leave tabs, Shople tab reference.
   - Reason: repeated user complaint and `ui-ux-pro-max` navigation active-state clarity.
   - Current proof gap: route sweep still has tab warnings; no closeup comparison.

2. **Filter bars**
   - Photos: segmented filter closeup, leave usage filters, leave status filters, attendance filters, request/document filters.
   - Reason: repeated user complaint and `ui-ux-pro-max` field grouping / aligned baselines.
   - Current proof gap: filter family has many `WARN missing`; no direct visual comparison.

3. **Wizard steppers**
   - Photos: schedule upload, support-worker upload, step closeup.
   - Reason: explicit line-through-circle and label-detachment issues.
   - Current proof gap: renderer hooks exist, but direct capture comparison not performed.

4. **Attendance KPI/status grammar and terminology**
   - Photos: attendance daily, period, stats.
   - Reason: user explicitly prefers daily top pattern and called out terminology inconsistency.
   - Current proof gap: terminology left unchanged; KPI warnings remain.

5. **Approval/detail rail structure**
   - Photos: approval stages, document queue, employee/site detail rails.
   - Reason: structure/hierarchy and business-app polish.
   - Current proof gap: hooks exist but no visual judgement.

## Next Required Action

Before additional styling edits:
- Capture or crop current deployed screenshots that match each reference image more closely than the coarse route sweep.
- Create side-by-side comparison artifacts for each row.
- Run a strict visual verdict for each row and only then edit the top failing component group.

