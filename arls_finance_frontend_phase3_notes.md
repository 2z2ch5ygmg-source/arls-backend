# ARLS Finance Frontend Phase 3 Notes

## Files Changed
- `frontend/index.html`
- `frontend/css/styles.css`
- `frontend/js/app.js`
- `arls_finance_frontend_state_contract.md`
- `arls_finance_frontend_phase3_manual_checklist.md`

## Backend Endpoints / Contracts Wired
- `GET /api/v1/schedules/finance-submission/status`
- `GET /api/v1/schedules/finance-submission/review-excel`
- `POST /api/v1/schedules/finance-submission/final-upload/preview`
- `POST /api/v1/schedules/finance-submission/final-upload/{finance_batch_id}/apply`
- `GET /api/v1/schedules/finance-submission/hq-workspace`
- `GET /api/v1/schedules/finance-submission/final-excel`

## How Flow A Works Now
- Context selection still drives the Finance workspace through tenant, site, and month.
- `1차 스케쥴 다운로드` now directly calls the live-regeneration backend route and refreshes status after download.
- Edited workbook selection updates file/site/month summary immediately.
- `업로드 미리보기` uses the backend preview contract and renders inline preview rows, blocked reasons, and preview summary.
- `게시` uses the backend publish apply route, shows a strong success banner on completion, refreshes current status, and reloads latest publish history.
- After successful publish, the selected file input is cleared so stale upload metadata does not linger on screen.

## How Flow B Works Now
- The HQ review/download tab reads backend site status rows directly instead of inferring state in the browser.
- Site rows render `게시 완료 / 파일 없음 / 업데이트 필요` from backend `status` and `selectable`.
- Summary cards at the top now show:
  - 게시 완료 수
  - 파일 없음 수
  - 업데이트 필요 수
  - 현재 선택 수
- `완료 지점 전체 선택` selects every backend-selectable row, including `업데이트 필요` rows.
- `2차 스케쥴 다운로드` calls the backend final artifact route and then refetches the HQ workspace so backend acknowledgement state is reflected immediately.

## How Update-Needed Is Rendered
- Removed the old frontend local-storage acknowledgement logic.
- `업데이트 필요` now comes only from the backend HQ workspace contract.
- Rows in `업데이트 필요` use the orange status pill and remain selectable.
- After a successful 2차 download, frontend reloads the HQ workspace so rows can move back to `게시 완료` when the current actor is caught up.

## How Publish History Is Refreshed
- Flow A publish success triggers a fresh `status` fetch.
- The history section always renders the latest 3 entries from `publish_history`.
- No full page refresh is required.
- Empty history stays as a compact empty-state panel.

## How Technical Clutter Was Reduced
- Removed frontend-only fake status computation for HQ review.
- Kept artifact/revision metadata out of the main operator table.
- Limited advanced metadata to the existing collapsed `상세 정보` section for development-capable users only.
- Main surface now prioritizes user actions, publish history, counts, and status pills instead of technical revision comparisons.

## What Was Intentionally Not Changed
- Mobile layout was not redesigned.
- Sentrix was not modified.
- Finance backend contracts were not redesigned in this phase.
- The old generic Excel upload workflow outside the Finance workspace was not rebuilt here.
- Backend role logic was not rewritten in this frontend wiring step.
