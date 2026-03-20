# Sentrix + ARLS 탭/버튼 기반 기능 QA 체크리스트  

작성일: 2026-03-19  
범위: `rg-arls-dev` 프런트(`frontend/index.html`, `frontend/js/app.js`) 기준  
적용 대상: Sentrix 연동 화면 + ARLS 전기능  
실행 원칙: 모든 항목은 “버튼/탭 동작 시 화면·네트워크·상태 반영” 확인 기준으로 PASS/FAIL 기록

## 공통 실행 준비

- [ ] 로그인 계정군(관리자/감독/일반) 별로 준비: 최소 `SUPER`, `MASTER`, `DEV`, `MANAGER`, `GUARD` 테스트
- [ ] 기본 진입 URL: `https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net`
- [ ] QA 중간에 `Console`/`Network` 탭 열고 요청 실패/토큰 갱신/권한 에러를 실시간 추적
- [ ] 테스트 데이터: 월/지점/현장/직원 최소 1개 이상
- [ ] 화면 상태 초기화: 라우트 캐시/임시폼/시트 닫기/필터 리셋
- [ ] 공통 실패 조건(모든 탭): 버튼 클릭 시 반응 없음, 빈 화면 고정, 콘솔 에러(`Unhandled data-action`) 발생, 권한 없는 화면 노출, 토큰 만료 처리 미흡

---

## 1) Sentrix QA (ARLS 내부 연동)

### 1-1. 라우트/진입 기본

- [ ] `P0` `/ops/support-workers` 라우트 진입
  - 재현: `/ops/support-workers` 직접 접근 또는 운영 화면 내 `지원근무자 현황` 이동
  - 기대: Sentrix 지원근무자 상태 뷰 렌더, `지원근무자 상태` 카탈로그/리스트가 로드됨
- [ ] `P0` Sentrix 뷰 진입 시 권한 가드
  - 재현: 접근 불가 권한 계정(직원/권한 미부여)으로 진입
  - 기대: 접근 거부 메시지 또는 홈 복귀, API가 권한 에러를 정확히 반환
- [ ] `P1` Sentrix 전환 시 이전 화면 폴백 정상성
  - 재현: 여러 탭 이동 후 브라우저 뒤로가기
  - 기대: 라우트 동기화/뷰 복원 및 새로고침 후 동일 라우트 렌더

### 1-2. `ops` 뷰에서 Sentrix 연동 버튼 (탭: 운영)

#### Ops 탭 바(overview / soc / sheets / logs)

- [ ] `P0` `ops-view-tab="overview"` 전환
  - 기대: 개요 패널 우선 렌더, 운영 요약 수치(예정/출근/결원/요약 문구) 갱신
- [ ] `P0` `ops-view-tab="soc"` 전환
  - 기대: SOC 패널 노출, 로그 상태/최신 실행 메타 갱신
- [ ] `P0` `ops-view-tab="sheets"` 전환
  - 기대: Google Sheet 연동 상태/동기화 패널 갱신
- [ ] `P0` `ops-view-tab="logs"` 전환
  - 기대: 작업 로그 목록 로딩, 로그 상세/요약 레이블 표시
- [ ] `P1` `refresh-ops-summary`
  - 기대: summary 패널 즉시 재조회, 로딩 후 값 변경
- [ ] `P1` `refresh-ops-automation`
  - 기대: 운영 자동화 상태/실패 항목 갱신

#### Ops 카드/버튼 액션

- [ ] `P1` `ops-open-attendance` (`focus=scheduled`, `present`, `vacancy`)
  - 재현: 각 focus 버튼 클릭
  - 기대: 출퇴근 화면 이동 + 해당 focus 기본 필터 반영
- [ ] `P1` `ops-open-report-overnight`
  - 기대: 야간/특이 근무 보고 탭/뷰로 이동
- [ ] `P1` `ops-open-schedule-today`
  - 기대: 스케줄 오늘 뷰로 이동
- [ ] `P1` `ops-open-support-workers`
  - 기대: `/ops/support-workers` 지원근무자 현황 뷰로 이동
