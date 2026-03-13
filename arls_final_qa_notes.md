## ARLS Final Workflow Verification - QA Pass

검증 일시: 2026-03-13  
검증 환경: production-like deployed frontend/backend  
프런트 build: `1773368798`  
백엔드 헬스: `https://rg-arls-backend.azurewebsites.net/health -> {"status":"ok"}`

### 사전 상태

- verification only로 진행했고 product code는 수정하지 않았습니다.
- 시작 시 worktree에는 이번 QA와 무관한 미커밋 변경이 있었습니다.
  - [/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py](/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py)
  - [/Users/mark/Desktop/rg-arls-dev/app/schemas.py](/Users/mark/Desktop/rg-arls-dev/app/schemas.py)
  - [/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py](/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py)
- 위 파일들은 건드리지 않고, 검증 산출물만 새로 작성했습니다.

### 검증 방법

- 배포본 확인
  - remote `config.js`에서 build id 확인
  - backend `/health` 확인
- 프런트 구조/권한 코드 확인
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html](/Users/mark/Desktop/rg-arls-dev/frontend/index.html)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js)
- HQ workflow 관련 backend 계약 확인
  - [/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py](/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py)

### 요약 결론

- ARLS는 현재 workbook workflow의 visible owner로 동작합니다.
  - `Excel로 근무표 간편 제작`
  - `지점별 스케쥴 업로드 확인`
- Tab A와 Tab B는 상태를 분리해 유지합니다.
  - Tab A: base upload wizard
  - Tab B: HQ export/upload wizard
- HQ workflow는 wizard형으로 정리되어 있고, 지점 matrix, aggregated preview, completion state가 코드상 구현되어 있습니다.
- 다만 defect 1건 확인:
  - 기술 상세 metadata가 `Development`에게만 열리고 `Master`에게는 숨겨집니다.
  - 요구사항은 `Development/Master` 모두 기술 상세 접근 가능이었으므로 현재 구현은 불일치입니다.

### 상세 확인 결과

#### A. Visible ownership

- top-level schedule tabs:
  - `Excel로 근무표 간편 제작`
  - `Finance용 스케쥴 제출`
  - `지점별 스케쥴 업로드 확인`
- 확인 위치:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2049](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2049)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2051](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2051)
- Excel workflow owner 메시지와 HQ upload header도 ARLS 기준으로 렌더됩니다.
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10175](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10175)

판정: PASS

#### B. Role visibility

- HQ wizard visibility:
  - `canUseScheduleUploadHqWizard()` = `hq_admin`, `developer`, `master`
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L38910](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L38910)
- Supervisor/Vice Supervisor는 HQ wizard tab route 접근 불가
  - route guard:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L17533](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L17533)
  - active tab guard:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L39125](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L39125)

판정: PASS

#### C. Tab A - base upload wizard

- 단계 정의:
  - 매핑 프로필
  - 대상 선택
  - 파일 준비
  - 반영 검토
  - 적용
- 각 단계는 한 번에 한 body만 보이게 숨김 처리됩니다.
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10032](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10032)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10054](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10054)
- context bar:
  - tenant / site / month / file / revision / current step
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9971](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9971)
- 분석 중에는 tenant/site/month/file 잠금:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10208](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10208)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10231](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10231)

판정: PASS

#### D. Tab B independence

- Tab B tenant/month state는 별도 함수 사용:
  - `getScheduleHqTenantCode()`
  - `buildScheduleSupportHqContext()`
  - `getScheduleHqSelectedSiteCodes()`
- Tab A는 별도:
  - `getScheduleBaseTenantCode()`
  - `#scheduleImportSite`
  - `#scheduleImportMonth`
- 확인 위치:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9229](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9229)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9261](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9261)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9335](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9335)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10591](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10591)

판정: PASS

#### E. Tab B Step 3 site matrix

- site matrix/table 존재:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2533](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2533)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2551](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2551)
- buttons:
  - `완료 지점 전체 선택`
  - `선택 해제`
- selectable only for `downloadReady` sites:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10672](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10672)
  - checkbox `disabled = !site.downloadReady`
- recent upload time secondary text 표시:
  - same render block

판정: PASS

#### F. Tab B Step 4 validation

- upload mismatch box in-place 존재:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2610](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2610)
- selected site missing / extra site validation:
  - `buildScheduleSupportHqWorkbookMismatch()`
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10743](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10743)
- BC34 fallback rule은 backend 계약에 존재:
  - [/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py](/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py)
- file replace path:
  - same file input reused, stale reset support present

판정: PASS

#### G. Tab B Step 5 aggregated preview

- aggregated table columns match requested 9-column contract:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2640](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2640)
- `기본 보기 / 전체 보기` toggle 존재:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2635](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2635)
- one row per support scope rendering:
  - `buildScheduleSupportHqAggregatedPreviewRows(...)`
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js)
- 기본 보기 = actionable only 메시지:
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10953](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L10953)

판정: PASS

#### H. Step 6 completion flow

- centered completion state:
  - `업로드 진행중...`
  - `업로드 완료`
  - 종료 버튼 / X
  - [/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2672](/Users/mark/Desktop/rg-arls-dev/frontend/index.html#L2672)
- finish action:
  - resume key clear
  - HQ wizard step reset to export(step 3)
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L50689](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L50689)

판정: PASS

#### I. Draft / resume

- prompt exists:
  - `마지막 종료 시점에서 다시 시작하시겠습니까?`
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9904](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9904)
- restored fields:
  - tenantCode
  - month
  - selectedSiteCodes
  - step
  - artifactId
  - revision
  - fileName
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9877](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9877)

판정: PASS

#### J. Artifact / technical metadata

- HQ artifact selection/download and final state buttons exist.
- 기술 metadata details는 normal user에게 숨김 처리됩니다.
- 하지만 구현은 `Development`만 보이게 하고 `Master`는 제외합니다.
  - [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L11302](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L11302)
  - `canSelectScheduleWorkflowTenant()` 기준이라 `DEV`만 true

판정: FAIL

### 최종 판정

- 전반적 wizard ownership / HQ workflow 구조: PASS
- 탭/가드/미리보기/완료 복귀/재개: PASS
- 기술 상세 metadata의 `Master` 접근성: FAIL

상세 defect는 [/Users/mark/Desktop/rg-arls-dev/arls_final_qa_defects.md](/Users/mark/Desktop/rg-arls-dev/arls_final_qa_defects.md)에 정리했습니다.
