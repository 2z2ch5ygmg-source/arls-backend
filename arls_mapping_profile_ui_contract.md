# ARLS Mapping Profile UI Contract

## Template Screen Ownership
- `근무 템플릿` 화면이 템플릿과 매핑 프로필의 관리 owner다.
- 템플릿 행은 visible action으로 `수정 / 복제 / 비활성화 / 삭제`를 가진다.
- 삭제는 hidden 하지 않고, 불가 시 이유를 함께 보여준다.

## Mapping Profile Tab Structure
- 내부 탭:
  - `근무 템플릿`
  - `매핑 프로필`
- `매핑 프로필` 탭은 업로드용 프로필의 기본 정보와 규칙 상태를 보여준다.

## Profile List Fields
- 프로필명
- 설명
- 적용 범위
- 상태
- 기본 프로필 여부
- 규칙 수
- 마지막 수정일
- 작업

## Profile Editor Fields
- 기본 정보
  - 프로필명
- 매핑 규칙
  - `주간 / 초과 / 야간` grouped rows
  - 시간값
  - 연결 템플릿

## Step 1 Selection Behavior
- Step 1은 기존 프로필을 선택하고 readiness를 확인하는 곳이다.
- 프로필 생성/편집은 Step 1 inline에서 하지 않는다.
- Step 1 관리 버튼은 `근무 템플릿 > 매핑 프로필` owner 화면으로 이동시킨다.

## Readiness States
- `준비 완료`
- `일부 누락`
- `비활성 프로필`
- `프로필 미선택`

## Validation Rules
- 한 프로필 안에서 `(row_type, hour_value)` key는 하나의 template에만 연결된다.
- 누락/비활성/invalid template 참조가 있으면 readiness는 완료가 아니다.
- selected profile이 준비 완료일 때만 upload 다음 단계로 진행할 수 있다.

## What Is Intentionally Excluded
- date-based exception rule UI
- weekday-based exception rule UI
- site-specific exception override UI
- upload preview row-level manual override UI
