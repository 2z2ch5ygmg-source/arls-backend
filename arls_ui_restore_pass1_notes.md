## ARLS Excel Workflow UI Ownership Restore - Pass 1

### Files changed
- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/css/styles.css`

### Old scattered ownership problems
- `Excel로 근무표 간편 제작` 탭은 사실상 기본 월간 업로드만 보여서 전체 Excel workflow owner처럼 보이지 않았습니다.
- `보고` 탭이 지원근무자 제출/export/handoff 흐름을 사실상 메인 작업공간처럼 갖고 있어, 사용자가 어디서 시작해야 하는지 혼동됐습니다.
- `근무 템플릿 생성` 탭 안에 매핑 프로필이 같이 노출되어 월간 업로드 workflow와 템플릿 관리의 소유권이 섞여 보였습니다.

### Removed or demoted duplicate/wrong entry points
- `보고` 탭의 지원근무자 제출 영역은 full workflow shell에서 shortcut/card 역할로 낮췄습니다.
- `근무 템플릿 생성` 탭의 매핑 프로필 직접 소유 UI는 제거하고, `Excel workflow에서 열기`만 남겼습니다.
- 지원근무 Excel 흐름의 메인 진입은 `스케쥴 > 근무일정 > Excel로 근무표 간편 제작` 한 곳으로 정리했습니다.

### New workflow order
`Excel로 근무표 간편 제작` 안에서 다음 순서가 보이도록 재배치했습니다.

1. `매핑 프로필 설정`
2. `기본 월간 근무표 업로드`
3. `HQ 제출용 추출`
4. `HQ 지원근무자 반영 업로드`

- 상단에 workflow step 탭을 추가해 각 구간으로 바로 이동할 수 있게 했습니다.
- 지점/월/현재 단계 요약을 상단 context strip으로 보여 workflow family라는 점을 강화했습니다.
- 기본 월간 업로드는 기존 준비/분석 결과/적용 3단계를 유지한 채 Step 2로 감쌌습니다.

### Mapping profile move
- 매핑 프로필 요약/설정 UI를 `Excel로 근무표 간편 제작` Step 1로 옮겼습니다.
- 기존 템플릿 탭에는 secondary note와 `Excel workflow에서 열기` 버튼만 남겼습니다.
- 따라서 월간 workbook 분석 전에 필요한 준비가 같은 workflow 안에서 보입니다.

### Report tab ownership correction
- `보고` 탭은 더 이상 지원근무자 제출의 메인 owner처럼 보이지 않습니다.
- `지원근무자 제출(바로가기)`는 `Excel workflow`의 Step 3/4로 보내는 shortcut 역할만 수행합니다.
- `Finance 스케쥴 제출(월말)`은 계속 `보고` 탭의 고유 업무로 유지했습니다.

### Intentionally not changed
- 월간 업로드 parser/apply business logic 자체는 재설계하지 않았습니다.
- Sentrix 내부 roster/ticket truth 소유 구조는 변경하지 않았습니다.
- 모바일 레이아웃은 변경하지 않았습니다.
- Finance workflow 상세 로직은 이번 pass 범위에서 유지했습니다.
