# Sentrix Final Support-State Verification - QA Pass

검증 일시: 2026-03-13  
검증 범위: verification only, no product code changes

## 환경

- Sentrix repo: `/Users/mark/Desktop/security-ops-center`
- 브랜치: `codex/sentrix-employee-profile-dedupe`
- 운영 헬스:
  - [https://security-ops-center-prod-002-260227135557.azurewebsites.net/health](https://security-ops-center-prod-002-260227135557.azurewebsites.net/health)
  - 응답: `{"ok":true,"status":"ok","read_only":false,...}`
- 운영 자산:
  - `/styles.css?v=20260312-ops-support-ui-rollback-v1`
  - `/app.js?v=v20260313-ops-support-workbook-cleanup-v1`

## 이번 패스에서 다시 확인한 것

### 1. Visible ownership rollback

- live `app.js` 에서 `redirectOpsSupportWorkbookFlowToArls(...)` 존재 확인
- legacy `mode === "hq-submission"` 분기 확인
- `opsSupportSubmissionWorkspace` 잔여 root 제거 경로 확인
- support 상태 화면 쪽 정적 마크업에는 workbook submission workspace가 섞여 있지 않음

판정: PASS

### 2. Support status UI intact

- 정적 DOM 확인:
  - `opsSupportSiteFilter`
  - `opsSupportCalendarView`
  - `opsSupportListView`
  - detail sheet 유지
- 렌더 코드에서 calendar/list 토글 유지
- workbook workflow root는 support 화면 렌더 전에 정리됨

판정: PASS

### 3. Ticket / roster core

재실행:

```bash
cd /Users/mark/Desktop/security-ops-center
python3 -m unittest -q test_sentrix_support_roster_side_effects.py test_sentrix_support_roster_engine_core.py
```

결과:

- `Ran 13 tests in 0.306s`
- `OK`

core에서 재확인된 내용:

- missing logical scope -> ticket create
- existing logical scope -> same ticket in-place update
- `request_count`는 ARLS normalized snapshot 값 사용
- latest snapshot replace semantics 유지
- exact-filled -> `approved`
- underfilled / overfilled -> `pending`
- confirmed workers는 pending 상태에서도 유지
- day scope reason 누락은 `DAY_REASON_REQUIRED`로 차단
- night purpose는 `work_purpose`로 유지

판정: PASS

### 4. Confirmed workers

재확인된 내용:

- valid worker는 `affiliation + name + raw_display + self_staff + employee_id` 형태로 보존
- external worker도 confirmed-worker data에 남음
- self-staff도 confirmed-worker data에 남음
- pending 상태에서도 confirmed-worker list가 비워지지 않음

판정: PASS

### 5. Step 3B side-effect band

재확인된 내용:

- `get_ticket_status_label` 경로가 더 이상 runtime failure를 만들지 않음
- notification body generation이 정상 path에서 성공
- approved path -> notify + UPSERT
- pending reversal path -> notify + RETRACT
- new pending scope with workers -> notify
- pending -> pending roster change -> notify
- identical re-upload -> suppressed
- external-only approved scope -> notify only, no bridge
- mixed approved scope -> self-staff subset만 bridge

주의:

- 테스트 출력에 보인
  - `[support-roster.side-effect] failed stage=build_notification_body ... RuntimeError:boom`
  는 negative regression test가 의도적으로 `side_effect=RuntimeError("boom")`를 주입한 결과입니다.
- 이는 현재 runtime defect 재현이 아니라 failure-isolation 경로 검증입니다.

판정: PASS

### 6. Notification contract

확인된 계약:

- audience:
  - site Vice Supervisor
  - site Supervisor
  - HQ
  - Development
- message:
  - `[HQ] 지원근무자 업데이트 발생`
- meaningful pending change도 notify
- identical repeated upload는 spam 억제

판정: PASS

### 7. Bridge rules

확인된 계약:

- approved valid self-staff -> UPSERT
- pending from previously approved -> RETRACT
- external worker -> no bridge
- mixed scope -> self-staff subset only
- unchanged repeated upload -> duplicate outbox 없음

판정: PASS

## 최종 결론

이번 QA 재검증 기준으로 Sentrix는 더 이상 visible workbook owner가 아닙니다. 현재 역할은 support ticket/state engine, support roster truth owner, support worker status UI owner로 정리돼 있고, Step 3B side-effect band도 notification / ARLS bridge / outbox까지 정상 경로를 통과합니다.

## 한계

- 브라우저 자동화/실스크린샷 캡처는 이 셸에서 수행하지 않았습니다.
- legacy route redirect는 deployed JS asset과 코드 경로로 검증했고, 브라우저 클릭 녹화는 하지 않았습니다.