- [ ] `P1` `ops-open-overview` (홈에서 운영로 이동)
  - 기대: `view-ops` 렌더 및 운영 요약이 비어 있지 않음

#### Ops에서 실패 처리/재시도(로그 연계)

- [ ] `P1` `ops-retry-target` (target=soc/sheets/excel)
  - 재현: 대상 탭에서 실패 항목이 존재하는 상태에서 재시도
  - 기대: 재시도 API 호출 및 상태가 처리중 → 완료 또는 에러 이유 표시
- [ ] `P1` `ops-log-select`
  - 기대: 선택한 로그 키 기준으로 상세 로그/목록이 즉시 전환되어 렌더

- [ ] `P1` `ops-retry-sheets-sync`
  - 기대: 구글 시트 동기화 재시도 API 실행 및 진행/완료/에러 상태 표시
- [ ] `P1` `ops-view-logs` (target=soc/sheets/excel)
  - 기대: 해당 타깃 로그 목록 필터링됨

#### Sentrix 운영 특화

- [ ] `P0` `ops-run-apple-report`
  - 기대: Apple 리포트 실행/재실행 트리거되고 상태 갱신
- [ ] `P1` `home-attendance-check-back` / `home-open-settings` / 알림/기타 운영 진입 버튼
  - 기대: 경고없이 기존 기능 이동 및 화면 안정성 유지

### 1-3. 지원근무자 현황 뷰 (`/ops/support-workers`, Sentrix 브릿지 워크스페이스)

#### 워크스페이스 탭

- [ ] `P0` `support-status-workspace-tab="status"`
  - 기대: 기본 상태 목록·집계 메타 표시
- [ ] `P0` `support-status-workspace-tab="hq"`
  - 기대: HQ 업로드/검토 워크스페이스 전환
