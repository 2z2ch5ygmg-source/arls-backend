# Sentrix Analytics Desktop Relayout Refinement Notes

## A. What Was Read
- `/Users/mark/Desktop/security-ops-center/AGENTS.md`
- `/Users/mark/Desktop/security-ops-center/static/index.html`
- `/Users/mark/Desktop/security-ops-center/static/css/components.css`
- `/Users/mark/Desktop/security-ops-center/static/js/ui.js`
- `/Users/mark/Desktop/security-ops-center/static/app.js`
- `/Users/mark/Desktop/security-ops-center/sentrix_full_audit/03_ui_pattern_audit.md`
- `/Users/mark/Desktop/security-ops-center/sentrix_full_audit/09_ux_debt_and_broken_flows.md`
- `/Users/mark/Desktop/security-ops-center/sentrix_full_audit/10_implementation_readiness_report.md`
- `/Users/mark/Desktop/security-ops-center/analytics_followup_refinement_notes.md`
- `/Users/mark/Desktop/security-ops-center/analytics_workspace_refactor_notes.md`
- `/Users/mark/Desktop/security-ops-center/sentrix_pc2_task3_4_analytics_density_refinement_notes.md`

## B. Root Causes With Proof
- 상단 요약부가 `summary-primary + separate KPI column` 구조라, 리스크 카드와 KPI가 서로 눈길을 끌지 못하고 빈 면적이 크게 남아 있었습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/index.html`
  - 증거: `/Users/mark/Desktop/security-ops-center/static/css/components.css`
- 리스크 개요 메타가 긴 문장 2줄 텍스트만 갱신하는 방식이라, 기간/스코프/변동/피크가 스캔형 정보가 아니라 문서형 문장으로 보였습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/js/ui.js`
- 도넛과 상태/도움말 버튼이 하나의 클러스터가 아니고, 도움말 popover는 카드 내부에 중첩되어 있었습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/index.html`
- popover가 버튼과 분리되어 보인 직접 원인은 두 가지였습니다.
  - risk popover는 summary card 내부에 들어 있었고, store popover는 comparison toolbar 내부에 들어 있었습니다.
  - 두 popover 모두 viewport 좌표로 찍지만 trigger `right - popoverWidth` 기준 정렬을 써서 버튼 자체가 아니라 우측 끝 정렬처럼 보였습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/index.html`
  - 증거: `/Users/mark/Desktop/security-ops-center/static/js/ui.js`
  - 증거: `/Users/mark/Desktop/security-ops-center/static/app.js`
