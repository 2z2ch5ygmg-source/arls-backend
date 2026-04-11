# ARLS Leave / Approval / Documents Reference Comparison

- Team task: `task-3` — Leave, Approval, Documents UI comparison
- Worker: `worker-3`
- Scope: read-only UI analysis; no product source edits
- Output target: `output/arls-all-tabs-ui-reference-comparison/leave-approval-documents.md`

## Source evidence used

- ARLS catalog: `docs/design/arls-reference-action-layout-classification-20260412.md`
  - Leave / approval / documents cluster: ARLS images `4`, `7`, `8`, `9`, `10`, `11`, `13`, `16`, `17`, `18`, `20`.
- Shiftee catalog: `docs/design/shiftee-reference-action-layout-classification-20260412.md`
  - Usable leave/request references: images `14`, `15`, `16`, `18`, `22`, `41`; partial references `6`, `12`.
- Shople catalog: `docs/design/shople-reference-action-layout-classification-20260412.md`
  - Applicable traits: light operational surface, compact toolbars, domain-local actions, list/detail over card walls.
- Binding design law: `docs/design/arls-global-design-law.md`.
- Prior live audit: `.omx/audits/task-2-approval-leave-document-audit-20260409.md`.
- Current source read for route/panel shape only: `frontend/index.html`, `frontend/js/app.js`.

## Executive summary

ARLS has already moved several of these surfaces in the right direction: approval is closer to a queue + detail workspace, leave uses list/table grammar, and current HR document routing has distinct `apply`, `my-docs`, and `manage` segments. The remaining gap is not feature coverage; it is **surface hierarchy and plane discipline**. Compared with the Shiftee references, ARLS still tends to wrap the work inside repeated cards, subtitles, local tabs, and helper panels before the user reaches the operational list.

Recommended direction: keep each domain as one primary sheet with a compact command/filter row, one status segmentation model, and a dense list/table or focused editor. Preserve Shople's restraint: use spacing, dividers, type scale, and one-time accent rather than nested module cards.

## Prioritized issues and direction

| Priority | Surface | Evidence | Issue | Recommended UI direction | Must not break |
| --- | --- | --- | --- | --- | --- |
| P1 | Leave status / full surface | ARLS `4`, `8`; Shiftee leave accrual/status `14`, `16`; global law | Leave still reads as a mini-app with page title, local section tabs, toolbar card, summary/list cards, and repeated headings. This creates box-in-box and slows the path to the leave table. | Use a single leave workspace sheet. Header row: `휴가` + `휴가 신청` primary action. Then a compact KPI strip (`총 지급`, `사용`, `승인대기`, `잔여`) + one aligned filter row + dense table/list. Remove or collapse subtitles that restate the visible controls. | `#/leave`, `#/leave?tab=history`, `#/leave?tab=grants`, `#/leave?tab=settings`; employee vs manager scope; leave request creation; sync/download actions; policy/API failure states. |
| P1 | Leave usage history | ARLS `11`; Shiftee request/leave history `15`, `18`, `22`; prior audit | The `사용 흐름` chart/explainer competes with the history list in the default path. History is primarily a scan/triage task, not a chart-first analytics page. | Default to filter + history list/table. Make the flow chart optional, collapsed, or secondary below the table. If a chart remains, keep it same-plane and avoid a separate card that feels like another screen before the list. | History filters, export/download, unit selector, requester/site filters, existing status semantics. |
| P1 | Leave grants / accrual | ARLS `9`; Shiftee accrual `14`, `16`, leave modal `41` | ARLS uses another local mode switch (`부여 내역` / `구성원별`) and toolbar card, which is valid functionally but visually risks becoming a second navigation layer. | Keep the mode switch only as a compact table-mode control inside the header/toolbar, similar to Shiftee's employee/list toggle. Add a small summary line if it materially changes decisions; avoid a new card or explanatory block. | Grant history vs member view semantics; policy filter; employee search; grant amounts/periods; manager-only permissions. |
| P1 | Leave settings / policy list | ARLS `10`; global law; prior audit | `활성 / 비활성` is implemented as a local tab, adding another navigation layer for what is essentially a policy state filter. | Convert active/inactive to a chip/dropdown inside the same filter row. Keep one policy list with columns for type, target, grant rule, paid/unpaid, carry-forward, status. | Policy list status, editable permissions, 429/error visibility, hidden no-permission states. |
| P1 | Approval document queues | ARLS `13`, `16`, `18`; Shiftee request history `15`, `18`, `22`; global law | Approval is correctly framed as a queue, but the screen can still double-segment status via a global status filter plus secondary tabs. Row/status copy can repeat request state in multiple places. | Use exactly one status segmentation model per queue. If status is the main workflow split, use a straight underline status strip and remove the generic status dropdown. Otherwise keep a single dropdown. Rows should emphasize type, requester, target date/period, elapsed time, current approver state, and one urgency signal. | Approval state transitions, detail drawer actions, sorting, employee/site/date filters, pending/in-progress/completed/rejected semantics. |
| P1 | Approval queue workload summary | ARLS `13`, `16`, `18`; Shople traits | The current priority queue + KPI strip direction is useful, but helper icon/copy and nested card treatment can make it feel like an extra dashboard above the actual work. | Keep a compact queue summary bar (`승인 대기`, `오늘 마감`, `긴급/오래된 요청`) directly above the list. If priority items are separate, render as same-plane rows, not a second card wall. | Priority ordering, overdue/urgent logic, refresh behavior, selected detail panel state. |
| P1 | Documents IA and segment routing | ARLS `7`, `17`, `20`; prior audit; current code read | Prior live audit found `segment=apply` and `segment=my-docs` collapsing into the approval-rule admin view. Current source now has distinct `apply`, `my-docs`, and `manage` panel visibility; this is a regression-sensitive win. | Preserve the current separation: `문서 발급` = requestable document flow, `내 문서` = personal output/history table, `승인 절차` = manager/admin rule editor. Do not duplicate the same document domain under both approval and document center except where approval inbox owns document approvals. | `#/hr?segment=apply`, `#/hr?segment=my-docs`, `#/hr?segment=manage`; employee-only vs manager-only visibility; document approval requests; PDF/download generation. |
| P2 | Document issue/apply form | ARLS `20`; Shiftee leave/request create patterns; Shople traits | The document card grid plus selected form is functionally clear, but the grid can become a card wall if every document type receives a large bordered card with explanatory copy. | Treat document type selection as a compact request catalog or list. Keep the selected form as the main work area. Put primary action on the form header/footer, and hide repetitive copy such as “승인 후 출력 가능” when the status model already communicates it. | Document type eligibility, quota, purpose selection, resignation-specific fields, address/phone toggles, validation and disabled reasons. |
| P2 | My documents | ARLS `7`; Shiftee request history `15`, `18`, `22` | The table direction is good; the risk is visual mismatch if it is wrapped inside heavy module cards or lacks direct status/action scannability. | Keep as a clean personal history table with requested time, document type/purpose, approval/file state, issue number, and one row action. Empty state should be icon + short text on the sheet plane, not a tinted mini-card. | Refresh, download/view action, file-ready/generating/requested/rejected states, employee privacy scope. |
| P2 | Approval procedure editor | ARLS `17`; global law exception classes | This is one of the few valid exceptions where an editor/inspector can use stronger grouping. The current editor + preview + template library shape is acceptable, but the template library can dominate the authoring task. | Keep a focused editor shell: top template selector + create/save actions, middle stage editor, side or lower preview. Put template library/version history behind a lower-priority collapsible section or manager-only advanced area. | Approval stage save/create, validation errors, template type selector, template upload/version controls, manager/admin permissions. |
| P2 | Empty states across leave/approval/docs | Global law; Shiftee history empty states `15`, `18` | Empty/no-data states should not become orange/tinted or bordered mini-cards. | Use centered icon + title + short optional copy on the current plane. Keep alignment consistent across sibling surfaces. | No-data, no-permission, loading, API failure, and no-filter-result states remain distinguishable and accessible. |

