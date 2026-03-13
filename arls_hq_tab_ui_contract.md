## Tab visibility rules

- `Excel로 근무표 간편 제작`
  - visible to all schedule-upload roles
- `지점별 스케쥴 업로드 확인`
  - visible to HQ / Development / Master
  - hidden from Supervisor / Vice Supervisor
- HQ users should see the HQ tab as the visually emphasized workflow entry.

## Tab A vs Tab B state separation

### Tab A state

- tenant
- site
- month
- mapping profile
- uploaded base workbook
- preview/apply state

### Tab B state

- tenant
- month
- selected site set
- last downloaded revision/workbook context
- uploaded HQ workbook reference
- inspect/apply result
- dismissible success banner

- Tab B must not inherit Tab A selected site/month/file.
- Tab A must not inherit Tab B tenant/month/selected sites.

## Step structure

### Tab A

1. 매핑 프로필 선택
2. 업로드 컨텍스트 선택
3. 양식 다운로드 + 파일 업로드
4. 반영 검토
5. 적용 진행 / 완료

### Tab B

3. HQ 제출용 추출
4. HQ 작성본 업로드
5. 업로드 미리보기
6. 업로드 진행 / 완료

## Site status table fields

Tab B Step 3 table fields:
- 선택
- 지점명
- 상태
- 최근 업로드 시각
- 메모

Status pill rules:
- 업로드 완료
- 파일 없음
- 재업로드 필요 / stale

Selection rules:
- file-missing rows are disabled
- `완료 지점 전체 선택` selects only ready rows
- `선택 해제` clears the current selected-site set

## Mismatch handling behavior

Step 4 upload mismatch stays in the same page.

Required in-place handling:
- selected site missing from workbook => explicit error
- workbook contains unselected extra site => explicit error
- damaged sheet-name fallback may use BC34 text
- unresolved sheet/site mapping blocks continue
- user can replace the file without leaving Step 4

## Preview table contract

Tab B Step 5 preview row grain:
- one row per site/date/shift scope

Columns:
- 시트명
- 지점
- 날짜
- 구분
- 요청인원수
- 입력인원수
- 근무자명
- Ticket상태
- 사유

Behavior:
- default filter = 오류/검토 중심
- `전체 보기` toggle supported
- 근무자명 is joined by comma in source order
- day reason uses Sentrix support-request reason model
- night reason uses workbook 작업목적

## Technical metadata visibility rules

### HQ / field users

Hide from primary workflow surfaces:
- artifact_id
- raw revision
- source batch id
- raw ownership / bridge / internal system wording

### Development / Master

- May inspect the same metadata only in collapsed `상세 정보`

## Draft / resume behavior

On Tab B re-entry, prompt:
- `마지막 종료 시점에서 다시 시작하시겠습니까?`

If resumed, restore:
- month
- selected sites
- current step
- uploaded file reference if available
- last downloaded revision state if available

## Partial stale behavior

- If some selected sites are valid and some are stale, partial continue is allowed.
- Processed vs excluded counts must be explicit.
- Excluded stale sites remain visible and do not force a full restart.
