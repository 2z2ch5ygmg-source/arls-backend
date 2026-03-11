# Sentrix HQ Support Submission Workspace Control-State Fix Notes

## Scope
- Targeted frontend-only repair for the Sentrix HQ support submission workspace.
- No workbook parser changes.
- No unrelated Sentrix screen redesign.

## Production issue addressed
- After workspace bootstrap failure, major controls became inert:
  - 컨텍스트 새로고침
  - ARLS artifact 다운로드
  - 검토

## Fix summary
- Added explicit frontend workspace states:
  - `loading`
  - `retrying`
  - `ready`
  - `no_artifact`
  - `no_review`
  - `degraded`
  - `error`
- Added state derivation from workspace bootstrap contract:
  - `artifact_available`
  - `artifact_metadata`
  - `empty_state`
  - `degraded_state`
  - `upload_readiness`
  - `review_readiness`
  - `action_state`
- Made refresh retry-safe:
  - refresh is disabled only while the refresh request itself is in flight
  - failed bootstrap no longer permanently disables retry
- Added visible disabled reasons for major actions:
  - download
  - inspect/review
  - apply
- Added inline banner for degraded/error/retrying state so the workspace does not appear dead.
- Prevented stale half-dead UI by disabling major actions explicitly when fallback display state is being shown.

## Files changed
- `/Users/mark/Desktop/security-ops-center/static/app.js`
- `/Users/mark/Desktop/security-ops-center/static/index.html`
- `/Users/mark/Desktop/security-ops-center/static/css/components.css`
