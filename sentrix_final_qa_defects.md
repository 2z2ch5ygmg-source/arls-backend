# Sentrix Final QA Defects

## Blocking defects

없음.

이번 재검증에서 다음 blocking defect는 재현되지 않았습니다.

- visible workbook ownership regression
- `get_ticket_status_label` runtime failure
- notification body generation crash on normal path
- pending meaningful change notification suppression
- ARLS UPSERT / RETRACT outbox 미생성

## Non-blocking notes

### 1. Shell-only verification limitations

- browser screenshot은 캡처하지 못했습니다.
- legacy HQ route redirect는 live JS asset + code path로 확인했고, 실제 브라우저 클릭 녹화는 하지 않았습니다.

### 2. Negative failure-isolation test log is expected

- test output 중
  - `[support-roster.side-effect] failed stage=build_notification_body ... RuntimeError:boom`
  는 regression test가 의도적으로 body generator를 실패시키는 negative case입니다.
- 이는 현재 제품 결함이 아니라, failure-isolation과 outbox 지속 enqueue를 검증하는 테스트입니다.

## Overall defect verdict

- required QA acceptance 기준의 blocking defect: 없음
- Sentrix support-state / Step 3B side-effect band: PASS
