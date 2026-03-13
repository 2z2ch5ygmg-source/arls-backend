# ARLS Employee Drawer UI Shell Contract

## Drawer width rule
- 우측 side drawer 유지
- 데스크톱 기준 권장 폭: 약 `520px ~ 560px`
- 풀페이지 모달처럼 넓게 확장하지 않음

## Header fields
- 아바타 또는 이니셜
- 직원명
- 직원번호
- 관리번호
- 역할
- 재직 상태
- 회사
- 지점
- 입사일
- 계정 연동 상태
- 연락처/생년월일 보조 메타

## Badge rules
- 역할은 compact neutral badge
- 재직 상태는 상태 배지
- 배지는 직원명 옆에 배치

## Quick actions
- 직원 정보 수정
- 스케줄 보기
- 요청 보기
- 출퇴근 보기
- 필요 시 권한 기반으로만 노출
- 하단 footer가 아니라 헤더 근처에 배치

## Tab structure
- 개요
- 출퇴근
- 스케줄
- 휴가·요청

## Default tab behavior
- 기본 탭은 `개요`
- 개요는 다음을 우선 보여줌
  - 현재 상태 KPI
  - 근무 정보
  - 최근 활동

## Zero/empty-state compression rule
- 데이터가 전혀 없으면 여러 개의 `0` 카드 대신 compact empty state 사용
- 실제 0이 의미가 있는 경우에만 KPI 카드 유지
- 최근 기록이 없으면 “최근 7일 출퇴근 기록이 없습니다” 같은 한 줄 empty block 사용

## Benchmark principles used
- BambooHR: 강한 identity header
- Rippling: 헤더 근처 quick actions
- Shiftee: 직원번호/역할/지점/입사일 같은 workforce field 강조

## Intentionally excluded in this phase
- 백엔드 summary contract 확장
- 전체 이력 페이지급 상세 데이터
- 모바일 전용 레이아웃
- 더보기 드롭다운 액션
