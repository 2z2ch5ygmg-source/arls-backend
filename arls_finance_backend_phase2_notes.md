# ARLS Finance Backend Phase 2 Notes

## Files Changed
- `app/routers/v1/schedules.py`
- `app/schemas.py`
- `migrations/020_schedule_finance_download_acks.sql`
- `tests/test_schedule_finance_submission.py`

## Old Backend Problems
- Finance final upload still called generic schedule `apply_import()`, so Finance publish behaved like live schedule re-apply instead of artifact publish.
- Finance state logic disabled 2차 download when live revision changed after publish.
- HQ `업데이트 필요` existed only as frontend local state and was not computed on the backend.
- Role rules still allowed `vice_supervisor` visibility and blocked HQ from Finance publish upload.
- 1차 download permissions did not match the intended Supervisor-or-above operator flow.

## New Workflow Structure
- 1차 download stays a live regeneration path from current ARLS + Sentrix-derived state.
- Finance upload preview validates workbook family and target scope for publish only.
- Finance apply now publishes the uploaded workbook bytes as the current artifact for site+month.
- 2차 download now reads the latest published artifact instead of comparing against live revision.
- HQ workspace returns per-site status with backend-computed `게시 완료 / 파일 없음 / 업데이트 필요`.

## Current vs Archived Publish Artifact Behavior
- Current publish is the row referenced by `schedule_finance_submission_states.active_final_batch_id`.
- New publish replaces the current pointer for the same site+month.
- Older applied publish batches remain historical rows and appear in publish history, but no longer count as current.

## 1차 / 2차 Distinction
- 1차: live composition export from ARLS current schedule truth + Sentrix active support data already synchronized into ARLS.
- 게시: exact uploaded workbook bytes become canonical final artifact for site+month.
- 2차: artifact retrieval / packaging from latest published Finance artifact only. No live recomposition.

## Update-Needed Logic
- Added persistent HQ download acknowledgement table: `schedule_finance_download_acks`.
- On 2차 download, backend records the actor's last seen publish marker per site+month.
- HQ workspace compares current active publish against that stored marker.
- If a newer publish exists after prior HQ download, status becomes `업데이트 필요`.

## History Implementation
- Publish history is read from `schedule_finance_submission_batches` where `batch_kind='final_upload'` and `status='applied'`.
- UI contract returns latest 3 rows with `uploaded_at`, `actor`, `site`, `month`, `is_current`.

## Role Visibility Behavior
- Flow A view/download/upload: `supervisor`, `hq_admin`, `developer`
- Flow B HQ review/download: `hq_admin`, `developer`
- `vice_supervisor` is no longer part of Finance backend permissions.
- Supervisor site access is enforced through scoped site resolution.

## What Was Intentionally Not Changed
- Frontend rendering and mobile UX were not changed in this phase.
- Sentrix service logic was not modified in this phase.
- Existing generic schedule import workflow was not redesigned.
- The backend does not expose raw artifact ids as required top-level operator fields.
