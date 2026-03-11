## Manual Checklist

### Excel workflow ownership
- `스케쥴 > 근무일정 > Excel로 근무표 간편 제작`에 들어가면 상단에 4단계 workflow가 보인다.
- 순서가 `매핑 프로필 설정 -> 기본 월간 근무표 업로드 -> HQ 제출용 추출 -> HQ 지원근무자 반영 업로드`로 보인다.
- 상단 context strip에 대상 지점, 대상 월, 현재 단계가 표시된다.

### Mapping profile
- Step 1에서 현재 매핑 준비 상태와 missing mapping 요약이 보인다.
- `매핑 프로필 설정` 버튼으로 기존 편집 drawer/modal이 열린다.
- `근무 템플릿 생성` 탭에서는 매핑을 직접 관리하지 않고 `Excel workflow에서 열기`만 보인다.

### Base monthly upload
- Step 2 안에서 기존 준비 / 분석 결과 / 적용 흐름이 그대로 동작한다.
- 파일/지점/월 변경 시 기존 분석이 stale 처리되는 기존 동작이 유지된다.

### HQ support flow
- Step 3에서 지원수요 workbook 추출 상태와 다운로드 버튼이 보인다.
- Step 4에서 artifact handoff 정보와 `Sentrix에서 지원근무자 제출 열기` 버튼이 보인다.
- HQ 권한이 없으면 Step 3/4 action section이 disabled tone으로 보인다.

### Reports tab cleanup
- `보고` 탭의 지원근무자 제출은 full workflow가 아니라 shortcut card처럼 보인다.
- `보고` 탭에서 `Excel workflow에서 열기`를 누르면 `Excel로 근무표 간편 제작`의 해당 단계로 이동한다.
- `Finance 스케쥴 제출(월말)`은 계속 `보고` 탭에서 보인다.
