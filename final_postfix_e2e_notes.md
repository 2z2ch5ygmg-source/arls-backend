# Final Postfix ARLS ↔ Sentrix E2E Verification

검증 일시: 2026-03-13 (final re-verification)  
검증 방식: verification only, no product code changes

## 범위

- ARLS가 workbook ingress owner로 남아 있는지 확인
- Sentrix가 support roster/ticket/state engine으로만 동작하는지 확인
- Step 3B side-effect band 수정 이후 notification / ARLS bridge / support-origin materialization 흐름이 끝까지 이어지는지 확인

## 이번 패스의 증거 소스

- 운영 헬스 확인
  - ARLS: [https://rg-arls-backend.azurewebsites.net/health](https://rg-arls-backend.azurewebsites.net/health) -> `{"status":"ok"}`
  - Sentrix: [https://security-ops-center-prod-002-260227135557.azurewebsites.net/health](https://security-ops-center-prod-002-260227135557.azurewebsites.net/health) -> `{"ok":true,"status":"ok","read_only":false,...}`
- 운영 배포 자산 확인
  - Sentrix live `app.js` 에서 `redirectOpsSupportWorkbookFlowToArls`, legacy `mode="hq-submission"`, `opsSupportSubmissionWorkspace` 제거 경로 확인
  - ARLS live `app.js` 에서 `getScheduleHqTenantCode`, `buildScheduleSupportHqContext`, `scheduleSupportHqSuccessBanner`, `scheduleSupportHqMismatchBox` 확인
- ARLS 자동화 회귀 재실행
  - `test_schedule_support_roundtrip.py`
  - `test_schedule_monthly_import_canonical.py`
  - `test_soc_support_assignment_bridge.py`
  - `test_arls_support_origin_materialization.py`
  - 합산 결과 `Ran 61 tests ... OK`
- Sentrix 자동화 회귀 재실행
  - `/Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`
  - `/Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_engine_core.py`
  - 합산 결과 `Ran 13 tests ... OK`

## 최종 결론

이번 final re-verification 기준으로 요구된 8개 시나리오는 모두 통과했습니다. 다만 이 패스는 운영 workbook를 다시 업로드해 실제 운영 데이터를 변경하는 방식이 아니라, 운영 read-only 확인과 현재 브랜치의 회귀 하네스를 합쳐 판정했습니다.

핵심 판정:

- ARLS는 workbook upload/download의 유일한 visible owner입니다.
- Sentrix는 workbook UI owner가 아니라 support roster/ticket/state engine으로 동작합니다.
- exact-filled / underfilled / overfilled / external-only / mixed / approved->pending reversal이 모두 현재 회귀 하네스에서 통과합니다.
- Step 3B side-effect band는 더 이상 `get_ticket_status_label` 오류나 좁은 `meaningful_change` gate 때문에 중단되지 않습니다.
- valid self-staff만 ARLS bridge / support-origin materialization 대상이 되고, external worker는 Sentrix 안에서는 count되지만 ARLS로는 materialize되지 않습니다.
- live deployed assets에서도 ownership split이 유지됩니다.
  - Sentrix: legacy `hq-submission` -> ARLS redirect
  - ARLS: independent HQ wizard state model 유지

## 시나리오별 요약

### 1. Base monthly upload only

- ARLS base import/export contract와 support-demand row 생성 테스트 통과
- HQ workbook owner는 ARLS 자산 기준으로 유지
- Sentrix workbook UI 필요 없음
- 판정: PASS

### 2. HQ exact-filled support upload

- Sentrix: ticket create/update, confirmed workers 저장, `approved`, notification, UPSERT 통과
- ARLS: approved self-staff materialization 경로 통과
- 판정: PASS

### 3. HQ underfilled support upload

- Sentrix: same ticket update, confirmed workers 유지, `pending`, notification 통과
- 신규 underfilled pending scope에서는 approved bridge가 생기지 않음
- 기존 approved state가 있었다면 reversal 시 RETRACT는 시나리오 7에서 검증됨
- 판정: PASS

### 4. HQ overfilled support upload

- ARLS inspect는 overfill을 blocking이 아닌 review/warning으로 유지
- Sentrix 최종 상태는 `pending`
- confirmed workers에는 입력된 유효 인원이 모두 남음
- approved bridge/materialization은 남지 않음
- 판정: PASS

### 5. External worker only

- Sentrix는 fulfillment 계산에 external worker를 포함
- confirmed workers에 external worker가 보존됨
- ARLS bridge/outbox는 생성되지 않음
- 판정: PASS

### 6. Mixed external + self-staff

- Sentrix는 모든 유효 근무자를 count
- confirmed workers에 self + external 모두 남음
- ARLS bridge는 valid self-staff subset만 emit
- 판정: PASS

### 7. State reversal

- exact-filled approved 이후 replace upload로 underfilled pending 전환 시 같은 ticket 재사용
- latest confirmed-worker snapshot으로 교체
- Sentrix는 notification + RETRACT emit
- ARLS는 support-origin schedule row retract 경로 통과
- 판정: PASS

### 8. Multi-site HQ workbook

- HQ workspace는 tenant/month/site를 Tab A와 독립적으로 유지
- stale site가 섞여 있어도 partial continue 허용
- processed / excluded counts를 summary로 제공
- 판정: PASS

## 남는 점

- 이 셸에서는 브라우저 자동화나 실사용자 로그인 세션을 통한 live screenshot 캡처를 하지 못했습니다.
- `test_schedule_monthly_export_template.py` 는 로컬 테스트 경로가 하드코딩되어 있어 현재 머신에서 직접 재실행되지는 않았습니다. 이건 테스트 환경 경로 문제이며, 이번 핵심 workflow 회귀 판정에는 포함하지 않았습니다.
