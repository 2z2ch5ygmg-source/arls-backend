# Sentrix HQ Support Submission Workspace Control Fix Manual Checklist

## Refresh behavior
- Open Sentrix HQ support submission workspace.
- Trigger bootstrap failure or use a degraded backend response.
- Confirm `컨텍스트 새로고침` remains clickable after the failed load.
- Confirm it is disabled only while the refresh request is actually running.

## Download control
- Confirm `ARLS artifact 다운로드` is enabled only when `artifact_available = true`.
- Confirm disabled state shows a visible reason such as:
  - `아직 생성된 ARLS artifact가 없습니다.`
  - `최신 artifact를 찾을 수 없습니다.`

## Review control
- Confirm `검토` is disabled when no workbook file is selected.
- Confirm disabled state shows a visible reason such as:
  - `업로드된 파일이 없습니다.`
  - `아직 생성된 ARLS artifact가 없습니다.`
- After selecting a workbook, confirm `검토` becomes enabled only when workspace context is usable.

## Error/degraded UX
- Force workspace bootstrap failure.
- Confirm an inline banner is shown with retry guidance.
- Confirm month/site metadata remains visible if a last known safe workspace exists.
- Confirm buttons do not remain silently inert.

## Stale state handling
- Load workspace successfully once.
- Then cause bootstrap failure and refresh.
- Confirm UI enters explicit degraded/error behavior.
- Confirm old action bindings are not silently reused as if context were still healthy.
