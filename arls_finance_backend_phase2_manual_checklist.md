# ARLS Finance Backend Phase 2 Manual Checklist

## 1. 1차 다운로드 Regeneration
- As Supervisor, request `finance-submission/review-excel` for a site+month.
- Change live ARLS monthly schedule or Sentrix-derived support state.
- Request 1차 download again.
- Confirm the regenerated workbook reflects the changed live state.
- Confirm no stale saved 1차 file is reused.

## 2. Finance Publish Replace
- Download 1차 for a site+month.
- Edit workbook content visibly.
- Run `final-upload/preview` and confirm preview is publish validation, not schedule apply preview.
- Apply publish.
- Confirm current `active_final_batch_id` changes to the new batch.
- Confirm older publish remains in history and is no longer current.

## 3. Workbook Byte Preservation
- Publish a workbook containing formulas, formatting, hidden rows/cols, merged cells, widths, and page setup changes.
- Download single-site 2차.
- Confirm downloaded file matches uploaded workbook bytes/behavior exactly.

## 4. 2차 Latest Artifact Retrieval
- Publish version A for a site+month.
- Download 2차 and confirm version A is returned.
- Publish version B for the same site+month.
- Download 2차 again and confirm version B is returned without live regeneration.

## 5. Multi-Site 2차 Packaging
- Ensure at least two sites have current published Finance artifacts for the same month.
- Download with `scope=selected` and repeated `site_codes`.
- Confirm one workbook is returned.
- Confirm one visible sheet exists per selected site.
- Confirm each sheet name equals the site name exactly.

## 6. HQ Site Status
- Before any publish exists, confirm site row shows `파일 없음` and `selectable=false`.
- After first publish, confirm site row shows `게시 완료` and `selectable=true`.
- Download 2차 as HQ/Development.
- Publish a newer Finance file for the same site+month.
- Reload HQ workspace and confirm the site changes to `업데이트 필요`.

## 7. Publish History
- Publish at least 4 versions for the same site+month.
- Call `finance-submission/status`.
- Confirm only latest 3 history entries are returned to UI.
- Confirm exactly one history row has `is_current=true`.

## 8. Role Rules
- Supervisor: can view status, download 1차, preview/apply publish for own site scope.
- HQ: can view status, download 1차, preview/apply publish, access HQ workspace, download 2차.
- Developer/Master: can select tenant/site, access both flows.
- Vice Supervisor: confirm Finance backend routes return `403`.
