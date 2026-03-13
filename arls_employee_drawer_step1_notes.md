# ARLS Employee Drawer Step 1 Notes

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`

## Old UI shell problems
- 5개 탭으로 정보가 잘게 쪼개져 드로어가 답답하게 보였다.
- 상단 헤더가 약해서 직원이 누구인지, 현재 어떤 상태인지 즉시 파악하기 어려웠다.
- 출퇴근/스케줄/휴가/요청에 0값 카드가 반복돼 의미 없는 밀도가 높았다.
- 빠른 액션이 하단에 모여 있어 프로필 패널보다 데이터 덤프처럼 보였다.

## New header structure
- 우측 드로어는 유지했다.
- 상단 헤더에 다음을 올렸다.
  - 아바타/이니셜
  - 직원명
  - 직원번호/관리번호
  - 역할 배지
  - 재직 상태 배지
  - 회사, 지점, 입사일, 계정 연동 상태
  - 연락처/생년월일 보조 메타

## New tab structure
- 기존 5탭:
  - 기본정보
  - 출퇴근 요약
  - 스케줄 요약
  - 휴가 요약
  - 요청 이력
- 변경 후 4탭:
  - 개요
  - 출퇴근
  - 스케줄
  - 휴가·요청
- 기본 탭은 `개요`로 변경했다.

## Quick action placement
- 기존 하단 액션 바를 제거하고 헤더 바로 아래로 이동했다.
- 현재 노출 액션:
  - 직원 수정
  - 스케줄 보기
  - 출퇴근 보기
  - 휴가 보기
  - 요청 보기
- 권한에 따라 필요한 액션만 노출한다.

## Zero-card compression policy
- 최근 출퇴근 기록이 없으면 KPI 카드 묶음을 펼치기보다 compact empty state를 우선 사용한다.
- 다가오는 일정이 없으면 스케줄 탭은 요약 카드 대신 빈 상태 블록을 보여준다.
- 휴가·요청 모두 데이터가 없으면 다수의 `0` 카드 대신 하나의 요약 empty block으로 압축한다.
- 개요 탭의 최근 활동도 데이터가 없으면 각 섹션에 compact empty block을 사용한다.

## What was intentionally left for later steps
- 백엔드 summary contract는 그대로 사용했다.
- 출퇴근/스케줄/휴가·요청 탭의 심화 필터/확장 이력 UI는 이번 단계에 포함하지 않았다.
- 더보기 드롭다운, 추가 관리자 액션, 상세 타임라인형 뷰는 이후 단계로 남겼다.