- 비교영역 single-site 판정이 `ranked.length === 1` 이어서, 실제로는 다중 사이트인데 Top 1 필터만 걸린 상태도 single-site처럼 오인될 수 있었습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/js/ui.js`
- 사이트 selector는 incidents 기준 location만 수집해서, ticket 데이터만 있는 사이트 컨텍스트는 필터에 보이지 않을 수 있었습니다.
  - 증거: `/Users/mark/Desktop/security-ops-center/static/js/ui.js`

## C. Ordered Minimal Fix Plan
1. 상단 summary DOM을 최소 범위로 재배열하고 KPI strip를 summary 위로 승격
2. risk cluster와 info popover를 실제 앵커 구조로 정리
3. analytics runtime summary text를 chip 기반으로 전환
4. comparison single-site 판정과 site selector source를 실제 데이터 기준으로 수정
5. desktop 전용 CSS override로 밀도, 비율, key-color, trend/card sizing 조정

## D. Patch Summary
- 변경 파일
  - `/Users/mark/Desktop/security-ops-center/static/index.html`
  - `/Users/mark/Desktop/security-ops-center/static/css/components.css`
  - `/Users/mark/Desktop/security-ops-center/static/js/ui.js`
  - `/Users/mark/Desktop/security-ops-center/static/app.js`

## Old Layout Problems
- 상단 summary와 KPI가 분리되어 보여서 reading order가 약했습니다.
- Risk Overview card가 너무 넓고 내부 정보가 희박했습니다.
- donut이 우측 빈 공간에 떠 있는 것처럼 보였습니다.
- trend chart 2개가 둘 다 너무 길고 납작했습니다.
- single-site mode에서도 comparison canvas가 과장되어 있었습니다.
- key-color 안내가 약해 화면이 문서처럼 밋밋했습니다.

## Top Area Restructuring
- 상단 broad order는 유지했습니다.
  - page header
  - filter row
  - top summary
  - trend
  - heatmap
  - comparison
- top summary 내부는 이렇게 바꿨습니다.
  - KPI strip를 summary zone 첫 줄로 이동
  - Risk Overview를 가로 2열 요약 카드로 재정렬
  - 왼쪽은 scannable summary + chips + top factors
  - 오른쪽은 grade badge + info button + donut cluster
- KPI strip는 동일 높이, 동일 간격, tone별 accent bar를 갖는 4개 카드로 맞췄습니다.

## Donut Chart Repositioning Logic
- `analyticsRiskGrade` 를 도넛 중앙에서 빼서 우측 cluster head로 이동했습니다.
- grade badge와 info button을 같은 cluster head에 두고, donut은 그 아래 정렬했습니다.
- popover는 summary card 바깥의 analytics root로 이동시켜 card overflow 영향에서 분리했습니다.

## Trend Chart Resizing Logic
- incidents chart를 primary block으로 두고 비중을 키웠습니다.
- ECI3+ chart는 보조 block으로 축소했습니다.
- 두 카드 모두 높이는 약간 올리고, 불필요한 가로 길이는 줄였습니다.
- ECI3+ series가 희박하면 sparse class를 부여해 보조카드 톤을 더 얌전하게 처리했습니다.

## Single-Site Comparison Behavior
- single-site mode 판정을 `visible topN count` 가 아니라 `실제 scoped site count` 기준으로 바꿨습니다.
- single-site mode일 때는 comparison list를 ranking canvas가 아니라 site snapshot 카드로 렌더링합니다.
- 우측 insight panel과 Top 5 카드도 더 짧은 summary 성격으로 유지되게 desktop CSS를 줄였습니다.

## Key-Color Emphasis Rules Applied
- active period chip
- KPI strip accent bar
- Risk summary chips
- selected comparison row
- selected-site insight metric
- single-site snapshot card
- summary/ticket warning 계열 chip

## Popover Bug Root Cause And Fix
- root cause
  - popover가 button 근처의 독립 overlay가 아니라 내부 레이아웃 노드로 박혀 있었습니다.
  - 위치 계산도 trigger 중심이 아니라 right-edge 정렬이라 far-right에 뜬 것처럼 보였습니다.
- fix
  - risk/store popover 둘 다 analytics root 아래로 옮겼습니다.
  - fixed-position popover를 button center 기준으로 계산하도록 수정했습니다.
  - 화면 하단 여유가 부족하면 top으로 flip합니다.
  - scroll/resize 시 재계산은 기존 흐름을 유지했습니다.
  - outside click close / repeat click toggle도 유지했습니다.

## What Was Intentionally Preserved
- analytics 탭의 전체 정보 구조
- 기존 analytics data/state/service 사용
- summary / trend / heatmap / comparison 섹션 자체의 의미
- backend나 parser logic
- 다른 Sentrix 탭과 모바일 레이아웃

## What Was Intentionally Not Changed
- Home, Situation Room, Ticket, Apple Weekly, Report Hub, People/Accounts, Employee Score, Support Worker Status
- analytics 데이터 산식 자체
- workbook/parser/backend API
- 모바일 전용 배치 재설계

## E. Manual QA Targets
- Desktop 1366x768
- Desktop 1920x1080

## F. Regression Guards Added
- site filter option source를 incidents + tickets 로 확장
- single-site mode를 real scoped site count 기준으로 판정
- KPI cards에 실제 jump target을 연결
- risk/store popover를 button-anchored overlay로 고정
