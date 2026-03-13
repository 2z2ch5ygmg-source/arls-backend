## Manual Checklist

### 개요
- Open an employee drawer and confirm `개요` is the default tab.
- Verify the top section shows four compact KPI cards.
- Verify workforce fields render in a 2-column facts area.
- Verify recent attendance, requests, and upcoming schedules render as compact feeds.

### 출퇴근
- Verify `최근 30일 정상 / 지각 / 누락 / 휴가/외출` KPI cards appear first.
- Verify recent attendance rows show 날짜, 예정 시간, 출근/퇴근, 상태.
- Verify no recent records renders one compact empty-state message.

### 스케줄
- Verify `이번주 배정 / 다음주 배정 / 휴가 표시 / 다음 일정` KPI cards appear first.
- Verify upcoming schedules render as a compact list, not large cards.
- Verify no upcoming schedules renders a concise empty-state block.

### 휴가·요청
- Verify leave and request KPI sections both render.
- Verify recent leave entries and recent request entries render as separate compact feeds.
- Verify empty histories render concise empty-state messages instead of blank panels.

### State Distinction
- Verify real zero values render as `0`.
- Verify `empty` sections show user-facing empty messages.
- Verify `unavailable` sections show unavailable copy and do not masquerade as zeros.

### Loading
- Open the drawer on a cold load and verify skeleton KPI blocks and list rows appear.
- Verify a section-level error or empty-state does not collapse the whole drawer.
