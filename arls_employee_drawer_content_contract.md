## 개요 Tab
Order:
1. KPI summary grid
2. Basic workforce information
3. Recent attendance preview
4. Recent request preview
5. Upcoming schedule preview

## 출퇴근 Tab
Order:
1. Attendance KPI grid
2. Recent 7-day attendance feed
3. Compressed empty or unavailable state when needed

## 스케줄 Tab
Order:
1. Schedule KPI grid
2. Upcoming schedule feed
3. Optional future recent-change section only if backend supports it cheaply
4. Compressed empty or unavailable state when needed

## 휴가·요청 Tab
Order:
1. Leave KPI grid
2. Request KPI grid
3. Recent leave feed
4. Recent request feed
5. Compressed empty or unavailable state when needed

## KPI Rendering Rules
- KPIs render in compact cards, typically 2x2.
- Meaningful zero values may render as `0`.
- Cards can show subtle status emphasis using tone or badge state.
- Empty or unavailable KPI groups should not force multiple large zero cards.

## List Rendering Rules
- Recent-history sections use compact feed rows, not large cards.
- Feed item structure:
  - primary title line
  - secondary subtitle line
  - optional muted metadata
  - right-side status chip or time info

## Zero / Empty / Unavailable Rules
- `ok`: render the metric value directly, including valid `0`.
- `empty`: render a compact empty-state message instead of a KPI wall.
- `unavailable`: render a subtle unavailable message such as `데이터를 불러올 수 없습니다`.

## Loading / Error Rules
- KPI areas use skeleton cards while loading.
- Recent lists use skeleton rows while loading.
- One failing section should render a local empty/error state where possible instead of collapsing the whole drawer.

## Intent
- Identity first
- Current operational state second
- Recent useful activity third
- Secondary detail only after the operator has enough at-a-glance context
