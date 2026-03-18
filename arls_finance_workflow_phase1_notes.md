# ARLS Finance Workflow Phase 1 Notes

## Files Changed
- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/css/styles.css`
- `app/schemas.py`
- `app/routers/v1/schedules.py`

## Old UI Problems
- Finance actions were split into technical download/upload tabs instead of the real operator workflow
- 1차 download, publish upload, and HQ 2차 download were mixed together on the same surface
- HQ had to infer site freshness from raw or indirect text instead of an explicit status board
- Recent publish history was not surfaced as operator-facing history
- Main surface exposed too much implementation language and too little action guidance
- Review route labeling in the drawer pointed to the wrong schedule workflow (`hq-upload`) instead of Finance reports

## New Workflow Structure
- Rebuilt the Finance reports workspace into two explicit flows
- Flow A: `Finance용 스케쥴 제출`
  - context selection
  - `1차 스케쥴 다운로드`
  - edited workbook upload + `업로드 미리보기`
  - `게시`
  - recent publish history
- Flow B: `지점별 스케쥴 업로드 확인`
  - month/tenant context
  - per-site publish status table
  - bulk selection helpers
  - `2차 스케쥴 다운로드`

## Role Visibility Behavior
- Supervisor, HQ, Development/Master can access Flow A
- HQ, Development/Master can access Flow B
- Vice Supervisor is excluded from the Finance workflow in this phase
- Development/Master can switch tenant through the existing ARLS dev tenant context

## How 1차 / 2차 Flow Is Presented
- 1차 flow is presented as an operator sequence: download -> edit -> upload -> preview -> publish
- 2차 flow is presented as an HQ review table with explicit site states and a multi-site workbook download action
- The review drawer/menu entry now routes into the Finance reports workspace review subview instead of the support HQ upload wizard

## How Technical Clutter Was Reduced
- Removed technical download/upload subtabs from the main Finance surface
- Kept operator-facing labels only on the primary surface
- Moved technical detail exposure into a collapsed `상세 정보` section for Development/Master only
- Replaced raw-state inference with direct status labels: `게시 완료`, `파일 없음`, `업데이트 필요`
- Limited publish history to the latest 3 entries

## Minimal Compatibility Wiring Added
- Added Finance publish history to the status payload
- Added HQ workspace endpoint for month-wide per-site publish status
- Added multi-site 2차 download support so the frontend can request one workbook with multiple sheets
- Added exact site-name sheet cloning on the final workbook bundling path

## What Was Intentionally Not Changed
- Mobile-specific redesign was not introduced
- Sentrix UI was not modified
- Existing Excel 근무표 업로드/자동등록 workflow was not redesigned as part of this task
- Backend Finance business logic was not rewritten beyond the minimum compatibility needed for the new UI
- Raw artifact internals were not promoted into the main operator surface
