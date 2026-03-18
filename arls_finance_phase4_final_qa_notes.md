# ARLS Finance Schedule Workflow Final Verification - Phase 4

## 검증 개요

- 검증 일시: 2026-03-19 KST
- 검증 대상: ARLS Finance schedule workflow
- 검증 범위: ARLS verification only
- 제외 범위: Sentrix 변경, 모바일 변경, UI 재설계
- 최종 판정: `PASS`

이번 재검증에서는 Phase 4를 막았던 두 결함을 먼저 수정한 뒤, 같은 workflow를 다시 end-to-end로 검증했습니다.

정리된 항목:

1. `P4-002` 해결
   - Finance review workbook의 `export_source_version`을 publish upload validator와 호환되는 값으로 정렬
2. `P4-001` 해결
   - Vice Supervisor를 Flow A 권한에 포함
   - 동시에 site scope는 supervisor와 같은 방식으로 유지

## 검증 환경

- 작업 경로: `/Users/mark/Desktop/rg-arls-dev`
- 로컬 ARLS 서버: `http://127.0.0.1:18081`
- API base: `http://127.0.0.1:18081/api/v1`
- 검증 DB: `postgresql://postgres:postgres@localhost:5432/arls_finance_phase4_verify`
- 템플릿 경로: `/Users/mark/Desktop/rg-arls-dev/app/templates/monthly_schedule_template.xlsx`
- 자동 검증 결과 파일: `/tmp/arls_finance_phase4_results.json`
- 자동 검증 스크립트: `/tmp/arls_finance_phase4_verify.py`

검증용 tenant/site/account:

- tenant: `P447AF9F`
- month: `2026-03`
- site A: `R701 / P4_47AF9F_A`
- site B: `R702 / P4_47AF9F_B`
- site C: `R703 / P4_47AF9F_C`
- supervisor: `supervisor_a_47af9f`
- vice supervisor: `vice_a_47af9f`
- hq admin: `hq_admin_47af9f`
- master developer: `master_dev_47af9f`

## 검증 방법

### 1. 단위 테스트

실행한 테스트:

- `python3 -m unittest tests.test_schedule_finance_submission`

결과:

- PASS
- 새 회귀 검증 포함:
  - Finance review export source version이 upload-compatible한지
  - Vice Supervisor Flow A 권한이 맞는지

참고:

- `python3 -m unittest tests.test_schedule_monthly_import_canonical`는 이번 수정과 무관한 기존 실패 3건이 계속 존재했습니다.
- 실패 항목은 Finance workflow Phase 4 acceptance 범위 밖입니다.

### 2. 자동 API 재검증

`/tmp/arls_finance_phase4_verify.py`를 QA 우회 없이 다시 실행했습니다.

결과:

- 총 25건
- PASS 25건
- FAIL 0건
- defects 0건

중요한 차이:

- 이전 검증에서는 hidden metadata를 손대는 QA workaround가 필요했음
- 이번 재검증에서는 workaround 없이 raw `1차 스케쥴 다운로드` 파일을 그대로 수정해 preview/publish까지 통과시킴

### 3. 추가 spot check

자동 검증 외에 아래를 한 번 더 직접 확인했습니다.

- Vice Supervisor review download: `200`
- raw 1차 workbook 수정 후 preview: `200`
- `can_apply=true`
- `blocked_reasons=[]`
- `export_source_version=schedule_export.phase2.roundtrip`

## 핵심 계약 검증 결과

### 1차 다운로드 live regeneration

확인됨.

- 첫 다운로드: body `12`, support slot1 `BK 초기지원A`, day need `1`
- live state 변경 후 재다운로드: body `8`, support slot1 `F 변경지원A`, day need `2`
- SHA와 review revision 모두 변경

즉 `1차 다운로드`는 저장 파일 재사용이 아니라 현재 ARLS + Sentrix materialized truth 기준 재생성입니다.

### raw 1차 파일의 preview/publish 연결

확인됨.

- raw review workbook을 그대로 수정해 `업로드 미리보기` 호출
- `status=200`, `can_apply=true`, `blocked=[]`
- metadata `export_source_version`은 import-compatible 값으로 유지됨

이제 Flow A는 raw operator flow 기준으로도 끊기지 않습니다.

### 게시 replace

확인됨.

- 동일 site+month에 v1 게시 후 v2 게시
- v2가 current/latest
- v1은 archived history로 남음
- history에는 1건만 `is_current=true`

### 2차 다운로드 latest artifact

확인됨.

- 단일 site 2차 다운로드 SHA가 업로드된 게시본 SHA와 정확히 일치
- 멀티 site 2차 다운로드는 1 workbook / 2 visible sheets
- sheet name은 site name과 정확히 일치
- sheet marker도 최신 게시본과 일치

### update-needed

확인됨.

- HQ가 site A v2를 본 뒤 supervisor가 v3 게시
- HQ workspace row가 `업데이트 필요`로 변경
- HQ가 최신 v3를 다시 다운로드하면 `게시 완료`로 복귀

### publish history latest 3

확인됨.

- 최신 3건 반환
- 각 row에 `uploaded_at`, `actor`, `site_code`, `site_name`, `month`, `is_current`
- 최신 게시본 1건만 current badge 유지

### workbook byte/content preservation

확인됨.

보존 확인 항목:

- manual marker
- formula
- conditional formatting
- page setup orientation
- column width
- row height
- hidden row
- hidden column
- merged cells

단일 site 다운로드는 uploaded publish bytes와 SHA 기준 exact match였습니다.

### role verification

확인됨.

- Supervisor: Flow A 가능, Flow B 불가
- Vice Supervisor: Flow A 가능, Flow B 불가
- HQ / Developer: Flow A + Flow B 가능

### technical metadata visibility

확인됨.

- normal user main surface에는 artifact/revision raw metadata 노출 없음
- DEV gated details 구조 유지

## 코드 inspection으로 보강한 항목

브라우저 E2E 대신 코드 inspection으로 보강 확인한 항목:

- Flow B selection controls
- valid site 미선택 시 2차 다운로드 버튼 비활성화
- technical metadata 기본 숨김 / DEV gated details

관련 위치:

- `frontend/js/app.js:13575`
- `frontend/js/app.js:13628`
- `frontend/js/app.js:13718`
- `frontend/js/app.js:13843`
- `frontend/js/app.js:13844`
- `frontend/js/app.js:13486`
- `frontend/js/app.js:13665`
- `frontend/index.html:2778`

## 수정 근거 코드

- Finance review source version contract:
  - `app/routers/v1/schedules.py:253`
  - `app/routers/v1/schedules.py:1036`
  - `app/routers/v1/schedules.py:1045`
  - `app/routers/v1/schedules.py:3552`
  - `app/routers/v1/schedules.py:15336`
  - `app/routers/v1/schedules.py:15364`
- 회귀 테스트:
  - `tests/test_schedule_finance_submission.py`

## 결론

Phase 4 acceptance criteria는 현재 기준으로 모두 충족했습니다.

- 1차 다운로드는 항상 live-regenerated
- publish replace는 site+month 기준으로 동작
- 2차 다운로드는 latest published artifact 그대로 반환
- update-needed 정상 동작
- multi-site workbook 다운로드 정상 동작
- publish history 최신 3건 정상
- role visibility 정상
- workbook byte/content preservation 확인

따라서 Phase 4 최종 판정은 `PASS`입니다.
