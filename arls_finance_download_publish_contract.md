# ARLS Finance Download / Publish Contract

## 1. 1차 다운로드
- Route: `GET /api/v1/schedules/finance-submission/review-excel`
- Inputs: `tenant_code`, `site_code`, `month`
- Allowed roles: `supervisor`, `hq_admin`, `developer`
- Rule: every request regenerates the workbook from current ARLS live schedule truth plus current Sentrix-derived active support state already materialized in ARLS.
- Rule: do not return a previously saved 1차 file.
- Rule: if live composition fails, return an explicit failure. Do not silently fall back to an old file.
- State side effect: record `review_download_revision`, `review_downloaded_at`, `review_downloaded_by`, `review_download_filename` for the selected site+month.

## 2. Finance 게시 업로드
- Preview route: `POST /api/v1/schedules/finance-submission/final-upload/preview`
- Apply route: `POST /api/v1/schedules/finance-submission/final-upload/{finance_batch_id}/apply`
- Allowed roles: `supervisor`, `hq_admin`, `developer`
- Publish scope: `site + month`
- Publish semantics: replace

### Preview validation
- Validate target `tenant/site/month` against workbook metadata.
- Validate template family/version compatibility.
- Validate workbook structure enough to confirm it is a Finance publishable workbook.
- Do not block publish only because live ARLS/Sentrix state changed after 1차 download.
- Do not run schedule apply during Finance preview.

### Apply behavior
- Store uploaded workbook bytes as-is in `schedule_finance_submission_batches.artifact_bytes`.
- Do not merge workbook contents with an older published file.
- Do not patch parts of an older artifact.
- New publish becomes `active_final_batch_id` for the site+month.
- Previous published artifacts remain in history but are no longer current.
- 2차 downloadable current artifact is always the latest applied publish for the site+month.

## 3. Workbook Byte Preservation
- Stored publish artifact bytes are the exact uploaded workbook bytes.
- Preserved as uploaded:
  - formulas
  - conditional formatting
  - page setup
  - widths / heights
  - hidden rows / columns
  - merged cells
  - manual edits
- Single-site 2차 download returns those stored bytes directly.
- Multi-site 2차 download does not recompute from live ARLS/Sentrix; it packages the visible sheet from each stored published artifact into one workbook.

## 4. 2차 다운로드
- Route: `GET /api/v1/schedules/finance-submission/final-excel`
- Inputs:
  - single-site: `tenant_code`, `month`, `site_code`, `scope=site`
  - multi-site: `tenant_code`, `month`, repeated `site_codes`, `scope=selected`
- Allowed roles: `hq_admin`, `developer`
- Rule: resolve each selected site to the current/latest published Finance artifact for that site+month.
- Rule: do not regenerate from live ARLS/Sentrix for 2차.
- Rule: do not mutate the stored published workbook when returning single-site 2차.
- Rule: when multiple sites are selected, return one workbook with one sheet per site.
- Rule: sheet name must equal site name exactly.
- Guard: duplicate exact site names are rejected and logged via API error path rather than silently renamed.

## 5. Publish History Schema
- Source: `schedule_finance_submission_batches`
- Exposed through `GET /api/v1/schedules/finance-submission/status`
- UI history fields:
  - `uploaded_at`
  - `actor`
  - `site_code`
  - `site_name`
  - `month`
  - `is_current`
- UI payload returns latest 3 entries.
- Backend keeps full historical rows naturally through retained applied batches.

## 6. Current vs Archived Publish Behavior
- `schedule_finance_submission_states.active_final_batch_id` points to the current publish.
- Older `final_upload` batches with `status='applied'` remain historical publishes.
- Current/latest is derived by comparing history row id with `active_final_batch_id`.
