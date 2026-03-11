## Primary Visible Owner Workspace
- Primary owner workspace: `ARLS > 스케쥴 > 근무일정 > Excel로 근무표 간편 제작`
- ARLS visible ownership in this workspace:
  - 기본 근무표 업로드
  - HQ 제출용 추출
  - HQ 지원근무자 반영 업로드 entry/handoff
  - 매핑 프로필 설정

## Internal Workflow Order
1. `매핑 프로필 설정`
2. `기본 월간 근무표 업로드`
3. `HQ 제출용 추출`
4. `HQ 지원근무자 반영 업로드`

- Step 2 keeps the existing `준비 -> 분석 결과 -> 적용` inner flow.
- Step tabs inside the workspace are navigation/ownership markers, not separate products.

## Section Ownership
- Step 1: ARLS monthly workbook mapping preparation
- Step 2: ARLS base monthly workbook upload/analyze/review/apply
- Step 3: ARLS support-demand workbook artifact generation/export
- Step 4: ARLS visible handoff entry for HQ roster submission, with Sentrix as internal processing owner

## Report Tab Role After Cleanup
- `보고` tab remains a report/shortcut surface.
- `지원근무자 제출` in `보고` is shortcut-only and must not compete with the Excel workflow as primary owner.
- `Finance 스케쥴 제출(월말)` remains primarily in `보고`.

## Mapping Profile New Location
- Main visible location: `Excel로 근무표 간편 제작` Step 1
- `근무 템플릿 생성` may keep only a secondary link/note pointing back to Excel workflow

## Permission Display Behavior
- Base monthly upload: Supervisor and above
- Tenant-wide/HQ users see broader site scope
- HQ-oriented support sections should visibly indicate Sentrix handoff ownership
- If a role cannot execute Step 3/4 actions, buttons stay disabled and the section remains informational

## Shortcut-Only Surfaces
- `보고 > 지원근무자 제출(바로가기)` is shortcut-only
- `근무 템플릿 생성 > 매핑 프로필` is shortcut-only
- Full workflow ownership must remain in `Excel로 근무표 간편 제작`
