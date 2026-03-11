# Sentrix Analytics Desktop Manual Test Checklist

## Desktop Layout
- 1366x768에서 Analytics 탭 진입
- 1920x1080에서 Analytics 탭 진입
- 상단 filter row가 두껍게 비지 않고 툴바처럼 보이는지 확인
- KPI 4개가 한 줄 strip로 보이고 높이/간격이 같은지 확인
- Risk Overview card 좌우 비율이 60~65 / 35~40 수준으로 읽히는지 확인
- donut, grade badge, info button이 하나의 오른쪽 cluster로 읽히는지 확인

## Filter Behavior
- 7D, 30D, 90D 버튼 전환 시 KPI/summary/trend/heatmap/comparison이 모두 갱신되는지 확인
- 직접설정에서 from/to 날짜를 바꾸면 같은 화면 값이 같이 갱신되는지 확인
- 사이트 selector 변경 시 summary, KPI, trend, heatmap, comparison 값이 같이 바뀌는지 확인
- 비교 지표 변경 시 comparison list, summary stat, insight metric이 바뀌는지 확인
- 정렬 변경 시 comparison row 순서가 바뀌는지 확인
- 표시 개수 변경 시 row 수와 comparison context가 같이 바뀌는지 확인

## Popover
- Risk Overview의 `i` 버튼 클릭 시 popover가 버튼 바로 근처에 뜨는지 확인
- comparison toolbar의 `i` 버튼 클릭 시 popover가 버튼 근처에 뜨는지 확인
- 두 popover 모두 다시 클릭하면 닫히는지 확인
- 바깥 영역 클릭 시 닫히는지 확인
- 열린 상태에서 스크롤 시 버튼을 따라 위치가 유지되는지 확인

## Trend And Heatmap
- incidents chart가 ECI3+ chart보다 주도적으로 보이는지 확인
- chart가 과도하게 길고 얕지 않은지 확인
- heatmap header/day chips/legend 간격이 조밀해졌는지 확인
- heatmap이 line chart 구역과 시각적으로 구분되는지 확인

## Comparison
- multi-site 조건에서 left comparison + right insight 구조가 유지되는지 확인
- single-site 조건에서 large comparison canvas처럼 보이지 않는지 확인
- single-site snapshot 카드가 실제 사이트 summary처럼 읽히는지 확인
- selected row accent와 insight panel 값이 일치하는지 확인

## Key Color
- active period button에 subtle key-color가 보이는지 확인
- KPI strip accent bar가 과하지 않지만 읽기 시작점을 주는지 확인
- summary chips 중 중요한 값이 key-color로 구분되는지 확인
- selected comparison row와 insight headline이 key-color로 강조되는지 확인

## No-Data / Sparse Cases
- 데이터가 거의 없는 월/사이트에서 ECI3+ trend가 비정상적으로 길게 보이지 않는지 확인
- single-site이면서 incident volume이 낮은 조건에서도 상단/비교영역이 빈 종이처럼 퍼지지 않는지 확인
