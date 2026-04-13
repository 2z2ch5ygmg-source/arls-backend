# ARLS Targeted UI Cleanup Route Sweep Verdict

- Generated: 2026-04-13T09:16:50.057Z
- Artifact root: `artifacts/ui-sweep/20260413-1816-arls-ui-cleanup`
- Base URL: http://127.0.0.1:64131/frontend/index.html
- API: mocked
- Required route/viewport pairs: 3
- Captured route/viewport pairs: 3
- Overall route completeness: PASS

## Component Family Presence

| Viewport | Route | Tabs | Filters | Steppers | KPI | Detail panels | Approval flow | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 375 | /home | n/a | n/a | n/a | WARN missing | n/a | n/a | - |
| 768 | /home | n/a | n/a | n/a | PASS (10) | n/a | n/a | - |
| desktop | /home | n/a | n/a | n/a | PASS (10) | n/a | n/a | - |

## Artifact Contract

- `manifest.json`: route, viewport, dimensions, screenshot path, timestamps, console/network counts, checklist status.
- `console.json`: browser console messages captured during each route/viewport pass.
- `network.json`: mocked API requests plus any request failures.
- `desktop/`, `375/`, `768/`: full-page JPEG screenshots per required route.

