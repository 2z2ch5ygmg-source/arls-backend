# Sentrix Step 3B Status Label Contract

## Supported Status Values
- `pending` -> `승인대기`
- `approved` -> `승인완료`
- `rejected` -> `반려`
- `cancelled` -> `작업취소`
- `unavailable` -> `지원 불가`
- `needs_info` -> `보완요청`
- `done` -> `완료`
- `deleted` -> `삭제`

## Label Mapping Rules
- Status keys are normalized through Sentrix support-request status normalization first.
- `rejected + 지원 불가` semantics map to `unavailable`.
- `rejected + 작업 취소` semantics map to `cancelled`.
- The Step 3B helper reuses existing support-request label rules and only fills gaps for side-effect-only statuses.

## Notification Usage
- `_build_support_roster_notification_body()` uses the ticket-status label helper to render:
  - site/date/shift scope
  - confirmed/request count
  - final status label

## Side-Effect Stages Depending On It
- notification body generation
- support-roster broker notification payload text
- APNS/push body text
- any later audit/debug read of notification body output
