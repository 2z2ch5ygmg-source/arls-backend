# ARLS Finance UI Contract

## Scope
- Target: ARLS frontend Finance workflow in the schedule reports workspace
- Phase: UI Rebuild Phase 1
- Backend change scope: minimal compatibility wiring only for publish history, HQ site-status workspace, and multi-site 2차 download

## Flow A: Finance용 스케쥴 제출
1. 컨텍스트 선택
- Fields: `tenant`, `site`, `month`
- Controls:
  - Development/Master: tenant select visible
  - HQ/Supervisor: tenant readonly, fixed to own tenant
  - Supervisor: site defaults to own site through scoped site options
  - HQ: site select can choose any site in own tenant
- Main surface summary cards:
  - 현재 상태
  - 최근 1차 다운로드
  - 현재 게시본
  - 안내

2. 1차 스케쥴 다운로드
- Primary action label: `1차 스케쥴 다운로드`
- Helper copy explains that the workbook is regenerated from current ARLS + Sentrix live state

3. 수정본 업로드 / 미리보기
- File input for edited Finance workbook
- Visible summary fields:
  - 파일명
  - 대상 지점
  - 대상 월
  - 미리보기 상태
- Primary action label: `업로드 미리보기`
- Preview table is operator-facing and avoids raw technical jargon

4. 게시
- Summary fields:
  - 게시 대상
  - 대상 월
  - 미리보기 요약
  - 게시 상태
- Primary action label: `게시`
- Success state shows:
  - 게시 완료
  - 현재 게시본이 최신 상태
  - compact site/month/time summary

5. 최근 게시 이력
- Latest 3 rows only
- Fields:
  - 게시 시각
  - 게시자
  - 지점
  - 대상월
  - 현재 게시본 여부

## Flow B: 지점별 스케쥴 업로드 확인
1. 대상 월 선택
- Fields: `tenant`, `month`
- Controls:
  - Development/Master: tenant select visible
  - HQ: tenant readonly, fixed to own tenant

2. 지점별 상태 확인 + 선택
- Table columns:
  - 선택
  - 지점명
  - 상태
  - 최근 게시 시각
  - 메모
- Bulk actions:
  - `완료 지점 전체 선택`
  - `선택 해제`

3. 2차 스케쥴 다운로드
- Primary action label: `2차 스케쥴 다운로드`
- Download behavior:
  - multiple selected sites -> one workbook
  - each site -> separate sheet
  - sheet name = exact site name from published workbook context
- Helper copy states the workbook is merged by selected sites into one file

4. 완료 후 상태 확인
- Optional success banner after 2차 download
- If a newer publish exists after previously acknowledged HQ download, state changes to `업데이트 필요`

## Role Visibility Rules
- Flow A visible: `Supervisor`, `HQ_Admin`, `Developer`
- Flow B visible: `HQ_Admin`, `Developer`
- `Vice_Supervisor` is excluded from the rebuilt Finance workflow in Phase 1
- Development/Master tenant switching is allowed through the existing dev tenant context model

## State Values And Meanings
### Flow A top-level operator states
- `1차 다운로드 전`: no review download yet for the selected site + month
- `수정본 업로드 대기`: 1차 download happened and edited workbook upload is expected
- `게시 완료`: current published workbook exists and is latest
- `다시 게시 필요`: live source changed after prior publish; operator should regenerate/review and republish
- `검토 필요`: publish flow needs operator review due to conflict or validation condition

### Flow B site-status states
- `게시 완료`
  - Published workbook exists
  - Selectable
  - Green state
- `파일 없음`
  - No published workbook exists for the site + month
  - Not selectable
  - Red state
- `업데이트 필요`
  - Newer published workbook exists after HQ previously downloaded that site/month
  - Selectable
  - Orange state

## Publish History Fields
- `uploaded_at`
- `actor`
- `site`
- `month`
- `is_current`

## Update-Needed UX
- Rendered directly in the Flow B main table, not hidden in technical metadata
- Uses distinct orange state pill and explanatory memo text
- Remains selectable for 2차 download
- Client-side acknowledgement marker is stored per user + tenant + month + site after successful 2차 download

## Hidden Technical Metadata Policy
- Hidden from normal operator surface:
  - artifact ids
  - raw revision strings in primary cards/tables
  - source batch ids
  - backend ownership / handoff jargon
- Development/Master only optional details area may show compact diagnostic fields
- Technical details must remain inside collapsed `상세 정보`

## Main Table Columns
### Flow B HQ review table
- 선택
- 지점명
- 상태
- 최근 게시 시각
- 메모

### Flow A publish history table
- 게시 시각
- 게시자
- 지점
- 대상월
- 현재 게시본
