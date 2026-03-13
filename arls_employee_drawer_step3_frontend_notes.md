## Files Changed
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`

## Old Content Problems
- The drawer body felt like a cramped data dump rather than an operator console.
- The old layout relied on too many weak KPI cards and fragmented tabs.
- Recent attendance, schedule, leave, and request information were visually buried.
- Empty or unavailable sections often looked the same as real zero values.

## Rebuild Summary
- `개요` is now the operational default tab and uses:
  - a compact 2x2 KPI grid
  - workforce facts
  - three compact recent activity feeds
- `출퇴근` now prioritizes:
  - recent 30-day attendance KPI summary
  - recent 7-day attendance feed
  - one compressed empty state when records do not exist
- `스케줄` now prioritizes:
  - current/next week KPI strip
  - upcoming schedules feed
  - concise no-upcoming empty state
- `휴가·요청` now combines:
  - leave KPI summary
  - request KPI summary
  - recent leave feed
  - recent request feed

## Empty-State Compression
- Actual zero values still render as `0` where meaningful.
- `empty` data now renders as one compact explanatory block instead of multiple empty cards.
- `unavailable` data renders as a distinct unavailable message instead of pretending to be zero.

## Recent List Rendering
- Recent sections now use compact feed rows instead of large repeated cards.
- Each list item uses:
  - one primary line
  - a short subtitle line
  - optional muted metadata
  - a right-aligned status chip where useful

## Loading States
- The drawer body now uses section-shaped skeleton blocks rather than a single weak placeholder.
- KPI and feed areas shimmer independently so the shell feels intentional while loading.

## What Was Intentionally Not Changed
- Drawer open/close behavior
- Employee selection model from the list
- Backend summary contract from Step 2
- Mobile layouts