## Recommended screen-specific target shapes

### Leave

1. **Header**: `휴가` + primary `휴가 신청` button on the same row.
2. **Mode control**: only one straight underline section control for `현황 / 사용 이력 / 부여 / 설정`, or move these into sidebar if the app shell already owns them.
3. **현황**: KPI strip -> compact filters -> leave balance table/list -> detail drawer/sheet if needed.
4. **사용 이력**: filters -> history list/table first; `사용 흐름` as optional secondary insight.
5. **부여**: summary + compact `부여 내역 / 구성원별` mode toggle inside the toolbar; table remains primary.
6. **설정**: policy state is a filter, not a separate tab layer.

### Approval

1. **Treat as an inbox**: status/priority summary -> queue list -> detail/review panel.
2. **One status system**: do not show both a status dropdown and an equivalent status strip.
3. **Row density**: request type, requester, target date/period, submitted/elapsed time, current approver state, one urgency marker.
4. **Document approval** stays under approval as a queue; document issuance/history stays under the document center.

### Documents

1. **문서 발급**: compact request catalog + selected request form; keep validation and disabled reasons explicit.
2. **내 문서**: table-first personal history with row actions and concise file/approval state.
3. **승인 절차**: focused approval-rule editor; template library/version history demoted from first-view dominance.
4. **Regression-sensitive route split**: preserve current separate `apply`, `my-docs`, and `manage` panel rendering.

## Must-not-break constraints for implementation handoff

- Preserve route/deep-link behavior:
  - `#/leave`, `#/leave?tab=history`, `#/leave?tab=grants`, `#/leave?tab=settings`
  - `#/requests`, document/request status filters, and detail drawer selection
  - `#/hr?segment=apply`, `#/hr?segment=my-docs`, `#/hr?segment=manage`
- Preserve role behavior:
  - employee-only request/document surfaces
  - manager/admin-only leave grants/settings/approval procedure and template management
  - selected tenant/company scoping
- Preserve business outcomes:
  - leave request creation, leave sync/export, leave policy status and error handling
  - approval queue state transitions and row detail actions
  - document request quota/validation, approval, PDF/file generation, download/view actions
  - template upload/version management and approval stage save/create
- Preserve UI law:
  - no gratuitous box-in-box
  - no U-shaped tabs or pill fallback for primary section switching
  - no decorative title-left icons
  - no tinted/boxed empty-state cards unless an explicit exception applies
  - one primary action row per surface

## Suggested implementation order

1. **Documents regression guard first**: lock `apply`, `my-docs`, `manage` segment rendering with a small Playwright or DOM smoke before any visual edits.
2. **Approval status simplification**: choose one status segmentation path and compress queue summary/list hierarchy.
3. **Leave plane cleanup**: remove nested toolbar/list/chart card layers and demote `사용 흐름` from default history dominance.
4. **Document surface polish**: compact the document request catalog and demote template library chrome.
5. **Empty-state sweep**: normalize no-data states after the main sheet/list structure is stable.
