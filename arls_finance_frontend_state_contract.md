# ARLS Finance Frontend State Contract

## 1. Flow A State Machine
- Idle
  - tenant/site/month not fully selected yet
  - `1차 스케쥴 다운로드`, `업로드 미리보기`, `게시` stay blocked as appropriate
- Context Ready
  - tenant/site/month selected
  - latest submission status is fetched from `GET /api/v1/schedules/finance-submission/status`
- Review Downloading
  - `1차 스케쥴 다운로드` in flight
  - success => file download + compact success toast + status refresh
  - failure => user-facing error toast
- Upload Ready
  - edited workbook selected
  - file name / site / month summary updates immediately
- Preview Loading
  - `업로드 미리보기` in flight against `POST /api/v1/schedules/finance-submission/final-upload/preview`
- Preview Ready
  - preview rows, blocked reasons, summary cards rendered
  - `게시` enabled only when `can_apply=true` and preview batch id exists
- Publish Loading
  - `게시` in flight against `POST /api/v1/schedules/finance-submission/final-upload/{finance_batch_id}/apply`
- Publish Complete
  - success banner shows `게시 완료`
  - latest status and latest 3 publish history items are refetched
  - uploaded file input is cleared so stale file metadata is not left on screen
- Publish Error
  - inline apply result shows failure message
  - preview state stays visible only for the current attempt

## 2. Flow B State Machine
- Hidden
  - tab removed for roles outside HQ / Development backend-allowed review roles
- Loading
  - month or tenant changes trigger `GET /api/v1/schedules/finance-submission/hq-workspace`
- Ready
  - per-site rows render from backend-provided `status`, `selectable`, `note`
- Selecting
  - checkbox state updates `selectedSiteCodes` live
  - `완료 지점 전체 선택` selects every backend-selectable row
  - `선택 해제` clears the current selection
- Final Downloading
  - `2차 스케쥴 다운로드` requests `GET /api/v1/schedules/finance-submission/final-excel`
- Final Download Complete
  - compact success banner shown
  - HQ workspace refetched so backend acknowledgement clears `업데이트 필요` when current actor catches up
- Final Download Error
  - download button remains disabled when no valid rows are selected
  - backend/transport errors surface through user-facing error messaging

## 3. Loading / Success / Error States
- Flow A
  - review download: toast-driven loading/success/error
  - preview: inline batch info + toast feedback
  - publish: inline apply result + strong success banner + toast
- Flow B
  - workspace fetch: top state pill switches between `상태 확인 중`, `조회 실패`, normal summary states
  - final download: success banner + toast
  - no selection: download button disabled and helper text explains why

## 4. Publish History Rendering Rules
- Source: `status.publish_history`
- Render latest 3 items only
- Per row fields:
  - `uploaded_at`
  - `actor`
  - `site_name` or `site_code`
  - `month`
  - current/latest badge from `is_current`
- Empty state: compact panel `최근 게시 이력이 없습니다.`

## 5. Site Status Rendering Rules
- Source: `hq-workspace.sites[]`
- Main columns:
  - 선택
  - 지점명
  - 상태
  - 최근 게시 시각
  - 메모
- Status mapping:
  - `게시 완료` => green pill, selectable
  - `파일 없음` => red pill, not selectable
  - `업데이트 필요` => orange pill, selectable
- Summary cards above the table show:
  - 게시 완료 수
  - 파일 없음 수
  - 업데이트 필요 수
  - 현재 선택 수

## 6. Update-Needed Behavior
- Frontend does not simulate `업데이트 필요` in local storage or in-memory fake state
- Backend `status` is treated as the source of truth
- After successful 2차 download, frontend refetches the HQ workspace so backend acknowledgement state can move rows from `업데이트 필요` to `게시 완료`
- `업데이트 필요` stays visually distinct and selectable until backend says the actor is caught up

## 7. Technical Metadata Visibility Rules
- Normal operator UI hides:
  - artifact ids
  - raw revision ids
  - source batch ids
  - lineage/debug identifiers
- If backend returns technical metadata, frontend shows it only in the collapsed `상세 정보` area
- Technical details remain gated behind the existing development tenant-selection capability and are not primary workflow content