- [ ] `P0` `support-status-set-mode` (all/mine/site/day/...')
  - 기대: 뷰의 대상 스코프가 즉시 변경되고 리스트 재필터링
- [ ] `P1` `support-status-refresh`
  - 기대: 목록 + 카운트 + 상태메타 갱신
- [ ] `P1` `support-status-open-detail`
  - 기대: 선택된 row detail drawer 열림/닫힘 동작
- [ ] `P0` `support-status-close-drawer`
  - 기대: drawer 닫힘, 선택 해제

#### HQ 워크스페이스

- [ ] `P1` `support-status-hq-set-scope` (all/site)
  - 기대: 스코프 변경 시 site selector 노출/숨김이 일관되게 변경
- [ ] `P1` `support-status-hq-refresh`
  - 기대: HQ 계약/상태 정보를 재조회
- [ ] `P1` `support-status-hq-download`
  - 기대: 템플릿/리뷰 엑셀 다운로드 진행 및 파일명·월/사이트 일치
- [ ] `P1` `support-status-hq-inspect`
  - 기대: 업로드/검토 단계로 진입, 에러 라벨/요약 표시
- [ ] `P1` `support-status-hq-apply`
  - 기대: 적용 후 결과 반영, 에러 시 토스트/메시지 및 재시도 가능

#### Sentrix 연동 파라미터 확인

- [ ] `P0` Sentrix 상태/반영 동작으로 생성되는 URL 검증
  - 재현: apply/진입 과정 중 브라우저 열기 동작 추적
  - 기대: `mode=hq-submission` + `tenant_code`, `month`, `site`, `artifact_id`, `revision` 포함
- [ ] `P0` 연계된 항목이 Sentrix에서 상세 조회 가능한지 수동 확인
  - 기대: `artifact_id`/`tenant`/`month` 기준으로 동일 건 참조

---

## 2) ARLS UI/기능 QA (탭 + 버튼별)

## 2-1. 공통 네비게이션/사이드바

- [ ] `P0` `open-drawer` / `close-drawer`
  - 기대: 사이드바 오픈·클로즈 및 오버레이 동작 정상
- [ ] `P0` `open-notifications`
  - 기대: 알림 뷰 또는 알림 패널 오픈
- [ ] `P0` `toggle-password-visibility`
  - 기대: 비밀번호 입력값 표시/숨김 토글
- [ ] `P0` `logout`
  - 기대: 토큰/세션 초기화 + 로그인 화면 복귀
- [ ] `P1` `drawer-open-route`
  - 기대: 전달 `data-route`로 이동, 해당 뷰 라우트 정합성 확보
- [ ] `P1` `drawer-menu-item`, `drawer-toggle-submenu`
  - 기대: 서브메뉴 토글/탭 전환이 정상 렌더
- [ ] `P2` `drawer-help` / `drawer-notice` / `drawer-approvals` / `drawer-team-status` / `drawer-policies`
  - 기대: 각 메뉴 클릭 시 관련 화면/섹션 열림
- [ ] `P1` `drawer-open-view`
  - 기대: `data-view` 기반으로 해당 뷰 라우팅, 메뉴 닫힘/오버레이 정리 포함

#### 공통 모달/확인 액션

- [ ] `P1` `close-drawer` / `sheet-close` / `close-sheet`
  - 기대: 시트/드로어/상세 패널이 즉시 닫히고 포커스가 정상 복귀
- [ ] `P1` `confirm-accept` / `confirm-sheet-accept`
  - 기대: 확인 모달의 기본 동작이 실행되고 후처리 토스트/화면 갱신 확인
- [ ] `P1` `confirm-cancel` / `confirm-sheet-cancel`
  - 기대: 모달 종료 후 변경사항이 되돌려지고 에러 없이 닫힘
- [ ] `P1` `confirm-secondary` / `confirm-sheet-secondary`
  - 기대: 보조 액션 실행 후 상태 토스트 또는 다음 단계 이동 확인

## 2-2. 바텀 탭 이동(홈/출퇴근/요청/스케줄/더보기)

- [ ] `P0` `switch-view="home"` / `attendance` / `requests` / `schedule` / `profile`
  - 기대: 해당 뷰만 노출, 이전 뷰 타이머/폴링 정리 상태 정상

---

## 2-3. 홈 탭 (`view-home`)

#### 기본 카드/헤더

- [ ] `P0` `home-open-site-picker` / `home-refresh-location`
  - 기대: 현장 선택값 반영 + 위치 상태 텍스트 갱신
- [ ] `P0` `home-attendance-toggle`(출근/퇴근)
  - 기대: 현재 출근 상태 변경 흐름으로 전환(동의/실패 상태 토스트 분기)
- [ ] `P1` `home-check-in-request` (예외 출근 요청)
  - 기대: 출근 요청 뷰로 이동 또는 폼 오픈
- [ ] `P1` `home-open-schedule-tools`
  - 기대: 스케줄 관련 도구 진입
- [ ] `P1` `home-open-settings`
  - 기대: 설정 화면 이동

#### 홈 내 상단/카드 링크

- [ ] `P1` `ops-open-overview` / `drawer-open-route`로 `/schedules/calendar`, `/attendance`
  - 기대: 각 대상 뷰 이동
- [ ] `P1` `home-mobile-open-exception` / `home-mobile-open-leave` / `home-mobile-open-docs` / `home-mobile-open-schedule`
  - 기대: 해당 빠른메뉴 동작
- [ ] `P1` `home-refresh-week`
  - 기대: 주간 집계/카드 재조회
- [ ] `P1` `home-map` / `home-map-open-external` / `home-week-open-date` / `home-select-site`
  - 기대: 지도/날짜 상세 이동 정상

#### 홈 출근체크 진입

- [ ] `P0` `home-attendance-check-back`
  - 기대: 출근체크 뷰 → 홈으로 복귀
- [ ] `P0` `home-attendance-check-confirm` / `home-attendance-check-request`
  - 기대: 출근/퇴근 처리/요청 경로 진입
- [ ] `P1` `home-attendance-check-refresh`(동적)
  - 기대: 위치 정보/지도 상태 재조회
- [ ] `P1` `home-check-in`, `home-check-out`, `home-open-settings`
  - 기대: 출근·퇴근 분기 버튼 동작

---

## 2-4. 출근 체크 뷰 (`view-attendance-check`)

- [ ] `P0` `home-attendance-check-confirm`
  - 기대: 위치 검증 후 출근/퇴근 최종 확정
- [ ] `P0` `home-attendance-check-request`
  - 기대: 요청 생성/첨부/승인 흐름 시작
- [ ] `P1` `home-open-settings`
  - 기대: 설정 진입
- [ ] `P1` `home-attendance-check-back`
  - 기대: 홈/원래 뷰로 복귀

---

## 2-5. 운영 화면 (`view-ops`, Sentinel+운영 연계)

- [ ] `P1` `ops-view-tab` 전환(overview/soc/sheets/logs)
- [ ] `P1` `ops-open-attendance`(`scheduled|present|vacancy`)
- [ ] `P1` `ops-open-report-overnight`
- [ ] `P1` `ops-open-schedule-today`
- [ ] `P1` `ops-run-apple-report`
- [ ] `P1` `ops-open-support-workers`
- [ ] `P1` `ops-retry-target` + `ops-view-logs`
- [ ] `P1` `refresh-ops-summary` / `refresh-ops-automation`

각 항목은 탭 이동 시 해당 데이터 카드/버튼 유효성, 실패 메시지, 재시도 동작이 함께 표시되는지 확인.

---

## 2-6. 출근 요청 생성 뷰 (`view-checkin-request`)

- [ ] `P0` `request-open-map`
  - 기대: 요청 메타 지도 렌더/거리 계산 값 표시
- [ ] `P1` `request-clear-photos`
  - 기대: 첨부 미리보기 초기화
- [ ] `P0` `submit-attendance-request`
  - 기대: 요청 생성 완료 후 상태/요청 내역 업데이트
- [ ] `P1` `cancel-attendance-request`
  - 기대: pending 상태 요청만 취소 처리

---

## 2-7. 요청/승인 뷰 (`view-requests`)

#### 세그먼트/필터

- [ ] `P0` `requests-open-new-request`
  - 기대: 새 요청 작성 모드 이동
- [ ] `P0` `requests-open-filter`
  - 기대: 필터/검색 UI 표시
- [ ] `P0` `requests-refresh-current`
  - 기대: 현재 목록 즉시 재조회
- [ ] `P1` `requests-range`(today/yesterday/this-week/this-month)
  - 기대: 기간별 목록 변경
- [ ] `P1` `requests-sort` 및 `requests-kpi-filter`
  - 기대: 정렬과 KPI 뷰 반영
- [ ] `P1` `requests-my-filter` (all/pending/approved/rejected)
  - 기대: 내 요청 목록 전환
- [ ] `P1` `requests-processed-clear`
  - 기대: 처리 완료 목록 초기화 동작
- [ ] `P1` `requests-refresh-current`
  - 기대: 리프레시 후 목록/카운트 일관성

#### 탭 동작

- [ ] `P1` `requests-workspace-segment` (요청/HR/승인)
  - 기대: 영역별 API/컬럼/빈 상태 메시지 일치
- [ ] `P1` `work-mobile-segment`
  - 기대: 모바일에서 동일 탭 분기
- [ ] `P1` `approval-queue-tab` (pending/processed/soc)
  - 기대: 승인 대기/처리함/연동 반영 큐 분리
- [ ] `P1` `requests-close-drawer`
  - 기대: 상세 패널 닫힘

#### 빠른 요청

- [ ] `P1` `requests-quick-checkin`
- [ ] `P1` `requests-quick-leave`
- [ ] `P1` `requests-quick-correction`
  - 기대: 각 폼 라우트로 이동하고 제출/초기화 정상

#### 휴가 워크스페이스

- [ ] `P1` `leave-workspace-section` (요청유형/사용현황/정책)
- [ ] `P1` `leave-workspace-scope` (내/팀)
- [ ] `P1` `leave-workspace-sort` + `leave-usage-sort`
- [ ] `P1` `leave-workspace-quick-type` + `leave-history-filter` + `leave-scope-toggle`
- [ ] `P1` `leave-workspace-toggle-composer` / `leave-workspace-close-drawer`
- [ ] `P1` `leave-workspace-quick-type`(연차/반차/병가/조퇴), `leave-workspace-select`
- [ ] `P1` `leave-refresh`, `leave-history-detail`
- [ ] `P0` `leave-request-detail` / `leave-request-approve` / `leave-request-reject-*` (행 동작)
  - 기대: 승인/반려 상태 반영 및 목록 카운트 즉시 업데이트
- [ ] `P1` `leave-request-reject-sheet` / `leave-request-reject-confirm`
  - 기대: 반려 사유 입력 시트/확인 분기 후 반려 상태 반영
- [ ] `P1` `leave-quick-type`(상단 작성 폼)

#### 동적 행 액션 (요청/휴가/정정)

- [ ] `P1` `requests-manager-select`, `requests-my-detail`, `requests-manager-correction-detail`, `requests-my-cancel`
- [ ] `P1` `requests-workspace-select`, `requests-my-refresh`, `requests-open-filter`
  - 기대: 행/내역 선택 및 필터 재조회 후 리스트 반응성 확인
- [ ] `P1` `attendance-request-approve` / `attendance-request-reject` / `attendance-request-detail` / `attendance-request-map` / `attendance-request-reject-sheet` / `attendance-request-reject-confirm`
  - 기대: 승인/반려/지도/상세 분기 동작 후 상태/목록 일치
- [ ] `P1` `attendance-close-drawer`
  - 기대: 관리자 상세 패널이 즉시 닫히고 목록 포커스 복귀
- [ ] `P1` `leave-request-approve` / `attendance-correction-approve` / `attendance-correction-reject` / `correction-review` / `correction-submit` / `refresh-approvals`
  - 기대: 정정/요청 승인·반려 처리 후 처리 상태와 목록 카운트 반영

---

## 2-8. HR 뷰 (`view-hr`)

- [ ] `P1` `hr-refresh`
- [ ] `P1` `hr-workspace-segment` (요청/내문서/승인/템플릿)
- [ ] `P1` `hr-doc-open`
- [ ] `P1` `hr-purpose-select`
- [ ] `P1` `hr-employment-request-submit`
- [ ] `P1` `hr-employment-my-refresh`
- [ ] `P1` `hr-admin-panel-tab` (요청관리/템플릿)
- [ ] `P1` `hr-admin-status-filter`
- [ ] `P1` `hr-admin-search`
- [ ] `P1` `hr-template-refresh`, `hr-template-upload`
- [ ] `P1` `hr-employment-admin-refresh`
- [ ] `P0` 동적: `hr-employment-download`, `hr-employment-view-reason`, `hr-admin-approve`, `hr-admin-reject`
  - 기대: 문서 다운로드/사유 조회/승인/반려 동작 후 리스트 상태 반영

---

## 2-9. 지원근무자 현황 뷰 (`view-support-status`)

- [ ] `P0` `support-status-workspace-tab` status/hq 전환
- [ ] `P0` `support-status-set-mode`
- [ ] `P1` `support-status-refresh`
- [ ] `P1` `support-status-open-detail` + `support-status-close-drawer`
- [ ] `P1` `support-status-hq-set-scope` + `support-status-hq-refresh`
- [ ] `P1` `support-status-hq-download` + `support-status-hq-inspect` + `support-status-hq-apply`
- [ ] `P1` 동적: 행 click 시 `support-status-open-detail` dataset rowKey 적용 확인

---

## 2-10. 출근 관리 뷰 (`view-attendance`)

- [ ] `P0` `attendance-refresh`, `attendance-export-records`
- [ ] `P1` `attendance-open-filter`, `attendance-open-approval-inbox`
- [ ] `P1` `attendance-range-preset`(오늘/어제/달력)
- [ ] `P1` `attendance-toggle-exception-help`, `attendance-open-related-request`
- [ ] `P1` `attendance-sort`, `attendance-mobile-segment`, `attendance-focus-records`
- [ ] `P1` `attendance-filter-apply`, `attendance-filter-clear`
- [ ] `P1` `attendance-close-drawer`
- [ ] `P1` `attendance-open-related-request`, `attendance-request-approve`, `attendance-request-reject`, `attendance-request-detail`, `attendance-request-map`
- [ ] `P1` `attendance-set-status-filter`, `attendance-manager-select`, `attendance-record-select`, `attendance-timeline-detail`
- [ ] `P1` `attendance-correction-approve`, `attendance-correction-reject`, `attendance-go-correction`, `attendance-request-reject-sheet`, `attendance-request-reject-confirm`
- [ ] `P1` 동적: 날짜 선택 버튼 `attendance-date-today`, `attendance-date-yesterday`, `attendance-date-calendar`

---

## 2-11. 스케줄 뷰 (`view-schedule`)

#### 상위 뷰/탭/표시모드

- [ ] `P1` `schedule-set-view`(calendar/day/list)
- [ ] `P1` `schedule-hq-tab` (calendar/list/upload/hq/report/template)
- [ ] `P1` `drawer-help`  
- [ ] `P1` `schedule-toggle-action-dropdown`
  - 기대: 드롭다운 열림/닫힘 상태 동기화, 타겟 메뉴 전환 반응성 확인

#### 기본 액션

- [ ] `P1` `load-schedule` (수동 새로고침)
- [ ] `P1` `schedule-prev-month` / `schedule-next-month` / `schedule-jump-today` / `schedule-jump-week`
- [ ] `P1` `schedule-select-date`
- [ ] `P1` `schedule-open-day-detail` / `schedule-open-assignment`
- [ ] `P1` `schedule-open-download` / `schedule-download-monthly-excel` / `schedule-download-latest-base`
- [ ] `P1` `schedule-open-download-monthly-excel`(중복 호출 회귀)
- [ ] `P1` `schedule-close-drawer`
  - 기대: 데스크톱 전용 상세 드로어 닫힘

#### 업로드/생성 워크플로우

- [ ] `P0` `schedule-open-upload` / `schedule-open-upload-list`
- [ ] `P0` `schedule-open-create`, `schedule-create-single-open`, `schedule-create-bulk-open`
- [ ] `P1` `schedule-create-template-single`, `schedule-create-template-bulk`
- [ ] `P1` `schedule-base-wizard-step`, `schedule-base-wizard-next`, `schedule-base-wizard-prev`
- [ ] `P1` `schedule-base-wizard-finish`(있을 경우) 및 `schedule-open-template-profile-manager`
- [ ] `P1` `schedule-preview-mode`(actionable/all)
- [ ] `P1` `preview-schedule`, `apply-schedule`, `refresh-schedule-export`

#### HQ 업로드/연동

- [ ] `P1` `schedule-support-hq-dismiss-success`
- [ ] `P1` `schedule-support-hq-select-ready` / `schedule-support-hq-clear-selection`
- [ ] `P1` `schedule-support-hq-toggle-site` (개별 지점 체크)
- [ ] `P1` `schedule-support-hq-download`
- [ ] `P1` `schedule-support-hq-inspect`
- [ ] `P1` `schedule-support-preview`
  - 기대: 작성본 검토 뷰 오픈 및 HQ 데이터 반영 비교 확인
- [ ] `P1` `schedule-support-hq-preview-mode`
- [ ] `P1` `schedule-support-copy-artifact`
- [ ] `P1` `schedule-support-apply`
- [ ] `P1` `schedule-support-open-sentrix`  
  - 기대: Sentrix URL 창 열림 및 context(`tenant/site/month`) 전달
- [ ] `P1` `schedule-support-final-download`
- [ ] `P1` `schedule-hq-wizard-step`, `schedule-hq-wizard-prev`, `schedule-hq-wizard-next`, `schedule-hq-wizard-finish`
- [ ] `P1` `schedule-open-upload-section`, `schedule-upload-workflow-tab`, `schedule-upload-mode-tab`
- [ ] `P1` `schedule-reset-upload`

#### 재무 제출 워크플로우

- [ ] `P1` `schedule-finance-tab`(1차/2차)
- [ ] `P1` `schedule-finance-review-download`
- [ ] `P1` `schedule-finance-preview`
- [ ] `P1` `schedule-finance-apply`
- [ ] `P1` `schedule-finance-final-download`

#### 템플릿/매핑

- [ ] `P1` `schedule-template-owner-tab`(templates/profiles)
- [ ] `P1` `schedule-template-refresh`
- [ ] `P1` `schedule-template-create`
- [ ] `P1` `schedule-import-profile-manage`
- [ ] `P1` `schedule-template-edit`, `schedule-template-duplicate`
- [ ] `P1` `schedule-template-save`, `schedule-template-toggle-active`, `schedule-template-delete`
- [ ] `P1` `schedule-import-profile-delete`, `schedule-import-mapping-save`
- [ ] `P1` `schedule-reports-tab`
  - 기대: 보고서 탭(현재/기록/요약) 전환 후 표/요약 데이터 갱신

#### 일정 상세/편집/삭제

- [ ] `P1` `schedule-open-date-sheet` / `schedule-open-day-detail`
- [ ] `P1` `schedule-open-assignment`
- [ ] `P1` `schedule-edit` (개별 스케줄 수정)
- [ ] `P1` `schedule-delete` (동적 확인 모달 포함)
- [ ] `P1` `sheet-open-schedule-delete`, `sheet-confirm-schedule-delete`, `sheet-save-schedule-edit`, `sheet-close`
- [ ] `P1` `schedule-select-employee`, `schedule-toggle-day-expand`, `schedule-set-closer`

#### P1 확장 편집(시트행)

- [ ] `P1` `schedule-p1-refresh` / `schedule-p1-refresh-all`
- [ ] `P1` `schedule-p1-apple-ot-save`, `schedule-p1-late-save`, `schedule-p1-late-delete`
- [ ] `P1` `schedule-p1-support-save`, `schedule-p1-support-delete`
- [ ] `P1` `schedule-p1-event-save`, `schedule-p1-event-delete`

---

## 2-12. 프로필 탭 (`view-profile`)

- [ ] `P1` `profile-workspace-segment` 전환(설정/알림/기능)
- [ ] `P1` `notification-permission-flow` / `notification-resync` / `notification-open-settings`
- [ ] `P1` `notification-mark-read` / `notification-mark-all-read`
- [ ] `P1` `notification-request-permission`
- [ ] `P1` `integration-flags-refresh` / `integration-flags-save`
- [ ] `P1` `google-profile-refresh` / `google-profile-sync`
- [ ] `P1` `google-log-refresh`
- [ ] `P1` `soc-events-refresh`
- [ ] `P1` `ui-theme-set`(light/dark)
- [ ] `P1` `drawer-help`, `open-notifications`, `logout`
- [ ] `P1` 동적 알림/설정 탭에서의 읽음 반영 일관성

---

## 2-13. 리포트 뷰 (`view-reports`)

- [ ] `P1` `reports-view-tab` catalog / history / pack
- [ ] `P1` `reports-refresh`
- [ ] `P1` `reports-apple-refresh-status`
- [ ] `P1` `reports-apple-run`
- [ ] `P1` `reports-apple-retry`
- [ ] `P1` `reports-apple-view-logs`
- [ ] `P1` `reports-select-pack`, `reports-open-default-timesheet`, `reports-open-default-duty-log`, `reports-history-select`

---

## 2-14. 관리자/개발 콘솔 (`view-dev-console` / `view-employees` / `view-org`)

### 공통(Dev/Master) 모듈

- [ ] `P1` `master-route`, `master-refresh-dashboard`, `master-tenant-status`, `master-tenant-sort`
- [ ] `P1` `master-tenant-delete` / `master-tenant-delete-inline`
- [ ] `P1` `master-tenant-toggle-active`
- [ ] `P1` `master-user-apply-role`, `master-user-reset-password`, `master-user-toggle-active`, `master-user-copy-temp-password`, `master-user-force-logout`, `master-user-delete`
- [ ] `P1` `master-generate-temp-password`, `master-copy-temp-password`, `master-copy-create-summary`
- [ ] `P1` `master-soc-backfill`, `master-soc-full-reset`, `master-tenant-soc-reset`, `master-tenant-soc-backfill`
- [ ] `P1` `master-tenant-hr-reset`, `master-tenant-reset-full`
- [ ] `P1` `master-audit-filter`
- [ ] `P1` `master-tenant-profile-refresh`, `master-tenant-profile-upload-seal`, `master-tenant-profile-clear-seal`
- [ ] `P1` `master-users-refresh`
- [ ] `P2` `copy-generated-temp-password`
- [ ] `P1` `dev-user-refresh`, `dev-user-apply-role`, `dev-user-reset-password`, `dev-user-toggle-active`, `dev-user-delete`
- [ ] `P1` `dev-tenant-refresh`, `dev-tenant-edit`, `dev-tenant-form-reset`, `dev-tenant-toggle-active`
- [ ] `P2` `master-tenants-purge`, `dev-open-selected-tenant-overview`, `dev-open-selected-tenant-users`
- [ ] `P2` `lock-open-settings`

### 조직 허브(직원 뷰)

- [ ] `P1` `drawer-open-route` 직/지점 전환(직원/지점/회사)
- [ ] `P1` `employee-bulk-delete-site`
- [ ] `P1` `employee-open-create`/`employee-open-import-roster` / `employee-open-detail` / `employee-edit` / `employee-delete`
- [ ] `P1` `employee-form-reset` / `employee-roster-upload` / `employee-roster-rebuild-index` / `employee-roster-commit`
- [ ] `P1` `employee-roster-download-docx`, `employee-download-roster-file`, `employee-download-roster-row`, `employee-download-photo-file`
- [ ] `P1` `employee-sort`, `employee-refresh`, `employee-toggle-form`
- [ ] `P1` `employee-roster-import-close`
- [ ] `P1` `employee-directory-close`, `employee-directory-switch-tab`, `employee-directory-open-attendance`, `employee-directory-open-leave`, `employee-directory-open-schedule`, `employee-directory-open-requests`

### 조직 허브(지점 뷰)

- [ ] `P1` `site-open-create`, `site-search`, `site-sort`, `site-edit`, `site-toggle-active`, `site-delete`
- [ ] `P1` `site-editor-close`
- [ ] `P1` `site-address-search`, `site-address-use-query`, `site-address-pick`
- [ ] `P1` `site-use-current-location`, `site-open-map`
- [ ] `P2` `use-current-location`
  - 기대: 현재 위치 조회 액션 호출 시 지도/폼 좌표 자동 반영
- [ ] `P1` `site-tenant-retry`
- [ ] `P1` `submit-site`
- [ ] `P1` `site-open-create`/`site-open-map`/`site-search` 동적 row 동작 일관성

---

## 2-15. Sentrix 연동 브릿지 플로우(ARLS 스케줄/요청 상호작용)

- [ ] `P1` `roadmap-open-item`
  - 기대: 항목 코드별 목표 화면으로 라우팅되거나, 미지원 항목이면 안내 토스트 표시
- [ ] `P0` 스케줄 HQ 업로드→Sentrix 열기(`schedule-support-open-sentrix`)
  - 기대: 신규 창/탭에서 올바른 Sentrix URL, 월·사이트·artifact/revision 전달
- [ ] `P0` 지원근무자 현황 행의 Sentrix 이동 연계
  - 기대: 선택 행/리비전 기준으로 오픈 URL 생성
- [ ] `P1` Sentrix 반영 후 ARLS 상태 목록 동기화
  - 기대: 반영 직후 몇 분 내 상태/리스트 갱신 또는 폴링 대기 문구 노출

---

## 실행 결과 기록 포맷(권장)

- [ ] 항목, 계정권한, 입력 데이터, 기대 결과, 실제 결과, 스크린샷/네트워크 로그, 실패 시 에러 메시지
- [ ] `PASS` / `FAIL` / `N/A` + 재현 단계 1~2줄 최소 기재

## 위험도 높은 회귀 포인트(우선 점검)

1. 권한 라우팅 미비로 기능/버튼이 보이거나 접근되는 이슈(특히 DEV/MASTER/MANAGER)
2. Sentrix 브릿지 파라미터 누락(`tenant_code`, `site`, `month`, `revision`, `artifact_id`)
3. 스케줄 업로드/적용 중 파일·사이트 선택 상태 초기화/누락
4. 동적 행 액션(요청/휴가/직원/스케줄)에서 dataset 주입 실패로 `rowId` 누락
5. Drawer/menu 경유 라우팅 시 현재 뷰 상태와 폴링 타이머 충돌
