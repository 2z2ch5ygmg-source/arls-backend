# Final Postfix E2E Defects

## Blocking defects

없음.

이번 postfix QA 범위에서 요구된 8개 시나리오를 막는 workflow-blocking defect는 재현되지 않았습니다.

## Non-blocking issues / verification limitations

### 1. Browser screenshots were not captured in this shell-only pass

- 영향:
  - matrix의 screenshot evidence는 모두 `not captured (shell QA)`로 남았습니다.
- 범위:
  - 제품 defect가 아니라 현재 검증 환경 제한입니다.

### 2. `test_schedule_monthly_export_template.py` local execution is not portable on this machine

- 증상:
  - 일부 테스트가 `/Users/seoseong-won/Documents/rg-arls-dev/backend/app/templates/monthly_schedule_template.xlsx` 하드코딩 경로를 참조해 `FileNotFoundError`로 실패
- 영향:
  - export-template 스타일 회귀를 이 머신에서 추가로 자동 검증하지 못했습니다.
- 판정:
  - 현재 핵심 E2E 시나리오 blocking defect는 아님
  - test harness portability issue

### 3. Separate ARLS UI QA carry-over issue

- 별도 ARLS QA에서 확인된 non-blocking issue:
  - `Master` role이 technical details disclosure를 `Development`처럼 열지 못하는 불일치가 있었습니다.
- 영향:
  - workbook ownership / support-state engine / handoff / notification / bridge / materialization 핵심 흐름에는 직접 영향 없음
- 상태:
  - 이번 pass에서 재수정/재검증 대상은 아니었음
