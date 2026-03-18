# ARLS Finance Schedule Workflow Phase 4 Defects

## 현재 상태

현재 Phase 4 검증 범위에서 열린 blocker defect는 없습니다.

- 총 open defects: `0`
- 최종 acceptance 상태: `PASS`

## 이번 패스에서 해결된 항목

### P4-002 Resolved

#### 내용

raw `1차 스케쥴 다운로드` 파일이 그대로는 `업로드 미리보기`를 통과하지 못하던 문제

#### 조치

Finance review workbook이 쓰는 `export_source_version`을 publish upload validator와 호환되는 값으로 정렬했습니다.

#### 수정 위치

- `app/routers/v1/schedules.py:253`
- `app/routers/v1/schedules.py:15336`
- `app/routers/v1/schedules.py:15364`

#### 재검증 결과

- raw review workbook 수정 후 preview: `200`
- `can_apply=true`
- `blocked_reasons=[]`
- `export_source_version=schedule_export.phase2.roundtrip`

의미:

- raw `1차 다운로드 -> 수정 -> 업로드 미리보기 -> 게시` 흐름이 이제 그대로 연결됩니다.

### P4-001 Resolved

#### 내용

Vice Supervisor가 Flow A를 사용할 수 없어 Phase 4 role policy와 불일치하던 문제

#### 조치

- Vice Supervisor를 Flow A 권한에 포함
- 동시에 site scope는 supervisor와 동일하게 적용되도록 유지

#### 수정 위치

- `app/routers/v1/schedules.py:1036`
- `app/routers/v1/schedules.py:1045`
- `app/routers/v1/schedules.py:3552`

#### 재검증 결과

- Vice Supervisor review download: `200`
- Flow B HQ workspace: 계속 `403`

의미:

- Phase 4 role policy와 현재 동작이 일치합니다.

## 현재 남은 Phase 4 open defect

없음.

## 참고 사항

Finance workflow acceptance와 별개로, 전체 `tests/test_schedule_monthly_import_canonical.py`에는 기존 실패 3건이 남아 있습니다.

이 항목들은 이번 Finance Phase 4 수정 범위와 직접 연결되지 않았고, 재검증 결과에도 영향을 주지 않았습니다.
