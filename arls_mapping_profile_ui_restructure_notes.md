# ARLS Mapping Profile UI Restructure Notes

## Files Changed
- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/css/styles.css`

## Old Ownership Confusion
- `Excel로 근무표 간편 제작` Step 1이 매핑 프로필의 생성/편집 owner처럼 보였습니다.
- `근무 템플릿` 화면은 템플릿만 관리하는 것처럼 보였고, 매핑 프로필은 보조 요약만 노출되어 ownership이 분산돼 있었습니다.
- 템플릿 목록에는 `삭제` 액션이 보이지 않았습니다.

## New Tab / Section Structure
- `근무 템플릿` 화면 안에 내부 탭을 추가했습니다.
  - `근무 템플릿`
  - `매핑 프로필`
- `근무 템플릿` 탭은 템플릿 관리 owner입니다.
- `매핑 프로필` 탭은 업로드용 매핑 프로필 관리 owner입니다.
- `Excel로 근무표 간편 제작` Step 1은 매핑 프로필 선택 및 readiness 확인만 담당합니다.

## How Delete Was Added
- 템플릿 행에 `삭제` 액션을 추가했습니다.
- 현재 사용 중인 매핑 프로필이 있는 템플릿은 삭제 버튼이 비활성화되고 사유를 같이 표시합니다.
- 사용 중이 아니더라도 현재 backend delete API는 없으므로, 삭제는 visible action으로만 제공하고 제한 사유를 분명히 표시합니다.

## How Step 1 Selection Works
- Step 1에 `매핑 프로필 선택` selector를 추가했습니다.
- 선택한 프로필에 대해 아래 정보를 보여줍니다.
  - 프로필명
  - 적용 범위
  - 상태
  - 마지막 수정일
- 규칙 요약은 compact list로 보여줍니다.
- Step 1의 관리 버튼은 프로필 editor를 직접 열지 않고 `근무 템플릿 > 매핑 프로필` owner 영역으로 이동시킵니다.

## How Profile Readiness Is Shown
- readiness badge 상태:
  - `준비 완료`
  - `일부 누락`
  - `비활성 프로필`
  - `프로필 미선택`
- Step 1의 `다음` 버튼은 readiness가 `준비 완료`일 때만 활성화됩니다.
- preview 기준 누락 매핑이 있으면 Step 1 summary에 필요한 key를 그대로 보여줍니다.

## What Was Intentionally Not Changed
- date/weekday/site exception rule UI는 추가하지 않았습니다.
- upload preview row-level override UI는 추가하지 않았습니다.
- backend 다중 매핑 프로필 CRUD 계약은 이번 pass에서 확장하지 않았습니다.
