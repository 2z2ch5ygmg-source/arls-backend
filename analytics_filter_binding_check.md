# Sentrix Analytics Filter Binding Check

## Controls Checked

| Control | Wiring Status | Evidence | Fixed |
| --- | --- | --- | --- |
| 기간 quick filters (`7D/30D/90D/직접설정`) | Properly wired | `analyticsState.rangeMode` 갱신 후 `queueRefreshAnalyticsView()` 호출 | No logic change, desktop visual emphasis만 강화 |
| 직접설정 날짜 | Properly wired | `fromDate/toDate` 갱신 후 refresh | No |
| 사이트 filter | Partially wired | 기존에는 incidents location만 option source로 사용 | Yes. incidents + tickets 모두에서 site option 생성 |
| 비교 지표 selector | Properly wired | `analyticsState.metric` 갱신 후 `renderAnalyticsStoreComparison()` | No |
| 정렬 selector | Properly wired | `analyticsState.comparisonSort` 갱신 후 rerender | No |
| 표시 개수 selector | Properly wired | `analyticsState.comparisonLimit` 갱신 후 rerender | No |
| KPI totals | Properly wired | `renderAnalyticsKpis(model)` 가 current filtered model 사용 | No |
| Trend totals/delta | Properly wired | `renderAnalyticsTrends(model)` 가 current model 사용 | No |
| Heatmap/day tabs | Properly wired | `analyticsState.heatmapDay/heatmapDetail` 기반 rerender | No |
| Comparison summary / ranking / insight | Partially wired | single-site 판정이 `ranked.length === 1` 이라 Top 1과 실제 single-site를 혼동 가능 | Yes. real scoped site count(`rankedAll.length <= 1`) 기준으로 수정 |
| KPI card click affordance | Broken/misleading | 카드 click handler는 있었지만 HTML에 `data-kpi-jump` 가 없어 inert 상태 | Yes. 실제 jump target 연결 |

## What Was Fixed
- 사이트 selector source를 incidents + tickets 로 확장
- comparison single-site mode를 실제 scoped store count 기준으로 수정
- KPI strip 카드에 실제 jump target을 부여해 dead affordance 제거
- summary values는 long sentence 대신 chip row로 렌더링되지만, 기존 model 값을 그대로 사용

## Remaining Uncertainty
- 실제 운영 계정으로 다양한 site/month 조합을 수동 전환해보는 브라우저 QA는 별도 확인이 필요합니다.
- upstream source에 site 표기가 서로 다른 alias로 섞여 있으면, selector 분리는 여전히 source normalization 품질에 의존합니다.
