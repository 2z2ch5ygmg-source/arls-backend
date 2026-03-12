# ARLS Excel Workflow Wizard UI Contract

## Primary visible owner workspace
- `스케쥴 > 근무일정 > Excel로 근무표 간편 제작`

## Tab structure
- Base owner tab:
  - `Excel로 근무표 간편 제작`
- HQ owner tab:
  - `지점별 스케쥴 업로드 확인`

## Role visibility rules
- Base owner tab: visible to existing upload-capable users.
- HQ owner tab: visible only to HQ / Development / Master.
- Normal Supervisor / Vice Supervisor do not see the HQ owner tab.

## Step structure

### Base owner tab
1. 매핑 프로필 사전 설정
2. 업로드 대상 선택
3. 양식 다운로드 + 파일 업로드
4. 반영 검토
5. 적용 진행 / 완료

### HQ owner tab
3. HQ 제출용 추출
4. HQ 작성본 업로드
5. 업로드 미리보기
6. 업로드 진행 / 완료

## Context bar rules
- Always show:
  - tenant
  - site
  - month
  - file name
  - revision
  - current step
- Context bar updates as the active owner tab / step changes.

## Step transition rules
- Only one step body is visible at a time.
- Previous step body is hidden when moving forward.
- Explicit previous/next actions are used instead of scroll discovery.
- Analysis/apply in progress locks:
  - file
  - site
  - month
  - related mutating actions

## Mapping profile new visible ownership
- Mapping profile readiness belongs to Base Step 1.
- Step 1 shows:
  - readiness badge
  - compact mapping summary
  - manage/edit entrypoint
- Template-management area may keep a secondary technical access point only.

## HQ tab behavior
- Export is the first visible HQ step.
- Upload is the second HQ step.
- Preview uses aggregated support-scope rows.
- Completion is a dedicated finish state, not a long-scroll continuation.

## Resume UX
- HQ wizard persists local draft metadata:
  - month
  - site
  - current step
  - artifact id
  - revision
  - file name metadata
- On re-entry, the user is asked whether to resume.
- Resume reapplies saved context after site options are available.

## Partial stale UX
- This pass preserves stale detection and visible state messaging in the upload flow.
- Full partial-site stale selection/download matrix behavior is intentionally deferred; wizard ownership restore was prioritized first.

## Shortcut-only surfaces
- 보고 tab may keep shortcut/export entrypoints.
- The true visible workbook owner remains the upload wizard workspace.
